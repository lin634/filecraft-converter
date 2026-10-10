"""共享的文件列表数据源，供"转 Markdown"和"AI 总结"两个标签页复用。"""
from __future__ import annotations

import os
from dataclasses import dataclass, field

from PyQt6.QtCore import QObject, pyqtSignal


@dataclass
class FileItem:
    path: str
    name: str = ""
    ext: str = ""
    size: int = 0
    #: 转换/总结状态文案
    status: str = "待处理"
    #: 转换产出的 md 路径
    output_path: str = ""
    #: 缓存的 markdown 内容（避免重复解析）
    md_text: str = ""
    #: 归档到文件库的文件夹（相对根目录，"" = 根目录）
    folder: str = ""

    def __post_init__(self):
        if not self.name:
            self.name = os.path.basename(self.path)
        if not self.ext:
            self.ext = os.path.splitext(self.path)[1].lower()
        if not self.size:
            try:
                self.size = os.path.getsize(self.path)
            except OSError:
                self.size = 0

    @property
    def size_text(self) -> str:
        s = self.size
        for unit in ("B", "KB", "MB", "GB"):
            if s < 1024 or unit == "GB":
                return f"{s:.1f} {unit}" if unit != "B" else f"{s} B"
            s /= 1024
        return f"{s:.1f} GB"

    @property
    def type_text(self) -> str:
        mapping = {
            ".docx": "Word",
            ".doc": "Word(旧)",
            ".pptx": "PPT",
            ".ppt": "PPT(旧)",
            ".xlsx": "Excel",
            ".xls": "Excel(旧)",
            ".pdf": "PDF",
        }
        return mapping.get(self.ext, self.ext.lstrip(".").upper() or "未知")


class FileStore(QObject):
    """保存已导入文件，供多个标签页共享。"""

    files_changed = pyqtSignal()
    #: 新导入文件的绝对路径列表（用于自动归档等后续处理）
    files_added = pyqtSignal(list)

    def __init__(self):
        super().__init__()
        self._items: list[FileItem] = []
        self._paths: set[str] = set()

    # ---- 查询 ----------------------------------------------------------
    @property
    def items(self) -> list[FileItem]:
        return list(self._items)

    def __len__(self) -> int:
        return len(self._items)

    def is_empty(self) -> bool:
        return not self._items

    # ---- 修改 ----------------------------------------------------------
    def add_paths(self, paths: list[str]) -> tuple[int, list[str]]:
        """加入文件，返回 (新增数量, 被拒绝的文件名列表)。"""
        added = 0
        new_paths: list[str] = []
        rejected: list[str] = []
        for p in paths:
            p = os.path.abspath(p)
            if p in self._paths:
                continue
            if not os.path.isfile(p):
                continue
            item = FileItem(path=p)
            # 只接受受支持的格式，其余记录为拒绝
            from core.registry import is_supported

            if not is_supported(p):
                rejected.append(item.name)
                continue
            self._items.append(item)
            self._paths.add(p)
            added += 1
            new_paths.append(p)
        if added or rejected:
            self.files_changed.emit()
        if new_paths:
            self.files_added.emit(new_paths)
        return added, rejected

    def remove(self, paths: list[str]) -> None:
        drop = set(os.path.abspath(p) for p in paths)
        before = len(self._items)
        self._items = [it for it in self._items if it.path not in drop]
        self._paths -= drop
        if len(self._items) != before:
            self.files_changed.emit()

    def clear(self) -> None:
        if not self._items:
            return
        self._items.clear()
        self._paths.clear()
        self.files_changed.emit()

    def get(self, path: str) -> FileItem | None:
        for it in self._items:
            if it.path == path:
                return it
        return None