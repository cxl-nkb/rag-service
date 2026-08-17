#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""可靠性核心断言（pytest 版）：检索准确性 / 无匹配 / 边界 / 并发"""
import json
import threading
import urllib.error
import urllib.request

import pytest

BASE = "http://127.0.0.1:8931"


def post(path, body):
    req = urllib.request.Request(BASE + path, data=json.dumps(body).encode(),
                                 headers={"Content-Type": "application/json"})
    with urllib.request.urlopen(req, timeout=30) as r:
        return json.loads(r.read())


@pytest.fixture(scope="module")
def service_ready():
    # 确认服务在线
    for _ in range(10):
        try:
            with urllib.request.urlopen(BASE + "/health", timeout=3) as r:
                return json.loads(r.read())
        except Exception:  # noqa: BLE001
            import time
            time.sleep(1)
    pytest.skip("服务未启动")


ACCURACY_CASES = [
    ("Tiago Forte 的 PARA 方法", "Tiago Forte"),
    ("P8 内容归置的元规则是什么", "P8"),
    ("KV Cache 冷启动税是什么", "KV Cache"),
    ("什么是常绿笔记", "Andy"),
    ("笔记密度为什么比数量重要", "Andy"),
]


@pytest.mark.parametrize("query,expect", ACCURACY_CASES)
def test_search_accuracy(service_ready, query, expect):
    r = post("/search", {"query": query, "top_k": 3})
    assert r["hits"], f"查询应命中: {query}"
    assert any(expect in (h["file"] or "") for h in r["hits"]), \
        f"top hits 应含 {expect}: {[h['file'] for h in r['hits']]}"


UNRELATED = ["今天北京天气", "怎么写一个 Python 快速排序", "推荐一部电影"]


@pytest.mark.parametrize("query", UNRELATED)
def test_unrelated_no_hits(service_ready, query):
    r = post("/search", {"query": query, "top_k": 3})
    assert r["filtered"] is True or len(r["hits"]) == 0, f"无关查询不应命中: {query}"


def test_empty_query_rejected(service_ready):
    with pytest.raises(urllib.error.HTTPError) as e:
        post("/search", {"query": ""})
    assert e.value.code == 422


def test_long_query_rejected(service_ready):
    with pytest.raises(urllib.error.HTTPError) as e:
        post("/search", {"query": "a" * 600})
    assert e.value.code == 422


def test_special_chars_ok(service_ready):
    r = post("/search", {"query": "P8 的 【元规则】 以及 <JIT> 条件？", "top_k": 2})
    assert isinstance(r.get("hits"), list)


def test_concurrent_no_errors(service_ready):
    queries = ["PARA 方法", "常绿笔记", "KV Cache", "P8 规则", "Simon 工作流",
               "Tiago 分类", "密度", "JIT", "MCP 加载", "kanban"]
    outs = [None] * len(queries)
    errs = []

    def worker(i):
        try:
            outs[i] = post("/search", {"query": queries[i], "top_k": 2})
        except Exception as e:  # noqa: BLE001
            errs.append(str(e))

    threads = [threading.Thread(target=worker, args=(i,)) for i in range(len(queries))]
    for t in threads:
        t.start()
    for t in threads:
        t.join()

    assert not errs, f"并发报错: {errs}"
    assert all(o and o.get("hits") for o in outs), "每个并发请求都应有响应"
    # 结果结构完整
    for o in outs:
        for k in ("text", "file", "section", "score"):
            assert k in o["hits"][0], f"结果缺字段 {k}"
