"""Markdown -> PDF 渲染。

使用 reportlab Platypus 直接把 markdown 结构渲染为 PDF。
相比 html 中转方案，reportlab 可以通过 pdfmetrics 注册系统 TTF 字体，
在 Windows 上对中文支持最稳定，且无任何外部运行库依赖。
"""
from __future__ import annotations

import os
import re

#: 常见 Windows 中文字体（正常体, 粗体）。
#: 注意不要用 simsunb.ttf —— 那是 SimSun-ExtB，只含扩展区生僻字，常规汉字会缺字。
#: 末尾附 Linux 常见中文字体（filecraft-web 服务器部署用），Windows 上不会走到。
_CJK_FONT_CANDIDATES = [
    (r"C:\Windows\Fonts\msyh.ttc", r"C:\Windows\Fonts\msyhbd.ttc"),      # 微软雅黑
    (r"C:\Windows\Fonts\simhei.ttf", r"C:\Windows\Fonts\simhei.ttf"),    # 黑体（无粗体，退化）
    (r"C:\Windows\Fonts\simkai.ttf", r"C:\Windows\Fonts\simkai.ttf"),    # 楷体（无粗体，退化）
    (r"C:\Windows\Fonts\simsun.ttc", r"C:\Windows\Fonts\simsun.ttc"),    # 宋体（无粗体，退化）
    # Linux（Debian/Ubuntu）：apt install fonts-noto-cjk 或 fonts-wqy-zenhei
    ("/usr/share/fonts/opentype/noto/NotoSansCJK-Regular.ttc",
     "/usr/share/fonts/opentype/noto/NotoSansCJK-Bold.ttc"),             # Noto Sans CJK
    ("/usr/share/fonts/truetype/wqy/wqy-zenhei.ttc",
     "/usr/share/fonts/truetype/wqy/wqy-zenhei.ttc"),                    # 文泉驿正黑
    ("/usr/share/fonts/truetype/wqy/wqy-microhei.ttc",
     "/usr/share/fonts/truetype/wqy/wqy-microhei.ttc"),                  # 文泉驿微米黑
]

_FONT_NORMAL = "FileCraftCJK"
_FONT_BOLD = "FileCraftCJKBold"
_FONT_MONO = "FileCraftCJKMono"

_registered = False


def pick_cjk_font() -> str | None:
    """返回可用的中文正常体字体路径，找不到返回 None。"""
    for normal_path, _bold_path in _CJK_FONT_CANDIDATES:
        if os.path.exists(normal_path):
            return normal_path
    return None


def _find_linux_cjk_fonts() -> list[tuple[str, str]]:
    """最后兜底：在 /usr/share/fonts 下递归搜中文字体，返回全部候选。

    顺序上把 TrueType 的文泉驿放在 CFF 的 Noto CJK 之前——
    reportlab 的 TTFont 只支持 TrueType 轮廓，CFF OTC 注册会失败，
    所以把可能失败的 Noto 排后面，让 _register_fonts 逐个尝试降级。
    """
    import glob

    patterns = [
        "/usr/share/fonts/**/wqy-microhei*",
        "/usr/share/fonts/**/wqy-zenhei*",
        "/usr/share/fonts/**/wqy*",
        "/usr/share/fonts/**/*NotoSansCJK*Regular*",
        "/usr/share/fonts/**/*notosanscjk*regular*",
        "/usr/share/fonts/**/*CJK*",
        "/usr/share/fonts/**/*cjk*",
    ]
    seen: set[str] = set()
    out: list[tuple[str, str]] = []
    for pat in patterns:
        for p in sorted(glob.glob(pat, recursive=True)):
            if p.lower().endswith((".ttc", ".ttf", ".otf")) and p not in seen:
                seen.add(p)
                out.append((p, p))  # 无独立粗体文件，用同一文件退化
    return out


def _register_fonts() -> bool:
    """注册中文字体，返回是否成功。"""
    global _registered
    if _registered:
        return True
    try:
        from reportlab.pdfbase import pdfmetrics
        from reportlab.pdfbase.ttfonts import TTFont
    except ImportError:
        return False

    candidates = list(_CJK_FONT_CANDIDATES)
    if not any(os.path.exists(n) for n, _b in candidates):
        candidates.extend(_find_linux_cjk_fonts())

    for normal_path, bold_path in candidates:
        if not os.path.exists(normal_path):
            continue
        try:
            pdfmetrics.registerFont(TTFont(_FONT_NORMAL, normal_path))
        except Exception:
            continue
        # 粗体：优先粗体文件，退化用正常体
        if os.path.exists(bold_path):
            try:
                pdfmetrics.registerFont(TTFont(_FONT_BOLD, bold_path))
            except Exception:
                pdfmetrics.registerFont(TTFont(_FONT_BOLD, normal_path))
        else:
            pdfmetrics.registerFont(TTFont(_FONT_BOLD, normal_path))
        # 等宽（代码块）复用中文字体，保证中文能渲染
        pdfmetrics.registerFont(TTFont(_FONT_MONO, normal_path))
        pdfmetrics.registerFontFamily(
            _FONT_NORMAL,
            normal=_FONT_NORMAL,
            bold=_FONT_BOLD,
            italic=_FONT_NORMAL,
            boldItalic=_FONT_BOLD,
        )
        _registered = True
        return True
    return False


def _esc(text: str) -> str:
    """转义 reportlab 段落标记中的 XML 特殊字符。"""
    return text.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")


def _inline(text: str) -> str:
    """把 markdown 行内标记转换为 reportlab 支持的标签。"""
    t = _esc(text)
    # 行内代码 `code`
    t = re.sub(r"`([^`]+)`", r'<font face="%s" size="9.5">\1</font>' % _FONT_MONO, t)
    # 加粗 **text** 或 __text__
    t = re.sub(r"\*\*([^*]+)\*\*", r"<b>\1</b>", t)
    t = re.sub(r"__([^_]+)__", r"<b>\1</b>", t)
    # 斜体 *text*（避免误伤已处理的 **）
    t = re.sub(r"(?<!\*)\*([^*\n]+)\*(?!\*)", r"<i>\1</i>", t)
    # 链接 [text](url) -> text (url)
    t = re.sub(r"\[([^\]]+)\]\(([^)]+)\)", r'\1 (\2)', t)
    return t


def _split_table_row(line: str) -> list[str]:
    """按未转义的 | 切分表格行。"""
    line = line.strip()
    if line.startswith("|"):
        line = line[1:]
    if line.endswith("|"):
        line = line[:-1]
    # 用占位符保护 \|
    parts = re.split(r"(?<!\\)\|", line)
    return [p.replace("\\|", "|").strip() for p in parts]


def _is_table_sep(line: str) -> bool:
    s = line.strip()
    if not s.startswith("|") and "|" not in s:
        return False
    cells = _split_table_row(s)
    return all(re.fullmatch(r":?-{2,}:?", c) for c in cells if c != "")


class _MdRenderer:
    """把 markdown 文本解析成 reportlab flowables。"""

    def __init__(self):
        from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
        from reportlab.lib.units import cm

        self.cm = cm
        base = getSampleStyleSheet()
        self.styles = {
            "h1": ParagraphStyle(
                "h1", parent=base["Heading1"], fontName=_FONT_BOLD,
                fontSize=19, leading=26, spaceBefore=14, spaceAfter=8,
                textColor="#1a3a6b",
            ),
            "h2": ParagraphStyle(
                "h2", parent=base["Heading2"], fontName=_FONT_BOLD,
                fontSize=15, leading=22, spaceBefore=12, spaceAfter=6,
                textColor="#1a3a6b",
            ),
            "h3": ParagraphStyle(
                "h3", parent=base["Heading3"], fontName=_FONT_BOLD,
                fontSize=12.5, leading=19, spaceBefore=10, spaceAfter=4,
                textColor="#23477d",
            ),
            "h4": ParagraphStyle(
                "h4", parent=base["Heading4"], fontName=_FONT_BOLD,
                fontSize=11, leading=17, spaceBefore=8, spaceAfter=3,
                textColor="#23477d",
            ),
            "body": ParagraphStyle(
                "body", parent=base["BodyText"], fontName=_FONT_NORMAL,
                fontSize=10.5, leading=17, spaceBefore=3, spaceAfter=3,
            ),
            "li": ParagraphStyle(
                "li", parent=base["BodyText"], fontName=_FONT_NORMAL,
                fontSize=10.5, leading=17, leftIndent=16, bulletIndent=4,
                spaceBefore=1, spaceAfter=1,
            ),
            "quote": ParagraphStyle(
                "quote", parent=base["BodyText"], fontName=_FONT_NORMAL,
                fontSize=10, leading=16, leftIndent=14, textColor="#555555",
                spaceBefore=3, spaceAfter=3,
            ),
            "pre": ParagraphStyle(
                "pre", parent=base["Code"], fontName=_FONT_MONO,
                fontSize=9, leading=13.5, leftIndent=10, spaceBefore=4,
                spaceAfter=4, backColor="#f5f5f5", borderPadding=6,
            ),
        }

    def render(self, md_text: str) -> list:
        from reportlab.lib.styles import ParagraphStyle
        from reportlab.platypus import HRFlowable, Paragraph, Preformatted, Spacer, Table, TableStyle

        lines = md_text.replace("\r\n", "\n").replace("\r", "\n").split("\n")
        flow: list = []
        i = 0
        n = len(lines)

        while i < n:
            line = lines[i]
            stripped = line.strip()

            # 空行
            if not stripped:
                i += 1
                continue

            # 代码块
            if stripped.startswith("```"):
                i += 1
                buf: list[str] = []
                while i < n and not lines[i].strip().startswith("```"):
                    buf.append(lines[i])
                    i += 1
                i += 1  # 跳过结束 ```
                if buf:
                    flow.append(Preformatted("\n".join(buf), self.styles["pre"]))
                    flow.append(Spacer(1, 4))
                continue

            # 分隔线
            if re.fullmatch(r"(-{3,}|\*{3,}|_{3,})", stripped):
                flow.append(Spacer(1, 4))
                flow.append(HRFlowable(width="100%", thickness=0.6, color="#cccccc"))
                flow.append(Spacer(1, 6))
                i += 1
                continue

            # 表格
            if "|" in stripped and i + 1 < n and _is_table_sep(lines[i + 1]):
                header = _split_table_row(stripped)
                i += 2
                rows: list[list[str]] = []
                while i < n and "|" in lines[i] and lines[i].strip():
                    rows.append(_split_table_row(lines[i]))
                    i += 1
                flow.append(self._make_table(header, rows, Paragraph, Table, TableStyle))
                flow.append(Spacer(1, 6))
                continue

            # 标题
            m = re.match(r"^(#{1,6})\s+(.*)$", stripped)
            if m:
                level = len(m.group(1))
                key = f"h{min(level, 4)}"
                flow.append(Paragraph(_inline(m.group(2)), self.styles[key]))
                i += 1
                continue

            # 引用
            if stripped.startswith(">"):
                buf = []
                while i < n and lines[i].strip().startswith(">"):
                    buf.append(lines[i].strip().lstrip(">").strip())
                    i += 1
                flow.append(Paragraph(_inline(" ".join(buf)), self.styles["quote"]))
                continue

            # 列表
            m_ul = re.match(r"^(\s*)[-*+]\s+(.*)$", line)
            m_ol = re.match(r"^(\s*)\d+[.)]\s+(.*)$", line)
            if m_ul or m_ol:
                style = self.styles["li"]
                while i < n:
                    cur = lines[i]
                    mu = re.match(r"^(\s*)[-*+]\s+(.*)$", cur)
                    mo = re.match(r"^(\s*)\d+[.)]\s+(.*)$", cur)
                    if not (mu or mo):
                        break
                    indent = len((mu or mo).group(1))
                    text = (mu or mo).group(2)
                    bullet = "•" if mu else "–"
                    st = style if indent == 0 else ParagraphStyle(
                        f"li{indent}", parent=style,
                        leftIndent=16 + indent * 10,
                        bulletIndent=4 + indent * 10,
                    )
                    flow.append(Paragraph(_inline(text), st, bulletText=bullet))
                    i += 1
                flow.append(Spacer(1, 3))
                continue

            # 普通段落（合并连续行）
            buf = [stripped]
            i += 1
            while i < n:
                nxt = lines[i].strip()
                if (not nxt or nxt.startswith(("#", ">", "```", "|"))
                        or re.match(r"^(\s*)([-*+]|\d+[.)])\s+", lines[i])
                        or re.fullmatch(r"(-{3,}|\*{3,}|_{3,})", nxt)):
                    break
                buf.append(nxt)
                i += 1
            flow.append(Paragraph(_inline(" ".join(buf)), self.styles["body"]))

        return flow

    def _make_table(self, header, rows, Paragraph, Table, TableStyle):
        col_count = len(header)
        norm_rows = []
        for r in rows:
            r = list(r) + [""] * (col_count - len(r))
            norm_rows.append(r[:col_count])

        data = [[Paragraph(_inline(c), self.styles["body"]) for c in header]]
        for r in norm_rows:
            data.append([Paragraph(_inline(c), self.styles["body"]) for c in r])

        avail = 17.0 * self.cm  # A4 宽度减去页边距
        col_w = [avail / col_count] * col_count
        tbl = Table(data, colWidths=col_w, repeatRows=1)
        tbl.setStyle(TableStyle([
            ("BACKGROUND", (0, 0), (-1, 0), "#eef2f8"),
            ("GRID", (0, 0), (-1, -1), 0.5, "#bbbbbb"),
            ("VALIGN", (0, 0), (-1, -1), "TOP"),
            ("LEFTPADDING", (0, 0), (-1, -1), 5),
            ("RIGHTPADDING", (0, 0), (-1, -1), 5),
            ("TOPPADDING", (0, 0), (-1, -1), 4),
            ("BOTTOMPADDING", (0, 0), (-1, -1), 4),
        ]))
        return tbl


def markdown_to_pdf(md_text: str, pdf_path: str, title: str = "文档总结") -> str:
    """把 markdown 文本渲染为 PDF，返回生成的 pdf 路径。

    Raises:
        RuntimeError: 渲染失败。
    """
    try:
        from reportlab.lib.pagesizes import A4
        from reportlab.lib.units import cm
        from reportlab.platypus import SimpleDocTemplate
    except ImportError as e:
        raise RuntimeError("缺少 reportlab 库") from e

    if not _register_fonts():
        raise RuntimeError(
            "未找到可用的中文字体。请确认系统存在 C:\\Windows\\Fonts\\simhei.ttf 等中文字体。"
        )

    renderer = _MdRenderer()
    flow = renderer.render(md_text)

    def _on_page(canvas, doc):
        canvas.saveState()
        canvas.setFont(_FONT_NORMAL, 8.5)
        canvas.setFillColorRGB(0.53, 0.53, 0.53)
        canvas.drawCentredString(A4[0] / 2, 1.3 * cm, str(doc.page))
        # 页眉标题
        canvas.drawString(2 * cm, A4[1] - 1.45 * cm, title)
        canvas.setStrokeColorRGB(0.85, 0.85, 0.85)
        canvas.setLineWidth(0.5)
        canvas.line(2 * cm, A4[1] - 1.55 * cm, A4[0] - 2 * cm, A4[1] - 1.55 * cm)
        canvas.restoreState()

    try:
        doc = SimpleDocTemplate(
            pdf_path,
            pagesize=A4,
            leftMargin=2 * cm,
            rightMargin=2 * cm,
            topMargin=2.2 * cm,
            bottomMargin=1.8 * cm,
            title=title,
            author="FileCraft",
        )
        doc.build(flow, onFirstPage=_on_page, onLaterPages=_on_page)
    except Exception as e:
        raise RuntimeError(f"PDF 生成失败: {e}") from e
    return pdf_path