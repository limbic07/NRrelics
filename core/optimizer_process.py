"""Bounded deep search in a disposable process; no Qt objects cross this boundary."""
import ctypes
import json
import multiprocessing
import os
import time
from pathlib import Path
from types import SimpleNamespace


def _solve_child(connection, args, kwargs):
    try:
        # Wait until the parent has installed the OS resource guard.
        if connection.recv() != 'start':
            return
        for name in ('OMP_NUM_THREADS', 'OPENBLAS_NUM_THREADS', 'MKL_NUM_THREADS'):
            os.environ[name] = '2'
        from core.loadout_optimizer import optimize

        def publish(result):
            connection.send(('result', result))
            if connection.recv() != 'ack':
                raise InterruptedError('搜索已停止。')

        result = optimize(*args, **kwargs, solver_threads=2, solution_callback=publish,
                          progress=lambda message: connection.send(('progress', message)))
        publish(result or {'solutions': [], 'has_more': False})
        connection.send(('done', None))
    except Exception as exc:
        try:
            connection.send(('error', str(exc)))
        except (OSError, EOFError):
            pass
    finally:
        connection.close()


class WindowsSearchGuard:
    """Job hard memory ceiling, process counters, and kill-on-parent-exit."""
    def __init__(self, pid, memory_limit):
        from ctypes import wintypes as w
        size = ctypes.c_size_t

        class Basic(ctypes.Structure):
            _fields_ = [('process_time', ctypes.c_longlong), ('job_time', ctypes.c_longlong),
                        ('flags', w.DWORD), ('minimum', size), ('maximum', size),
                        ('active', w.DWORD), ('affinity', size), ('priority', w.DWORD),
                        ('scheduling', w.DWORD)]

        class IO(ctypes.Structure):
            _fields_ = [(n, ctypes.c_ulonglong) for n in ('read_ops','write_ops','other_ops','read','write','other')]

        class Extended(ctypes.Structure):
            _fields_ = [('basic', Basic), ('io', IO), ('process_memory', size),
                        ('job_memory', size), ('peak_process', size), ('peak_job', size)]

        class Counters(ctypes.Structure):
            _fields_ = [('cb', w.DWORD), ('faults', w.DWORD)] + [(n, size) for n in
                ('peak_working','working','peak_paged','paged','peak_nonpaged','nonpaged',
                 'pagefile','peak_pagefile','private')]

        class Memory(ctypes.Structure):
            _fields_ = [('length', w.DWORD), ('load', w.DWORD)] + [(n, ctypes.c_ulonglong) for n in
                ('total','available','total_page','available_page','total_virtual','available_virtual','extended')]

        self.Counters = Counters; self.Memory = Memory
        self.kernel = ctypes.WinDLL('kernel32', use_last_error=True)
        self.psapi = ctypes.WinDLL('psapi', use_last_error=True)
        k = self.kernel
        k.OpenProcess.argtypes = [w.DWORD, w.BOOL, w.DWORD]; k.OpenProcess.restype = w.HANDLE
        k.CreateJobObjectW.argtypes = [ctypes.c_void_p, w.LPCWSTR]; k.CreateJobObjectW.restype = w.HANDLE
        k.SetInformationJobObject.argtypes = [w.HANDLE, ctypes.c_int, ctypes.c_void_p, w.DWORD]
        k.AssignProcessToJobObject.argtypes = [w.HANDLE, w.HANDLE]
        k.SetPriorityClass.argtypes = [w.HANDLE, w.DWORD]
        k.CloseHandle.argtypes = [w.HANDLE]
        k.GlobalMemoryStatusEx.argtypes = [ctypes.POINTER(Memory)]
        self.psapi.GetProcessMemoryInfo.argtypes = [w.HANDLE, ctypes.POINTER(Counters), w.DWORD]
        self.process = k.OpenProcess(0x100 | 0x1 | 0x400 | 0x10 | 0x200, False, pid)
        self.job = k.CreateJobObjectW(None, None)
        try:
            if not self.process or not self.job:
                raise ctypes.WinError(ctypes.get_last_error())
            limit = Extended(); limit.basic.flags = 0x100 | 0x2000
            limit.process_memory = memory_limit
            if not k.SetInformationJobObject(self.job, 9, ctypes.byref(limit), ctypes.sizeof(limit)):
                raise ctypes.WinError(ctypes.get_last_error())
            if not k.AssignProcessToJobObject(self.job, self.process):
                raise ctypes.WinError(ctypes.get_last_error())
            if not k.SetPriorityClass(self.process, 0x4000):  # BELOW_NORMAL_PRIORITY_CLASS
                raise ctypes.WinError(ctypes.get_last_error())
        except Exception:
            self.close()
            raise

    def sample(self):
        c = self.Counters(); c.cb = ctypes.sizeof(c)
        m = self.Memory(); m.length = ctypes.sizeof(m)
        if not self.psapi.GetProcessMemoryInfo(self.process, ctypes.byref(c), c.cb):
            raise ctypes.WinError(ctypes.get_last_error())
        if not self.kernel.GlobalMemoryStatusEx(ctypes.byref(m)):
            raise ctypes.WinError(ctypes.get_last_error())
        return dict(private_bytes=c.private, working_bytes=c.working,
                    available_bytes=m.available, available_commit_bytes=m.available_page)

    def close(self):
        for name in ('job', 'process'):
            handle = getattr(self, name, None)
            if handle:
                self.kernel.CloseHandle(handle); setattr(self, name, None)


def resource_stop_reason(sample, elapsed, memory_limit, time_limit):
    if sample.get('private_bytes', 0) >= memory_limit * .85:
        return '求解内存达到保护阈值，已停止并保留结果。'
    if min(sample.get('available_bytes', float('inf')),
           sample.get('available_commit_bytes', float('inf'))) < 512 * 1024 ** 2:
        return '系统可用内存不足，已停止并保留结果。'
    if elapsed >= time_limit:
        return '达到本次搜索时间上限，已停止并保留结果。'
    return None


def run_isolated(args, kwargs, cancelled, publish, progress, log_path,
                 memory_limit=2 * 1024 ** 3, time_limit=30 * 60):
    """One result awaiting ACK at a time. Stop kills only our owned child."""
    # Avoid serializing the UI manager or its incidental state.
    args = list(args)
    args[3] = SimpleNamespace(**{name: getattr(args[3], name) for name in
        ('normal_general', 'deepnight_general', 'normal_dedicated', 'deepnight_whitelist_dedicated')})
    context = multiprocessing.get_context('spawn')
    parent, child = context.Pipe()
    process = context.Process(target=_solve_child, args=(child, tuple(args), kwargs), daemon=True)
    guard = None; started = False
    begin = time.monotonic(); last_sample = -2.; last_log = -2.; count = 0
    Path(log_path).parent.mkdir(parents=True, exist_ok=True)
    with open(log_path, 'a', encoding='utf-8', buffering=1) as log:
        def record(event, **fields):
            log.write(json.dumps(dict(event=event, elapsed=round(time.monotonic()-begin, 2),
                                      results=count, **fields), ensure_ascii=False)+'\n')
        try:
            if cancelled(): raise InterruptedError('搜索已停止，已有结果保留。')
            process.start(); started = True; child.close()
            if os.name == 'nt':
                guard = WindowsSearchGuard(process.pid, memory_limit)
            record('start', pid=process.pid, memory_limit=memory_limit, threads=2, time_limit=time_limit)
            parent.send('start')
            while True:
                if cancelled(): raise InterruptedError('搜索已停止，已有结果保留。')
                elapsed = time.monotonic()-begin
                if elapsed-last_sample >= .5:
                    sample = guard.sample() if guard and process.is_alive() else {}
                    last_sample = elapsed
                    reason = resource_stop_reason(sample, elapsed, memory_limit, time_limit)
                    if elapsed-last_log >= 2 or reason:
                        record('resources', **sample); last_log = elapsed
                    if reason: raise RuntimeError(reason)
                if not parent.poll(.1):
                    if not process.is_alive():
                        raise RuntimeError(f'求解进程意外退出（{process.exitcode}），已有结果保留。')
                    continue
                try: kind, payload = parent.recv()
                except EOFError as exc:
                    raise RuntimeError('求解进程异常结束或达到资源上限，已有结果保留。') from exc
                if kind == 'result':
                    count += len(payload.get('solutions', [])); publish(payload); parent.send('ack')
                elif kind == 'progress': progress(payload)
                elif kind == 'error': raise RuntimeError(payload)
                elif kind == 'done':
                    record('complete'); return
        except Exception as exc:
            record('stopped', reason=str(exc))
            raise
        finally:
            if started:
                if process.is_alive(): process.terminate()
                process.join(2)
                if process.is_alive(): process.kill(); process.join()
                record('closed', exitcode=process.exitcode)
                process.close()
            if guard: guard.close()
            parent.close(); child.close()
