# -*- mode: python ; coding: utf-8 -*-

from PyInstaller.utils.hooks import collect_data_files


# Keep user settings, inventory and imported presets outside the executable.
datas = [
    ('data/normal.txt', 'data'),
    ('data/normal_special.txt', 'data'),
    ('data/deepnight_pos.txt', 'data'),
    ('data/deepnight_neg.txt', 'data'),
    ('data/affix_catalog.json', 'data'),
    ('data/icon_cup.png', 'data'),
    ('data/icon_bookmark.png', 'data'),
    ('data/build_requirements.json', 'data'),
    ('data/vessels.json', 'data'),
    ('data/default_presets.json', 'data'),
    ('data/official_relics.json', 'data'),
]
datas += [('data/relic_validation', 'data/relic_validation')]
datas += collect_data_files('rapidocr')

hiddenimports = [
    'rapidocr.inference_engine.onnxruntime',
]

a = Analysis(
    ['main.py'],
    pathex=[],
    binaries=[],
    datas=datas,
    hiddenimports=hiddenimports,
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=[
        'matplotlib', 'pandas', 'tkinter', 'pytest',
        'sklearn', 'joblib', 'threadpoolctl',
        'PySide6.QtQml', 'PySide6.QtQuick', 'PySide6.QtPdf',
        'PySide6.QtMultimedia', 'PySide6.QtMultimediaWidgets',
        'PIL._avif',
    ],
    noarchive=False,
)

# The app reads still screenshots; OpenCV's video decoder is not used.
a.binaries = [binary for binary in a.binaries
              if not binary[0].replace('\\', '/').split('/')[-1].lower().startswith('opencv_videoio_ffmpeg')]

pyz = PYZ(a.pure)
exe = EXE(
    pyz,
    a.scripts,
    [],
    exclude_binaries=True,
    name='NRrelic_Bot',
    console=False,
)
coll = COLLECT(
    exe,
    a.binaries,
    a.zipfiles,
    a.datas,
    name='NRrelics',
)
