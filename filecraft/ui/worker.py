"""后台任务线程：避免文件解析和网络请求阻塞界面。"""
from __future__ import annotations

import traceback
from typing import Any, Callable

from PyQt6.QtCore import QThread, pyqtSignal


class Worker(QThread):
    """在子线程中执行一个可调用对象。

    fn 可以接收一个 progress 回调（通过 progress_cb 参数名传入）来上报进度。
    """

    progress = pyqtSignal(object)
    finished_ok = pyqtSignal(object)
    failed = pyqtSignal(str)

    def __init__(self, fn: Callable[..., Any], *args, **kwargs):
        super().__init__()
        self._fn = fn
        self._args = args
        self._kwargs = kwargs

    def run(self) -> None:  # noqa: D102
        try:
            result = self._fn(*self._args, progress=self.progress.emit, **self._kwargs)
            self.finished_ok.emit(result)
        except Exception as e:  # noqa: BLE001 - 需要把任何异常反馈到界面
            detail = f"{type(e).__name__}: {e}"
            self.failed.emit(detail)
            traceback.print_exc()