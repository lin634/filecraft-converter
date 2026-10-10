"""Converter 抽象基类。所有 converter 接收一个文件路径，返回 markdown 字符串。"""
from __future__ import annotations

import abc
from typing import Optional


class ConversionError(Exception):
    """文件转换失败。"""


class Converter(abc.ABC):
    """文档 -> Markdown 转换器基类。"""

    #: 此 converter 处理的扩展名（小写，含点），如 ".docx"
    extensions: tuple[str, ...] = ()

    @abc.abstractmethod
    def convert(self, path: str) -> str:
        """把 path 指向的文件转为 markdown 文本并返回。

        Raises:
            ConversionError: 转换失败时抛出。
        """
        raise NotImplementedError

    @staticmethod
    def _md_escape(text: str) -> str:
        """转义 markdown 中的表格管道符等特殊字符，保留可读性。"""
        return text.replace("|", "\\|")

    @staticmethod
    def _clean(text: Optional[str]) -> str:
        """清理文本：去首尾空白，None -> 空串。"""
        if not text:
            return ""
        return text.strip()
