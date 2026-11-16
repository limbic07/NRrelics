import json
import multiprocessing
import os
import time
from types import SimpleNamespace

import pytest
from core.optimizer_process import run_isolated, resource_stop_reason


def tiny_search():
    name = '提升物理攻击力'
    manager = SimpleNamespace(normal_general={'affixes': []}, deepnight_general={'affixes': []},
        normal_dedicated={'test': {'affixes': [name]}}, deepnight_whitelist_dedicated={})
    items = [dict(id=i, relic_type='normal', color='红', affixes=[name]) for i in range(4)]
    vessels = [dict(name_en='test', hero_en='Ironeye', normal_en='Red, Red, Red', deep_en='Red, Red, Red')]
    return (({'hero': '铁之眼'}, items, vessels, manager, {}),
            dict(normal_preset_id='test', deepnight_preset_id='none', page_size=5, min_ratio=0, time_limit=2))


def hanging_child(connection, args, kwargs):
    connection.recv()
    connection.send(('result', {'solutions': [{'score': 1}], 'has_more': True}))
    connection.recv()
    time.sleep(60)


def crashing_child(connection, args, kwargs):
    connection.recv()
    os._exit(7)


def test_isolated_tiny_search_and_os_guard(tmp_path):
    args, kwargs = tiny_search(); results = []
    log = tmp_path/'resources.jsonl'
    run_isolated(args, kwargs, lambda: False, results.append, lambda _: None, log, time_limit=20)
    assert sum(len(r['solutions']) for r in results) == 4
    assert results[-1]['has_more'] is False
    records = [json.loads(line) for line in log.read_text(encoding='utf-8').splitlines()]
    assert records[0]['threads'] == 2
    assert records[-1]['event'] == 'closed'
    assert all(p.pid != records[0]['pid'] for p in multiprocessing.active_children())
    if os.name == 'nt':
        assert any(r.get('private_bytes', 0) > 0 for r in records)


def test_cancel_kills_only_worker_and_keeps_partial(tmp_path, monkeypatch):
    monkeypatch.setattr('core.optimizer_process._solve_child', hanging_child)
    args, kwargs = tiny_search(); results = []; start = time.monotonic()
    with pytest.raises(InterruptedError):
        run_isolated(args, kwargs, lambda: bool(results), results.append, lambda _: None, tmp_path/'stop.jsonl')
    assert time.monotonic()-start < 10
    assert len(results) == 1
    assert not multiprocessing.active_children()


def test_native_crash_reported_without_parent_crash(tmp_path, monkeypatch):
    monkeypatch.setattr('core.optimizer_process._solve_child', crashing_child)
    args, kwargs = tiny_search()
    with pytest.raises(RuntimeError, match='求解进程'):
        run_isolated(args, kwargs, lambda: False, lambda _: None, lambda _: None, tmp_path/'crash.jsonl')
    assert not multiprocessing.active_children()


def test_wall_budget_stops_hung_child(tmp_path, monkeypatch):
    monkeypatch.setattr('core.optimizer_process._solve_child', hanging_child)
    args, kwargs = tiny_search()
    with pytest.raises(RuntimeError, match='时间上限'):
        run_isolated(args, kwargs, lambda: False, lambda _: None, lambda _: None,
                     tmp_path/'timeout.jsonl', time_limit=.5)
    assert not multiprocessing.active_children()


def test_resource_thresholds():
    gb = 1024**3
    assert resource_stop_reason({'private_bytes': 1.8*gb}, 1, 2*gb, 60)
    assert resource_stop_reason({'available_bytes': 100}, 1, 2*gb, 60)
    assert resource_stop_reason({'available_commit_bytes': 100}, 1, 2*gb, 60)
    assert resource_stop_reason({}, 61, 2*gb, 60)
    assert resource_stop_reason({'private_bytes': .5*gb, 'available_bytes': 4*gb}, 1, 2*gb, 60) is None
