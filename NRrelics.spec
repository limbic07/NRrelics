# -*- mode: python ; coding: utf-8 -*-

import sys
import os
from PyInstaller.utils.hooks import collect_all

block_cipher = None

# -----------------------------------------------------------------------------
# 资源文件配置
# -----------------------------------------------------------------------------
# datas 列表格式: (源路径, 目标路径)
datas = [
    ('data', 'data'),  # 包含所有数据文件(图片模板, 词条库等)
]

# 只有当 resources 目录存在时才添加，避免报错
if os.path.exists('resources'):
    datas.append(('resources', 'resources'))

# -----------------------------------------------------------------------------
# 隐式导入配置
# -----------------------------------------------------------------------------
hiddenimports = [
    'scipy.special.cython_special',
    'rapidocr',
    'pyautogui',
    'pydirectinput',
    'keyboard',
    'cv2',
    'numpy',
    'PySide6.QtCore',
    'PySide6.QtGui',
    'PySide6.QtWidgets',
    'qfluentwidgets',  # 确保 UI 库被正确包含
]

# 收集可能丢失的子模块
tmp_ret = collect_all('rapidocr')
datas += tmp_ret[0]
binaries = tmp_ret[1]
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
    excludes=[],
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
    exclude_binaries=True,  # 文件夹模式必须为 True
    name='NRrelic_Bot',
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=True,
    console=False,  # False = 隐藏控制台窗口 (GUI模式)
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
    # icon='data/app.ico',  # 如果有 .ico 图标文件，取消注释并指定路径
)

# 文件夹模式收集器
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
