"""功能2：选择若干文件做 AI 总结，并导出为 PDF。"""
from __future__ import annotations

import os

from PyQt6.QtCore import Qt, QUrl, pyqtSignal
from PyQt6.QtGui import QDesktopServices
from PyQt6.QtWidgets import (
    QComboBox,
    QFileDialog,
    QGroupBox,
    QHBoxLayout,
    QLabel,
    QMessageBox,
    QProgressBar,
    QPushButton,
    QSplitter,
    QTabWidget,
    QTextBrowser,
    QTextEdit,
    QVBoxLayout,
    QWidget,
)

from core.history_store import HistoryStore, new_id, now_text
from core.md_to_pdf import markdown_to_pdf
from core.mindmap import markdown_to_mindmap_html
from core.registry import convert_file
from core.summarizer import FileInfo, Summarizer

from .convert_tab import FILE_FILTER
from .file_store import FileItem, FileStore
from .file_table import FileTable
from .worker import Worker


class SummaryTab(QWidget):
    """AI 总结标签页。"""

    request_settings = pyqtSignal()

    def __init__(self, store: FileStore, get_config, get_archive=None, history: HistoryStore | None = None, parent=None):
        super().__init__(parent)
        self._store = store
        self._get_config = get_config
        self._get_archive = get_archive
        self._history_store = history or HistoryStore()
        self._worker: Worker | None = None
        self._last_pdf: str = ""
        #: 本次总结的来源文件所在归档文件夹（用于把总结存到对应位置）
        self._source_folder: str = ""
        #: 最近一次总结的元信息（存历史用）
        self._last_files: list[dict] = []
        self._last_instruction: str = ""

        self._build_ui()
        self.refresh_folder_combo()
        self._update_buttons()

    # ---- 界面 ----------------------------------------------------------
    def _build_ui(self) -> None:
        root = QVBoxLayout(self)

        tip = QLabel(
            "左边勾选要总结的文件并填写额外要求，右边预览总结结果。"
            "若总内容超出单次输入上限，会自动分段总结再合并。"
        )
        tip.setWordWrap(True)
        tip.setStyleSheet("color:#6E6E73; padding:2px;")
        root.addWidget(tip)

        self.main_split = QSplitter(Qt.Orientation.Horizontal)
        root.addWidget(self.main_split, 1)

        # 左：文件选择 + 额外要求（窄）
        left = QWidget()
        ll = QVBoxLayout(left)
        ll.setContentsMargins(0, 0, 0, 0)

        file_box = QGroupBox("参与总结的文件")
        fl = QVBoxLayout(file_box)
        bar = QHBoxLayout()
        self.btn_import = QPushButton("导入文件…")
        self.btn_import.setToolTip("支持 .docx / .pptx / .xlsx / .pdf")
        self.btn_import.clicked.connect(self._on_import)
        self.btn_select_all = QPushButton("全选")
        self.btn_select_all.clicked.connect(lambda: self.table.set_checked(None, True))
        self.btn_select_none = QPushButton("全不选")
        self.btn_select_none.clicked.connect(lambda: self.table.set_checked(None, False))
        bar.addWidget(self.btn_import)
        bar.addWidget(self.btn_select_all)
        bar.addWidget(self.btn_select_none)
        fl.addLayout(bar)

        self.table = FileTable(self._store)
        self.table.check_changed.connect(self._on_check_changed)
        fl.addWidget(self.table)

        bar2 = QHBoxLayout()
        bar2.addWidget(QLabel("归档到："))
        self.combo_folder = QComboBox()
        self.combo_folder.setToolTip("导入的文件会自动复制一份到文件库的这个文件夹")
        self.combo_folder.setMinimumWidth(100)
        self.combo_folder.currentIndexChanged.connect(self._on_folder_combo)
        bar2.addWidget(self.combo_folder, 1)
        self.lbl_count = QLabel("已选 0 个")
        bar2.addWidget(self.lbl_count)
        fl.addLayout(bar2)
        ll.addWidget(file_box)

        instr_box = QGroupBox("额外要求（可选）")
        il = QVBoxLayout(instr_box)
        self.edit_instruction = QTextEdit()
        self.edit_instruction.setPlaceholderText(
            "例如：重点关注财务数据和风险点，用 800 字以内概括，面向管理层汇报。"
        )
        il.addWidget(self.edit_instruction)
        ll.addWidget(instr_box)

        self.main_split.addWidget(left)

        # 右：按钮 + 预览（宽）
        right = QWidget()
        rl = QVBoxLayout(right)
        rl.setContentsMargins(0, 0, 0, 0)

        act = QHBoxLayout()
        self.btn_generate = QPushButton("生成总结")
        self.btn_generate.setObjectName("primary")
        self.btn_generate.setMinimumHeight(34)
        self.btn_generate.clicked.connect(self._on_generate)
        act.addWidget(self.btn_generate)

        self.btn_preview = QPushButton("刷新预览")
        self.btn_preview.clicked.connect(self._refresh_preview)
        act.addWidget(self.btn_preview)

        self.btn_export = QPushButton("导出为 PDF…")
        self.btn_export.clicked.connect(self._on_export)
        act.addWidget(self.btn_export)

        self.btn_save_md = QPushButton("保存 .md")
        self.btn_save_md.clicked.connect(self._on_save_md)
        act.addWidget(self.btn_save_md)

        self.btn_mindmap = QPushButton("思维导图")
        self.btn_mindmap.setToolTip("把当前总结生成为可在浏览器打开的思维导图")
        self.btn_mindmap.clicked.connect(self._on_mindmap)
        act.addWidget(self.btn_mindmap)

        self.btn_open_pdf = QPushButton("打开 PDF")
        self.btn_open_pdf.clicked.connect(self._on_open_pdf)
        act.addWidget(self.btn_open_pdf)

        self.btn_history = QPushButton("历史记录")
        self.btn_history.setToolTip("查看过去的总结，可还原到编辑器")
        self.btn_history.clicked.connect(self._on_history)
        act.addWidget(self.btn_history)
        act.addStretch(1)
        rl.addLayout(act)

        self.progress = QProgressBar()
        self.progress.setRange(0, 0)  # 忙碌态
        self.progress.setVisible(False)
        rl.addWidget(self.progress)

        self.lbl_status = QLabel("就绪")
        self.lbl_status.setStyleSheet("color:#6E6E73;")
        rl.addWidget(self.lbl_status)

        self.result_tabs = QTabWidget()
        self.preview = QTextBrowser()
        self.preview.setOpenExternalLinks(True)
        self.result_tabs.addTab(self.preview, "预览")
        self.editor = QTextEdit()
        self.editor.setPlaceholderText("生成的总结会显示在这里，可直接修改后再导出 PDF。")
        self.editor.setAcceptRichText(False)
        self.editor.textChanged.connect(self._on_editor_changed)
        self.result_tabs.addTab(self.editor, "编辑 Markdown")
        self.result_tabs.currentChanged.connect(self._on_result_tab_changed)
        rl.addWidget(self.result_tabs, 1)
        self.main_split.addWidget(right)

        # 左窄右宽
        self.main_split.setSizes([400, 760])

    # ---- 工具 ----------------------------------------------------------
    def _is_busy(self) -> bool:
        return self._worker is not None and self._worker.isRunning()

    # ---- 归档目标文件夹 ------------------------------------------------
    def refresh_folder_combo(self) -> None:
        """同步「归档到」下拉框与文件库当前选中的文件夹。"""
        if not self._get_archive:
            return
        mgr = self._get_archive()
        if not mgr:
            return
        current = mgr.active_folder()
        self.combo_folder.blockSignals(True)
        self.combo_folder.clear()
        self.combo_folder.addItem("根目录", "")
        for name in mgr.folders():
            self.combo_folder.addItem(name, name)
        idx = self.combo_folder.findData(current)
        if idx >= 0:
            self.combo_folder.setCurrentIndex(idx)
        self.combo_folder.blockSignals(False)

    def _on_folder_combo(self, index: int) -> None:
        if not self._get_archive or index < 0:
            return
        rel = self.combo_folder.itemData(index) or ""
        self._get_archive().set_active_folder(rel)

    def _on_check_changed(self) -> None:
        n = len(self.table.checked_paths()) if not self._store.is_empty() else 0
        self.lbl_count.setText(f"已选 {n} 个")
        self._update_buttons()

    # ---- 导入文件 ------------------------------------------------------
    def _on_import(self) -> None:
        if self._is_busy():
            return
        paths, _ = QFileDialog.getOpenFileNames(self, "选择要总结的文档", "", FILE_FILTER)
        if not paths:
            return
        added, rejected = self._store.add_paths(paths)
        if rejected:
            QMessageBox.warning(
                self,
                "部分文件被跳过",
                "以下文件格式不受支持，已跳过：\n\n" + "\n".join(rejected[:20])
                + ("\n…" if len(rejected) > 20 else "")
                + "\n\n请用 Office 另存为 .docx/.pptx/.xlsx，或转换为文本型 PDF。",
            )
        self.lbl_status.setText(f"已导入 {added} 个文件（跳过 {len(rejected)} 个）")

    def _update_buttons(self) -> None:
        busy = self._is_busy()
        checked = len(self.table.checked_paths()) if not self._store.is_empty() else 0
        self.btn_generate.setEnabled(checked > 0 and not busy)
        self.btn_generate.setText(f"生成总结（已选 {checked}）" if checked else "生成总结")
        has_text = bool(self.editor.toPlainText().strip())
        self.btn_export.setEnabled(has_text and not busy)
        self.btn_save_md.setEnabled(has_text and not busy)
        self.btn_mindmap.setEnabled(has_text and not busy)
        self.btn_preview.setEnabled(has_text)
        self.btn_open_pdf.setEnabled(bool(self._last_pdf) and not busy)
        self.btn_import.setEnabled(not busy)
        for b in (self.btn_select_all, self.btn_select_none):
            b.setEnabled(not busy)

    def _on_editor_changed(self) -> None:
        self._update_buttons()

    def _refresh_preview(self) -> None:
        self.preview.setMarkdown(self.editor.toPlainText())

    def _on_result_tab_changed(self, index: int) -> None:
        # 切到「预览」页签时自动用当前编辑内容刷新
        if self.result_tabs.tabText(index) == "预览":
            self._refresh_preview()

    # ---- 生成总结 ------------------------------------------------------
    def _on_generate(self) -> None:
        if self._is_busy():
            return
        paths = self.table.checked_paths()
        items: list[FileItem] = [it for it in (self._store.get(p) for p in paths) if it]
        if not items:
            return

        # 总结产物跟随来源文件：取第一个有归档文件夹的来源
        self._source_folder = next(
            (it.folder for it in items if it.folder), ""
        )

        cfg = self._get_config()
        if not cfg.llm.api_key:
            ret = QMessageBox.question(
                self,
                "尚未配置 API Key",
                "还没有配置大模型接口密钥，无法生成总结。\n\n现在去设置吗？",
            )
            if ret == QMessageBox.StandardButton.Yes:
                self.request_settings.emit()
            return

        instruction = self.edit_instruction.toPlainText().strip()
        self._last_files = [{"name": it.name, "path": it.path} for it in items]
        self._last_instruction = instruction
        for it in items:
            it.status = "待解析"
        self.table.sync_from_store()

        self.progress.setVisible(True)
        self.lbl_status.setText("正在准备…")
        self.btn_generate.setEnabled(False)

        self._worker = Worker(self._summarize_all, items, cfg.llm, instruction)
        self._worker.progress.connect(self._on_progress)
        self._worker.finished_ok.connect(self._on_done)
        self._worker.failed.connect(self._on_failed)
        self._worker.finished.connect(self._on_worker_finished)
        self._worker.start()

    @staticmethod
    def _summarize_all(items: list[FileItem], llm_cfg, instruction: str, progress) -> str:
        files: list[FileInfo] = []
        for it in items:
            if not it.md_text:
                progress(("status", it.path, "解析中…"))
                it.md_text = convert_file(it.path)
            it.status = "已解析"
            progress(("status", it.path, "已解析"))
            files.append(FileInfo(name=it.name, markdown=it.md_text))

        s = Summarizer(llm_cfg)
        if instruction:
            s.SYSTEM_PROMPT = s.SYSTEM_PROMPT + f"\n\n用户额外要求：{instruction}"
        return s.summarize(files, progress=lambda msg: progress(("msg", msg)))

    def _on_progress(self, payload) -> None:
        if isinstance(payload, tuple):
            kind = payload[0]
            if kind == "status":
                _, path, text = payload
                it = self._store.get(path)
                if it:
                    it.status = text
                self.table.set_status(path, text)
            elif kind == "msg":
                self.lbl_status.setText(payload[1])
        elif isinstance(payload, str):
            self.lbl_status.setText(payload)

    def _on_done(self, result: str) -> None:
        self.editor.setPlainText(result)
        self._refresh_preview()
        self.result_tabs.setCurrentIndex(0)
        self.lbl_status.setText(f"总结完成，共 {len(result)} 字符。可编辑后导出 PDF。")
        # 存入历史
        first_line = next((ln.strip() for ln in result.splitlines() if ln.strip()), "总结")
        self._history_store.upsert_summary({
            "id": new_id(),
            "time": now_text(),
            "title": first_line.lstrip("# ").strip()[:40] or "总结",
            "files": self._last_files,
            "instruction": self._last_instruction,
            "content": result,
        })

    def _on_history(self) -> None:
        from .history_dialog import HistoryDialog

        dlg = HistoryDialog("summary", self._history_store, self)
        dlg.exec()
        if dlg.loaded_record:
            self.editor.setPlainText(dlg.loaded_record.get("content", ""))
            self.result_tabs.setCurrentIndex(0)
            self._refresh_preview()
            files = [f.get("name", "") for f in dlg.loaded_record.get("files", [])]
            self.lbl_status.setText(
                f"已还原 {dlg.loaded_record.get('time', '')} 的总结"
                + (f"（来源文件：{'、'.join(files[:3])}{'…' if len(files) > 3 else ''}）" if files else "")
            )

    def _on_failed(self, err: str) -> None:
        self.lbl_status.setText("生成失败")
        QMessageBox.critical(
            self,
            "生成失败",
            err + "\n\n请检查：API Key 是否正确、Base URL 是否可达、模型名称是否存在。",
        )

    def _on_worker_finished(self) -> None:
        self.progress.setVisible(False)
        self._update_buttons()

    # ---- 思维导图 ------------------------------------------------------
    def _on_mindmap(self) -> None:
        text = self.editor.toPlainText().strip()
        if not text:
            QMessageBox.information(self, "提示", "还没有总结内容。")
            return
        default = os.path.join(os.path.expanduser("~"), "总结思维导图.html")
        path, _ = QFileDialog.getSaveFileName(self, "生成思维导图", default, "HTML (*.html)")
        if not path:
            return
        if not path.lower().endswith(".html"):
            path += ".html"
        try:
            markdown_to_mindmap_html(text, path, title="文档总结")
        except Exception as e:  # noqa: BLE001
            QMessageBox.critical(self, "生成失败", str(e))
            return
        self.lbl_status.setText(f"已生成思维导图：{path}")
        QDesktopServices.openUrl(QUrl.fromLocalFile(path))

    # ---- 导出 ----------------------------------------------------------
    def _archive_output(self, path: str) -> None:
        """把生成的总结产物记入历史，并归档到来源文件夹的「总结」子夹。"""
        if not self._get_archive:
            return
        mgr = self._get_archive()
        if not mgr:
            return
        archived, skipped, errors = mgr.archive_summary(path, self._source_folder)
        if archived:
            where = f"「{self._source_folder} / 总结」" if self._source_folder else "「根目录 / 总结」"
            self.lbl_status.setText(f"已存入文件库 {where}")
        if errors:
            QMessageBox.warning(self, "归档失败", "\n".join(errors[:10]))

    def _on_save_md(self) -> None:
        text = self.editor.toPlainText().strip()
        if not text:
            return
        path, _ = QFileDialog.getSaveFileName(self, "保存 Markdown", "总结.md", "Markdown (*.md)")
        if not path:
            return
        try:
            with open(path, "w", encoding="utf-8") as f:
                f.write(text)
        except OSError as e:
            QMessageBox.critical(self, "错误", f"保存失败：{e}")
            return
        self.lbl_status.setText(f"已保存：{path}")
        self._archive_output(path)

    def _on_export(self) -> None:
        text = self.editor.toPlainText().strip()
        if not text:
            QMessageBox.information(self, "提示", "还没有总结内容。")
            return
        default = os.path.join(os.path.expanduser("~"), "文档总结.pdf")
        path, _ = QFileDialog.getSaveFileName(self, "导出 PDF", default, "PDF (*.pdf)")
        if not path:
            return
        if not path.lower().endswith(".pdf"):
            path += ".pdf"
        try:
            markdown_to_pdf(text, path, title="文档总结")
        except Exception as e:  # noqa: BLE001
            QMessageBox.critical(self, "导出失败", str(e))
            return
        self._last_pdf = path
        self.lbl_status.setText(f"已导出 PDF：{path}")
        self._update_buttons()
        self._archive_output(path)
        ret = QMessageBox.question(self, "导出成功", f"已生成：\n{path}\n\n现在打开吗？")
        if ret == QMessageBox.StandardButton.Yes:
            QDesktopServices.openUrl(QUrl.fromLocalFile(path))

    def _on_open_pdf(self) -> None:
        if self._last_pdf and os.path.exists(self._last_pdf):
            QDesktopServices.openUrl(QUrl.fromLocalFile(self._last_pdf))