# PyInstaller: gera a pasta dist\MetaOverlay com o .exe e tudo que ele precisa.
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
        (os.path.join(SRC, "classes"), "classes"),
    ] + ([(os.path.join(SRC, "skill_icons"), "skill_icons")] if os.path.isdir(os.path.join(SRC, "skill_icons")) else []) + [
    ],
    hiddenimports=collect_submodules("scapy.layers") + ["scapy.all", "scapy.arch.windows", "psutil", "zoneinfo", "tzdata", "lz4", "lz4.block", "dps_live", "icons", "respawn", "skills_db", "world_live", "net_hub", "field_bosses", "i18n_en", "i18n_es", "instance", "region_select", "netlib", "gamedata", "hotkey_ui", "scapy.layers.ppp", "scapy.layers.l2"],
    excludes=[
        "tkinter", "matplotlib", "scipy", "pandas", "IPython", "yaml", "cryptography", "PySide6.QtWebEngineCore", "PySide6.QtWebEngineWidgets",
        "PySide6.QtWebEngineQuick", "PySide6.Qt3DCore", "PySide6.Qt3DRender", "PySide6.QtQuick",
        "PySide6.QtQuick3D", "PySide6.QtQml", "PySide6.QtCharts", "PySide6.QtDataVisualization",
        "PySide6.QtGraphs", "PySide6.QtPdf", "PySide6.QtPdfWidgets", "PySide6.QtDesigner",
        "PySide6.QtLocation", "PySide6.QtPositioning", "PySide6.QtBluetooth", "PySide6.QtNfc",
        "PySide6.QtSensors", "PySide6.QtSerialPort", "PySide6.QtTest", "PySide6.QtSql",
        # o app só usa QtCore/QtGui/QtWidgets (+ o plugin de SVG); o resto só ocupa espaço
        "PySide6.QtMultimedia", "PySide6.QtMultimediaWidgets", "PySide6.QtNetwork", "PySide6.QtOpenGL",
        "PySide6.QtOpenGLWidgets", "PySide6.QtQuickWidgets", "PySide6.QtWebChannel", "PySide6.QtWebSockets",
        "PySide6.QtXml", "PySide6.QtConcurrent", "PySide6.QtDBus", "PySide6.QtHelp", "PySide6.QtPrintSupport",
        "PySide6.QtRemoteObjects", "PySide6.QtScxml", "PySide6.QtSpatialAudio", "PySide6.QtStateMachine",
        "PySide6.QtTextToSpeech", "PySide6.QtHttpServer", "PySide6.QtUiTools", "PySide6.QtAxContainer",
        "numpy.f2py", "numpy.testing", "unittest", "pydoc", "doctest", "lib2to3",
    ],
    noarchive=False,
)
# arquivos que vêm junto das bibliotecas mas o app nunca usa (dezenas de MB)
_DROP = (
    "opengl32sw.dll",            # OpenGL por software do Qt (~20 MB); o app desenha com QPainter
    "d3dcompiler_",              # compilador de shader do Qt Quick
    "opencv_videoio_ffmpeg",     # vídeo do OpenCV (~25 MB); o app só compara imagens
    "qt6quick", "qt6qml", "qt6pdf", "qt6virtualkeyboard", "qt6network", "qt6opengl",
    "qt6multimedia", "qt6shadertools", "qt6designer", "qt6charts", "qt6webengine",
    "avcodec", "avformat", "avutil", "swresample", "swscale",
    "/qml/", "\\qml\\", "/translations/", "\\translations\\",
    "qtvirtualkeyboard", "platforminputcontexts", "/multimedia/", "\\multimedia\\",
    "qnetworklistmanager", "qtuiotouchplugin", "/generic/", "\\generic\\",
    "/tls/", "\\tls\\", "networkinformation",
)


def _keep(entry):
    name = (entry[0] + "|" + entry[1]).lower()
    return not any(d in name for d in _DROP)


a.binaries = [b for b in a.binaries if _keep(b)]
a.datas = [d for d in a.datas if _keep(d)]

pyz = PYZ(a.pure)
exe = EXE(
    pyz, a.scripts, [],
    exclude_binaries=True,
    name="MetaOverlay",
    icon=os.path.join(SRC, "icon.ico"),
    console=False,
    upx=False,
)
coll = COLLECT(exe, a.binaries, a.datas, name="MetaOverlay", upx=False)
