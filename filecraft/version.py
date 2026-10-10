"""软件版本与作者信息——全局唯一定义处，改版本号只改这里。

版本规则（语义化）：
    主版本.次版本.修订号
    - 新增功能        -> 次版本 +1（如 1.1.0）
    - 修复问题/小调整  -> 修订号 +1（如 1.0.1）
"""
APP_NAME = "FileCraft"
APP_VERSION = "1.2.0"
APP_AUTHOR = "gnahihsnil"
APP_TAGLINE = "本地文档转 Markdown 与 AI 总结"


def window_title() -> str:
    return f"{APP_NAME} v{APP_VERSION} — {APP_TAGLINE}"


def about_text() -> str:
    return (
        f"<b>{APP_NAME}</b> v{APP_VERSION} — {APP_TAGLINE}<br>"
        f"作者：{APP_AUTHOR}<br><br>"
    )
