"""converters 子包：按文件类型把文档解析为 markdown 文本。"""
from .base import Converter, ConversionError
from .docx_converter import DocxConverter
from .pptx_converter import PptxConverter
from .xlsx_converter import XlsxConverter
from .pdf_converter import PdfConverter

__all__ = [
    "Converter",
    "ConversionError",
    "DocxConverter",
    "PptxConverter",
    "XlsxConverter",
    "PdfConverter",
]
