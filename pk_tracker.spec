# PyInstaller spec for PK Tracker.
#
# Build a single-file executable:
#     pip install pyinstaller
#     pyinstaller pk_tracker.spec
#
# Output: dist/PKTracker  (on Windows: dist\PKTracker.exe).
#
# The data files (schema.sql, substances.json) are loaded via package-relative
# paths, so they must be bundled at the same pk_tracker/data/ location.

block_cipher = None

a = Analysis(
    ["run.py"],
    pathex=["."],
    binaries=[],
    datas=[
        ("pk_tracker/data/schema.sql", "pk_tracker/data"),
        ("pk_tracker/data/substances.json", "pk_tracker/data"),
    ],
    hiddenimports=["pyqtgraph"],
    hookspath=[],
    runtime_hooks=[],
    # Trim large Qt modules the app clearly does not use, to keep the binary
    # smaller. Kept conservative: QtNetwork/QtSql are left in because PySide6 and
    # pyqtgraph can pull them in transitively, and a missing transitive import
    # would crash at runtime.
    excludes=[
        "PySide6.QtQml", "PySide6.QtQuick", "PySide6.QtWebEngineCore",
        "PySide6.QtWebEngineWidgets", "PySide6.Qt3DCore", "PySide6.QtMultimedia",
        "PySide6.QtCharts",
        "tkinter", "matplotlib",
    ],
    cipher=block_cipher,
    noarchive=False,
)

pyz = PYZ(a.pure, a.zipped_data, cipher=block_cipher)

exe = EXE(
    pyz,
    a.scripts,
    a.binaries,
    a.zipfiles,
    a.datas,
    [],
    name="PKTracker",
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=True,
    runtime_tmpdir=None,
    console=False,            # GUI app: no console window
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
)
