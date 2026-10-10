"""把桌面版 FileCraft 的可复用核心同步到本 Web 项目。

用法（在 filecraft-web 目录下）：
    python sync_core.py

同步内容：
    ../filecraft/core/          -> ./core/          （转换器/总结/问答/PDF/思维导图）
    ../filecraft/assets/markmap -> ./assets/markmap （思维导图离线渲染脚本）

core/ 是唯一需要与桌面版保持一致的代码，改完桌面版核心后重新跑一次即可。
本项目的其它文件（server.py、static/、config.py 等）不受影响。
"""
from __future__ import annotations

import os
import shutil
import sys

WEB_ROOT = os.path.dirname(os.path.abspath(__file__))
DESKTOP_ROOT = os.path.dirname(WEB_ROOT) if os.path.basename(WEB_ROOT) == "filecraft-web" else None

if DESKTOP_ROOT is None:
    print("请把本项目目录保持为 filecraft-web（需要与 filecraft 平级）")
    sys.exit(1)

DESKTOP_CORE = os.path.join(DESKTOP_ROOT, "filecraft", "core")
DESKTOP_ASSETS = os.path.join(DESKTOP_ROOT, "filecraft", "assets", "markmap")
WEB_CORE = os.path.join(WEB_ROOT, "core")
WEB_ASSETS = os.path.join(WEB_ROOT, "assets", "markmap")


def rm(path: str) -> None:
    if os.path.isdir(path):
        shutil.rmtree(path)
    elif os.path.exists(path):
        os.remove(path)


def copytree(src: str, dst: str, skip_dir: str = "__pycache__") -> None:
    os.makedirs(os.path.dirname(dst), exist_ok=True)
    shutil.copytree(
        src, dst,
        ignore=shutil.ignore_patterns(skip_dir, "*.pyc"),
        dirs_exist_ok=True,
    )


def main() -> None:
    if not os.path.isdir(DESKTOP_CORE):
        print(f"找不到桌面版核心目录: {DESKTOP_CORE}")
        sys.exit(1)

    rm(WEB_CORE)
    copytree(DESKTOP_CORE, WEB_CORE)
    print(f"core/          <- {DESKTOP_CORE}")

    if os.path.isdir(DESKTOP_ASSETS):
        rm(WEB_ASSETS)
        copytree(DESKTOP_ASSETS, WEB_ASSETS)
        print(f"assets/markmap <- {DESKTOP_ASSETS}")

    print("同步完成。")


if __name__ == "__main__":
    main()
