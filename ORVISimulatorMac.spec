# -*- mode: python ; coding: utf-8 -*-


a = Analysis(
    ['mac/orvi_mac.py'],
    pathex=[],
    binaries=[],
    datas=[('mac/sounds', 'sounds')],
    hiddenimports=[],
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=[],
    noarchive=False,
    optimize=0,
)
pyz = PYZ(a.pure)

exe = EXE(
    pyz,
    a.scripts,
    [],
    exclude_binaries=True,
    name='ORVISimulatorMac',
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=False,
    console=False,
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch='universal2',
    codesign_identity=None,
    entitlements_file=None,
)
coll = COLLECT(
    exe,
    a.binaries,
    a.datas,
    strip=False,
    upx=False,
    upx_exclude=[],
    name='ORVISimulatorMac',
)
app = BUNDLE(
    coll,
    name='ORVISimulatorMac.app',
    icon=None,
    bundle_identifier='com.orvi.simulator',
    info_plist={
        'LSUIElement': True,
        'NSAppleEventsUsageDescription': 'ORVI Simulator использует System Events для эффекта дрожания окон.',
    },
)
