"""主窗口：两个标签页（转 Markdown / AI 总结）共享同一份文件列表。"""
from __future__ import annotations

import os

from PyQt6.QtCore import Qt
from PyQt6.QtGui import QAction, QKeySequence
from PyQt6.QtWidgets import (
    QFileDialog,
    QLabel,
    QMainWindow,
    QMessageBox,
    QStatusBar,
    QTabWidget,
    QWidget,
)

from config import AppConfig, load_config, save_config
from core.history_store import HistoryStore
from version import APP_AUTHOR, APP_VERSION, about_text, window_title
from core.archive import ArchiveManager

from .archive_tab import ArchiveTab
from .convert_tab import FILE_FILTER, ConvertTab
from .file_store import FileStore
from .qa_tab import QATab
from .settings_dialog import SettingsDialog
from .summary_tab import SummaryTab


class MainWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle(window_title())
        self.resize(1180, 820)
        self.setAcceptDrops(True)

        self.cfg: AppConfig = load_config()
        self.store = FileStore()
        self.archive = ArchiveManager(lambda: self.cfg)
        self.history = HistoryStore()
        # 导入的文件自动归档到文件库的「导入文件」目录
        self.store.files_added.connect(self._on_files_added)

        self._build_menu()
        self._build_body()

        self.store.files_changed.connect(self._update_status)

    def _on_files_added(self, paths: list) -> None:
        """导入的文件自动复制一份到当前归档文件夹（可关）。"""
        folder = self.cfg.archive.active_folder
        for p in paths:
            it = self.store.get(p)
            if it:
                it.folder = folder
        archived, skipped, errors = self.archive.archive_imports(paths, folder)
        if archived:
            where = folder or "根目录"
            self.statusBar().showMessage(
                f"已归档 {archived} 个文件到「{where}」"
                + (f"（跳过重复 {skipped} 个）" if skipped else ""),
                6000,
            )
        if errors:
            QMessageBox.warning(
                self, "自动归档失败",
                "以下文件未能存入文件库：\n\n" + "\n".join(errors[:10]),
            )

    # ---- 菜单 ----------------------------------------------------------
    def _build_menu(self) -> None:
        m_file = self.menuBar().addMenu("文件(&F)")

        act_import = QAction("导入文件…", self)
        act_import.setShortcut(QKeySequence.StandardKey.Open)
        act_import.triggered.connect(self._on_import)
        m_file.addAction(act_import)

        act_clear = QAction("清空文件列表", self)
        act_clear.triggered.connect(self.store.clear)
        m_file.addAction(act_clear)

        m_file.addSeparator()
        act_quit = QAction("退出", self)
        act_quit.setShortcut(QKeySequence.StandardKey.Quit)
        act_quit.triggered.connect(self.close)
        m_file.addAction(act_quit)

        m_tool = self.menuBar().addMenu("工具(&T)")
        act_settings = QAction("设置…", self)
        act_settings.triggered.connect(self._open_settings)
        m_tool.addAction(act_settings)

        m_help = self.menuBar().addMenu("帮助(&H)")
        act_about = QAction("关于 / 使用说明", self)
        act_about.triggered.connect(self._show_about)
        m_help.addAction(act_about)

    # ---- 主体 ----------------------------------------------------------
    def _build_body(self) -> None:
        self.tabs = QTabWidget()
        self.convert_tab = ConvertTab(self.store, lambda: self.cfg, lambda: self.archive)
        self.summary_tab = SummaryTab(self.store, lambda: self.cfg, lambda: self.archive, self.history)
        self.archive_tab = ArchiveTab(self.store, lambda: self.cfg, lambda: self.archive)
        self.qa_tab = QATab(self.store, lambda: self.cfg, lambda: self.archive, self.history)
        self.convert_tab.request_settings.connect(self._open_settings)
        self.summary_tab.request_settings.connect(self._open_settings)
        self.qa_tab.request_settings.connect(self._open_settings)

        self.tabs.addTab(self.summary_tab, "① AI 总结并导出 PDF")
        self.tabs.addTab(self.convert_tab, "② 转 Markdown")
        self.tabs.addTab(self.archive_tab, "③ 文件库")
        self.tabs.addTab(self.qa_tab, "④ 文档问答")
        self.tabs.currentChanged.connect(self._on_tab_changed)
        self.setCentralWidget(self.tabs)

        bar = QStatusBar()
        self.lbl_store = QLabel()
        bar.addWidget(self.lbl_store)
        bar.addPermanentWidget(QLabel(f"接口：{self.cfg.llm.model or '未配置'}"))
        bar.addPermanentWidget(QLabel(f"v{APP_VERSION} · {APP_AUTHOR}"))
        self.setStatusBar(bar)
        self._update_status()

    def _on_tab_changed(self, _index: int) -> None:
        """切到文件库时刷新视图；其它页刷新归档目标下拉框。"""
        w = self.tabs.currentWidget()
        if w is self.archive_tab:
            self.archive_tab.refresh_all()
        else:
            self.summary_tab.refresh_folder_combo()
            self.convert_tab.refresh_folder_combo()

    def _update_status(self) -> None:
        n = len(self.store)
        self.lbl_store.setText(f"已导入 {n} 个文件" if n else "尚未导入文件（可拖拽文件到窗口）")

    # ---- 拖拽导入 ------------------------------------------------------
    def dragEnterEvent(self, event) -> None:  # noqa: N802
        if event.mimeData().hasUrls():
            event.acceptProposedAction()

    def dropEvent(self, event) -> None:  # noqa: N802
        paths = [u.toLocalFile() for u in event.mimeData().urls() if u.isLocalFile()]
        # 支持拖入文件夹
        expanded: list[str] = []
        for p in paths:
            if os.path.isdir(p):
                for root, _dirs, names in os.walk(p):
                    expanded.extend(os.path.join(root, n) for n in names)
            else:
                expanded.append(p)
        if not expanded:
            return
        added, rejected = self.store.add_paths(expanded)
        if rejected:
            QMessageBox.warning(
                self,
                "部分文件被跳过",
                f"已导入 {added} 个，跳过 {len(rejected)} 个不支持的格式：\n\n"
                + "\n".join(rejected[:15])
                + ("\n…" if len(rejected) > 15 else ""),
            )
        event.acceptProposedAction()

    # ---- 动作 ----------------------------------------------------------
    def _on_import(self) -> None:
        # 两个标签页共享同一份文件列表，在当前页导入即可，不必跳转
        self.convert_tab._on_import()

    def _open_settings(self) -> None:
        dlg = SettingsDialog(self.cfg, self)
        if dlg.exec():
            save_config(self.cfg)
            self.statusBar().clearMessage()
            self.statusBar().addPermanentWidget(QLabel(f"接口：{self.cfg.llm.model or '未配置'}"))
            self.statusBar().showMessage("设置已保存", 4000)

    def _show_about(self) -> None:
        QMessageBox.information(
            self,
            "关于 FileCraft",
            about_text()
            + "本地文档转 Markdown + AI 总结<br><br>"
            "<b>支持格式</b>：.docx / .pptx / .xlsx / .pdf<br>"
            "<b>不支持</b>：旧版 .doc/.ppt/.xls（请用 Office 另存为新格式）、扫描件 PDF（无 OCR）<br><br>"
            "<b>使用流程</b><br>"
            "1. 「导入文件」或直接拖拽文件/文件夹进窗口<br>"
            "2. 在「① AI 总结并导出 PDF」勾选文件生成总结，可编辑后导出 PDF<br>"
            "3. 需要转格式时切到「② 转 Markdown」勾选文件转换<br>"
            "4. 「③ 文件库」按文件夹分类存放文件，支持全文搜索与思维导图<br>"
            "5. 在「④ 文档问答」左侧勾选文件，右侧多轮提问<br><br>"
            "接口已内置 ModelScope 配置，无需设置即可使用；"
            "如需更换可在「工具 → 设置」修改。",
        )