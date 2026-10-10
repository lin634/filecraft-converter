"""功能1：导入文件并转换为 Markdown。"""
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
    QLineEdit,
    QMessageBox,
    QProgressBar,
    QPushButton,
    QVBoxLayout,
    QWidget,
)

from core.registry import SUPPORTED_EXTENSIONS, convert_file

from .file_store import FileItem, FileStore
from .file_table import FileTable
from .worker import Worker

FILE_FILTER = (
    "支持的文档 (*.docx *.pptx *.xlsx *.pdf);;"
    "Word (*.docx);;PowerPoint (*.pptx);;Excel (*.xlsx);;PDF (*.pdf);;所有文件 (*)"
)


def _unique_path(path: str) -> str:
    """若目标已存在，追加 _1、_2 … 避免覆盖。"""
    if not os.path.exists(path):
        return path
    stem, ext = os.path.splitext(path)
    i = 1
    while True:
        cand = f"{stem}_{i}{ext}"
        if not os.path.exists(cand):
            return cand
        i += 1


class ConvertTab(QWidget):
    """转 Markdown 标签页。"""

    request_settings = pyqtSignal()

    def __init__(self, store: FileStore, get_config, get_archive=None, parent=None):
        super().__init__(parent)
        self._store = store
        self._get_config = get_config
        self._get_archive = get_archive
        self._worker: Worker | None = None

        self._build_ui()
        self.refresh_folder_combo()
        self._update_buttons()

    # ---- 界面 ----------------------------------------------------------
    def _build_ui(self) -> None:
        root = QVBoxLayout(self)

        # 顶部说明
        tip = QLabel(
            "支持格式：" + "、".join(SUPPORTED_EXTENSIONS) +
            "。注意：旧版 .doc/.ppt/.xls 与扫描件 PDF 不支持，请先另存为新格式。"
        )
        tip.setWordWrap(True)
        tip.setStyleSheet("color:#6E6E73; padding:2px;")
        root.addWidget(tip)

        # 文件区
        file_box = QGroupBox("待转换文件")
        fl = QVBoxLayout(file_box)

        bar = QHBoxLayout()
        self.btn_import = QPushButton("导入文件…")
        self.btn_import.clicked.connect(self._on_import)
        self.btn_select_all = QPushButton("全选")
        self.btn_select_all.clicked.connect(lambda: self.table.set_checked(None, True))
        self.btn_select_none = QPushButton("全不选")
        self.btn_select_none.clicked.connect(lambda: self.table.set_checked(None, False))
        self.btn_remove = QPushButton("移除选中")
        self.btn_remove.clicked.connect(self._on_remove)
        self.btn_clear = QPushButton("清空列表")
        self.btn_clear.clicked.connect(self._store.clear)
        for b in (self.btn_import, self.btn_select_all, self.btn_select_none,
                  self.btn_remove, self.btn_clear):
            bar.addWidget(b)
        bar.addStretch(1)
        # 归档目标文件夹（与文件库联动）
        bar.addWidget(QLabel("归档到："))
        self.combo_folder = QComboBox()
        self.combo_folder.setToolTip("导入的文件会自动复制一份到文件库的这个文件夹")
        self.combo_folder.setMinimumWidth(120)
        self.combo_folder.currentIndexChanged.connect(self._on_folder_combo)
        bar.addWidget(self.combo_folder)
        fl.addLayout(bar)

        self.table = FileTable(self._store)
        self.table.check_changed.connect(self._update_buttons)
        fl.addWidget(self.table)
        root.addWidget(file_box, 1)

        # 输出设置
        out_box = QGroupBox("输出设置")
        ol = QHBoxLayout(out_box)
        ol.addWidget(QLabel("输出目录："))
        self.edit_outdir = QLineEdit()
        self.edit_outdir.setPlaceholderText("留空 = 与源文件同目录")
        ol.addWidget(self.edit_outdir, 1)
        self.btn_pick_outdir = QPushButton("选择…")
        self.btn_pick_outdir.clicked.connect(self._on_pick_outdir)
        ol.addWidget(self.btn_pick_outdir)
        self.btn_clear_outdir = QPushButton("清除")
        self.btn_clear_outdir.clicked.connect(lambda: self.edit_outdir.clear())
        ol.addWidget(self.btn_clear_outdir)
        ol.addWidget(QLabel("命名："))
        self.combo_naming = QComboBox()
        self.combo_naming.addItems(["与源文件同名", "加 _md 后缀"])
        ol.addWidget(self.combo_naming)
        root.addWidget(out_box)

        # 操作区
        act = QHBoxLayout()
        self.btn_convert = QPushButton("开始转换")
        self.btn_convert.setObjectName("primary")
        self.btn_convert.setMinimumHeight(34)
        self.btn_convert.clicked.connect(self._on_convert)
        act.addWidget(self.btn_convert)

        self.btn_open_out = QPushButton("打开输出位置")
        self.btn_open_out.clicked.connect(self._on_open_output)
        act.addWidget(self.btn_open_out)

        self.btn_open_md = QPushButton("打开选中的 .md")
        self.btn_open_md.clicked.connect(self._on_open_md)
        act.addWidget(self.btn_open_md)
        act.addStretch(1)
        root.addLayout(act)

        self.progress = QProgressBar()
        self.progress.setValue(0)
        root.addWidget(self.progress)

        self.lbl_status = QLabel("就绪")
        self.lbl_status.setStyleSheet("color:#6E6E73;")
        root.addWidget(self.lbl_status)

    # ---- 工具 ----------------------------------------------------------
    def _update_buttons(self) -> None:
        has = not self._store.is_empty()
        checked = len(self.table.checked_paths()) if has else 0
        busy = self._worker is not None and self._worker.isRunning()
        self.btn_convert.setEnabled(has and checked > 0 and not busy)
        self.btn_convert.setText(
            f"开始转换（已选 {checked}）" if checked else "开始转换"
        )
        for b in (self.btn_import, self.btn_remove, self.btn_clear,
                  self.btn_select_all, self.btn_select_none, self.btn_open_out):
            b.setEnabled(not busy)

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

    # ---- 槽函数 --------------------------------------------------------
    def _on_import(self) -> None:
        paths, _ = QFileDialog.getOpenFileNames(self, "选择要导入的文档", "", FILE_FILTER)
        if not paths:
            return
        added, rejected = self._store.add_paths(paths)
        if rejected:
            QMessageBox.warning(
                self,
                "部分文件被跳过",
                "以下文件格式不受支持，已跳过：\n\n" + "\n".join(rejected[:20]) +
                ("\n…" if len(rejected) > 20 else "") +
                "\n\n请用 Office 另存为 .docx/.pptx/.xlsx，或转换为文本型 PDF。",
            )
        self.lbl_status.setText(f"已导入 {added} 个文件（跳过 {len(rejected)} 个）")

    def _on_remove(self) -> None:
        paths = self.table.selected_paths()
        if not paths:
            QMessageBox.information(self, "提示", "请先在列表中选中要移除的行。")
            return
        self._store.remove(paths)

    def _on_pick_outdir(self) -> None:
        d = QFileDialog.getExistingDirectory(self, "选择输出目录", self.edit_outdir.text() or "")
        if d:
            self.edit_outdir.setText(d)

    def _on_open_output(self) -> None:
        paths = self.table.checked_paths() or self.table.selected_paths()
        target = ""
        for p in paths:
            it = self._store.get(p)
            if it and it.output_path:
                target = os.path.dirname(it.output_path)
                break
        if not target:
            target = self.edit_outdir.text().strip()
        if not target and paths:
            target = os.path.dirname(paths[0])
        if not target or not os.path.isdir(target):
            QMessageBox.information(self, "提示", "暂无可打开的输出目录，请先完成转换或指定目录。")
            return
        QDesktopServices.openUrl(QUrl.fromLocalFile(target))

    def _on_open_md(self) -> None:
        paths = self.table.selected_paths()
        it = self._store.get(paths[0]) if paths else None
        if not it or not it.output_path or not os.path.exists(it.output_path):
            QMessageBox.information(self, "提示", "选中的文件还没有生成 markdown。")
            return
        QDesktopServices.openUrl(QUrl.fromLocalFile(it.output_path))

    def _on_convert(self) -> None:
        if self._is_busy():
            return
        paths = self.table.checked_paths()
        items: list[FileItem] = [it for it in (self._store.get(p) for p in paths) if it]
        if not items:
            return

        out_dir = self.edit_outdir.text().strip()
        if out_dir and not os.path.isdir(out_dir):
            try:
                os.makedirs(out_dir, exist_ok=True)
            except OSError as e:
                QMessageBox.critical(self, "错误", f"无法创建输出目录：{e}")
                return

        suffix = "_md" if self.combo_naming.currentIndex() == 1 else ""
        for it in items:
            it.status = "排队中"
        self.table.sync_from_store()

        self.progress.setRange(0, len(items))
        self.progress.setValue(0)
        self.btn_convert.setEnabled(False)

        self._worker = Worker(self._convert_all, items, out_dir, suffix)
        self._worker.progress.connect(self._on_progress)
        self._worker.finished_ok.connect(self._on_done)
        self._worker.failed.connect(self._on_failed)
        self._worker.finished.connect(self._update_buttons)
        self._worker.start()

    # ---- 后台任务 ------------------------------------------------------
    @staticmethod
    def _convert_all(items: list[FileItem], out_dir: str, suffix: str, progress) -> dict:
        if out_dir:
            os.makedirs(out_dir, exist_ok=True)
        done, failed = 0, 0
        errors: list[str] = []
        for it in items:
            progress(("status", it.path, "转换中…"))
            try:
                md = convert_file(it.path)
                if out_dir:
                    base = os.path.splitext(it.name)[0] + suffix + ".md"
                    target = os.path.join(out_dir, base)
                else:
                    target = os.path.splitext(it.path)[0] + suffix + ".md"
                target = _unique_path(target)
                with open(target, "w", encoding="utf-8") as f:
                    f.write(md)
                it.md_text = md
                it.output_path = target
                it.status = "已完成"
                done += 1
                progress(("status", it.path, "已完成"))
            except Exception as e:  # noqa: BLE001
                it.status = f"失败: {e}"
                failed += 1
                errors.append(f"{it.name}: {e}")
                progress(("status", it.path, it.status))
            progress(("tick",))
        return {"done": done, "failed": failed, "errors": errors}

    def _on_progress(self, payload) -> None:
        if isinstance(payload, tuple):
            kind = payload[0]
            if kind == "status":
                _, path, text = payload
                self._store.get(path).status = text if self._store.get(path) else text
                self.table.set_status(path, text)
            elif kind == "tick":
                self.progress.setValue(self.progress.value() + 1)
        elif isinstance(payload, str):
            self.lbl_status.setText(payload)

    def _on_done(self, result: dict) -> None:
        self._update_buttons()
        msg = f"转换完成：成功 {result['done']} 个，失败 {result['failed']} 个。"
        self.lbl_status.setText(msg)
        if result["errors"]:
            QMessageBox.warning(self, "部分文件转换失败", msg + "\n\n" + "\n".join(result["errors"][:15]))
        else:
            QMessageBox.information(self, "完成", msg)

    def _on_failed(self, err: str) -> None:
        self._update_buttons()
        self.lbl_status.setText("任务失败")
        QMessageBox.critical(self, "任务失败", err)