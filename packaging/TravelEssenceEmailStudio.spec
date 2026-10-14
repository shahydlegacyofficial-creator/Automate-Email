# PyInstaller build spec - produces a single, self-contained Windows executable.
#   pyinstaller --noconfirm --clean packaging/TravelEssenceEmailStudio.spec
import os

ROOT = os.path.abspath(os.path.join(SPECPATH, ".."))

a = Analysis(
    [os.path.join(ROOT, "main.py")],
    pathex=[ROOT],
    datas=[
        (os.path.join(ROOT, "assets", "icon.png"), "assets"),
        (os.path.join(ROOT, "assets", "icon.ico"), "assets"),
        (os.path.join(ROOT, "assets", "signature_icons"), os.path.join("assets", "signature_icons")),
    ],
    hiddenimports=[
        "win32timezone",
        "win32com.client",
        "pythoncom",
        "pywintypes",
        "keyring.backends.Windows",
        "win32crypt",
    ],
    excludes=["tkinter", "unittest", "pytest", "aiosmtpd"],
    noarchive=False,
)
pyz = PYZ(a.pure)

exe = EXE(
    pyz,
    a.scripts,
    a.binaries,
    a.datas,
    [],
    name="TravelEssenceEmailStudio",
    console=False,
    icon=os.path.join(ROOT, "assets", "icon.ico"),
    version=os.path.join(ROOT, "packaging", "version_info.txt"),
    upx=False,
    disable_windowed_traceback=False,
)
