"""文件库归档：按可视化文件夹分类存放导入文件与总结产物。

目录模型（全部位于 root_dir 下，用户可新建任意多层文件夹）：
    <root>/
    ├── 客户A资料/          ← 导入的源文件直接存放
    │   └── 总结/           ← 由该文件夹内文件生成的总结自动存到这里
    └── 会议材料/
        └── 总结/

归档是"复制"而非"移动"——原文件不动，文件库里保留副本。
同名同大小的文件不会重复归档。
"""
from __future__ import annotations

import datetime
import os
import shutil
from typing import Callable

from config import AppConfig, save_config

#: 历史记录最多保留条数
HISTORY_LIMIT = 200

SUMMARY_SUBDIR = "总结"

#: 文件夹名中不允许出现的字符
_INVALID_NAME_CHARS = '\\/:*?"<>|'


def unique_path(path: str) -> str:
    """目标已存在时追加 _1、_2 … 避免覆盖。"""
    if not os.path.exists(path):
        return path
    stem, ext = os.path.splitext(path)
    i = 1
    while True:
        cand = f"{stem}_{i}{ext}"
        if not os.path.exists(cand):
            return cand
        i += 1


class ArchiveManager:
    """文件库的文件夹管理与归档动作，配置变更立即持久化。"""

    def __init__(self, get_config: Callable[[], AppConfig]):
        self._get = get_config

    # ---- 根目录与当前文件夹 --------------------------------------------
    def root(self) -> str:
        return self._get().archive.root_dir

    def set_root(self, d: str) -> None:
        self._get().archive.root_dir = d
        self._save()

    def active_folder(self) -> str:
        return self._get().archive.active_folder

    def set_active_folder(self, rel: str) -> None:
        self._get().archive.active_folder = rel or ""
        self._save()

    # ---- 路径计算 ------------------------------------------------------
    def folder_abs(self, rel: str) -> str:
        """相对文件夹名 -> 绝对路径。空串表示根目录。

        防越界：拒绝绝对路径与 .. 上跳，异常输入一律回落到根目录。
        """
        rel = (rel or "").replace("\\", "/").strip("/")
        root = os.path.abspath(self.root())
        if not rel or rel == ".":
            return root
        if os.path.isabs(rel) or ".." in rel.split("/"):
            return root
        p = os.path.abspath(os.path.join(root, rel))
        return p if p.startswith(root + os.sep) or p == root else root

    def summary_rel(self, rel: str) -> str:
        """某文件夹对应的总结子夹（相对路径）。"""
        return f"{rel}/{SUMMARY_SUBDIR}" if rel else SUMMARY_SUBDIR

    def summary_dir(self, rel: str = "") -> str:
        return self.folder_abs(self.summary_rel(rel))

    # ---- 文件夹管理 ----------------------------------------------------
    def folders(self, include_summary: bool = False) -> list[str]:
        """根目录下所有子文件夹的相对路径（含多级，按名字排序）。

        默认不包含名为「总结」的子夹及其内部（那是自动管理的总结目录）。
        """
        root = self.root()
        out: list[str] = []
        if not os.path.isdir(root):
            return out
        for r, dirs, _files in os.walk(root):
            rel = os.path.relpath(r, root).replace("\\", "/")
            for d in sorted(dirs):
                if not include_summary and d == SUMMARY_SUBDIR:
                    dirs.remove(d)  # 剪枝：总结子夹内部不再遍历
                    continue
                out.append(d if rel == "." else f"{rel}/{d}")
        return sorted(out)

    def ensure_root(self) -> None:
        try:
            os.makedirs(self.root(), exist_ok=True)
        except OSError:
            pass

    def default_folder_name(self, parent_rel: str = "") -> str:
        """返回在指定父文件夹下未占用的默认名：新建文件夹 / 新建文件夹_2 …"""
        base = self.folder_abs(parent_rel)
        name = "新建文件夹"
        i = 1
        while os.path.exists(os.path.join(base, name)):
            i += 1
            name = f"新建文件夹_{i}"
        return name

    def create_folder(self, name: str, parent_rel: str = "") -> tuple[str | None, str]:
        """在指定父文件夹（可为多级）下新建文件夹。

        返回 (新文件夹的相对路径, 错误信息)。
        """
        name = (name or "").strip()
        if not name:
            return None, "文件夹名不能为空"
        if any(c in name for c in _INVALID_NAME_CHARS):
            return None, f"名称不能包含以下字符：{_INVALID_NAME_CHARS}"
        parent = self.folder_abs(parent_rel)
        target = os.path.join(parent, name)
        if os.path.exists(target):
            return None, "同名文件夹已存在"
        try:
            os.makedirs(target)
        except OSError as e:
            return None, str(e)
        parent_rel = (parent_rel or "").replace("\\", "/").strip("/")
        rel = f"{parent_rel}/{name}" if parent_rel else name
        return rel, ""

    def delete_folder(self, rel: str) -> str:
        """删除文件夹（必须整棵为空）。返回错误信息，空串=成功。"""
        p = self.folder_abs(rel)
        root = os.path.abspath(self.root())
        if p == root:
            return "不能删除根目录"
        if not os.path.isdir(p):
            return "文件夹不存在"
        for _r, _d, files in os.walk(p):
            if files:
                return "文件夹不为空，请先移动或删除其中的文件"
        try:
            shutil.rmtree(p)
        except OSError as e:
            return str(e)
        if self.active_folder() and self.folder_abs(self.active_folder()).startswith(p):
            self.set_active_folder("")
        return ""

    @staticmethod
    def is_summary_rel(rel: str) -> bool:
        """判断相对路径最后一段是否为自动管理的「总结」子夹。"""
        rel = (rel or "").replace("\\", "/").strip("/")
        return rel.split("/")[-1] == SUMMARY_SUBDIR if rel else False

    # ---- 文件移动 ------------------------------------------------------
    def move_files(self, paths: list[str], rel_target: str) -> tuple[int, int, list[str]]:
        """把文件库内的文件移动到目标文件夹。返回 (移动数, 跳过数, 错误列表)。

        目标已有同名同大小文件时跳过；同名不同大小则自动加后缀改名。
        """
        moved = skipped = 0
        errors: list[str] = []
        if not paths:
            return 0, 0, errors
        target = self.folder_abs(rel_target)
        root = os.path.abspath(self.root())
        try:
            os.makedirs(target, exist_ok=True)
        except OSError as e:
            return 0, 0, [f"无法创建目标目录: {e}"]

        for p in paths:
            try:
                if not p or not os.path.isfile(p):
                    continue
                src = os.path.abspath(p)
                # 只允许移动文件库内部的副本
                if not (src == root or src.startswith(root + os.sep)):
                    errors.append(f"{os.path.basename(p)}: 不在文件库内")
                    continue
                if os.path.dirname(src) == target:
                    skipped += 1
                    continue
                dest = os.path.join(target, os.path.basename(src))
                if os.path.exists(dest):
                    if self._same_file(src, dest):
                        skipped += 1
                        continue
                    dest = unique_path(dest)
                shutil.move(src, dest)
                moved += 1
            except Exception as e:  # noqa: BLE001 - 单个文件失败不影响其余
                errors.append(f"{os.path.basename(p) or p}: {e}")
        return moved, skipped, errors

    # ---- 归档动作 ------------------------------------------------------
    @staticmethod
    def _same_file(a: str, b: str) -> bool:
        try:
            return os.path.getsize(a) == os.path.getsize(b)
        except OSError:
            return False

    def archive_into(self, paths: list[str], rel_folder: str = "") -> tuple[int, int, list[str]]:
        """把文件复制到指定文件夹。返回 (归档数, 跳过数, 错误列表)。"""
        archived = skipped = 0
        errors: list[str] = []
        if not paths:
            return 0, 0, errors
        target = self.folder_abs(rel_folder)
        try:
            os.makedirs(target, exist_ok=True)
        except OSError as e:
            return 0, 0, [f"无法创建目录 {target}: {e}"]

        for p in paths:
            try:
                if not p or not os.path.isfile(p):
                    continue
                dest = os.path.join(target, os.path.basename(p))
                if os.path.exists(dest) and self._same_file(p, dest):
                    skipped += 1
                    continue
                dest = unique_path(dest)
                shutil.copy2(p, dest)
                archived += 1
            except Exception as e:  # noqa: BLE001 - 单个文件失败不影响其余
                errors.append(f"{os.path.basename(p) or p}: {e}")
        return archived, skipped, errors

    def archive_imports(self, paths: list[str], folder: str | None = None) -> tuple[int, int, list[str]]:
        """归档导入的源文件到当前（或指定）文件夹。auto_import 关闭时不动作。"""
        cfg = self._get().archive
        if not cfg.auto_import or not paths:
            return 0, 0, []
        rel = self.active_folder() if folder is None else folder
        return self.archive_into(paths, rel)

    def archive_summary(self, path: str, folder: str | None = None) -> tuple[int, int, list[str]]:
        """记录并把总结产物归档到来源文件夹的「总结」子夹。

        无论自动归档开关与否都写入历史；auto_summary 关闭时只记录不复制。
        """
        cfg = self._get().archive
        rel = self.active_folder() if folder is None else (folder or "")
        self.record_output(path, rel)
        if not cfg.auto_summary:
            return 0, 0, []
        return self.archive_into([path], self.summary_rel(rel))

    # ---- 生成产物历史 --------------------------------------------------
    def record_output(self, path: str, folder: str = "") -> None:
        """记录一个生成产物（去重、限量），立即持久化。"""
        path = os.path.abspath(path)
        cfg = self._get()
        entry = {
            "path": path,
            "time": datetime.datetime.now().strftime("%Y-%m-%d %H:%M"),
            "folder": folder or "",
        }
        history = [h for h in cfg.archive.history if h.get("path") != path]
        history.insert(0, entry)
        cfg.archive.history = history[:HISTORY_LIMIT]
        self._save()

    def unarchived_history(self) -> list[dict]:
        """历史中尚未存入对应「总结」子夹的产物。"""
        out: list[dict] = []
        for h in self._get().archive.history:
            p = h.get("path", "")
            if not p or not os.path.isfile(p):
                continue
            dest_dir = self.summary_dir(h.get("folder", ""))
            if not os.path.exists(os.path.join(dest_dir, os.path.basename(p))):
                out.append(h)
        return out

    # ---- 内部 ----------------------------------------------------------
    def _save(self) -> None:
        try:
            save_config(self._get())
        except OSError:
            pass  # 配置写失败不阻塞主流程
