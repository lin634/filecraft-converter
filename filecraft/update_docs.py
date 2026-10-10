"""使用文档自动更新。

每次重新打包（build.bat 会自动调用本脚本）都会执行：
1. 用 version.py 的版本号 / 作者刷新文档头部的版本行
2. 把 docs/CHANGELOG.md 同步为文档末尾的「更新日志」章节
3. 用软件内置引擎重新生成 docs/FileCraft 使用文档.pdf

用法：python update_docs.py
"""
from __future__ import annotations

import os
import re
import sys

_HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, _HERE)

from version import APP_AUTHOR, APP_VERSION  # noqa: E402

DOCS_DIR = os.path.join(_HERE, "docs")
MD_PATH = os.path.join(DOCS_DIR, "FileCraft 使用文档.md")
PDF_PATH = os.path.join(DOCS_DIR, "FileCraft 使用文档.pdf")
CHANGELOG_PATH = os.path.join(DOCS_DIR, "CHANGELOG.md")

#: 文档头部版本行（行首引用块）
_VERSION_LINE_RE = re.compile(r"^> 版本 .* · 作者 .*$", re.M)
#: 文档中已有的「更新日志」章节：它是文档最后一章，因此一直替换到文件末尾。
#: （曾经用"到下一个二级标题"的匹配，结果 CHANGELOG 里的版本条目也是二级标题，
#:   导致每次同步都在尾部追加一份全量日志——重复 v1.0.0 出现了 5 次。）
_CHANGELOG_SECTION_RE = re.compile(r"^## 七、更新日志[\s\S]*$", re.M)

_CHANGELOG_HEADING = "## 七、更新日志"


def _fail(msg: str) -> None:
    print(f"[update_docs] {msg}")
    raise SystemExit(1)


def _check_no_duplicate_sections(md: str) -> None:
    """文档级校验：二级标题不允许重复，防止再出现章节堆积。"""
    heads = re.findall(r"^## (.+)$", md, re.M)
    dupes = sorted({h for h in heads if heads.count(h) > 1})
    if dupes:
        _fail(f"文档存在重复章节，请先手工清理：{dupes}")


def stamp_version(md: str) -> str:
    """把文档头部的版本行刷成 version.py 的当前值。"""
    line = f"> 版本 v{APP_VERSION} · 作者 {APP_AUTHOR}"
    if _VERSION_LINE_RE.search(md):
        return _VERSION_LINE_RE.sub(line, md, count=1)
    # 没有版本行（首行标题后）补一条
    return re.sub(r"^(# .*\n)", rf"\1\n{line}\n", md, count=1)


def sync_changelog(md: str) -> str:
    """把 CHANGELOG.md 的内容作为文档末尾的「更新日志」章节。"""
    if not os.path.exists(CHANGELOG_PATH):
        print("[update_docs] 未找到 CHANGELOG.md，跳过更新日志章节")
        return md
    with open(CHANGELOG_PATH, "r", encoding="utf-8") as f:
        changelog = f.read().strip()
    # 去掉日志文件自身的一级标题，避免和文档标题重复
    changelog = re.sub(r"^# 更新日志\s*\n+", "", changelog)
    section = f"{_CHANGELOG_HEADING}\n\n{changelog}\n"
    if _CHANGELOG_SECTION_RE.search(md):
        return _CHANGELOG_SECTION_RE.sub(section, md, count=1)
    return md.rstrip() + "\n\n" + section


def main() -> int:
    if not os.path.exists(MD_PATH):
        _fail(f"未找到使用文档：{MD_PATH}")

    with open(MD_PATH, "r", encoding="utf-8") as f:
        md = f.read()
    original = md

    md = stamp_version(md)
    md = sync_changelog(md)
    _check_no_duplicate_sections(md)

    if md != original:
        with open(MD_PATH, "w", encoding="utf-8") as f:
            f.write(md)
        print(f"[update_docs] Markdown 已更新（v{APP_VERSION}）")
    else:
        print(f"[update_docs] Markdown 无需变更（v{APP_VERSION}）")

    from core.md_to_pdf import markdown_to_pdf

    markdown_to_pdf(md, PDF_PATH, title=f"FileCraft 使用文档 v{APP_VERSION}")
    size = os.path.getsize(PDF_PATH)
    print(f"[update_docs] PDF 已重新生成：{PDF_PATH}（{size} 字节）")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
