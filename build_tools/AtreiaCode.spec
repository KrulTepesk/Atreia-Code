# PyInstaller: gera a pasta dist\AtreiaCode com o .exe e tudo que ele precisa.
import os
from PyInstaller.utils.hooks import collect_submodules

ROOT = os.path.abspath(os.path.join(SPECPATH, ".."))
SRC = os.path.join(ROOT, "overlay")

a = Analysis(
    [os.path.join(SRC, "main.py")],
    pathex=[SRC],
    datas=[
        (os.path.join(SRC, "data"), "data"),
        (os.path.join(SRC, "sounds"), "sounds"),
        (os.path.join(SRC, "fundos"), "fundos"),
        (os.path.join(SRC, "icon.png"), "."),
        (os.path.join(SRC, "logo.png"), "."),
        (os.path.join(SRC, "shugo_icon.png"), "."),
        (os.path.join(SRC, "ui"), "ui"),
        (os.path.join(SRC, "fonts"), "fonts"),
        (os.path.join(SRC, "icons"), "icons"),
    ] + ([(os.path.join(SRC, "skill_icons"), "skill_icons")] if os.path.isdir(os.path.join(SRC, "skill_icons")) else []) + [
    ],
    hiddenimports=collect_submodules("scapy.layers") + ["scapy.all", "scapy.arch.windows", "psutil", "zoneinfo", "tzdata", "lz4", "lz4.block", "dps_live", "icons", "respawn", "skills_db"],
    excludes=[
        "tkinter", "matplotlib", "scipy", "pandas", "IPython", "yaml", "cryptography", "PySide6.QtWebEngineCore", "PySide6.QtWebEngineWidgets",
        "PySide6.QtWebEngineQuick", "PySide6.Qt3DCore", "PySide6.Qt3DRender", "PySide6.QtQuick",
        "PySide6.QtQuick3D", "PySide6.QtQml", "PySide6.QtCharts", "PySide6.QtDataVisualization",
        "PySide6.QtGraphs", "PySide6.QtPdf", "PySide6.QtPdfWidgets", "PySide6.QtDesigner",
        "PySide6.QtLocation", "PySide6.QtPositioning", "PySide6.QtBluetooth", "PySide6.QtNfc",
        "PySide6.QtSensors", "PySide6.QtSerialPort", "PySide6.QtTest", "PySide6.QtSql",
    ],
    noarchive=False,
)
pyz = PYZ(a.pure)
exe = EXE(
    pyz, a.scripts, [],
    exclude_binaries=True,
    name="AtreiaCode",
    icon=os.path.join(SRC, "icon.ico"),
    console=False,
    upx=False,
)
coll = COLLECT(exe, a.binaries, a.datas, name="AtreiaCode", upx=False)
