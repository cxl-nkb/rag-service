#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""M3 pytest 验收：FastAPI 路由 + 并发安全（TestClient + 线程并发查询）"""
import sys
import threading
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "app"))


@pytest.fixture(scope="module")
def client():
    from fastapi.testclient import TestClient
    from main import app
    with TestClient(app) as c:
        yield c


def test_health(client):
    r = client.get("/health")
    assert r.status_code == 200
    assert r.json()["status"] == "ok"


def test_stats(client):
    r = client.get("/stats")
    assert r.status_code == 200
    d = r.json()
    assert d["chunk_count"] > 100
    assert d["model"]
    assert d["auto_watch"]["mode"] == "polling"


def test_search_related(client):
    r = client.post("/search", json={"query": "Tiago Forte 的 PARA 方法"})
    assert r.status_code == 200
    d = r.json()
    assert d["hits"], "相关查询应命中"
    assert "Tiago Forte" in d["hits"][0]["file"]


def test_search_unrelated_filtered(client):
    r = client.post("/search", json={"query": "今天北京天气怎么样"})
    d = r.json()
    assert d["filtered"] is True
    assert d["hits"] == []


def test_search_top_k_limit(client):
    r = client.post("/search", json={"query": "常绿笔记", "top_k": 2})
    d = r.json()
    assert len(d["hits"]) <= 2


def test_ingest_manual(client):
    """索引已构建：手动触发增量应为"无变化"快速返回"""
    r = client.post("/ingest")
    assert r.status_code == 200
    d = r.json()
    assert d["ok"] is True
    assert d["total_chunks"] > 100
    assert d["added"] == 0  # 索引已同步，无新增


def test_concurrent_searches_no_cross_talk(client):
    """并发查询：多线程同时查不同问题，结果不应互相串扰"""
    queries = [
        ("Tiago Forte 的 PARA 方法", "Tiago Forte"),
        ("什么是常绿笔记", "Andy Matuschak"),
        ("Simon Willison 的工作流理念", "Simon Willison"),
    ]
    results = [None] * len(queries)
    errors = []

    def worker(idx):
        try:
            r = client.post("/search", json={"query": queries[idx][0]})
            results[idx] = r.json()
        except Exception as e:  # noqa: BLE001
            errors.append((idx, str(e)))

    threads = [threading.Thread(target=worker, args=(i,)) for i in range(len(queries))]
    for t in threads:
        t.start()
    for t in threads:
        t.join()

    assert not errors, f"并发执行出错: {errors}"
    for i, (q, expect) in enumerate(queries):
        assert results[i]["hits"], f"查询{i} 无命中"
        assert expect in results[i]["hits"][0]["file"], f"查询{i} 结果串扰: {results[i]['hits'][0]['file']}"
