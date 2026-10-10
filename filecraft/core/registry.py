"""按文件扩展名分发到对应 converter。"""
from __future__ import annotations

import os
from typing import Optional

from .converters import (
    ConversionError,
    Converter,
    DocxConverter,
    PdfConverter,
    PptxConverter,
    XlsxConverter,
)

#: 支持的扩展名（小写，含点）
SUPPORTED_EXTENSIONS: tuple[str, ...] = (
    ".docx",
    ".pptx",
    ".xlsx",
    ".pdf",
)

#: 扩展名 -> converter 实例
_CONVERTERS: dict[str, Converter] = {}


def _register(converter: Converter) -> None:
    for ext in converter.extensions:
        _CONVERTERS[ext.lower()] = converter


_register(DocxConverter())
_register(PptxConverter())
_register(XlsxConverter())
_register(PdfConverter())


def get_converter(path: str) -> Optional[Converter]:
    ext = os.path.splitext(path)[1].lower()
    return _CONVERTERS.get(ext)


def is_supported(path: str) -> bool:
    ext = os.path.splitext(path)[1].lower()
    return ext in SUPPORTED_EXTENSIONS


def convert_file(path: str) -> str:
    """把指定文件转为 markdown 字符串。

    Raises:
        ConversionError: 不支持或转换失败。
    """
    conv = get_converter(path)
    if conv is None:
        ext = os.path.splitext(path)[1]
        raise ConversionError(f"不支持的格式 {ext or '(无扩展名)'}，仅支持 {', '.join(SUPPORTED_EXTENSIONS)}")
    return conv.convert(path)
