"""③ 文件库：可视化文件夹管理、全文搜索，分类存放导入文件与总结产物。

结构：根目录下的每个文件夹存放导入的源文件，其「总结」子夹存放
由该文件夹内文件生成的总结。文件夹可新建/删除，选择即切换视图。
支持按文件名与文件内容搜索（docx/pptx/xlsx/pdf 会现场解析）。
"""
from __future__ import annotations

import datetime
import os
from typing import Callable

from PyQt6.QtCore import Qt, QUrl
from PyQt6.QtGui import QDesktopServices
from PyQt6.QtWidgets import (
    QAbstractItemView,
    QCheckBox,
    QFileDialog,
    QHBoxLayout,
    QHeaderView,
    QInputDialog,
    QLabel,
    QLineEdit,
    QMessageBox,
    QPushButton,
    QSplitter,
    QStyle,
    QTableWidget,
    QTableWidgetItem,
    QTreeWidget,
    QTreeWidgetItem,
    QVBoxLayout,
    QWidget,
)

from config import AppConfig, save_config

from core.archive import ArchiveManager, SUMMARY_SUBDIR
from core.mindmap import markdown_to_mindmap_html
from core.registry import SUPPORTED_EXTENSIONS

from .file_store import FileStore
from .worker import Worker

ROOT_REL = ""  # 树节点中代表根目录的相对路径

#: 搜索结果上限
SEARCH_LIMIT = 300

#: 全文搜索时会读取文本内容的扩展名
_TEXT_EXTS = (".md", ".txt")

#: 超过此大小（字节）的文件跳过内容搜索（只搜文件名）
_SEARCH_MAX_BYTES = 30 * 1024 * 1024

#: 搜索时 PDF 最多解析前 N 页（避免大文件拖垮搜索）
_SEARCH_PDF_MAX_PAGES = 50


class ArchiveTab(QWidget):
    """文件库标签页。"""

    def __init__(
        self,
        store: FileStore,
        get_config: Callable[[], AppConfig],
        get_archive: Callable[[], ArchiveManager],
        parent=None,
    ):
        super().__init__(parent)
        self._store = store
        self._get_config = get_config
        self._get_archive = get_archive
        self._rel = ROOT_REL  # 当前在树中选中的文件夹（用于右侧文件视图）
        self._in_search = False  # 右侧表格当前是否显示搜索结果
        self._search_worker: Worker | None = None
        self._md_worker: Worker | None = None

        self._build_ui()
        store.files_added.connect(self._on_files_added)
        self.table.itemSelectionChanged.connect(self._update_mindmap_button)
        self.refresh_all()

    # ---- 工具 ----------------------------------------------------------
    def _mgr(self) -> ArchiveManager:
        return self._get_archive()

    def _dir_icon(self):
        return self.style().standardIcon(QStyle.StandardPixmap.SP_DirIcon)

    # ---- 界面 ----------------------------------------------------------
    def _build_ui(self) -> None:
        root = QVBoxLayout(self)

        tip = QLabel(
            "导入的文件自动存到下方选中的文件夹（保留原文件，存副本）；"
            "由某文件夹内文件生成的总结，会存到该文件夹的「总结」子夹里。"
            "所有内容只保存在本机，重启后仍在。"
        )
        tip.setWordWrap(True)
        tip.setStyleSheet("color:#6E6E73; padding:2px;")
        root.addWidget(tip)

        # 根目录行
        rl = QHBoxLayout()
        rl.addWidget(QLabel("文件库位置："))
        self.lbl_root = QLabel()
        self.lbl_root.setStyleSheet("color:#333;")
        rl.addWidget(self.lbl_root, 1)
        btn_pick_root = QPushButton("更换位置…")
        btn_pick_root.setToolTip("把整个文件库移动到其它磁盘/目录")
        btn_pick_root.clicked.connect(self._on_pick_root)
        rl.addWidget(btn_pick_root)
        btn_open_root = QPushButton("打开根目录")
        btn_open_root.clicked.connect(lambda: self._open_dir(self._mgr().root()))
        rl.addWidget(btn_open_root)
        root.addLayout(rl)

        # 自动归档开关
        ol = QHBoxLayout()
        self.chk_auto_import = QPushButton()
        self.chk_auto_import.setCheckable(True)
        self.chk_auto_import.clicked.connect(self._on_auto_toggled)
        self.chk_auto_import.setToolTip("关闭后导入时不再自动存入文件夹，可在本页手动归档")
        self.chk_auto_summary = QPushButton()
        self.chk_auto_summary.setCheckable(True)
        self.chk_auto_summary.clicked.connect(self._on_auto_toggled)
        self.chk_auto_summary.setToolTip("关闭后生成总结时不再自动存入文件夹，历史产物可手动归档")
        ol.addWidget(self.chk_auto_import)
        ol.addWidget(self.chk_auto_summary)
        ol.addStretch(1)
        root.addLayout(ol)

        # 全文搜索
        sl = QHBoxLayout()
        sl.addWidget(QLabel("搜索："))
        self.edit_search = QLineEdit()
        self.edit_search.setPlaceholderText("按文件名或文件内容搜索整个文件库，回车执行…")
        self.edit_search.returnPressed.connect(self._on_search)
        sl.addWidget(self.edit_search, 1)
        self.chk_search_content = QCheckBox("搜索文件内容")
        self.chk_search_content.setChecked(True)
        self.chk_search_content.setToolTip("docx/pptx/xlsx/pdf 会现场解析文本，文件较多时稍慢")
        sl.addWidget(self.chk_search_content)
        self.btn_search = QPushButton("搜索")
        self.btn_search.clicked.connect(self._on_search)
        sl.addWidget(self.btn_search)
        self.btn_clear_search = QPushButton("清除结果")
        self.btn_clear_search.setEnabled(False)
        self.btn_clear_search.clicked.connect(self._on_clear_search)
        sl.addWidget(self.btn_clear_search)
        root.addLayout(sl)

        splitter = QSplitter(Qt.Orientation.Horizontal)
        root.addWidget(splitter, 1)

        # 左侧：文件夹树
        left = QWidget()
        ll = QVBoxLayout(left)
        ll.setContentsMargins(0, 0, 0, 0)
        fl = QHBoxLayout()
        btn_new = QPushButton("新建文件夹")
        btn_new.clicked.connect(self._on_new_folder)
        fl.addWidget(btn_new)
        self.btn_del_folder = QPushButton("删除文件夹")
        self.btn_del_folder.clicked.connect(self._on_delete_folder)
        fl.addWidget(self.btn_del_folder)
        btn_open_folder = QPushButton("打开")
        btn_open_folder.clicked.connect(self._on_open_selected_folder)
        fl.addWidget(btn_open_folder)
        fl.addStretch(1)
        ll.addLayout(fl)

        self.tree = QTreeWidget()
        self.tree.setHeaderLabel("文件夹")
        self.tree.setIconSize(self.tree.iconSize())
        self.tree.itemSelectionChanged.connect(self._on_tree_selection)
        ll.addWidget(self.tree)
        splitter.addWidget(left)

        # 右侧：当前文件夹的文件
        right = QWidget()
        rlay = QVBoxLayout(right)
        rlay.setContentsMargins(0, 0, 0, 0)
        self.lbl_current = QLabel()
        self.lbl_current.setStyleSheet("font-weight:bold;")
        rlay.addWidget(self.lbl_current)

        bar = QHBoxLayout()
        self.btn_archive_now = QPushButton()
        self.btn_archive_now.clicked.connect(self._on_archive_now)
        bar.addWidget(self.btn_archive_now)
        self.btn_move = QPushButton("移动到…")
        self.btn_move.setToolTip("把选中的文件移动到文件库的其它文件夹")
        self.btn_move.clicked.connect(self._on_move_files)
        bar.addWidget(self.btn_move)
        self.btn_mindmap = QPushButton("生成思维导图")
        self.btn_mindmap.setToolTip("把选中的 .md 文件生成可在浏览器打开的思维导图")
        self.btn_mindmap.clicked.connect(self._on_mindmap)
        bar.addWidget(self.btn_mindmap)
        btn_refresh = QPushButton("刷新")
        btn_refresh.clicked.connect(self.refresh_all)
        bar.addWidget(btn_refresh)
        btn_open_file = QPushButton("打开选中")
        btn_open_file.clicked.connect(self._on_open_file)
        bar.addWidget(btn_open_file)
        btn_del_file = QPushButton("删除选中")
        btn_del_file.clicked.connect(self._on_delete_files)
        bar.addWidget(btn_del_file)
        bar.addStretch(1)
        rlay.addLayout(bar)

        self.table = QTableWidget(0, 3)
        self.table.setHorizontalHeaderLabels(["文件名", "大小", "修改时间"])
        self.table.verticalHeader().setVisible(False)
        self.table.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        self.table.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        self.table.setAlternatingRowColors(True)
        self.table.setSelectionMode(QAbstractItemView.SelectionMode.ExtendedSelection)
        hdr = self.table.horizontalHeader()
        hdr.setSectionResizeMode(0, QHeaderView.ResizeMode.Stretch)
        hdr.setSectionResizeMode(1, QHeaderView.ResizeMode.ResizeToContents)
        hdr.setSectionResizeMode(2, QHeaderView.ResizeMode.ResizeToContents)
        rlay.addWidget(self.table)

        self.lbl_status = QLabel("就绪")
        self.lbl_status.setStyleSheet("color:#6E6E73;")
        rlay.addWidget(self.lbl_status)
        splitter.addWidget(right)
        splitter.setSizes([320, 640])

    # ---- 数据与刷新 ----------------------------------------------------
    def refresh_all(self) -> None:
        """刷新根目录显示、文件夹树、开关状态与右侧文件表。"""
        mgr = self._mgr()
        root = mgr.root()
        self.lbl_root.setText(root)
        self.lbl_root.setToolTip(root)

        cfg = self._get_config().archive
        self.chk_auto_import.blockSignals(True)
        self.chk_auto_import.setChecked(cfg.auto_import)
        self.chk_auto_import.setText("导入自动归档：开" if cfg.auto_import else "导入自动归档：关")
        self.chk_auto_import.blockSignals(False)
        self.chk_auto_summary.blockSignals(True)
        self.chk_auto_summary.setChecked(cfg.auto_summary)
        self.chk_auto_summary.setText("总结自动归档：开" if cfg.auto_summary else "总结自动归档：关")
        self.chk_auto_summary.blockSignals(False)

        self.refresh_tree()
        self.refresh_files()
        self.refresh_archive_button()

    def refresh_tree(self) -> None:
        """递归重建文件夹树，展示任意层级的子文件夹。"""
        mgr = self._mgr()
        mgr.ensure_root()
        self.tree.blockSignals(True)
        self.tree.clear()

        icon = self._dir_icon()
        root_item = QTreeWidgetItem(["（根目录）"])
        root_item.setData(0, Qt.ItemDataRole.UserRole, ROOT_REL)
        root_item.setIcon(0, icon)
        self.tree.addTopLevelItem(root_item)
        self._populate_tree(root_item, mgr.folder_abs(ROOT_REL), ROOT_REL, icon)

        self.tree.expandAll()
        # 恢复选中：优先当前查看的文件夹
        self._select_item(self._rel)
        self.tree.blockSignals(False)
        if not self.tree.selectedItems():
            # 找不到对应节点（如文件夹被删）则回落到根目录
            self._rel = ROOT_REL
            self.tree.setCurrentItem(root_item)

    def _populate_tree(self, parent_item, abs_dir: str, rel: str, icon) -> None:
        try:
            names = sorted(os.listdir(abs_dir))
        except OSError:
            return
        for d in names:
            p = os.path.join(abs_dir, d)
            if not os.path.isdir(p):
                continue
            child_rel = f"{rel}/{d}" if rel else d
            item = QTreeWidgetItem([d])
            item.setData(0, Qt.ItemDataRole.UserRole, child_rel)
            item.setData(0, Qt.ItemDataRole.UserRole + 1, d == SUMMARY_SUBDIR)
            item.setIcon(0, icon)
            if d == SUMMARY_SUBDIR:
                item.setForeground(0, self._summary_brush())
            parent_item.addChild(item)
            self._populate_tree(item, p, child_rel, icon)

    @staticmethod
    def _summary_brush():
        from PyQt6.QtGui import QBrush, QColor

        return QBrush(QColor("#999999"))

    def _select_item(self, rel: str) -> None:
        """按相对路径递归查找并选中树节点。"""
        target = (rel or "").replace("\\", "/").strip("/")

        def walk(item) -> QTreeWidgetItem | None:
            if (item.data(0, Qt.ItemDataRole.UserRole) or "") == target and target:
                return item
            for i in range(item.childCount()):
                found = walk(item.child(i))
                if found:
                    return found
            return None

        top = self.tree.topLevelItem(0)
        if top is None:
            return
        if target == ROOT_REL:
            self.tree.setCurrentItem(top)
            return
        found = walk(top)
        if found:
            self.tree.setCurrentItem(found)

    def refresh_files(self) -> None:
        """刷新右侧文件表，显示当前选中文件夹内的文件。"""
        # 离开搜索结果视图，恢复普通三列
        if self._in_search:
            self._exit_search_mode()
        mgr = self._mgr()
        d = mgr.folder_abs(self._rel)
        if self._rel == ROOT_REL:
            self.lbl_current.setText("当前查看：根目录")
        else:
            name = self._rel.replace("/", " / ")
            self.lbl_current.setText(f"当前查看：{name}")

        self.table.blockSignals(True)
        self.table.setRowCount(0)
        if os.path.isdir(d):
            try:
                names = sorted(os.listdir(d))
            except OSError as e:
                self.lbl_status.setText(f"读取目录失败：{e}")
                self.table.blockSignals(False)
                return
            for name in names:
                p = os.path.join(d, name)
                if not os.path.isfile(p):
                    continue
                row = self.table.rowCount()
                self.table.insertRow(row)
                item = QTableWidgetItem(name)
                item.setData(Qt.ItemDataRole.UserRole, p)
                item.setToolTip(p)
                self.table.setItem(row, 0, item)
                try:
                    size = os.path.getsize(p)
                except OSError:
                    size = 0
                self.table.setItem(row, 1, QTableWidgetItem(self._size_text(size)))
                try:
                    t = datetime.datetime.fromtimestamp(os.path.getmtime(p)).strftime("%Y-%m-%d %H:%M")
                except OSError:
                    t = ""
                self.table.setItem(row, 2, QTableWidgetItem(t))
            count = self.table.rowCount()
            self.lbl_status.setText(f"共 {count} 个文件")
        else:
            self.lbl_status.setText("该文件夹为空或尚未创建")
        self.table.blockSignals(False)

    def refresh_archive_button(self) -> None:
        mgr = self._mgr()
        n = len(self._store)
        target = mgr.active_folder() or "根目录"
        self.btn_archive_now.setText(f"把导入的文件归档到「{target}」({n})")
        self.btn_archive_now.setEnabled(n > 0)

    @staticmethod
    def _size_text(n: int) -> str:
        s = float(n)
        for unit in ("B", "KB", "MB", "GB"):
            if s < 1024 or unit == "GB":
                return f"{int(s)} {unit}" if unit == "B" else f"{s:.1f} {unit}"
            s /= 1024
        return f"{s:.1f} GB"

    # ---- 树交互 --------------------------------------------------------
    def _on_tree_selection(self) -> None:
        items = self.tree.selectedItems()
        if not items:
            return
        rel = items[0].data(0, Qt.ItemDataRole.UserRole) or ROOT_REL
        self._rel = rel
        # 选中普通文件夹（任意层级）时，把它设为导入的默认归档位置；
        # 选中「总结」子夹仅切换查看，不改变导入目标。
        if not ArchiveManager.is_summary_rel(rel):
            self._mgr().set_active_folder(rel)
            self.refresh_archive_button()
        self.refresh_files()

    def _on_new_folder(self) -> None:
        mgr = self._mgr()
        # 在当前选中的文件夹下创建；若选中的是「总结」子夹则回到其上级
        parent = self._rel
        if mgr.is_summary_rel(parent):
            parent = parent.rsplit("/", 1)[0]
        parent_name = parent or "根目录"
        name, ok = QInputDialog.getText(
            self, "新建文件夹",
            f"在「{parent_name}」下新建文件夹，名称：",
            text=mgr.default_folder_name(parent),
        )
        if not ok:
            return
        created, err = mgr.create_folder(name, parent)
        if err:
            QMessageBox.warning(self, "无法创建", err)
            return
        self._rel = created or ROOT_REL
        self.refresh_tree()
        self._select_item(self._rel)
        self._mgr().set_active_folder(self._rel)
        self.refresh_files()
        self.refresh_archive_button()
        self.lbl_status.setText(f"已创建「{created}」，之后导入的文件将存到这里")

    def _on_delete_folder(self) -> None:
        items = self.tree.selectedItems()
        if not items:
            QMessageBox.information(self, "提示", "请先在左侧选中要删除的文件夹。")
            return
        rel = items[0].data(0, Qt.ItemDataRole.UserRole) or ROOT_REL
        if rel == ROOT_REL:
            QMessageBox.information(self, "提示", "根目录不能删除。")
            return
        ret = QMessageBox.question(
            self,
            "确认删除",
            f"确定删除文件夹「{rel}」吗？\n\n只有文件夹为空时才能删除；"
            "删除不影响原始文件。",
        )
        if ret != QMessageBox.StandardButton.Yes:
            return
        err = self._mgr().delete_folder(rel)
        if err:
            QMessageBox.warning(self, "无法删除", err)
        if self._rel == rel:
            self._rel = ROOT_REL
        self.refresh_all()

    def _on_open_selected_folder(self) -> None:
        self._open_dir(self._mgr().folder_abs(self._rel))

    def _open_dir(self, d: str) -> None:
        if not os.path.isdir(d):
            try:
                os.makedirs(d, exist_ok=True)
            except OSError as e:
                QMessageBox.critical(self, "错误", f"无法创建目录：{e}")
                return
        QDesktopServices.openUrl(QUrl.fromLocalFile(d))

    # ---- 根目录与开关 --------------------------------------------------
    def _on_pick_root(self) -> None:
        d = QFileDialog.getExistingDirectory(self, "选择文件库位置", self._mgr().root())
        if not d:
            return
        self._mgr().set_root(d)
        self._rel = ROOT_REL
        self.refresh_all()

    def _on_auto_toggled(self) -> None:
        cfg = self._get_config().archive
        cfg.auto_import = self.chk_auto_import.isChecked()
        cfg.auto_summary = self.chk_auto_summary.isChecked()
        try:
            save_config(self._get_config())
        except OSError:
            pass
        self.chk_auto_import.setText("导入自动归档：开" if cfg.auto_import else "导入自动归档：关")
        self.chk_auto_summary.setText("总结自动归档：开" if cfg.auto_summary else "总结自动归档：关")
        self.lbl_status.setText("自动归档设置已保存")

    # ---- 导入联动 ------------------------------------------------------
    def _on_files_added(self, paths: list) -> None:
        self.refresh_all()

    def set_active_folder(self, rel: str) -> None:
        """供其它标签页切换默认归档文件夹。"""
        self._mgr().set_active_folder(rel or ROOT_REL)
        self._rel = rel or ROOT_REL
        self.refresh_all()

    # ---- 归档与文件操作 ------------------------------------------------
    def _on_archive_now(self) -> None:
        mgr = self._mgr()
        paths = [it.path for it in self._store.items]
        if not paths:
            QMessageBox.information(self, "提示", "当前没有已导入的文件。")
            return
        target = mgr.active_folder()
        archived, skipped, errors = mgr.archive_into(paths, target)
        self.refresh_all()
        msg = f"已归档 {archived} 个，跳过重复 {skipped} 个。"
        self.lbl_status.setText(msg)
        if errors:
            QMessageBox.warning(self, "部分归档失败", msg + "\n\n" + "\n".join(errors[:10]))
        else:
            QMessageBox.information(self, "完成", msg)

    # ---- 文件移动 ------------------------------------------------------
    def _choose_folder(self, title: str) -> str | None:
        """弹出文件夹选择框（含多级），返回相对路径；取消返回 None。"""
        mgr = self._mgr()
        options = ["根目录"]
        data = [ROOT_REL]
        for f in mgr.folders():
            options.append(f)
            data.append(f)
        idx, ok = QInputDialog.getItem(
            self, title, "目标文件夹：", options, 0, False
        )
        if not ok:
            return None
        return data[options.index(idx)]

    def _on_move_files(self) -> None:
        paths = self._selected_paths()
        if not paths:
            QMessageBox.information(self, "提示", "请先选中要移动的文件。")
            return
        rel = self._choose_folder(f"移动 {len(paths)} 个文件到…")
        if rel is None:
            return
        moved, skipped, errors = self._mgr().move_files(paths, rel)
        self.refresh_all()
        target_name = rel or "根目录"
        msg = f"已移动 {moved} 个到「{target_name}」，跳过 {skipped} 个。"
        self.lbl_status.setText(msg)
        if errors:
            QMessageBox.warning(self, "部分移动失败", msg + "\n\n" + "\n".join(errors[:10]))
        elif moved:
            QMessageBox.information(self, "完成", msg)

    def _selected_paths(self) -> list[str]:
        out = []
        for idx in self.table.selectionModel().selectedRows():
            item = self.table.item(idx.row(), 0)
            if item:
                out.append(item.data(Qt.ItemDataRole.UserRole))
        return [p for p in out if p]

    def _on_open_file(self) -> None:
        paths = self._selected_paths()
        if not paths:
            QMessageBox.information(self, "提示", "请先选中文件。")
            return
        for p in paths[:5]:
            if os.path.isfile(p):
                QDesktopServices.openUrl(QUrl.fromLocalFile(p))

    def _on_delete_files(self) -> None:
        paths = self._selected_paths()
        if not paths:
            QMessageBox.information(self, "提示", "请先选中要删除的文件。")
            return
        ret = QMessageBox.question(
            self,
            "确认删除",
            f"确定从文件库删除选中的 {len(paths)} 个文件吗？\n\n"
            "只删除文件库里的副本，不影响原始文件。",
        )
        if ret != QMessageBox.StandardButton.Yes:
            return
        errors = []
        for p in paths:
            try:
                os.remove(p)
            except OSError as e:
                errors.append(f"{os.path.basename(p)}: {e}")
        self.refresh_all()
        if errors:
            QMessageBox.warning(self, "部分删除失败", "\n".join(errors[:10]))
    # ---- 全文搜索 ------------------------------------------------------
    def _on_search(self) -> None:
        if self._search_worker is not None and self._search_worker.isRunning():
            return
        kw = self.edit_search.text().strip()
        if not kw:
            QMessageBox.information(self, "提示", "请输入搜索关键字。")
            return
        root = self._mgr().root()
        if not os.path.isdir(root):
            QMessageBox.information(self, "提示", "文件库目录还不存在。")
            return
        self.btn_search.setEnabled(False)
        self.btn_search.setText("搜索中…")
        self.lbl_status.setText("正在搜索…")

        self._search_worker = Worker(
            _search_library, root, kw, self.chk_search_content.isChecked()
        )
        self._search_worker.progress.connect(self.lbl_status.setText)
        self._search_worker.finished_ok.connect(self._on_search_done)
        self._search_worker.failed.connect(self._on_search_failed)
        self._search_worker.finished.connect(
            lambda: (self.btn_search.setEnabled(True), self.btn_search.setText("搜索"))
        )
        self._search_worker.start()

    def _on_search_done(self, result) -> None:
        results, scanned = result
        kw = self.edit_search.text().strip()
        self._in_search = True
        self.btn_clear_search.setEnabled(True)

        t = self.table
        t.blockSignals(True)
        t.clear()
        t.setColumnCount(4)
        t.setHorizontalHeaderLabels(["文件名", "所在文件夹", "匹配内容", "修改时间"])
        hdr = t.horizontalHeader()
        hdr.setSectionResizeMode(0, QHeaderView.ResizeMode.Stretch)
        hdr.setSectionResizeMode(1, QHeaderView.ResizeMode.ResizeToContents)
        hdr.setSectionResizeMode(2, QHeaderView.ResizeMode.Stretch)
        hdr.setSectionResizeMode(3, QHeaderView.ResizeMode.ResizeToContents)
        t.setRowCount(0)
        for r in results:
            row = t.rowCount()
            t.insertRow(row)
            name_item = QTableWidgetItem(r["name"])
            name_item.setData(Qt.ItemDataRole.UserRole, r["path"])
            name_item.setToolTip(r["path"])
            t.setItem(row, 0, name_item)
            t.setItem(row, 1, QTableWidgetItem(r["folder"] or "（根目录）"))
            s_item = QTableWidgetItem(r["snippet"] or "（仅文件名匹配）")
            s_item.setToolTip(r["snippet"])
            t.setItem(row, 2, s_item)
            t.setItem(row, 3, QTableWidgetItem(r["mtime"]))
        t.blockSignals(False)

        self.lbl_current.setText(f"搜索「{kw}」：{len(results)} 个结果")
        self.lbl_status.setText(
            f"扫描了 {scanned} 个文件，命中 {len(results)} 个。"
            + ("已达结果上限，可换更精确的关键字。" if len(results) >= SEARCH_LIMIT else "")
        )
        self._update_mindmap_button()

    def _on_search_failed(self, err: str) -> None:
        self.lbl_status.setText("搜索失败")
        QMessageBox.critical(self, "搜索失败", err)

    def _on_clear_search(self) -> None:
        self.edit_search.clear()
        self.btn_clear_search.setEnabled(False)
        # refresh_files 会退出搜索视图并恢复三列
        self.refresh_files()
        self.lbl_current.setText("当前查看：根目录")

    def _exit_search_mode(self) -> None:
        """从搜索结果视图切回普通文件夹视图。"""
        self._in_search = False
        self.btn_clear_search.setEnabled(False)
        t = self.table
        t.blockSignals(True)
        t.clear()
        t.setColumnCount(3)
        t.setHorizontalHeaderLabels(["文件名", "大小", "修改时间"])
        hdr = t.horizontalHeader()
        hdr.setSectionResizeMode(0, QHeaderView.ResizeMode.Stretch)
        hdr.setSectionResizeMode(1, QHeaderView.ResizeMode.ResizeToContents)
        hdr.setSectionResizeMode(2, QHeaderView.ResizeMode.ResizeToContents)
        t.setRowCount(0)
        t.blockSignals(False)

    # ---- 思维导图 ------------------------------------------------------
    def _update_mindmap_button(self) -> None:
        paths = self._selected_paths()
        ok = any(p.lower().endswith(".md") for p in paths if os.path.isfile(p))
        self.btn_mindmap.setEnabled(ok)

    def _on_mindmap(self) -> None:
        paths = [p for p in self._selected_paths() if p.lower().endswith(".md")]
        if not paths:
            QMessageBox.information(self, "提示", "请先选中一个 .md 文件。")
            return
        made = []
        errors = []
        for p in paths[:5]:
            try:
                with open(p, "r", encoding="utf-8", errors="ignore") as f:
                    md = f.read()
                out = os.path.splitext(p)[0] + ".思维导图.html"
                markdown_to_mindmap_html(md, out, title=os.path.splitext(os.path.basename(p))[0])
                made.append(out)
            except Exception as e:  # noqa: BLE001
                errors.append(f"{os.path.basename(p)}: {e}")
        self.refresh_files()
        if errors:
            QMessageBox.warning(self, "部分生成失败", "\n".join(errors[:10]))
        if made:
            self.lbl_status.setText(f"已生成 {len(made)} 个思维导图")
            QDesktopServices.openUrl(QUrl.fromLocalFile(made[0]))


def _snippet_of(text: str, kw: str, width: int = 90) -> str:
    """返回关键字附近的文本片段。"""
    low = text.lower()
    i = low.find(kw.lower())
    if i < 0:
        return ""
    start = max(0, i - 30)
    end = min(len(text), i + len(kw) + 60)
    s = text[start:end].replace("\n", " ").strip()
    return ("…" if start else "") + s + ("…" if end < len(text) else "")


def _read_file_text(path: str, cache: dict) -> str | None:
    """读取文件文本：.md/.txt 直接读，受支持文档现场解析，带 (路径, mtime) 缓存。

    有意做了限速保护：超大文件（>30MB）跳过；PDF 只解析前 50 页。
    搜索的目的是定位，不追求完整转换。
    """
    ext = os.path.splitext(path)[1].lower()
    try:
        mtime = os.path.getmtime(path)
        if os.path.getsize(path) > _SEARCH_MAX_BYTES:
            cache[key] = None
            return None
    except OSError:
        return None
    key = (path, mtime)
    if key in cache:
        return cache[key]
    text: str | None = None
    if ext in _TEXT_EXTS:
        try:
            with open(path, "r", encoding="utf-8", errors="ignore") as f:
                text = f.read()
        except OSError:
            text = None
    elif ext == ".pdf":
        # PDF 直接用 pdfplumber 读前 50 页，比完整转换快得多
        try:
            import pdfplumber

            with pdfplumber.open(path) as pdf:
                pages = pdf.pages[:_SEARCH_PDF_MAX_PAGES]
                text = "\n".join((pg.extract_text() or "") for pg in pages)
        except Exception:  # noqa: BLE001
            text = None
    elif ext in SUPPORTED_EXTENSIONS:
        from core.registry import get_converter

        conv = get_converter(path)
        if conv is not None:
            try:
                text = conv.convert(path)
            except Exception:  # noqa: BLE001 - 单个解析失败不影响整体搜索
                text = None
    cache[key] = text
    return text


def _search_library(root: str, keyword: str, include_content: bool, progress):
    """遍历文件库，按文件名/内容搜索。返回 (结果列表, 扫描文件数)。"""
    kw = keyword.lower()
    cache: dict = {}
    results: list[dict] = []
    scanned = 0

    for r, _dirs, files in os.walk(root):
        rel = os.path.relpath(r, root).replace("\\", "/")
        if rel == ".":
            rel = ""
        for name in sorted(files):
            scanned += 1
            if scanned % 20 == 0:
                progress(f"正在搜索… 已扫描 {scanned} 个文件")
            p = os.path.join(r, name)
            name_match = kw in name.lower()
            snippet = ""
            if not name_match and include_content:
                text = _read_file_text(p, cache)
                if not text:
                    continue
                snippet = _snippet_of(text, kw)
                if not snippet:
                    continue
            if not (name_match or snippet):
                continue
            try:
                mtime = datetime.datetime.fromtimestamp(os.path.getmtime(p)).strftime("%Y-%m-%d %H:%M")
            except OSError:
                mtime = ""
            results.append({
                "path": p,
                "name": name,
                "folder": rel,
                "snippet": snippet,
                "mtime": mtime,
            })
            if len(results) >= SEARCH_LIMIT:
                return results, scanned
    return results, scanned
