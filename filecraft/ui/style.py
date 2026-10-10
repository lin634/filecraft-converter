"""全局界面样式：极简白（苹果风）。

配色：
    窗口背景   #F5F5F7
    卡片/面板   #FFFFFF
    强调色     #0A84FF（唯一蓝色点缀）
    主文字     #1D1D1F
    次要文字   #6E6E73
    分割线     #E5E5EA / 淡分隔 #F0F0F3
"""

STYLE = """
/* ---------- 基础 ---------- */
QWidget {
    font-family: "Microsoft YaHei UI", "Microsoft YaHei";
    font-size: 13px;
    color: #1D1D1F;
}
QMainWindow, QDialog { background: #F5F5F7; }
QWidget:disabled { color: #AEAEB2; }

QToolTip {
    background: #FFFFFF; color: #1D1D1F;
    border: 1px solid #E5E5EA; border-radius: 6px;
    padding: 4px 8px;
}

/* ---------- 菜单栏与菜单 ---------- */
QMenuBar { background: #F5F5F7; border-bottom: 1px solid #E5E5EA; padding: 2px 6px; }
QMenuBar::item { background: transparent; padding: 5px 10px; border-radius: 6px; }
QMenuBar::item:selected { background: #E8E8ED; }
QMenu {
    background: #FFFFFF; border: 1px solid #E5E5EA;
    border-radius: 8px; padding: 4px;
}
QMenu::item { padding: 6px 24px 6px 12px; border-radius: 6px; }
QMenu::item:selected { background: #F0F0F3; }
QMenu::item:disabled { color: #AEAEB2; }
QMenu::separator { height: 1px; background: #E5E5EA; margin: 4px 8px; }

/* ---------- 标签页：文字选中变蓝 + 底部细蓝线 ---------- */
QTabWidget::pane { border: none; border-top: 1px solid #E5E5EA; background: #F5F5F7; top: 0; }
QTabBar { background: transparent; }
QTabBar::tab {
    background: transparent; color: #6E6E73;
    padding: 8px 18px;
    border: none; border-bottom: 2px solid transparent;
    margin-right: 8px;
}
QTabBar::tab:selected { color: #0A84FF; border-bottom: 2px solid #0A84FF; font-weight: 600; }
QTabBar::tab:hover:!selected { color: #1D1D1F; }

/* ---------- 按钮：白底细边，胶囊形 ---------- */
QPushButton {
    background: #FFFFFF; color: #0A84FF;
    border: 1px solid #E5E5EA; border-radius: 15px;
    padding: 6px 16px;
}
QPushButton:hover { background: #F0F0F3; }
QPushButton:pressed { background: #E8E8ED; }
QPushButton:disabled { color: #AEAEB2; border-color: #F0F0F3; background: #FFFFFF; }
QPushButton#primary {
    background: #0A84FF; color: #FFFFFF; border: none; font-weight: 600;
    padding: 7px 22px;
}
QPushButton#primary:hover { background: #0070E0; }
QPushButton#primary:pressed { background: #0060C8; }
QPushButton#primary:disabled { background: #E8E8ED; color: #AEAEB2; }

/* ---------- 输入框 ---------- */
QLineEdit, QTextEdit, QPlainTextEdit, QTextBrowser {
    background: #FFFFFF; color: #1D1D1F;
    border: 1px solid #E5E5EA; border-radius: 8px;
    padding: 5px 8px;
    selection-background-color: #B3D7FF; selection-color: #1D1D1F;
}
QLineEdit:focus, QTextEdit:focus, QPlainTextEdit:focus { border: 1px solid #0A84FF; }
QTextBrowser { border: 1px solid #E5E5EA; }

/* ---------- 下拉框 ---------- */
QComboBox {
    background: #FFFFFF; color: #1D1D1F;
    border: 1px solid #E5E5EA; border-radius: 8px; padding: 4px 10px;
}
QComboBox:hover { border-color: #C7C7CC; }
QComboBox::drop-down { border: none; width: 24px; }
QComboBox::down-arrow {
    width: 0; height: 0;
    border-left: 4px solid transparent; border-right: 4px solid transparent;
    border-top: 5px solid #8E8E93; margin-right: 8px;
}
QComboBox QAbstractItemView {
    background: #FFFFFF; color: #1D1D1F;
    border: 1px solid #E5E5EA; border-radius: 8px;
    selection-background-color: #F0F0F3; selection-color: #1D1D1F;
    outline: none; padding: 4px;
}

/* ---------- 表格：无竖线、细分隔 ---------- */
QTableWidget, QTreeView, QTreeWidget {
    background: #FFFFFF;
    border: 1px solid #E5E5EA; border-radius: 10px;
    gridline-color: transparent;
    selection-background-color: #EAF2FF; selection-color: #1D1D1F;
    alternate-background-color: #FAFAFC;
    outline: none;
}
QTableWidget::item, QTreeWidget::item, QTreeView::item {
    border: none; border-bottom: 1px solid #F0F0F3;
    padding: 3px 4px;
}
QTableWidget::item:selected, QTreeWidget::item:selected, QTreeView::item:selected {
    background: #EAF2FF; color: #1D1D1F;
}
QTableWidget::item:hover, QTreeWidget::item:hover, QTreeView::item:hover {
    background: #F0F0F3;
}
QHeaderView::section {
    background: #FAFAFC; color: #6E6E73;
    border: none; border-bottom: 1px solid #E5E5EA;
    padding: 6px 8px; font-size: 12px;
}
QTableCornerButton::section { background: #FAFAFC; border: none; }

/* ---------- 分组卡片 ---------- */
QGroupBox {
    background: #FFFFFF;
    border: 1px solid #E5E5EA; border-radius: 10px;
    margin-top: 14px; padding: 8px 6px 6px 6px;
    font-weight: 600;
}
QGroupBox::title {
    subcontrol-origin: margin; left: 12px; top: 2px;
    padding: 0 4px; color: #6E6E73; font-size: 12px; font-weight: 600;
}

/* ---------- 滚动条：细 ---------- */
QScrollBar:vertical { background: transparent; width: 8px; margin: 2px; }
QScrollBar::handle:vertical { background: #C7C7CC; border-radius: 4px; min-height: 30px; }
QScrollBar::handle:vertical:hover { background: #AEAEB2; }
QScrollBar:horizontal { background: transparent; height: 8px; margin: 2px; }
QScrollBar::handle:horizontal { background: #C7C7CC; border-radius: 4px; min-width: 30px; }
QScrollBar::handle:horizontal:hover { background: #AEAEB2; }
QScrollBar::add-line, QScrollBar::sub-line { width: 0; height: 0; }
QScrollBar::add-page, QScrollBar::sub-page { background: transparent; }

/* ---------- 进度条 ---------- */
QProgressBar {
    background: #E8E8ED; border: none; border-radius: 4px;
    min-height: 8px; max-height: 8px; text-align: center; color: transparent;
}
QProgressBar::chunk { background: #0A84FF; border-radius: 4px; }

/* ---------- 状态栏与分割线 ---------- */
QStatusBar { background: #F5F5F7; border-top: 1px solid #E5E5EA; color: #6E6E73; }
QStatusBar::item { border: none; }
QSplitter::handle { background: transparent; }
QSplitter::handle:horizontal { width: 6px; }
QSplitter::handle:vertical { height: 6px; }
"""
