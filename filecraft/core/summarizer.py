"""AI 总结模块：调用 OpenAI 兼容接口，支持长文本 map-reduce。"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Callable, List, Optional

from config import LLMConfig


@dataclass
class FileInfo:
    """一份待总结的文件信息（已转为 markdown）。"""
    name: str
    markdown: str


class Summarizer:
    def __init__(self, cfg: LLMConfig):
        self.cfg = cfg
        self._client = None

    @property
    def client(self):
        if self._client is None:
            try:
                from openai import OpenAI
            except ImportError as e:
                raise RuntimeError("缺少 openai 库") from e
            self._client = OpenAI(
                base_url=self.cfg.base_url,
                api_key=self.cfg.api_key,
            )
        return self._client

    # ---- 单次调用 ------------------------------------------------------
    SYSTEM_PROMPT = (
        "你是一个专业的文档总结助手。请阅读用户提供的多个文档内容，"
        "生成一份结构化的中文总结，使用 Markdown 格式输出，包含："
        "1) 总体概述；2) 各文档要点（按文档名分小节）；3) 关键数据/结论；4) 潜在风险或注意事项。"
        "保持客观、简洁，不要编造原文没有的内容。"
    )

    def _chat(self, user_content: str, system: str = SYSTEM_PROMPT) -> str:
        if not self.cfg.api_key:
            raise ValueError("未配置 API Key，请在设置中填写")
        resp = self.client.chat.completions.create(
            model=self.cfg.model,
            temperature=self.cfg.temperature,
            messages=[
                {"role": "system", "content": system},
                {"role": "user", "content": user_content},
            ],
        )
        return resp.choices[0].message.content or ""

    # ---- 分块 ----------------------------------------------------------
    def _split_chunks(self, files: List[FileInfo]) -> List[str]:
        """把所有文件内容切成不超过 max_chars_per_chunk 的块。"""
        chunks: list[str] = []
        current: list[str] = []
        current_len = 0
        for f in files:
            header = f"\n\n=== 文档：{f.name} ===\n\n"
            body = f.markdown
            segment = header + body
            seg_len = len(segment)
            # 单个文件就超阈值：单独成块，必要时再硬切
            if seg_len > self.cfg.max_chars_per_chunk:
                if current:
                    chunks.append("".join(current))
                    current = []
                    current_len = 0
                # 硬切大文件
                for start in range(0, seg_len, self.cfg.max_chars_per_chunk):
                    chunks.append(segment[start:start + self.cfg.max_chars_per_chunk])
                continue
            if current_len + seg_len > self.cfg.max_chars_per_chunk:
                chunks.append("".join(current))
                current = [segment]
                current_len = seg_len
            else:
                current.append(segment)
                current_len += seg_len
        if current:
            chunks.append("".join(current))
        return chunks

    # ---- 对外接口 ------------------------------------------------------
    def summarize(
        self,
        files: List[FileInfo],
        progress: Optional[Callable[[str], None]] = None,
    ) -> str:
        """对多份文档生成总结，返回 markdown 字符串。

        长文本自动走 map-reduce：先分块各自总结，再合并。
        """
        if not files:
            raise ValueError("没有可总结的文件")

        chunks = self._split_chunks(files)

        if len(chunks) == 1:
            if progress:
                progress("正在生成总结…")
            return self._chat(self._build_user_prompt(files, chunks[0]))

        # map-reduce
        partial_summaries: list[str] = []
        for i, chunk in enumerate(chunks, 1):
            if progress:
                progress(f"正在总结第 {i}/{len(chunks)} 段…")
            prompt = (
                "以下是部分文档内容，请先对这部分做要点总结（Markdown），"
                "保留关键数据和结论，标注该段覆盖的文档名。\n\n" + chunk
            )
            partial_summaries.append(self._chat(prompt, system="你是一个文档要点提取助手，输出中文 Markdown。"))

        if progress:
            progress("正在合并各段总结…")
        merged = "\n\n---\n\n".join(
            f"## 第 {i} 段总结\n\n{s}" for i, s in enumerate(partial_summaries, 1)
        )
        file_names = ", ".join(f.name for f in files)
        final_prompt = (
            f"以下是对 {len(files)} 份文档（{file_names}）分段提取的要点总结。"
            "请合并成一份完整、连贯的最终总结，按总体概述/各文档要点/关键结论/风险注意事项的结构输出 Markdown：\n\n"
            + merged
        )
        return self._chat(final_prompt)

    def _build_user_prompt(self, files: List[FileInfo], content: str) -> str:
        names = ", ".join(f.name for f in files)
        return (
            f"以下是对 {len(files)} 份文档（{names}）的完整内容，请生成结构化中文总结：\n\n"
            + content
        )
