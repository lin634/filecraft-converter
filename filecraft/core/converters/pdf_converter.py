"""PDF (.pdf) -> Markdown 转换器。仅支持文本型 PDF，不支持扫描件。"""
from __future__ import annotations

import os

from .base import ConversionError, Converter


class PdfConverter(Converter):
    extensions = (".pdf",)

    def convert(self, path: str) -> str:
        try:
            import pdfplumber
        except ImportError as e:
            raise ConversionError("缺少 pdfplumber 库") from e

        title = os.path.splitext(os.path.basename(path))[0]
        lines: list[str] = [f"# {title}", ""]

        try:
            with pdfplumber.open(path) as pdf:
                for i, page in enumerate(pdf.pages, start=1):
                    lines.append(f"## 第 {i} 页")
                    lines.append("")
                    text = page.extract_text() or ""
                    text = self._clean(text)
                    if text:
                        lines.append(text)
                        lines.append("")
                    # 尝试提取表格
                    try:
                        tables = page.extract_tables()
                    except Exception:
                        tables = []
                    for tbl in tables:
                        md_tbl = self._table_to_md(tbl)
                        if md_tbl:
                            lines.append(md_tbl)
                            lines.append("")
                    lines.append("---")
                    lines.append("")
        except Exception as e:
            raise ConversionError(f"PDF 解析失败: {e}") from e

        return "\n".join(lines).strip() + "\n"

    def _table_to_md(self, table) -> str:
        rows: list[list[str]] = []
        col_count = 0
        for raw in table:
            cells = [self._clean(c) if c is not None else "" for c in raw]
            col_count = max(col_count, len(cells))
            rows.append(cells)
        if not rows:
            return ""
        for r in rows:
            while len(r) < col_count:
                r.append("")
        out = []
        for i, r in enumerate(rows):
            out.append("| " + " | ".join(self._md_escape(c) for c in r) + " |")
            if i == 0:
                out.append("|" + "|".join(["---"] * col_count) + "|")
        return "\n".join(out)
