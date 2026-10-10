"""④ 文档问答：针对导入的文件或文件库中的文件进行多轮提问。

布局：左边窄栏为提问范围——可在「导入的文件」与「文件库」两个来源间切换，
勾选要提问的文件；右边宽栏为对话输出。
"""
from __future__ import annotations

import html
import os
from typing import Callable, List

from PyQt6.QtCore import Qt, pyqtSignal
from PyQt6.QtWidgets import (
    QAbstractItemView,
    QCheckBox,
    QGroupBox,
    QHBoxLayout,
    QHeaderView,
    QLabel,
    QLineEdit,
    QMessageBox,
    QPushButton,
    QSplitter,
    QTabWidget,
    QTableWidget,
    QTableWidgetItem,
    QTextBrowser,
    QVBoxLayout,
    QWidget,
)

from core.history_store import HistoryStore, new_id, now_text
from core.qa import QAEngine
from core.registry import SUPPORTED_EXTENSIONS, convert_file, get_converter

from .file_store import FileItem, FileStore
from .file_table import FileTable
from .worker import Worker

#: 用户气泡 / 助手气泡底色（配合全局极简白样式）
_BUBBLE_USER = "#EAF2FF"
_BUBBLE_AI = "#F0F0F3"

#: 问答可直接提取文本的扩展名
_QA_TEXT_EXTS = (".md", ".txt")

#: 文件库列表规模上限（防极端情况卡死）
_LIBRARY_MAX_ROWS = 1000

SOURCE_IMPORT = 0
SOURCE_LIBRARY = 1


class LibraryTable(QTableWidget):
    """文件库文件列表：遍历文件库根目录（含子文件夹），带勾选框。"""

    check_changed = pyqtSignal()

    COL_CHECK, COL_NAME, COL_FOLDER, COL_SIZE = 0, 1, 2, 3

    def __init__(self, get_root: Callable[[], str], parent=None):
        super().__init__(0, 4, parent)
        self._get_root = get_root
        self.setHorizontalHeaderLabels(["", "文件名", "所在文件夹", "大小"])
        self.verticalHeader().setVisible(False)
        self.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        self.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        self.setAlternatingRowColors(True)
        hdr = self.horizontalHeader()
        hdr.setSectionResizeMode(self.COL_CHECK, QHeaderView.ResizeMode.Fixed)
        hdr.setSectionResizeMode(self.COL_NAME, QHeaderView.ResizeMode.Stretch)
        hdr.setSectionResizeMode(self.COL_FOLDER, QHeaderView.ResizeMode.ResizeToContents)
        hdr.setSectionResizeMode(self.COL_SIZE, QHeaderView.ResizeMode.ResizeToContents)
        self.setColumnWidth(self.COL_CHECK, 34)
        self.itemChanged.connect(self._on_item_changed)

    def refresh(self) -> None:
        root = self._get_root() or ""
        self.blockSignals(True)
        self.setRowCount(0)
        if os.path.isdir(root):
            for r, _dirs, files in os.walk(root):
                rel = os.path.relpath(r, root).replace("\\", "/")
                if rel == ".":
                    rel = ""
                for name in sorted(files):
                    if self.rowCount() >= _LIBRARY_MAX_ROWS:
                        break
                    p = os.path.join(r, name)
                    if not os.path.isfile(p):
                        continue
                    row = self.rowCount()
                    self.insertRow(row)
                    chk = QTableWidgetItem()
                    chk.setFlags(
                        Qt.ItemFlag.ItemIsUserCheckable
                        | Qt.ItemFlag.ItemIsEnabled
                        | Qt.ItemFlag.ItemIsSelectable
                    )
                    chk.setCheckState(Qt.CheckState.Unchecked)
                    chk.setData(Qt.ItemDataRole.UserRole, p)
                    self.setItem(row, self.COL_CHECK, chk)
                    name_item = QTableWidgetItem(name)
                    name_item.setData(Qt.ItemDataRole.UserRole, p)
                    name_item.setToolTip(p)
                    self.setItem(row, self.COL_NAME, name_item)
                    self.setItem(row, self.COL_FOLDER, QTableWidgetItem(rel or "（根目录）"))
                    try:
                        size = os.path.getsize(p)
                    except OSError:
                        size = 0
                    self.setItem(row, self.COL_SIZE, QTableWidgetItem(self._size_text(size)))
        self.blockSignals(False)
        self.check_changed.emit()

    def checked_paths(self) -> list[str]:
        out = []
        for row in range(self.rowCount()):
            item = self.item(row, self.COL_CHECK)
            if item and item.checkState() == Qt.CheckState.Checked:
                out.append(item.data(Qt.ItemDataRole.UserRole))
        return [p for p in out if p]

    def set_checked_all(self, on: bool) -> None:
        state = Qt.CheckState.Checked if on else Qt.CheckState.Unchecked
        for row in range(self.rowCount()):
            item = self.item(row, self.COL_CHECK)
            if item:
                item.setCheckState(state)

    def set_checked_paths(self, paths: list[str]) -> None:
        target = set(paths)
        for row in range(self.rowCount()):
            item = self.item(row, self.COL_CHECK)
            if item:
                p = item.data(Qt.ItemDataRole.UserRole)
                item.setCheckState(Qt.CheckState.Checked if p in target else Qt.CheckState.Unchecked)

    def _on_item_changed(self, item: QTableWidgetItem) -> None:
        if item.column() == self.COL_CHECK:
            self.check_changed.emit()

    @staticmethod
    def _size_text(n: int) -> str:
        s = float(n)
        for unit in ("B", "KB", "MB", "GB"):
            if s < 1024 or unit == "GB":
                return f"{int(s)} {unit}" if unit == "B" else f"{s:.1f} {unit}"
            s /= 1024
        return f"{s:.1f} GB"


class QATab(QWidget):
    """文档问答标签页。"""

    request_settings = pyqtSignal()

    def __init__(self, store: FileStore, get_config, get_archive=None, history: "HistoryStore | None" = None, parent=None):
        super().__init__(parent)
        self._store = store
        self._get_config = get_config
        self._get_archive = get_archive
        self._history_store = history or HistoryStore()
        self._worker: Worker | None = None
        #: 对话历史 [{"role": "user"|"assistant", "content": str}]
        self._history: List[dict] = []
        #: 当前会话（持久化用）：首次提问时创建，清空对话后重开
        self._session_id: str | None = None
        self._session_time: str = ""
        self._session_files: list[dict] = []
        #: 文件库文件的文本缓存 {(路径, mtime): 文本}
        self._lib_cache: dict = {}

        self._build_ui()
        self._update_buttons()

    # ---- 界面 ----------------------------------------------------------
    def _build_ui(self) -> None:
        root = QVBoxLayout(self)

        tip = QLabel(
            "左边选择提问范围（导入的文件或文件库里的文件）并勾选，右边像聊天一样多轮追问。"
            "回答只依据文件内容，没有依据会明确说「文档中未提及」。"
        )
        tip.setWordWrap(True)
        tip.setStyleSheet("color:#6E6E73; padding:2px;")
        root.addWidget(tip)

        split = QSplitter(Qt.Orientation.Horizontal)
        root.addWidget(split, 1)

        # 左：提问范围（窄）
        left = QWidget()
        ll = QVBoxLayout(left)
        ll.setContentsMargins(0, 0, 0, 0)

        file_box = QGroupBox("提问范围（勾选要提问的文件）")
        fl = QVBoxLayout(file_box)
        self.source_tabs = QTabWidget()
        self.source_tabs.addTab(self._build_import_page(), "导入的文件")
        self.lib_page = self._build_library_page()
        self.source_tabs.addTab(self.lib_page, "文件库")
        self.source_tabs.currentChanged.connect(self._on_source_changed)
        fl.addWidget(self.source_tabs)
        ll.addWidget(file_box)
        split.addWidget(left)

        # 右：对话（宽）
        right = QWidget()
        rl = QVBoxLayout(right)
        rl.setContentsMargins(0, 0, 0, 0)

        self.chat = QTextBrowser()
        self.chat.setOpenExternalLinks(True)
        self.chat.setPlaceholderText("还没有对话。勾选文件后输入第一个问题吧。")
        rl.addWidget(self.chat, 1)

        act = QHBoxLayout()
        self.chk_cite = QCheckBox("要求注明出处")
        self.chk_cite.setChecked(True)
        act.addWidget(self.chk_cite)
        act.addStretch(1)
        self.btn_history = QPushButton("历史记录")
        self.btn_history.setToolTip("查看过去的问答，可载入继续追问")
        self.btn_history.clicked.connect(self._on_history)
        act.addWidget(self.btn_history)
        self.btn_clear = QPushButton("清空对话")
        self.btn_clear.clicked.connect(self._on_clear)
        act.addWidget(self.btn_clear)
        rl.addLayout(act)

        inp = QHBoxLayout()
        self.edit_question = QLineEdit()
        self.edit_question.setPlaceholderText("针对勾选的文件提问，回车发送…")
        self.edit_question.returnPressed.connect(self._on_ask)
        self.edit_question.textChanged.connect(self._update_buttons)
        inp.addWidget(self.edit_question, 1)
        self.btn_ask = QPushButton("发送")
        self.btn_ask.setObjectName("primary")
        self.btn_ask.clicked.connect(self._on_ask)
        inp.addWidget(self.btn_ask)
        rl.addLayout(inp)

        self.lbl_status = QLabel("就绪")
        self.lbl_status.setStyleSheet("color:#6E6E73;")
        rl.addWidget(self.lbl_status)
        split.addWidget(right)

        # 左窄右宽
        split.setSizes([380, 760])

    def _build_import_page(self) -> QWidget:
        page = QWidget()
        pl = QVBoxLayout(page)
        pl.setContentsMargins(4, 4, 4, 4)
        bar = QHBoxLayout()
        self.btn_select_all = QPushButton("全选")
        self.btn_select_all.clicked.connect(lambda: self.table.set_checked(None, True))
        self.btn_select_none = QPushButton("全不选")
        self.btn_select_none.clicked.connect(lambda: self.table.set_checked(None, False))
        bar.addWidget(self.btn_select_all)
        bar.addWidget(self.btn_select_none)
        bar.addStretch(1)
        self.lbl_count_import = QLabel("已选 0 个")
        bar.addWidget(self.lbl_count_import)
        pl.addLayout(bar)

        self.table = FileTable(self._store)
        self.table.check_changed.connect(self._on_check_changed)
        pl.addWidget(self.table)
        return page

    def _build_library_page(self) -> QWidget:
        page = QWidget()
        pl = QVBoxLayout(page)
        pl.setContentsMargins(4, 4, 4, 4)
        bar = QHBoxLayout()
        self.btn_lib_refresh = QPushButton("刷新")
        self.btn_lib_refresh.setToolTip("重新扫描文件库（含子文件夹）")
        self.btn_lib_refresh.clicked.connect(self._on_lib_refresh)
        bar.addWidget(self.btn_lib_refresh)
        self.btn_lib_all = QPushButton("全选")
        self.btn_lib_all.clicked.connect(lambda: self.lib_table.set_checked_all(True))
        bar.addWidget(self.btn_lib_all)
        self.btn_lib_none = QPushButton("全不选")
        self.btn_lib_none.clicked.connect(lambda: self.lib_table.set_checked_all(False))
        bar.addWidget(self.btn_lib_none)
        bar.addStretch(1)
        self.lbl_count_lib = QLabel("已选 0 个")
        bar.addWidget(self.lbl_count_lib)
        pl.addLayout(bar)

        get_root = (lambda: self._get_archive().root()) if self._get_archive else (lambda: "")
        self.lib_table = LibraryTable(get_root)
        self.lib_table.check_changed.connect(self._on_check_changed)
        pl.addWidget(self.lib_table)
        return page

    # ---- 工具 ----------------------------------------------------------
    def _is_busy(self) -> bool:
        return self._worker is not None and self._worker.isRunning()

    def _active_source(self) -> int:
        return self.source_tabs.currentIndex()

    def _on_source_changed(self, _index: int) -> None:
        # 首次切到文件库页签时自动扫描
        if self._active_source() == SOURCE_LIBRARY and self.lib_table.rowCount() == 0:
            self._on_lib_refresh()
        self._update_buttons()

    def _on_lib_refresh(self) -> None:
        if not self._get_archive:
            return
        self.lib_table.refresh()
        n = self.lib_table.rowCount()
        self.lbl_status.setText(f"文件库扫描完成，共 {n} 个文件")

    def _on_check_changed(self) -> None:
        self.lbl_count_import.setText(f"已选 {len(self.table.checked_paths())} 个")
        self.lbl_count_lib.setText(f"已选 {len(self.lib_table.checked_paths())} 个")
        self._update_buttons()

    def _update_buttons(self) -> None:
        busy = self._is_busy()
        if self._active_source() == SOURCE_LIBRARY:
            checked = len(self.lib_table.checked_paths())
        else:
            checked = len(self.table.checked_paths()) if not self._store.is_empty() else 0
        has_q = bool(self.edit_question.text().strip())
        self.btn_ask.setEnabled(has_q and not busy)
        self.btn_clear.setEnabled(bool(self._history) and not busy)
        self.edit_question.setEnabled(not busy)
        for b in (self.btn_select_all, self.btn_select_none,
                  self.btn_lib_all, self.btn_lib_none, self.btn_lib_refresh):
            b.setEnabled(not busy)

    # ---- 文档收集 ------------------------------------------------------
    def _collect_docs(self) -> tuple[list[tuple[str, str]], list[str], str]:
        """按当前来源收集勾选文件的内容。

        返回 ([(文件名, 文本)], [文件路径], 错误信息)。
        错误信息非空时 docs 里可能仍有部分内容（如跳过不支持的文件后）。
        """
        if self._active_source() == SOURCE_LIBRARY:
            paths = self.lib_table.checked_paths()
            docs: list[tuple[str, str]] = []
            skipped: list[str] = []
            for p in paths:
                name = os.path.basename(p)
                text = self._lib_text(p)
                if text:
                    docs.append((name, text))
                else:
                    skipped.append(name)
            if skipped:
                return docs, paths, "以下文件不支持提取文本，已跳过：\n" + "\n".join(skipped[:10])
            return docs, paths, ""
        # 导入的文件
        paths = self.table.checked_paths()
        items: list[FileItem] = [it for it in (self._store.get(p) for p in paths) if it]
        if not items:
            return [], [], "请先在左侧勾选要提问的文件。"
        docs = []
        for it in items:
            if not it.md_text:
                it.status = "解析中…"
                self.table.set_status(it.path, it.status)
                try:
                    it.md_text = convert_file(it.path)
                except Exception as e:  # noqa: BLE001
                    it.status = f"解析失败: {e}"
                    self.table.set_status(it.path, it.status)
                    return [], [], f"{it.name}: {e}"
                it.status = "已解析"
                self.table.set_status(it.path, it.status)
            docs.append((it.name, it.md_text))
        return docs, paths, ""

    def _lib_text(self, path: str) -> str | None:
        """文件库文件 -> 文本。md/txt 直接读，受支持文档现场解析，带缓存。"""
        ext = os.path.splitext(path)[1].lower()
        try:
            key = (path, os.path.getmtime(path))
        except OSError:
            return None
        if key in self._lib_cache:
            return self._lib_cache[key]
        text: str | None = None
        if ext in _QA_TEXT_EXTS:
            try:
                with open(path, "r", encoding="utf-8", errors="ignore") as f:
                    text = f.read()
            except OSError:
                text = None
        elif ext in SUPPORTED_EXTENSIONS:
            conv = get_converter(path)
            if conv is not None:
                try:
                    text = conv.convert(path)
                except Exception:  # noqa: BLE001
                    text = None
        self._lib_cache[key] = text
        return text

    # ---- 聊天渲染 ------------------------------------------------------
    @staticmethod
    def _fmt(text: str) -> str:
        return html.escape(text).replace("\n", "<br>")

    def _append_bubble(self, who: str, text: str, color: str) -> None:
        self.chat.append(
            f'<table width="100%" cellspacing="0" cellpadding="0"><tr>'
            f'<td width="{18 if who == "我" else 4}%" bgcolor="#F5F5F7"></td>'
            f'<td bgcolor="{color}" style="padding:6px;">'
            f'<b>{who}：</b>{self._fmt(text)}</td>'
            f'<td width="{4 if who == "我" else 18}%" bgcolor="#F5F5F7"></td>'
            f"</tr></table>"
        )
        self.chat.verticalScrollBar().setValue(self.chat.verticalScrollBar().maximum())

    # ---- 提问 ----------------------------------------------------------
    def _on_ask(self) -> None:
        if self._is_busy():
            return
        question = self.edit_question.text().strip()
        if not question:
            return

        cfg = self._get_config()
        if not cfg.llm.api_key:
            ret = QMessageBox.question(
                self, "尚未配置 API Key",
                "还没有配置大模型接口密钥。\n\n现在去设置吗？",
            )
            if ret == QMessageBox.StandardButton.Yes:
                self.request_settings.emit()
            return

        docs, doc_paths, err = self._collect_docs()
        if err:
            QMessageBox.warning(self, "无法开始" if not docs else "部分文件已跳过", err)
            if not docs:
                return
        if not docs:
            return
        # 会话信息（用于持久化历史）
        self._session_files = [
            {"name": name, "path": path}
            for (name, _text), path in zip(docs, doc_paths)
        ]

        self._append_bubble("我", question, _BUBBLE_USER)
        self._history.append({"role": "user", "content": question})
        self.edit_question.clear()
        self._append_bubble("AI", "正在阅读文档并思考…", _BUBBLE_AI)

        self._update_buttons()
        cite = self.chk_cite.isChecked()

        self._worker = Worker(self._do_ask, docs, question, list(self._history), cfg.llm, cite)
        self._worker.progress.connect(lambda _p: None)
        self._worker.finished_ok.connect(self._on_answer)
        self._worker.failed.connect(self._on_failed)
        self._worker.finished.connect(self._update_buttons)
        self._worker.start()

    @staticmethod
    def _do_ask(docs, question, history, llm_cfg, cite, progress):
        engine = QAEngine(llm_cfg)
        q = question + ("\n\n（回答时请注明信息来自哪个文档。）" if cite else "")
        return engine.ask(q, docs, history[:-1])  # 最后一条是本次问题，由引擎追加

    def _on_answer(self, answer: str) -> None:
        # 去掉"正在思考"占位：整页按历史重绘
        self._redraw_history()
        self._history.append({"role": "assistant", "content": answer})
        self._append_bubble("AI", answer, _BUBBLE_AI)
        self.lbl_status.setText(f"回答完成（{len(answer)} 字符）")
        self._save_session()

    # ---- 会话持久化 ----------------------------------------------------
    def _save_session(self) -> None:
        """把当前对话存入历史（每轮回答后更新，退出软件也保留）。"""
        if not self._history:
            return
        if not self._session_id:
            self._session_id = new_id()
            self._session_time = now_text()
        first_q = next((h["content"] for h in self._history if h["role"] == "user"), "问答")
        self._history_store.upsert_qa({
            "id": self._session_id,
            "time": self._session_time,
            "title": first_q[:40],
            "files": self._session_files,
            "turns": list(self._history),
        })

    def _on_history(self) -> None:
        from .history_dialog import HistoryDialog

        dlg = HistoryDialog("qa", self._history_store, self)
        dlg.exec()
        if dlg.loaded_record:
            self._load_session(dlg.loaded_record)

    def _load_session(self, rec: dict) -> None:
        """载入一段历史对话，可直接继续追问。"""
        self._history = [dict(t) for t in rec.get("turns", [])]
        self._session_id = rec.get("id")
        self._session_time = rec.get("time", "")
        self._session_files = rec.get("files", [])
        self._redraw_history()
        # 尽力恢复勾选：导入的文件还能找到就勾导入列表，否则勾文件库
        paths = [f.get("path", "") for f in self._session_files if f.get("path")]
        existing = [p for p in paths if os.path.isfile(p)]
        in_store = [p for p in existing if self._store.get(p)]
        if in_store:
            self.source_tabs.setCurrentIndex(SOURCE_IMPORT)
            self.table.set_checked(None, False)
            self.table.set_checked(in_store, True)
        elif existing:
            self.source_tabs.setCurrentIndex(SOURCE_LIBRARY)
            self.lib_table.refresh()
            self.lib_table.set_checked_paths(existing)
        self.lbl_status.setText(
            f"已载入 {rec.get('time', '')} 的历史对话（{len(self._history)} 条消息），可继续追问"
        )

    def _redraw_history(self) -> None:
        self.chat.clear()
        for h in self._history:
            if h["role"] == "user":
                self._append_bubble("我", h["content"], _BUBBLE_USER)
            else:
                self._append_bubble("AI", h["content"], _BUBBLE_AI)

    def _on_failed(self, err: str) -> None:
        self._redraw_history()
        self._history.append({"role": "assistant", "content": f"（出错了：{err}）"})
        self._append_bubble("AI", f"出错了：{err}\n\n请检查接口配置与网络后重试。", _BUBBLE_AI)
        self.lbl_status.setText("提问失败")

    def _on_clear(self) -> None:
        # 当前会话已保存在历史里，清空后开启新会话
        self._session_id = None
        self._session_time = ""
        self._session_files = []
        self._history.clear()
        self.chat.clear()
        self.chat.setPlaceholderText("还没有对话。勾选文件后输入第一个问题吧。")
        self.lbl_status.setText("对话已清空")
        self._update_buttons()