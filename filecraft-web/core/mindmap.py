"""Markdown -> 思维导图 HTML（markmap 渲染，完全离线）。

前端依赖 d3 与 markmap-view 已打包在 assets/markmap 下，生成的 HTML
把它们内联进去，双击即可在浏览器打开，无需联网。
解析器只提取结构：标题(#..######) 与无序/有序列表（按缩进嵌套），
表格行折叠为一个节点，其余段落作为当前层级的叶子节点。
"""
from __future__ import annotations

import json
import os
import re
import sys

#: 思维导图最大节点数，防止超大文档卡死浏览器
MAX_NODES = 1500


def _assets_dir() -> str:
    if getattr(sys, "frozen", False):
        base = sys._MEIPASS  # type: ignore[attr-defined]
    else:
        base = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    return os.path.join(base, "assets", "markmap")


def _read_asset(name: str) -> str | None:
    p = os.path.join(_assets_dir(), name)
    if os.path.exists(p):
        try:
            with open(p, "r", encoding="utf-8") as f:
                return f.read()
        except OSError:
            return None
    return None


def _esc(s: str) -> str:
    return s.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")


def _strip_inline(s: str) -> str:
    # 图片 -> 仅保留 alt；链接 -> 仅保留文字；去掉加粗/斜体/代码标记
    s = re.sub(r"!\[([^\]]*)\]\(([^)]*)\)", r"\1", s)
    s = re.sub(r"\[([^\]]+)\]\(([^)]*)\)", r"\1", s)
    s = s.replace("**", "").replace("__", "").replace("`", "")
    s = re.sub(r"[*_]{1,3}([^*_]+)[*_]{1,3}", r"\1", s)
    return s.strip()


def _cap_nodes(node: dict, limit: int) -> None:
    """超限时截断子树，保证浏览器流畅。"""
    count = 0

    def walk(n: dict):
        nonlocal count
        count += 1
        if count > limit:
            n["children"] = []
            return
        kids = n.get("children", [])
        kept = 0
        for c in kids:
            if count >= limit:
                break
            walk(c)
            kept += 1
        if kept < len(kids):
            n["children"] = kids[:kept] + (
                [{"content": "…（已截断）", "children": []}] if kept < len(kids) else []
            )

    walk(node)


def md_to_tree(md_text: str, fallback_title: str = "思维导图") -> dict:
    """把 markdown 解析成 markmap 节点树 {content, children}。"""
    lines = md_text.replace("\r\n", "\n").split("\n")
    root: dict = {"content": "", "children": []}
    stack: list[tuple[int, dict]] = [(0, root)]
    last_h = 0
    in_code = False

    for raw in lines:
        stripped = raw.strip()
        if stripped.startswith("```"):
            in_code = not in_code
            continue
        if in_code or not stripped:
            continue

        # 标题
        m = re.match(r"^(#{1,6})\s+(.*)$", stripped)
        if m:
            level = len(m.group(1))
            text = _esc(_strip_inline(m.group(2)))
            if level == 1 and not root["content"]:
                root["content"] = text
                last_h = 1
                continue
            node = {"content": text or " ", "children": []}
            while stack and stack[-1][0] >= level:
                stack.pop()
            stack[-1][1]["children"].append(node)
            stack.append((level, node))
            last_h = level
            continue

        # 表格行 -> 折叠为一个节点
        if stripped.startswith("|"):
            cells = [c.strip() for c in stripped.strip("|").split("|")]
            cells = [c for c in cells if c and not re.fullmatch(r":?-{2,}:?", c)]
            if cells:
                text = _esc(" / ".join(cells))
                level = last_h + 1
                while len(stack) > 1 and stack[-1][0] >= level:
                    stack.pop()
                node = {"content": text, "children": []}
                stack[-1][1]["children"].append(node)
            continue

        # 列表（按缩进嵌套）
        m_ul = re.match(r"^(\s*)[-*+]\s+(.*)$", raw)
        m_ol = re.match(r"^(\s*)\d+[.)]\s+(.*)$", raw)
        if m_ul or m_ol:
            lead = (m_ul or m_ol).group(1)
            units = sum(1 if ch == "\t" else 0.5 for ch in lead)
            level = last_h + 1 + int(units)
            text = _esc(_strip_inline((m_ul or m_ol).group(2)))
            if not text:
                continue
            while len(stack) > 1 and stack[-1][0] >= level:
                stack.pop()
            node = {"content": text, "children": []}
            stack[-1][1]["children"].append(node)
            stack.append((level, node))
            continue

        # 引用/普通段落 -> 当前层级叶子
        m_bq = re.match(r"^>\s?(.*)$", stripped)
        para = _esc(_strip_inline(m_bq.group(1) if m_bq else stripped))
        if not para:
            continue
        level = last_h + 1
        while len(stack) > 1 and stack[-1][0] >= level:
            stack.pop()
        stack[-1][1]["children"].append({"content": para, "children": []})

    if not root["content"]:
        root["content"] = _esc(fallback_title)
    if not root["children"]:
        root["children"] = [{"content": "（无内容）", "children": []}]
    _cap_nodes(root, MAX_NODES)
    return root


def markdown_to_mindmap_html(md_text: str, out_path: str, title: str = "思维导图") -> str:
    """生成可在浏览器直接打开的思维导图 HTML，返回文件路径。"""
    data = md_to_tree(md_text, fallback_title=title)

    d3 = _read_asset("d3.min.js")
    view = _read_asset("markmap-view.js")
    if d3 and view:
        # 内联脚本：只处理 </script 提前结束的风险
        safe = lambda s: re.sub(r"</(script)", r"<\\/\1", s, flags=re.I)  # noqa: E731
        scripts = f"<script>{safe(d3)}</script>\n<script>{safe(view)}</script>"
    else:
        # 本地资源缺失时退化为 CDN（打开时需要联网）
        scripts = (
            '<script src="https://cdn.jsdelivr.net/npm/d3@7"></script>\n'
            '<script src="https://cdn.jsdelivr.net/npm/markmap-view@0.18"></script>'
        )

    payload = json.dumps(data, ensure_ascii=False).replace("</", "<\\/")

    html = f"""<!DOCTYPE html>
<html lang="zh-CN">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>{_esc(title)}</title>
<style>
  html, body {{ margin: 0; padding: 0; height: 100%; background: #F5F5F7; }}
  #mindmap {{ width: 100vw; height: 100vh; display: block; }}
  .mm-title {{
    position: fixed; top: 14px; left: 18px;
    font-family: "Microsoft YaHei", sans-serif; font-size: 15px;
    color: #6E6E73; background: rgba(255,255,255,.85);
    padding: 6px 14px; border-radius: 14px;
    border: 1px solid #E5E5EA; pointer-events: none;
  }}
  svg .markmap-node text {{ font-family: "Microsoft YaHei", sans-serif; }}
</style>
{scripts}
</head>
<body>
<div class="mm-title">{_esc(title)}（滚轮缩放，拖拽平移，点击折叠）</div>
<svg id="mindmap"></svg>
<script>
const data = {payload};
markmap.Markmap.create(
  document.getElementById('mindmap'),
  {{ maxWidth: 320, duration: 300, spacingVertical: 8, initialExpandLevel: 3 }},
  data
);
</script>
</body>
</html>
"""
    with open(out_path, "w", encoding="utf-8") as f:
        f.write(html)
    return out_path
