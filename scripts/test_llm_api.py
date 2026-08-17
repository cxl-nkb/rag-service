#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""测试可用 LLM API（OpenAI 兼容端点），返回最小生成结果"""
import os
import sys
import urllib.request
import json


def try_openai():
    key = os.environ.get("OPENAI_API_KEY")
    if not key:
        return None, "无 OPENAI_API_KEY"
    url = "https://api.openai.com/v1/chat/completions"
    body = json.dumps({
        "model": "gpt-4o-mini",
        "messages": [{"role": "user", "content": "只回复：OK"}],
        "max_tokens": 5,
    }).encode()
    req = urllib.request.Request(url, data=body, headers={
        "Authorization": f"Bearer {key}", "Content-Type": "application/json"})
    try:
        with urllib.request.urlopen(req, timeout=20) as r:
            d = json.loads(r.read())
            return "OK", d["choices"][0]["message"]["content"].strip()
    except Exception as e:
        return None, f"openai 失败: {type(e).__name__}: {e}"


def try_mm():
    key = os.environ.get("MM_API_KEY")
    if not key:
        return None, "无 MM_API_KEY"
    url = "https://api.minimax.chat/v1/text/chatcompletion_v2"
    body = json.dumps({
        "model": "MiniMax-Text-01",
        "messages": [{"role": "user", "content": "只回复：OK"}],
        "max_tokens": 5,
    }).encode()
    req = urllib.request.Request(url, data=body, headers={
        "Authorization": f"Bearer {key}", "Content-Type": "application/json"})
    try:
        with urllib.request.urlopen(req, timeout=20) as r:
            d = json.loads(r.read())
            return "OK", d.get("choices", [{}])[0].get("message", {}).get("content", "").strip()
    except Exception as e:
        return None, f"minimax 失败: {type(e).__name__}: {e}"


if __name__ == "__main__":
    for name, fn in [("OPENAI", try_openai), ("MINIMAX", try_mm)]:
        ok, msg = fn()
        print(f"{name}: {ok if ok else '不可用'} — {msg if not ok else msg[:50]}")
