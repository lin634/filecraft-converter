"""历史记录浏览弹窗：AI 总结与文档问答共用。

左侧记录列表（时间 + 标题），右侧详情；支持载入与删除。
载入后由调用方处理（问答=恢复对话继续追问，总结=还原到编辑器）。
"""
from __future__ import annotations

import html

from PyQt6.QtCore import Qt
from PyQt6.QtWidgets import (
    QDialog,
    QHBoxLayout,
    QLabel,
    QListWidget,
    QListWidgetItem,
    QMessageBox,
    QPushButton,
    QTextBrowser,
    QVBoxLayout,
)

from core.history_store import HistoryStore

_BUBBLE_USER = "#EAF2FF"
_BUBBLE_AI = "#F0F0F3"


class HistoryDialog(QDialog):
    def __init__(self, kind: str, store: HistoryStore, parent=None):
        super().__init__(parent)
        self._kind = kind
        self._store = store
        #: 用户点了「载入」后，这里是要恢复的记录
        self.loaded_record: dict | None = None

        title = "问答历史" if kind == "qa" else "总结历史"
        self.setWindowTitle(title)
        self.resize(940, 620)

        root = QVBoxLayout(self)
        tip = QLabel("选择一条记录查看详情。「载入」会把内容恢复到对应页面。")
        tip.setStyleSheet("color:#6E6E73;")
        root.addWidget(tip)

        body = QHBoxLayout()
        root.addLayout(body, 1)

        self.listw = QListWidget()
        self.listw.setMinimumWidth(280)
        body.addWidget(self.listw, 1)

        self.detail = QTextBrowser()
        self.detail.setOpenExternalLinks(True)
        body.addWidget(self.detail, 2)

        btns = QHBoxLayout()
        self.btn_load = QPushButton("载入对话" if kind == "qa" else "还原到编辑器")
        self.btn_load.setObjectName("primary")
        self.btn_load.setEnabled(False)
        self.btn_load.clicked.connect(self._on_load)
        btns.addWidget(self.btn_load)
        self.btn_delete = QPushButton("删除这条")
        self.btn_delete.setEnabled(False)
        self.btn_delete.clicked.connect(self._on_delete)
        btns.addWidget(self.btn_delete)
        btns.addStretch(1)
        btn_close = QPushButton("关闭")
        btn_close.clicked.connect(self.reject)
        btns.addWidget(btn_close)
        root.addLayout(btns)

        self.listw.currentRowChanged.connect(self._on_select)
        self._reload_list()

    # ---- 列表与详情 ----------------------------------------------------
    def _records(self) -> list[dict]:
        return self._store.list_qa() if self._kind == "qa" else self._store.list_summary()

    def _reload_list(self) -> None:
        self.listw.clear()
        for r in self._records():
            item = QListWidgetItem(f"{r.get('time', '')}\n{r.get('title', '')}")
            item.setData(Qt.ItemDataRole.UserRole, r.get("id"))
            self.listw.addItem(item)
        if self.listw.count():
            self.listw.setCurrentRow(0)
        else:
            self.detail.setPlainText("还没有历史记录。")

    def _current_record(self) -> dict | None:
        item = self.listw.currentItem()
        if not item:
            return None
        rid = item.data(Qt.ItemDataRole.UserRole)
        for r in self._records():
            if r.get("id") == rid:
                return r
        return None

    def _on_select(self, _row: int) -> None:
        r = self._current_record()
        has = r is not None
        self.btn_load.setEnabled(has)
        self.btn_delete.setEnabled(has)
        if not r:
            self.detail.setPlainText("")
            return
        if self._kind == "summary":
            self.detail.setMarkdown(r.get("content", ""))
        else:
            self.detail.setHtml(self._qa_html(r.get("turns", [])))

    @staticmethod
    def _qa_html(turns: list[dict]) -> str:
        parts = ['<div style="font-family:\'Microsoft YaHei\';">']
        for t in turns:
            user = t.get("role") == "user"
            who = "我" if user else "AI"
            color = _BUBBLE_USER if user else _BUBBLE_AI
            text = html.escape(t.get("content", "")).replace("\n", "<br>")
            parts.append(
                f'<table width="100%" cellspacing="0" cellpadding="0"><tr>'
                f'<td width="{12 if user else 2}%" bgcolor="#F5F5F7"></td>'
                f'<td bgcolor="{color}" style="padding:5px;">'
                f'<b>{who}：</b>{text}</td>'
                f'<td width="{2 if user else 12}%" bgcolor="#F5F5F7"></td>'
                f"</tr></table>"
            )
        parts.append("</div>")
        # 文件清单
        return "".join(parts)

    # ---- 动作 ----------------------------------------------------------
    def _on_load(self) -> None:
        r = self._current_record()
        if not r:
            return
        self.loaded_record = r
        self.accept()

    def _on_delete(self) -> None:
        r = self._current_record()
        if not r:
            return
        ret = QMessageBox.question(
            self, "确认删除",
            f"确定删除这条历史记录吗？\n\n{r.get('time', '')}  {r.get('title', '')}",
        )
        if ret != QMessageBox.StandardButton.Yes:
            return
        self._store.delete(self._kind, r.get("id", ""))
        self._reload_list()