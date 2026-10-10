"""可复用的文件列表控件：带勾选框、状态列。"""
from __future__ import annotations

import os

from PyQt6.QtCore import Qt, pyqtSignal
from PyQt6.QtWidgets import (
    QAbstractItemView,
    QHeaderView,
    QTableWidget,
    QTableWidgetItem,
)

from .file_store import FileItem, FileStore

COL_CHECK = 0
COL_NAME = 1
COL_TYPE = 2
COL_SIZE = 3
COL_STATUS = 4


class FileTable(QTableWidget):
    """展示 FileStore 中的文件，每行带一个勾选框和状态。"""

    check_changed = pyqtSignal()

    def __init__(self, store: FileStore, parent=None):
        super().__init__(0, 5, parent)
        self._store = store
        self._check_states: dict[str, bool] = {}

        self.setHorizontalHeaderLabels(["", "文件名", "类型", "大小", "状态"])
        self.verticalHeader().setVisible(False)
        self.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        self.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        self.setAlternatingRowColors(True)
        self.setShowGrid(False)
        hdr = self.horizontalHeader()
        hdr.setSectionResizeMode(COL_CHECK, QHeaderView.ResizeMode.Fixed)
        hdr.setSectionResizeMode(COL_NAME, QHeaderView.ResizeMode.Stretch)
        hdr.setSectionResizeMode(COL_TYPE, QHeaderView.ResizeMode.ResizeToContents)
        hdr.setSectionResizeMode(COL_SIZE, QHeaderView.ResizeMode.ResizeToContents)
        hdr.setSectionResizeMode(COL_STATUS, QHeaderView.ResizeMode.ResizeToContents)
        self.setColumnWidth(COL_CHECK, 34)

        store.files_changed.connect(self.refresh)
        self.itemChanged.connect(self._on_item_changed)
        self.refresh()

    # ---- 刷新 ----------------------------------------------------------
    def refresh(self) -> None:
        self.blockSignals(True)
        items = self._store.items
        self.setRowCount(len(items))
        for row, it in enumerate(items):
            chk = QTableWidgetItem()
            chk.setFlags(
                Qt.ItemFlag.ItemIsUserCheckable
                | Qt.ItemFlag.ItemIsEnabled
                | Qt.ItemFlag.ItemIsSelectable
            )
            checked = self._check_states.get(it.path, True)
            chk.setCheckState(Qt.CheckState.Checked if checked else Qt.CheckState.Unchecked)
            chk.setData(Qt.ItemDataRole.UserRole, it.path)
            self.setItem(row, COL_CHECK, chk)

            name_item = QTableWidgetItem(it.name)
            name_item.setData(Qt.ItemDataRole.UserRole, it.path)
            name_item.setToolTip(it.path)
            self.setItem(row, COL_NAME, name_item)

            self.setItem(row, COL_TYPE, QTableWidgetItem(it.type_text))
            self.setItem(row, COL_SIZE, QTableWidgetItem(it.size_text))
            self.setItem(row, COL_STATUS, QTableWidgetItem(it.status))
        self.blockSignals(False)
        self.check_changed.emit()

    def _on_item_changed(self, item: QTableWidgetItem) -> None:
        if item.column() != COL_CHECK:
            return
        path = item.data(Qt.ItemDataRole.UserRole)
        if path:
            self._check_states[path] = item.checkState() == Qt.CheckState.Checked
            self.check_changed.emit()

    # ---- 勾选操作 ------------------------------------------------------
    def checked_paths(self) -> list[str]:
        out = []
        for row in range(self.rowCount()):
            item = self.item(row, COL_CHECK)
            if item and item.checkState() == Qt.CheckState.Checked:
                out.append(item.data(Qt.ItemDataRole.UserRole))
        return [p for p in out if p]

    def selected_paths(self) -> list[str]:
        paths = []
        for idx in self.selectionModel().selectedRows():
            item = self.item(idx.row(), COL_NAME)
            if item:
                paths.append(item.data(Qt.ItemDataRole.UserRole))
        return [p for p in paths if p]

    def set_checked(self, paths: list[str] | None, checked: bool) -> None:
        """勾选/取消勾选；paths 为 None 时表示全部。"""
        target = set(paths) if paths is not None else None
        for row in range(self.rowCount()):
            item = self.item(row, COL_CHECK)
            if not item:
                continue
            path = item.data(Qt.ItemDataRole.UserRole)
            if target is None or path in target:
                item.setCheckState(Qt.CheckState.Checked if checked else Qt.CheckState.Unchecked)

    # ---- 状态更新 ------------------------------------------------------
    def set_status(self, path: str, status: str) -> None:
        for row in range(self.rowCount()):
            name_item = self.item(row, COL_NAME)
            if name_item and name_item.data(Qt.ItemDataRole.UserRole) == path:
                self.item(row, COL_STATUS).setText(status)
                break

    def sync_from_store(self) -> None:
        """把 store 中的状态文案回写到表格。"""
        for row in range(self.rowCount()):
            name_item = self.item(row, COL_NAME)
            if not name_item:
                continue
            path = name_item.data(Qt.ItemDataRole.UserRole)
            it = self._store.get(path)
            if it:
                self.item(row, COL_STATUS).setText(it.status)