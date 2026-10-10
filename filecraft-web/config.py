"""filecraft-web 配置：全部来自环境变量（服务器上放 .env），带与桌面版一致的默认值。

core/summarizer.py 与 core/qa.py 会 `from config import LLMConfig`，
本模块提供同名字段的数据类，保证核心代码无需改动即可复用。
"""
from __future__ import annotations

import os
from dataclasses import dataclass, field


def _env(key: str, default: str = "") -> str:
    return os.environ.get(key, default).strip()


def _env_int(key: str, default: int) -> int:
    try:
        return int(os.environ.get(key, "").strip() or default)
    except ValueError:
        return default


#: 项目根目录（server.py 所在目录）
BASE_DIR = os.path.dirname(os.path.abspath(__file__))

#: 上传/生成文件的存储根目录
DATA_DIR = _env("FILECRAFT_DATA_DIR", os.path.join(BASE_DIR, "data"))

#: 监听地址与端口（服务器上必须 127.0.0.1，由 Nginx 反代）
HOST = _env("FILECRAFT_HOST", "127.0.0.1")
PORT = _env_int("FILECRAFT_PORT", 3100)

#: 单文件上传上限（MB）
MAX_FILE_MB = _env_int("FILECRAFT_MAX_FILE_MB", 40)

#: 工作区保留天数（超期未活动自动清理）
WORKSPACE_TTL_DAYS = _env_int("FILECRAFT_WORKSPACE_TTL_DAYS", 7)

#: 每个 IP 每小时最多发起的 AI 调用次数（总结+问答合计，简单限流）
AI_RATE_LIMIT_PER_HOUR = _env_int("FILECRAFT_AI_RATE_LIMIT", 30)

#: core/history_store.py 兼容需要（Web 版不用历史文件，给个无害路径即可）
CONFIG_DIR = os.path.join(DATA_DIR, ".config")


@dataclass
class LLMConfig:
    """与桌面版 config.LLMConfig 字段一致；Web 版从环境变量读取。

    默认值沿用桌面版内置的 ModelScope 配置，使本地开箱可测；
    服务器部署时用 .env 覆盖。
    """

    base_url: str = field(default_factory=lambda: _env(
        "FILECRAFT_LLM_BASE_URL", "https://api-inference.modelscope.cn/v1"))
    api_key: str = field(default_factory=lambda: _env(
        "FILECRAFT_LLM_API_KEY", ""))  # 通过 .env 或环境变量配置你的 API Key
    model: str = field(default_factory=lambda: _env(
        "FILECRAFT_LLM_MODEL", "deepseek-ai/DeepSeek-V4.1-Flash"))
    temperature: float = 0.3
    max_chars_per_chunk: int = 100000


def llm_config() -> LLMConfig:
    return LLMConfig()
