"""历史记录持久化：AI 总结与文档问答，保存在本机 %USERPROFILE%\\.filecraft\\history.json。

- qa：每条是一段完整对话会话（多轮 turns + 参与文件），载入后可继续追问
- summary：每条是一次总结的完整内容，可还原到编辑器
"""
from __future__ import annotations

import json
import os
import time
import uuid

from config import CONFIG_DIR

HISTORY_PATH = os.path.join(CONFIG_DIR, "history.json")

#: 每类最多保留条数（超出淘汰最旧的）
MAX_RECORDS = 50


def new_id() -> str:
    return time.strftime("%Y%m%d-%H%M%S") + "-" + uuid.uuid4().hex[:4]


def now_text() -> str:
    return time.strftime("%Y-%m-%d %H:%M:%S")


class HistoryStore:
    """内存持有全部历史，读写同一份 JSON。"""

    def __init__(self, path: str | None = None):
        # 运行时解析而不是默认参数绑定，方便测试或特殊场景重定向
        self.path = path or HISTORY_PATH
        self._data: dict = {"qa": [], "summary": []}
        self._load()

    # ---- 读写 ----------------------------------------------------------
    def _load(self) -> None:
        if not os.path.exists(self.path):
            return
        try:
            with open(self.path, "r", encoding="utf-8") as f:
                data = json.load(f)
            if isinstance(data, dict):
                self._data["qa"] = data.get("qa", []) or []
                self._data["summary"] = data.get("summary", []) or []
        except Exception:  # noqa: BLE001 - 历史文件损坏时按空处理，不影响主功能
            self._data = {"qa": [], "summary": []}

    def _save(self) -> None:
        try:
            os.makedirs(os.path.dirname(self.path), exist_ok=True)
            with open(self.path, "w", encoding="utf-8") as f:
                json.dump(self._data, f, ensure_ascii=False, indent=2)
        except OSError:
            pass  # 保存失败不阻塞主流程

    # ---- 文档问答会话 --------------------------------------------------
    def upsert_qa(self, session: dict) -> None:
        """插入或更新一段问答会话（按 id 去重，新的在前）。"""
        sid = session.get("id")
        if not sid:
            return
        self._data["qa"] = [r for r in self._data["qa"] if r.get("id") != sid]
        self._data["qa"].insert(0, session)
        self._data["qa"] = self._data["qa"][:MAX_RECORDS]
        self._save()

    def list_qa(self) -> list[dict]:
        return list(self._data["qa"])

    # ---- AI 总结记录 ---------------------------------------------------
    def upsert_summary(self, record: dict) -> None:
        rid = record.get("id")
        if not rid:
            return
        self._data["summary"] = [r for r in self._data["summary"] if r.get("id") != rid]
        self._data["summary"].insert(0, record)
        self._data["summary"] = self._data["summary"][:MAX_RECORDS]
        self._save()

    def list_summary(self) -> list[dict]:
        return list(self._data["summary"])

    # ---- 删除 ----------------------------------------------------------
    def delete(self, kind: str, rid: str) -> None:
        if kind not in ("qa", "summary"):
            return
        self._data[kind] = [r for r in self._data[kind] if r.get("id") != rid]
        self._save()