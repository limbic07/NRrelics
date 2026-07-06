# -*- mode: python ; coding: utf-8 -*-

import sys
import os as _os
from PyInstaller.utils.hooks import collect_all
import shutil as _shutil
import pathlib as _pl

block_cipher = None

# -----------------------------------------------------------------------------
# 资源文件配置 — 只打包静态资源，排除用户数据
# -----------------------------------------------------------------------------
_static_data = [
    ('data/normal.txt', 'data'),
    ('data/normal_special.txt', 'data'),
    ('data/deepnight_pos.txt', 'data'),
    ('data/deepnight_neg.txt', 'data'),
    ('data/icon_cup.png', 'data'),
    ('data/icon_bookmark.png', 'data'),
]
datas = list(_static_data)

# conda 环境缺失的系统 DLL
_conda_bin = r'D:\anaconda3\envs\NRrelics\Library\bin'
_binaries_to_add = [
    ('expat.dll', '.'), ('libexpat.dll', '.'), ('ffi.dll', '.'),
    ('liblzma.dll', '.'), ('libbz2.dll', '.'), ('libmpdec-4.dll', '.'),
]
binaries = []
for _dll, _dest in _binaries_to_add:
    _dll_path = _os.path.join(_conda_bin, _dll)
    if _os.path.exists(_dll_path):
        binaries.append((_dll_path, _dest))
    else:
        print(f'WARNING: DLL not found: {_dll_path}')

# -----------------------------------------------------------------------------
# 隐式导入
# -----------------------------------------------------------------------------
hiddenimports = [
    'rapidocr',
    'pyautogui',
    'pydirectinput',
    'keyboard',
    'cv2',
    'numpy',
    'PySide6.QtCore',
    'PySide6.QtGui',
    'PySide6.QtWidgets',
    'qfluentwidgets',
]

tmp_ret = collect_all('rapidocr')
datas += tmp_ret[0]
binaries += tmp_ret[1]
hiddenimports += tmp_ret[2]

tmp_ret = collect_all('qfluentwidgets')
datas += tmp_ret[0]
binaries += tmp_ret[1]
hiddenimports += tmp_ret[2]


a = Analysis(
    ['main.py'],
    pathex=[],
    binaries=binaries,
    datas=datas,
    hiddenimports=hiddenimports,
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=[
        'scipy', 'matplotlib', 'pandas',
        'tkinter', 'tcl', 'tcl8', 'tcl8.6', 'tk8', 'tk8.6',
        'qtpy', 'PyQt5', 'PyQt6',
        'traitlets', 'ipython', 'jupyter', 'notebook',
        'pytest', 'unittest',
        'setuptools', 'distutils', 'pip', 'wheel', 'pkg_resources',
    ],
    win_no_prefer_redirects=False,
    win_private_assemblies=False,
    cipher=block_cipher,
    noarchive=False,
)

pyz = PYZ(a.pure, a.zipped_data, cipher=block_cipher)

exe = EXE(
    pyz,
    a.scripts,
    [],
    exclude_binaries=True,
    name='NRrelic_Bot',
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=True,
    console=False,
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
)

coll = COLLECT(
    exe,
    a.binaries,
    a.zipfiles,
    a.datas,
    strip=False,
    upx=True,
    upx_exclude=[],
    name='NRrelics',
)

# =============================================================================
# 打包后清理 — 删除不需要的文件以减小体积
# =============================================================================
_DIST = _pl.Path('dist/NRrelics/_internal')
_PYSIDE = _DIST / 'PySide6'
removed_size = 0

def _safe_rm(path):
    global removed_size
    if not path.exists():
        return
    if path.is_file():
        removed_size += path.stat().st_size
        path.unlink()
    elif path.is_dir():
        removed_size += sum(f.stat().st_size for f in path.rglob('*') if f.is_file())
        _shutil.rmtree(path)

# PySide6 多媒体/OpenGL/QML/PDF DLL
_pyside_junk = [
    'opengl32sw.dll', 'avcodec-61.dll', 'avformat-61.dll',
    'avutil-59.dll', 'swscale-8.dll', 'swresample-5.dll',
    'Qt6Pdf.dll', 'Qt6Quick.dll', 'Qt6Qml.dll',
    'Qt6QmlModels.dll', 'Qt6QmlMeta.dll', 'Qt6QmlWorkerScript.dll',
    'Qt6Multimedia.dll', 'Qt6MultimediaWidgets.dll', 'Qt6VirtualKeyboard.dll',
]
for _f in _pyside_junk:
    _safe_rm(_PYSIDE / _f)

# Qt 翻译 — 只保留中文
_translations = _PYSIDE / 'translations'
if _translations.exists():
    for _tf in _translations.iterdir():
        if _tf.is_file() and 'qt_zh' not in _tf.name and 'qtbase_zh' not in _tf.name:
            _safe_rm(_tf)

# PySide6 不需要的插件
_safe_rm(_PYSIDE / 'plugins' / 'multimedia')
for _pfx in ['qgif', 'qicns', 'qjp2', 'qmng', 'qtga', 'qtiff', 'qwbmp', 'qwebp']:
    _safe_rm(_PYSIDE / 'plugins' / 'imageformats' / f'{_pfx}.dll')

# opencv 视频 I/O DLL
for _vf in (_DIST / 'cv2').glob('opencv_videoio_*.dll'):
    _safe_rm(_vf)

# PIL 不用编解码器
for _pfx in ['_avif', '_imagingft', '_webp', '_imagingcms', '_imagingmath', '_imagingtk']:
    for _fp in _DIST.glob(f'PIL/{_pfx}.*.pyd'):
        _safe_rm(_fp)

print(f"[瘦身] 已移除 {removed_size / (1024*1024):.1f} MB 不必要的文件")
