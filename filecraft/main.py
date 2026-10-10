"""FileCraft 入口。

用法：
    python main.py
"""
from __future__ import annotations

import os
import sys

# 保证从任意工作目录启动都能 import 到项目模块
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))


def main() -> int:
    # 自检模式：验证打包后的 exe 内部依赖是否完整
    if "--selftest" in sys.argv:
        idx = sys.argv.index("--selftest")
        out = sys.argv[idx + 1] if len(sys.argv) > idx + 1 else None
        from selftest import run_selftest

        return run_selftest(out)

    try:
        from PyQt6.QtWidgets import QApplication
    except ImportError:
        print("缺少 PyQt6，请先执行：pip install -r requirements.txt", file=sys.stderr)
        return 1

    import version
    from ui.main_window import MainWindow
    from ui.style import STYLE

    app = QApplication(sys.argv)
    app.setApplicationName(version.APP_NAME)
    app.setApplicationVersion(version.APP_VERSION)
    app.setOrganizationName(version.APP_AUTHOR)
    app.setStyleSheet(STYLE)

    win = MainWindow()
    win.show()
    return app.exec()


if __name__ == "__main__":
    raise SystemExit(main())