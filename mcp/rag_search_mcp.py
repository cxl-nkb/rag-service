#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""rag-service MCP server：供 DeepCode 等 MCP 客户端调用本地检索服务。

工具：
  knowledge_search(query, top_k=3)  → 调 rag-service /search，返回命中的知识片段

部署（注册到 DeepCode settings.json）：
  "mcpServers": {
    "rag-service": {
      "command": "/root/ubuntu-manage/chat/venv-rag/bin/python",
      "args": ["/opt/rag-service/mcp/rag_search_mcp.py"],
      "timeout": 60000
    }
  }
"""
import json
import os
import urllib.request

from mcp.server.fastmcp import FastMCP

# rag-service 检索端点（标准部署 8931；开发可用 127.0.0.1）
RAG_BASE = os.environ.get("RAG_BASE", "http://127.0.0.1:8931")

mcp = FastMCP("rag-service")


def _search(query: str, top_k: int) -> dict:
    req = urllib.request.Request(
        RAG_BASE + "/search",
        data=json.dumps({"query": query, "top_k": top_k}).encode(),
        headers={"Content-Type": "application/json"},
    )
    with urllib.request.urlopen(req, timeout=30) as r:
        return json.loads(r.read())


@mcp.tool()
def knowledge_search(query: str, top_k: int = 3) -> str:
    """查询本地 llm-wiki 知识库（方法论/P8 规则/系统概念）。

    当用户问题可能涉及个人知识库、过往记录、笔记方法论时调用；
    命中返回知识片段（含来源），供回答引用；无命中返回"未匹配"。
    """
    try:
        result = _search(query, top_k)
    except Exception as e:  # noqa: BLE001
        return f"[检索失败] {e}"

    hits = result.get("hits") or []
    if not hits:
        return "[未匹配] 知识库无相关内容"

    lines = [f"命中 {len(hits)} 条（来自本地知识库）："]
    for i, h in enumerate(hits, 1):
        text = h["text"].replace("\n", " ")[:300]
        lines.append(f"{i}. [来源:{h['file']}→{h['section']}] {text}")
    return "\n".join(lines)


if __name__ == "__main__":
    mcp.run()
