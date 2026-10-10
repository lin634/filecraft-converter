"""检查某进程加载的 Qt DLL 来自哪个路径。

这是判断打包是否自包含的关键：如果 Qt6Core.dll 来自 _MEI 临时解包目录，
说明 exe 自带 Qt，可以发给别人；如果来自本机 Python 的 site-packages，
说明它在借用开发机的环境，换台电脑就会启动失败。

用法：
    python module_probe.py <进程名>
"""
from __future__ import annotations

import ctypes
import ctypes.wintypes as wt
import sys

psapi = ctypes.windll.psapi
kernel32 = ctypes.windll.kernel32

# 显式声明签名，否则 HMODULE 的 64 位句柄会被当成 int 而溢出
kernel32.OpenProcess.argtypes = [wt.DWORD, wt.BOOL, wt.DWORD]
kernel32.OpenProcess.restype = wt.HANDLE
kernel32.CloseHandle.argtypes = [wt.HANDLE]
kernel32.CloseHandle.restype = wt.BOOL
psapi.EnumProcessModulesEx.argtypes = [
    wt.HANDLE, ctypes.c_void_p, wt.DWORD, ctypes.POINTER(wt.DWORD), wt.DWORD,
]
psapi.EnumProcessModulesEx.restype = wt.BOOL
psapi.GetModuleFileNameExW.argtypes = [
    wt.HANDLE, ctypes.c_void_p, wt.LPWSTR, wt.DWORD,
]
psapi.GetModuleFileNameExW.restype = wt.DWORD

PROCESS_QUERY_INFORMATION = 0x0400
PROCESS_VM_READ = 0x0010
LIST_MODULES_ALL = 0x03


def _pids(name: str) -> list[int]:
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


def modules_of(pid: int) -> list[str]:
    h = kernel32.OpenProcess(PROCESS_QUERY_INFORMATION | PROCESS_VM_READ, False, pid)
    if not h:
        return []
    try:
        needed = wt.DWORD()
        psapi.EnumProcessModulesEx(h, None, 0, ctypes.byref(needed), LIST_MODULES_ALL)
        if needed.value == 0:
            return []
        buf_arr = ctypes.create_string_buffer(needed.value)
        if not psapi.EnumProcessModulesEx(
            h, buf_arr, needed.value, ctypes.byref(needed), LIST_MODULES_ALL
        ):
            return []
        count = needed.value // ctypes.sizeof(ctypes.c_void_p)
        handles = ctypes.cast(
            buf_arr, ctypes.POINTER(ctypes.c_void_p)
        )
        out = []
        name_buf = ctypes.create_unicode_buffer(1024)
        for i in range(count):
            if psapi.GetModuleFileNameExW(h, handles[i], name_buf, 1024):
                out.append(name_buf.value)
        return out
    finally:
        kernel32.CloseHandle(h)


def main() -> int:
    name = sys.argv[1] if len(sys.argv) > 1 else "FileCraft.exe"
    pids = _pids(name)
    if not pids:
        print(f"没有找到进程 {name}")
        return 1

    interesting = ("qt6", "qwindows", "python3", "msvcp", "vcruntime", "pyside")
    verdict_lines = []
    for pid in pids:
        mods = modules_of(pid)
        qt = [m for m in mods if any(k in m.lower() for k in interesting)]
        if not qt:
            continue
        print(f"--- PID {pid}（共 {len(mods)} 个模块）---")
        for m in sorted(qt):
            print(f"    {m}")
        verdict_lines.append((pid, qt))

    if not verdict_lines:
        print("未发现 Qt 相关模块（进程可能尚未加载完）")
        return 2

    print("\n=== 判定 ===")
    ok = False
    for pid, qt in verdict_lines:
        for m in qt:
            low = m.lower()
            if "qt6core.dll" in low:
                if "_mei" in low:
                    print(f"✓ Qt6Core.dll 来自打包解包目录 _MEI —— exe 自带 Qt，可以独立分发")
                    ok = True
                else:
                    print(f"✗ Qt6Core.dll 来自本机环境：\n    {m}")
                    print("  → exe 在借用开发机的 Qt，换台电脑会启动失败")
                break
    return 0 if ok else 3


if __name__ == "__main__":
    raise SystemExit(main())