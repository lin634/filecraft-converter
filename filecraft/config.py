"""配置管理：持久化到用户目录的 config.json。"""
from __future__ import annotations

import json
import os
from dataclasses import asdict, dataclass, field
from typing import Optional

CONFIG_DIR = os.path.join(os.path.expanduser("~"), ".filecraft")
CONFIG_PATH = os.path.join(CONFIG_DIR, "config.json")


@dataclass
class LLMConfig:
    # 默认值即 ModelScope 兼容接口配置，需在「工具 → 设置」中填入自己的 API Key。
    # 用户可在设置中修改，修改结果保存在本机 config.json 中会覆盖这里的默认值。
    base_url: str = "https://api-inference.modelscope.cn/v1"
    api_key: str = ""  # 在「工具 → 设置」中填入你的 API Key
    model: str = "deepseek-ai/DeepSeek-V4.1-Flash"
    temperature: float = 0.3
    # 单次调用最大输入字符数（粗略阈值，超出则走 map-reduce）
    max_chars_per_chunk: int = 100000


def _default_archive_root() -> str:
    """文件库默认根目录：我的文档\FileCraft（无文档目录则退回用户主目录）。"""
    docs = os.path.join(os.path.expanduser("~"), "Documents")
    if not os.path.isdir(docs):
        docs = os.path.expanduser("~")
    return os.path.join(docs, "FileCraft")


@dataclass
class ArchiveConfig:
    """文件库配置：根目录、当前归档文件夹、自动归档开关与生成历史。

    文件夹结构（全部在 root_dir 下）：
        <根目录>/
        ├── 某文件夹/           ← 导入的源文件直接存放
        │   └── 总结/           ← 由该文件夹内文件生成的总结产物
        └── 另一个文件夹/...
    """
    root_dir: str = field(default_factory=_default_archive_root)
    # 当前选中的归档文件夹（相对 root_dir 的路径，"" 表示根目录本身）
    active_folder: str = ""
    # 导入文件时自动复制一份到当前归档文件夹
    auto_import: bool = True
    # 生成/保存总结文件时自动复制一份到来源文件夹的「总结」子夹
    auto_summary: bool = True
    # 生成过的总结产物记录，项: {"path": str, "time": str, "folder": str}
    history: list = field(default_factory=list)


@dataclass
class AppConfig:
    llm: LLMConfig = field(default_factory=LLMConfig)
    archive: ArchiveConfig = field(default_factory=ArchiveConfig)
    # 上次使用的输出目录
    last_output_dir: str = ""


def load_config() -> AppConfig:
    if os.path.exists(CONFIG_PATH):
        try:
            with open(CONFIG_PATH, "r", encoding="utf-8") as f:
                data = json.load(f)
            llm_data = data.get("llm", {})
            llm = LLMConfig(**{k: llm_data.get(k, v) for k, v in LLMConfig().__dict__.items()})
            # 文件库配置：旧版 config.json 没有 root_dir 时，从旧版
            # import_dir（…/FileCraft/导入文件）推导根目录，保证旧文件不丢
            a_data = data.get("archive", {})
            a_def = ArchiveConfig()
            root = a_data.get("root_dir", "")
            if not root:
                old_import = a_data.get("import_dir", "")
                root = os.path.dirname(old_import) if old_import else a_def.root_dir
            archive = ArchiveConfig(
                root_dir=root,
                active_folder=a_data.get("active_folder", ""),
                auto_import=a_data.get("auto_import", a_def.auto_import),
                auto_summary=a_data.get("auto_summary", a_def.auto_summary),
                history=a_data.get("history", []),
            )
            return AppConfig(
                llm=llm,
                archive=archive,
                last_output_dir=data.get("last_output_dir", ""),
            )
        except Exception:
            pass
    return AppConfig()


def save_config(cfg: AppConfig) -> None:
    os.makedirs(CONFIG_DIR, exist_ok=True)
    data = asdict(cfg)
    with open(CONFIG_PATH, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)
