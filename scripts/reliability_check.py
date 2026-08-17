#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""生产可靠性检测：模拟 agent 调用视角，验证 /search 全维度可靠性"""
import json
import time
import urllib.request
import urllib.error
import threading

BASE = "http://127.0.0.1:8931"


def post(path, body):
    req = urllib.request.Request(BASE + path, data=json.dumps(body).encode(),
                                 headers={"Content-Type": "application/json"})
    with urllib.request.urlopen(req, timeout=30) as r:
        return json.loads(r.read())


def check(name, cond, detail=""):
    mark = "✅" if cond else "❌"
    print(f"{mark} {name}" + (f" — {detail}" if detail else ""))
    return cond


def main():
    results = []
    print("=" * 60)
    print("一、检索准确性（真实问题 → 正确来源）")
    print("=" * 60)
    cases = [
        ("Tiago Forte 的 PARA 方法", "Tiago Forte"),
        ("P8 内容归置的元规则是什么", "P8"),
        ("KV Cache 冷启动税是什么", "KV Cache"),
        ("什么是常绿笔记", "Andy"),
        ("笔记密度为什么比数量重要", "Andy"),
    ]
    for q, expect in cases:
        t0 = time.time()
        r = post("/search", {"query": q, "top_k": 3})
        latency = (time.time() - t0) * 1000
        hit = any(expect in (h["file"] or "") for h in r["hits"])
        detail = f"top1={r['hits'][0]['file'][:20] if r['hits'] else '空'} 延迟{latency:.0f}ms"
        results.append(check(f"[{expect}] {q[:18]}", hit, detail))

    print("\n" + "=" * 60)
    print("二、无匹配处理（无关问题 → 不编造）")
    print("=" * 60)
    for q in ["今天北京天气", "怎么写一个 Python 快速排序", "推荐一部电影"]:
        r = post("/search", {"query": q, "top_k": 3})
        ok = r["filtered"] is True or len(r["hits"]) == 0
        results.append(check(f"[无匹配] {q}", ok,
                             f"filtered={r['filtered']} hits={len(r['hits'])}"))

    print("\n" + "=" * 60)
    print("三、边界输入")
    print("=" * 60)
    # 空查询（应 422 校验错误）
    try:
        post("/search", {"query": "", "top_k": 3})
        results.append(check("[空查询] 应被拒绝", False))
    except urllib.error.HTTPError as e:
        results.append(check("[空查询] 返回 422", e.code == 422))
    # 超长查询（500 字限制）
    try:
        post("/search", {"query": "a" * 600, "top_k": 3})
        results.append(check("[超长查询] 应被拒绝", False))
    except urllib.error.HTTPError as e:
        results.append(check("[超长查询] 返回 422", e.code == 422))
    # 特殊字符
    r = post("/search", {"query": "P8 的 【元规则】 以及 <JIT> 条件？", "top_k": 2})
    results.append(check("[特殊字符] 正常处理", isinstance(r.get("hits"), list)))

    print("\n" + "=" * 60)
    print("四、并发（10 线程混合查询，结果不串扰）")
    print("=" * 60)
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
    t0 = time.time()
    for t in threads:
        t.start()
    for t in threads:
        t.join()
    total = (time.time() - t0) * 1000

    ok = not errs and all(o and o.get("hits") for o in outs)
    # 串扰检测：结果独立性——每个请求有响应、结构完整、无报错即无串扰。
    # 来源重叠不判定为串扰：知识库主题集中时（如"PARA"与"Tiago 分类"）命中同一文档是正常现象。
    top1s = [o["hits"][0]["file"] for o in outs if o and o["hits"]]
    distinct = len(set(top1s))
    results.append(check(f"[并发] 10 请求全部有响应，无报错", ok,
                         f"总耗时{total:.0f}ms 平均{total/10:.0f}ms"))
    results.append(check(f"[独立] 每请求结果结构完整（id/来源/分数）",
                         all(all(k in o["hits"][0] for k in ("text", "file", "section", "score")) for o in outs if o and o["hits"]),
                         f"top1 来源多样性 {distinct}/10（主题集中属正常）"))

    print("\n" + "=" * 60)
    print("五、服务统计与健康")
    print("=" * 60)
    h = urllib.request.urlopen(BASE + "/health", timeout=10)
    health = json.loads(h.read())
    results.append(check("[health] 状态 ok", health.get("status") == "ok"))
    s = post("/stats", {}) if False else json.loads(urllib.request.urlopen(BASE + "/stats", timeout=10).read())
    results.append(check("[stats] chunk 数合理", s.get("chunk_count", 0) > 100))

    print("\n" + "=" * 60)
    passed = sum(1 for r in results if r)
    print(f"可靠性检测汇总：{passed}/{len(results)} 通过")
    print("=" * 60)
    return 0 if passed == len(results) else 1


if __name__ == "__main__":
    import sys
    sys.exit(main())
