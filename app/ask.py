#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""AskService：检索 → 注入 prompt → LLM 汇总（ARK OpenAI 兼容端点）"""
import json
import os
import urllib.error
import urllib.request
from typing import Dict, List, Optional

from search import Retriever

# ARK 配置（从环境读取，用户配置 ARK_API_KEY 后即生效）
ARK_BASE = "https://ark.cn-beijing.volces.com/api/coding/v3"
ARK_MODEL = "ark-code-latest"


class AskService:
    def __init__(self, retriever: Retriever):
        self.retriever = retriever

    @staticmethod
    def _build_prompt(query: str, hits: List[Dict]) -> List[Dict]:
        """构建注入 prompt：检索结果作为上下文，问题驱动，要求基于来源回答"""
        system = (
            "你是知识库助手。基于提供的检索片段回答用户问题。"
            "要求：\n"
            "1. 优先使用检索片段中的信息回答，可注明来源（文件/章节）\n"
            "2. 检索片段不足或无关时，明确说'知识库中没有相关内容'，不要编造\n"
            "3. 回答简洁、结构化，直接给结论\n"
        )
        if hits:
            ctx = "\n\n".join(
                f"[来源: {h['file']} → {h['section']}]\n{h['text'][:600]}"
                for h in hits
            )
            user = f"【检索片段】\n{ctx}\n\n【问题】{query}\n\n请基于以上检索片段回答。"
        else:
            user = f"【检索片段】无匹配内容\n\n【问题】{query}\n\n知识库中无相关内容时请直接说明。"
        return [
            {"role": "system", "content": system},
            {"role": "user", "content": user},
        ]

    @staticmethod
    def _call_llm(messages: List[Dict]) -> str:
        """调用 ARK（OpenAI 兼容）。无 key 时抛错由调用方处理"""
        key = os.environ.get("ARK_API_KEY")
        if not key:
            raise RuntimeError("ARK_API_KEY 未配置")

        body = json.dumps({
            "model": ARK_MODEL,
            "messages": messages,
            "max_tokens": 1024,
            "temperature": 0.2,
        }).encode()
        req = urllib.request.Request(ARK_BASE + "/chat/completions", data=body, headers={
            "Authorization": f"Bearer {key}",
            "Content-Type": "application/json",
        })
        try:
            with urllib.request.urlopen(req, timeout=60) as r:
                d = json.loads(r.read())
            return d["choices"][0]["message"]["content"].strip()
        except urllib.error.HTTPError as e:
            detail = e.read().decode()[:200]
            raise RuntimeError(f"ARK API 错误 {e.code}: {detail}") from e

    def ask(self, query: str, top_k: int = 3) -> Dict:
        """完整 RAG：检索 → 注入 prompt → LLM 汇总"""
        result = self.retriever.search(query, top_k=top_k)
        hits = result["hits"]
        messages = self._build_prompt(query, hits)
        answer = self._call_llm(messages)
        return {
            "query": query,
            "answer": answer,
            "sources": [{"file": h["file"], "section": h["section"], "score": h["score"]} for h in hits],
            "retrieval": {"hits": len(hits), "filtered": result["filtered"]},
        }
