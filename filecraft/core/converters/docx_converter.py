"""Word (.docx) -> Markdown 转换器。"""
from __future__ import annotations

from typing import TYPE_CHECKING

from .base import ConversionError, Converter

if TYPE_CHECKING:
    from docx import Document  # noqa: F401
    from docx.table import Table  # noqa: F401


class DocxConverter(Converter):
    extensions = (".docx",)

    def convert(self, path: str) -> str:
        try:
            from docx import Document
            from docx.table import Table
            from docx.text.paragraph import Paragraph
        except ImportError as e:
            raise ConversionError("缺少 python-docx 库，请先 pip install python-docx") from e

        try:
            doc = Document(path)
        except Exception as e:
            raise ConversionError(f"无法打开 docx 文件: {e}") from e

        lines: list[str] = []
        # 标题
        lines.append(f"# {self._get_title(doc, path)}")
        lines.append("")

        for block in self._iter_block_items(doc):
            if isinstance(block, Paragraph):
                md = self._paragraph_to_md(block)
                if md:
                    lines.append(md)
            elif isinstance(block, Table):
                lines.append("")
                lines.append(self._table_to_md(block))
                lines.append("")

        return "\n".join(lines).strip() + "\n"

    # ---- helpers --------------------------------------------------------
    @staticmethod
    def _get_title(doc, path: str) -> str:
        try:
            if doc.core_properties and doc.core_properties.title:
                return doc.core_properties.title.strip()
        except Exception:
            pass
        import os

        return os.path.splitext(os.path.basename(path))[0] or "Untitled"

    @staticmethod
    def _iter_block_items(doc):
        """按文档顺序迭代段落与表格。"""
        from docx.oxml.ns import qn
        from docx.table import Table
        from docx.text.paragraph import Paragraph

        parent_elm = doc.element.body
        for child in parent_elm.iterchildren():
            if child.tag == qn("w:p"):
                yield Paragraph(child, doc)
            elif child.tag == qn("w:tbl"):
                yield Table(child, doc)

    def _paragraph_to_md(self, para) -> str:
        text = self._clean(para.text)
        if not text:
            return ""
        style = (para.style.name or "").lower() if para.style else ""
        if "heading 1" in style:
            return f"## {text}"
        if "heading 2" in style:
            return f"### {text}"
        if "heading 3" in style:
            return f"#### {text}"
        if "heading 4" in style or "heading 5" in style or "heading 6" in style:
            return f"##### {text}"
        if "list" in style:
            return f"- {text}"
        if "title" in style:
            return f"# {text}"
        return text

    def _table_to_md(self, table) -> str:
        rows = []
        for i, row in enumerate(table.rows):
            cells = [self._md_escape(self._clean(c.text)) for c in row.cells]
            rows.append("| " + " | ".join(cells) + " |")
            if i == 0:
                rows.append("|" + "|".join(["---"] * len(cells)) + "|")
        return "\n".join(rows)
