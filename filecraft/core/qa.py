"""基于文档的问答引擎。

把勾选文件的内容作为上下文，支持多轮追问。
约束模型只依据文档内容回答，没有依据时明确说明，避免编造。
"""
from __future__ import annotations

from typing import List, Optional

from config import LLMConfig

#: 保留的最近对话轮数（一问一答算一轮）
MAX_HISTORY_TURNS = 6

#: 上下文总字符上限（超出时按比例截断每个文件）
CONTEXT_CAP = 150_000


class QAError(Exception):
    pass


class QAEngine:
    SYSTEM_PROMPT = (
        "你是基于用户文档的问答助手。请只依据下面提供的文档内容回答问题；"
        "如果文档中没有相关信息，请明确回答「文档中未提及」，不要编造。"
        "回答使用中文，简洁准确；涉及数据时注明来自哪个文档。"
    )

    def __init__(self, cfg: LLMConfig):
        self.cfg = cfg
        self._client = None

    @property
    def client(self):
        if self._client is None:
            try:
                from openai import OpenAI
            except ImportError as e:
                raise QAError("缺少 openai 库") from e
            self._client = OpenAI(base_url=self.cfg.base_url, api_key=self.cfg.api_key)
        return self._client

    # ---- 上下文 --------------------------------------------------------
    @staticmethod
    def build_context(files: List[tuple[str, str]], cap: int = CONTEXT_CAP) -> str:
        """files: [(文件名, markdown 文本)]，拼接为带分隔头的上下文。

        总量超过 cap 时按比例截断每个文件，并在末尾注明。
        """
        parts = [f"=== 文档：{name} ===\n{md}" for name, md in files]
        total = sum(len(p) for p in parts)
        if total <= cap or not parts:
            return "\n\n".join(parts)

        # 按比例分配额度
        quota = max(500, cap // len(parts))
        trimmed = []
        for name, md in files:
            seg = f"=== 文档：{name} ===\n{md}"
            if len(seg) > quota:
                seg = seg[:quota] + "\n…（因篇幅限制已截断）"
            trimmed.append(seg)
        note = f"\n\n（注意：文档总内容超过 {cap} 字符，以上为按比例截断后的内容）"
        return "\n\n".join(trimmed) + note

    # ---- 问答 ----------------------------------------------------------
    def ask(
        self,
        question: str,
        files: List[tuple[str, str]],
        history: Optional[List[dict]] = None,
    ) -> str:
        """回答一个关于文档的问题。history 为之前的问答对列表。"""
        if not files:
            raise QAError("没有提供文档")
        question = (question or "").strip()
        if not question:
            raise QAError("问题不能为空")
        if not self.cfg.api_key:
            raise QAError("未配置 API Key，请在设置中填写")

        context = self.build_context(files)
        messages: List[dict] = [
            {"role": "system", "content": self.SYSTEM_PROMPT},
            {"role": "user", "content": "以下是可供提问的文档内容：\n\n" + context},
        ]
        # 最近几轮问答，支持追问
        for h in (history or [])[-MAX_HISTORY_TURNS * 2:]:
            role = h.get("role")
            if role in ("user", "assistant") and h.get("content"):
                messages.append({"role": role, "content": h["content"]})
        messages.append({"role": "user", "content": question})

        try:
            resp = self.client.chat.completions.create(
                model=self.cfg.model,
                temperature=self.cfg.temperature,
                messages=messages,
            )
        except Exception as e:  # noqa: BLE001 - 统一转为 QAError 给界面展示
            raise QAError(f"{type(e).__name__}: {e}") from e
        return resp.choices[0].message.content or ""
