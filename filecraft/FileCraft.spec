# -*- mode: python ; coding: utf-8 -*-
"""FileCraft 打包配置。

为什么需要手工指定 Qt 的 DLL：
PyInstaller 自带的 PyQt6 钩子在本环境下只收集到了 PyQt6/*.pyd 和 Qt6/translations，
漏掉了 Qt6/bin 下的核心 DLL 和 plugins/platforms 里的平台插件。
结果就是 exe 在本机能跑（从本机 Python 环境借用了 Qt），换台电脑会因为
找不到 Qt 平台插件而直接启动失败。这里显式把必需的 Qt 组件打进包里。

只挑必需组件而不是整个 Qt6/bin：整个目录 143 MB（含 WebEngine），
必需的核心三个 DLL 加起来约 25 MB。
"""
import os
import sys

from PyInstaller.utils.hooks import collect_all, collect_submodules

# ---------------------------------------------------------------- Qt 组件
def _pyqt6_qt_root() -> str | None:
    """定位 PyQt6 自带的 Qt6 目录。"""
    try:
        import PyQt6.QtCore as qc
        return qc.QLibraryInfo.path(qc.QLibraryInfo.LibraryPath.PrefixPath)
    except Exception:
        pass
    try:
        import PyQt6, os.path as p
        cand = p.join(p.dirname(PyQt6.__file__), "Qt6")
        return cand if p.isdir(cand) else None
    except Exception:
        return None


def _qt_binaries() -> tuple[list, list]:
    """返回 (binaries, 说明日志)。"""
    root = _pyqt6_qt_root()
    if not root:
        print("[spec] 警告：未找到 PyQt6 的 Qt6 目录，Qt 组件不会被包含！", file=sys.stderr)
        return [], []

    root = root.replace("/", os.sep) if os.sep == "\\" else root
    bin_dir = os.path.join(root, "bin")
    plug_dir = os.path.join(root, "plugins")
    out: list = []
    log: list[str] = []

    # 核心 Qt 动态库 —— 缺一不可
    core_dlls = [
        "Qt6Core.dll",
        "Qt6Gui.dll",
        "Qt6Widgets.dll",
    ]
    # 可选：有就带上，没有也不影响基本窗口
    optional_dlls = [
        "Qt6Svg.dll",          # 部分图标为 SVG 时需要
        "Qt6Network.dll",      # Qt 部分内部功能会用到
    ]

    for name in core_dlls + optional_dlls:
        src = os.path.join(bin_dir, name)
        if os.path.exists(src):
            out.append((src, os.path.join("PyQt6", "Qt6", "bin")))
            log.append(f"  + Qt6/bin/{name}")

    # 平台插件 —— 缺了这个窗口根本起不来
    for plugin in ("qwindows.dll", "qminimal.dll", "qoffscreen.dll"):
        src = os.path.join(plug_dir, "platforms", plugin)
        if os.path.exists(src):
            out.append((src, os.path.join("PyQt6", "Qt6", "plugins", "platforms")))
            log.append(f"  + plugins/platforms/{plugin}")

    # 样式与图像格式插件（有更好，没有 Qt 会退回内置样式）
    for sub, names in (
        ("styles", ["qmodernwindowsstyle.dll"]),
        ("imageformats", ["qico.dll", "qjpeg.dll", "qgif.dll", "qsvg.dll"]),
        ("iconengines", ["qsvgicon.dll"]),
    ):
        for name in names:
            src = os.path.join(plug_dir, sub, name)
            if os.path.exists(src):
                out.append((src, os.path.join("PyQt6", "Qt6", "plugins", sub)))
                log.append(f"  + plugins/{sub}/{name}")

    # MSVC C++ 运行库 —— Qt6 依赖它，干净系统上可能没有
    sys32 = os.path.join(os.environ.get("SystemRoot", r"C:\Windows"), "System32")
    for dll in ("msvcp140.dll", "msvcp140_1.dll", "vcruntime140.dll", "vcruntime140_1.dll"):
        src = os.path.join(sys32, dll)
        if os.path.exists(src):
            out.append((src, "."))
            log.append(f"  + {dll}")

    return out, log


_qt_bins, _qt_log = _qt_binaries()
print("[spec] 已显式加入的 Qt / 运行库组件：")
for line in _qt_log:
    print(line)

# ---------------------------------------------------------------- 依赖收集
# openai 与 reportlab 有大量动态导入和数据文件，必须整体收集
_openai = collect_all("openai")
_reportlab = collect_all("reportlab")

datas = list(_openai[0]) + list(_reportlab[0])
# 思维导图前端库（离线渲染用）
import glob as _glob
for _f in sorted(_glob.glob("assets/markmap/*.js")):
    datas.append((_f, "assets/markmap"))
binaries = list(_openai[1]) + list(_reportlab[1]) + _qt_bins
hiddenimports = (
    list(_openai[2])
    + list(_reportlab[2])
    + collect_submodules("pdfplumber")
    + collect_submodules("pdfminer")
    + ["docx", "pptx", "openpyxl", "markdown"]
)

a = Analysis(
    ["main.py"],
    pathex=[],
    binaries=binaries,
    datas=datas,
    hiddenimports=hiddenimports,
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=[
        # 明确排除，避免体积膨胀
        "tkinter", "matplotlib", "numpy", "pandas", "scipy",
        "PyQt6.QtWebEngineCore", "PyQt6.QtWebEngineWidgets", "PyQt6.QtQml", "PyQt6.QtQuick",
        "PyQt6.QtMultimedia", "PyQt6.QtBluetooth", "PyQt6.QtDesigner", "PyQt6.QtSql",
        "PyQt6.QtTest", "PyQt6.QtHelp", "PyQt6.QtWebSockets", "PyQt6.QtPositioning",
        "PyQt6.QtSensors", "PyQt6.QtSerialPort", "PyQt6.QtTextToSpeech",
    ],
    noarchive=False,
    optimize=0,
)

pyz = PYZ(a.pure)

exe = EXE(
    pyz,
    a.scripts,
    a.binaries,
    a.datas,
    [],
    name="FileCraft",
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=False,
    upx_exclude=[],
    runtime_tmpdir=None,
    console=False,
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
)