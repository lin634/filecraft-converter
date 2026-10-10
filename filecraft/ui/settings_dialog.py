"""设置弹窗：配置 OpenAI 兼容接口。"""
from __future__ import annotations

from PyQt6.QtWidgets import (
    QComboBox,
    QDialog,
    QDialogButtonBox,
    QFormLayout,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QMessageBox,
    QPushButton,
    QSpinBox,
    QDoubleSpinBox,
    QVBoxLayout,
)

from config import AppConfig, save_config

#: 常见服务商的 base_url 预设
PRESETS = [
    ("ModelScope 魔搭", "https://api-inference.modelscope.cn/v1", "deepseek-ai/DeepSeek-V4.1-Flash"),
    ("OpenAI", "https://api.openai.com/v1", "gpt-4o-mini"),
    ("智谱 GLM", "https://open.bigmodel.cn/api/paas/v4", "glm-4-plus"),
    ("DeepSeek", "https://api.deepseek.com/v1", "deepseek-chat"),
    ("月之暗面 Kimi", "https://api.moonshot.cn/v1", "moonshot-v1-8k"),
    ("阿里通义千问", "https://dashscope.aliyuncs.com/compatible-mode/v1", "qwen-plus"),
    ("本地 Ollama", "http://localhost:11434/v1", "llama3"),
    ("自定义", "", ""),
]


class SettingsDialog(QDialog):
    def __init__(self, cfg: AppConfig, parent=None):
        super().__init__(parent)
        self.setWindowTitle("设置")
        self.setMinimumWidth(560)
        self._cfg = cfg

        root = QVBoxLayout(self)

        hint = QLabel(
            "填写任意 OpenAI 兼容接口的地址与密钥。密钥仅保存在本机 "
            r"%USERPROFILE%\.filecraft\config.json，不会上传。"
        )
        hint.setWordWrap(True)
        hint.setStyleSheet("color:#666;")
        root.addWidget(hint)

        form = QFormLayout()

        # 预设
        self.combo_preset = QComboBox()
        for name, _, _ in PRESETS:
            self.combo_preset.addItem(name)
        self.combo_preset.currentIndexChanged.connect(self._apply_preset)
        form.addRow("服务商预设：", self.combo_preset)

        # base_url
        row_url = QHBoxLayout()
        self.edit_url = QLineEdit(cfg.llm.base_url)
        self.edit_url.setPlaceholderText("https://api.example.com/v1")
        row_url.addWidget(self.edit_url, 1)
        form.addRow("Base URL：", row_url)

        # api key
        self.edit_key = QLineEdit(cfg.llm.api_key)
        self.edit_key.setEchoMode(QLineEdit.EchoMode.Password)
        self.edit_key.setPlaceholderText("sk-…")
        row_key = QHBoxLayout()
        row_key.addWidget(self.edit_key, 1)
        self.btn_show_key = QPushButton("显示")
        self.btn_show_key.setCheckable(True)
        self.btn_show_key.toggled.connect(self._toggle_key)
        row_key.addWidget(self.btn_show_key)
        form.addRow("API Key：", row_key)

        # model
        self.edit_model = QLineEdit(cfg.llm.model)
        form.addRow("模型名称：", self.edit_model)

        # temperature
        self.spin_temp = QDoubleSpinBox()
        self.spin_temp.setRange(0.0, 2.0)
        self.spin_temp.setSingleStep(0.1)
        self.spin_temp.setValue(cfg.llm.temperature)
        form.addRow("Temperature：", self.spin_temp)

        # 分块阈值
        self.spin_chunk = QSpinBox()
        self.spin_chunk.setRange(1000, 500000)
        self.spin_chunk.setSingleStep(1000)
        self.spin_chunk.setValue(cfg.llm.max_chars_per_chunk)
        self.spin_chunk.setToolTip("超过此字符数时自动分段总结再合并（map-reduce）")
        form.addRow("单次输入上限（字符）：", self.spin_chunk)

        root.addLayout(form)

        btns = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Save | QDialogButtonBox.StandardButton.Cancel
        )
        btns.button(QDialogButtonBox.StandardButton.Save).setText("保存")
        btns.button(QDialogButtonBox.StandardButton.Cancel).setText("取消")
        btns.accepted.connect(self._on_save)
        btns.rejected.connect(self.reject)
        root.addWidget(btns)

        self._sync_preset_selection()

    # ---- 内部 ----------------------------------------------------------
    def _apply_preset(self, idx: int) -> None:
        name, url, model = PRESETS[idx]
        if name == "自定义":
            return
        self.edit_url.setText(url)
        if model:
            self.edit_model.setText(model)

    def _sync_preset_selection(self) -> None:
        cur_url = self._cfg.llm.base_url
        for i, (_, url, _) in enumerate(PRESETS):
            if url and url == cur_url:
                self.combo_preset.blockSignals(True)
                self.combo_preset.setCurrentIndex(i)
                self.combo_preset.blockSignals(False)
                return

    def _toggle_key(self, shown: bool) -> None:
        self.edit_key.setEchoMode(
            QLineEdit.EchoMode.Normal if shown else QLineEdit.EchoMode.Password
        )
        self.btn_show_key.setText("隐藏" if shown else "显示")

    def _on_save(self) -> None:
        url = self.edit_url.text().strip()
        if not url:
            QMessageBox.warning(self, "提示", "Base URL 不能为空。")
            return
        self._cfg.llm.base_url = url
        self._cfg.llm.api_key = self.edit_key.text().strip()
        self._cfg.llm.model = self.edit_model.text().strip()
        self._cfg.llm.temperature = self.spin_temp.value()
        self._cfg.llm.max_chars_per_chunk = self.spin_chunk.value()
        try:
            save_config(self._cfg)
        except OSError as e:
            QMessageBox.critical(self, "错误", f"配置保存失败：{e}")
            return
        self.accept()