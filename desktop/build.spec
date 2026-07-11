# -*- mode: python ; coding: utf-8 -*-
"""PyInstaller 打包规范（轻量版，无 PySide6）"""
import os
block_cipher = None
try:
    SPEC_DIR = SPECPATH
except NameError:
    SPEC_DIR = os.getcwd()
ROOT_DIR = os.path.dirname(SPEC_DIR)

datas = [
    (os.path.join(ROOT_DIR, 'index.html'), '.'),
    (os.path.join(ROOT_DIR, 'school-logo.png'), '.'),
    (os.path.join(ROOT_DIR, 'main.py'), '.'),
    (os.path.join(ROOT_DIR, 'manifest.json'), '.'),
]

hiddenimports = [
    'flask', 'flask.json', 'jinja2', 'markupsafe', 'itsdangerous', 'click', 'werkzeug',
    # pywebview 后端
    'webview', 'webview.platforms.edgechromium', 'webview.platforms.winforms',
    # pystray
    'pystray', 'pystray._win32',
    # Pillow
    'PIL', 'PIL.PngImagePlugin', 'PIL.Image',
    # requests
    'requests', 'urllib3', 'certifi', 'charset_normalizer', 'idna',
    # 通知
    'win11toast',
    # 桌面端模块
    'config', 'network', 'notifier',
]

excludes = [
    'PySide6',      # ★ 排除 PySide6（150MB+）
    'PyQt5', 'PyQt6',
    'tkinter',
    'unittest', 'pydoc', 'test',
    'numpy', 'scipy', 'matplotlib',
    'IPython', 'jupyter',
]

a = Analysis(
    ['main.py'],
    pathex=[SPEC_DIR, ROOT_DIR],
    binaries=[],
    datas=datas,
    hiddenimports=hiddenimports,
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=excludes,
    win_no_prefer_redirects=False,
    win_private_assemblies=False,
    cipher=block_cipher,
    noarchive=False,
)
pyz = PYZ(a.pure, a.zipped_data, cipher=block_cipher)
exe = EXE(
    pyz, a.scripts, a.binaries, a.zipfiles, a.datas, [],
    name='学生会人事管理系统',
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=True,
    upx_exclude=[],
    runtime_tmpdir=None,
    console=False,
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
    icon=os.path.join(ROOT_DIR, 'school-logo.png'),
)
