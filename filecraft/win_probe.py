"""枚举某进程的所有顶层窗口标题，用来判断 GUI 是真起来了还是弹了错误框。

用法：
    python win_probe.py <进程名>
"""
from __future__ import annotations

import ctypes
import ctypes.wintypes as wt
import sys

user32 = ctypes.windll.user32
kernel32 = ctypes.windll.kernel32

EnumWindows = user32.EnumWindows
EnumWindowsProc = ctypes.WINFUNCTYPE(wt.BOOL, wt.HWND, wt.LPARAM)


def _pid_of(hwnd: int) -> int:
    pid = wt.DWORD()
    user32.GetWindowThreadProcessId(hwnd, ctypes.byref(pid))
    return pid.value


def _text(hwnd: int) -> tuple[str, str]:
    n = user32.GetWindowTextLengthW(hwnd)
    buf = ctypes.create_unicode_buffer(n + 2)
    user32.GetWindowTextW(hwnd, buf, n + 2)
    cls = ctypes.create_unicode_buffer(256)
    user32.GetClassNameW(hwnd, cls, 256)
    return buf.value, cls.value


def find_pids(name: str) -> list[int]:
    """按映像名找 PID。"""
    import subprocess

    out = subprocess.run(
        ["tasklist", "/FI", f"IMAGENAME eq {name}", "/FO", "CSV", "/NH"],
        capture_output=True, text=True, errors="ignore",
    ).stdout
    pids = []
    for line in out.splitlines():
        parts = [p.strip('"') for p in line.split('","')]
        if len(parts) >= 2 and parts[0].lower() == name.lower():
            try:
                pids.append(int(parts[1]))
            except ValueError:
                pass
    return pids


def main() -> int:
    name = sys.argv[1] if len(sys.argv) > 1 else "FileCraft.exe"
    pids = find_pids(name)
    print(f"进程 {name} 的 PID: {pids}")
    if not pids:
        print("没有找到运行中的进程")
        return 1

    found: list[tuple[str, str, bool]] = []

    def cb(hwnd, _lparam):
        pid = _pid_of(hwnd)
        if pid in pids:
            title, cls = _text(hwnd)
            visible = bool(user32.IsWindowVisible(hwnd))
            if title or visible:
                found.append((title, cls, visible))
        return True

    EnumWindows(EnumWindowsProc(cb), 0)

    print(f"\n找到 {len(found)} 个顶层窗口：")
    for title, cls, visible in found:
        print(f"  可见={visible}  类名={cls!r}")
        print(f"      标题={title!r}")

    titles = " ".join(t for t, _, _ in found)
    print("\n--- 判定 ---")
    if "FileCraft" in titles:
        print("✓ 主窗口已正常显示")
        return 0
    if any(k in titles for k in ("could not", "无法", "Error", "错误", "Qt", "Plugin", "插件")):
        print("✗ 弹出了错误对话框 —— GUI 未能正常启动")
        return 2
    print("? 未识别到主窗口标题，请人工看上面的标题")
    return 3


if __name__ == "__main__":
    raise SystemExit(main())