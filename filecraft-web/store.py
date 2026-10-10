"""工作区存储：每个浏览器会话一个独立目录，互不可见。

目录结构：
    <DATA_DIR>/workspaces/<sid>/
        meta.json          # {files: {id: {name, ext, size, uploaded}}} 及摘要记录
        files/<id>.<ext>   # 上传的原始文件
        md/<id>.md         # 转换结果缓存
        summaries/<id>.md  # 生成的总结

sid 由服务端生成（uuid hex），写入 HttpOnly Cookie。
"""
from __future__ import annotations

import json
import os
import re
import threading
import time
import uuid

import config

_META_NAME = "meta.json"
_lock = threading.Lock()

#: 支持的扩展名（与 core.registry 一致，这里显式声明避免 import 开销歧义）
ALLOWED_EXTS = (".docx", ".pptx", ".xlsx", ".pdf")


def _ws_root(sid: str) -> str:
    return os.path.join(config.DATA_DIR, "workspaces", sid)


class Workspace:
    def __init__(self, sid: str):
        self.sid = sid
        self.root = _ws_root(sid)

    # ---- 路径 ----------------------------------------------------------
    @property
    def meta_path(self) -> str:
        return os.path.join(self.root, _META_NAME)

    def _ensure_dirs(self) -> None:
        for sub in ("files", "md", "summaries", "history"):
            os.makedirs(os.path.join(self.root, sub), exist_ok=True)

    # ---- 元数据 --------------------------------------------------------
    def _load_meta(self) -> dict:
        try:
            with open(self.meta_path, "r", encoding="utf-8") as f:
                return json.load(f)
        except (OSError, ValueError):
            return {"files": {}}

    def _save_meta(self, meta: dict) -> None:
        self._ensure_dirs()
        tmp = self.meta_path + ".tmp"
        with open(tmp, "w", encoding="utf-8") as f:
            json.dump(meta, f, ensure_ascii=False, indent=1)
        os.replace(tmp, self.meta_path)

    # ---- 会话 ----------------------------------------------------------
    @staticmethod
    def new_sid() -> str:
        return uuid.uuid4().hex

    @staticmethod
    def valid_sid(sid: str | None) -> bool:
        return bool(sid) and bool(re.fullmatch(r"[0-9a-f]{32}", sid))

    def touch(self) -> None:
        """刷新活动时间（用于 TTL 清理）。"""
        try:
            os.utime(self.root, None)
        except OSError:
            pass

    # ---- 文件操作 ------------------------------------------------------
    @staticmethod
    def _sanitize_name(name: str) -> str:
        """保留中文等 unicode 字符，仅去掉路径与 Windows 非法字符。"""
        bad = '\\/:*?"<>|\r\n\t'
        cleaned = "".join("_" if ch in bad else ch for ch in name).strip().strip(".")
        return cleaned or "unnamed"

    def add_file(self, original_name: str, content: bytes) -> dict:
        original_name = self._sanitize_name(os.path.basename(original_name))
        ext = os.path.splitext(original_name)[1].lower()
        if ext not in ALLOWED_EXTS:
            raise ValueError(f"不支持的格式 {ext or '(无扩展名)'}，仅支持 {'/'.join(ALLOWED_EXTS)}")
        fid = uuid.uuid4().hex[:12]
        # 每个文件一个子目录 files/<fid>/<原始名>：
        # 转换器用 basename 做标题回退（桌面版逻辑），文件名必须保持原样
        fdir = os.path.join(self.root, "files", fid)
        os.makedirs(fdir, exist_ok=True)
        with open(os.path.join(fdir, original_name), "wb") as f:
            f.write(content)
        with _lock:
            meta = self._load_meta()
            meta["files"][fid] = {
                "name": original_name,
                "ext": ext,
                "size": len(content),
                "uploaded": time.strftime("%Y-%m-%d %H:%M:%S"),
            }
            self._save_meta(meta)
        self.touch()
        return self.file_info(fid, meta)

    def file_info(self, fid: str, meta: dict | None = None) -> dict | None:
        meta = meta or self._load_meta()
        info = meta["files"].get(fid)
        if not info:
            return None
        md_path = os.path.join(self.root, "md", fid + ".md")
        return {
            "id": fid,
            "name": info["name"],
            "ext": info["ext"],
            "size": info["size"],
            "uploaded": info["uploaded"],
            "converted": os.path.exists(md_path),
            "md_size": os.path.getsize(md_path) if os.path.exists(md_path) else 0,
        }

    def list_files(self) -> list[dict]:
        meta = self._load_meta()
        out = [self.file_info(fid, meta) for fid in meta["files"]]
        out = [x for x in out if x]
        out.sort(key=lambda x: x["uploaded"], reverse=True)
        return out

    def get_file(self, fid: str) -> dict | None:
        return self.file_info(fid)

    def file_path(self, fid: str) -> str | None:
        """原始上传文件的磁盘路径（files/<fid>/<原始名>）。"""
        info = self.file_info(fid)
        if not info:
            return None
        fdir = os.path.join(self.root, "files", fid)
        if os.path.isdir(fdir):
            preferred = os.path.join(fdir, info["name"])
            if os.path.exists(preferred):
                return preferred
            names = os.listdir(fdir)
            if names:
                return os.path.join(fdir, names[0])
        return None

    def remove_file(self, fid: str) -> bool:
        info = self.file_info(fid)
        if not info:
            return False
        import shutil
        shutil.rmtree(os.path.join(self.root, "files", fid), ignore_errors=True)
        p = os.path.join(self.root, "md", fid + ".md")
        if os.path.exists(p):
            os.remove(p)
        with _lock:
            meta = self._load_meta()
            meta["files"].pop(fid, None)
            self._save_meta(meta)
        return True

    # ---- Markdown 缓存 -------------------------------------------------
    def save_md(self, fid: str, md: str) -> None:
        self._ensure_dirs()
        with open(os.path.join(self.root, "md", fid + ".md"), "w", encoding="utf-8") as f:
            f.write(md)
        self.touch()

    def load_md(self, fid: str) -> str | None:
        p = os.path.join(self.root, "md", fid + ".md")
        if not os.path.exists(p):
            return None
        with open(p, "r", encoding="utf-8") as f:
            return f.read()

    # ---- 总结 ----------------------------------------------------------
    def save_summary(self, md: str, title: str = "文档总结") -> str:
        self._ensure_dirs()
        sid = time.strftime("%Y%m%d-%H%M%S") + "-" + uuid.uuid4().hex[:4]
        with open(os.path.join(self.root, "summaries", sid + ".md"), "w", encoding="utf-8") as f:
            f.write(f"# {title}\n\n{md}" if not md.lstrip().startswith("#") else md)
        self.touch()
        return sid

    def summary_path(self, summary_id: str) -> str | None:
        if not re.fullmatch(r"[0-9A-Za-z\-]{1,40}", summary_id):
            return None
        p = os.path.join(self.root, "summaries", summary_id + ".md")
        return p if os.path.exists(p) else None

    # ---- 历史记录（总结 / 问答会话）--------------------------------------
    #: 每类最多保留条数（超出淘汰最旧的），与桌面版 history_store 一致
    HISTORY_CAP = 50

    def _hist_path(self, kind: str) -> str:
        return os.path.join(self.root, "history", f"{kind}.json")

    def _load_hist(self, kind: str) -> list:
        try:
            with open(self._hist_path(kind), "r", encoding="utf-8") as f:
                data = json.load(f)
            return data if isinstance(data, list) else []
        except (OSError, ValueError):
            return []

    def _save_hist(self, kind: str, items: list) -> None:
        self._ensure_dirs()
        tmp = self._hist_path(kind) + ".tmp"
        with open(tmp, "w", encoding="utf-8") as f:
            json.dump(items, f, ensure_ascii=False, indent=1)
        os.replace(tmp, self._hist_path(kind))

    # ---- 总结历史 --------------------------------------------------------
    def add_summary_history(self, summary_id: str, title: str,
                            file_names: list[str], extra: str,
                            source: str = "ai") -> None:
        with _lock:
            items = self._load_hist("summaries")
            items.insert(0, {
                "id": summary_id,
                "title": title,
                "time": time.strftime("%Y-%m-%d %H:%M:%S"),
                "files": file_names,
                "extra": extra,
                "source": source,
            })
            self._save_hist("summaries", items[:self.HISTORY_CAP])

    def list_summary_history(self) -> list[dict]:
        return self._load_hist("summaries")

    def get_summary_history_md(self, summary_id: str) -> str | None:
        p = self.summary_path(summary_id)
        if not p:
            return None
        with open(p, "r", encoding="utf-8") as f:
            return f.read()

    def delete_summary_history(self, summary_id: str) -> bool:
        with _lock:
            items = self._load_hist("summaries")
            kept = [x for x in items if x.get("id") != summary_id]
            if len(kept) == len(items):
                return False
            self._save_hist("summaries", kept)
        p = self.summary_path(summary_id)
        if p:
            os.remove(p)
        return True

    # ---- 问答会话历史 ----------------------------------------------------
    def qa_append(self, session_id: str, title: str,
                  file_names: list[str], file_ids: list[str],
                  question: str, answer: str) -> dict:
        """向会话追加一轮问答；会话不存在则创建（置顶）。"""
        with _lock:
            items = self._load_hist("qa")
            s = next((x for x in items if x.get("id") == session_id), None)
            if s is None:
                s = {"id": session_id, "title": title,
                     "time": time.strftime("%Y-%m-%d %H:%M:%S"),
                     "files": file_names, "file_ids": file_ids, "turns": []}
                items.insert(0, s)
            s["turns"].append({"role": "user", "content": question})
            s["turns"].append({"role": "assistant", "content": answer})
            self._save_hist("qa", items[:self.HISTORY_CAP])
            return s

    def qa_sessions(self) -> list[dict]:
        """会话列表（不含 turns 正文，减轻载荷）。"""
        return [{k: v for k, v in s.items() if k != "turns"} | {"turns_count": len(s.get("turns", [])) // 2}
                for s in self._load_hist("qa")]

    def qa_session(self, session_id: str) -> dict | None:
        return next((s for s in self._load_hist("qa") if s.get("id") == session_id), None)

    def qa_delete(self, session_id: str) -> bool:
        with _lock:
            items = self._load_hist("qa")
            kept = [x for x in items if x.get("id") != session_id]
            if len(kept) == len(items):
                return False
            self._save_hist("qa", kept)
        return True


# ---- 全局工具 ----------------------------------------------------------
def get_workspace(sid: str | None) -> Workspace | None:
    if not Workspace.valid_sid(sid):
        return None
    return Workspace(sid)


def cleanup_expired(ttl_days: int | None = None) -> int:
    """删除超过 TTL 未活动的工作区，返回删除数量。启动时和每天各跑一次。"""
    ttl_days = ttl_days or config.WORKSPACE_TTL_DAYS
    root = os.path.join(config.DATA_DIR, "workspaces")
    if not os.path.isdir(root):
        return 0
    cutoff = time.time() - ttl_days * 86400
    removed = 0
    for name in os.listdir(root):
        p = os.path.join(root, name)
        if not os.path.isdir(p):
            continue
        try:
            if os.path.getmtime(p) < cutoff:
                import shutil
                shutil.rmtree(p, ignore_errors=True)
                removed += 1
        except OSError:
            continue
    return removed
