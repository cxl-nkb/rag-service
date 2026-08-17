#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""V3-1 pytest 验收：评测接口 /eval"""
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "app"))

from evaluate import Evaluator  # noqa: E402


@pytest.fixture(scope="module")
def evaluator():
    from config import load_config
    from search import Retriever

    cfg = load_config(Path(__file__).resolve().parent.parent / "config.yaml")
    retriever = Retriever(cfg)
    eval_set_path = Path(__file__).resolve().parent.parent / "eval_set.yaml"
    return Evaluator(retriever, eval_set_path)


def test_eval_set_loads(evaluator):
    items = evaluator.load_eval_set()
    assert len(items) >= 8
    for it in items:
        assert it["query"] and it["expect"]


def test_evaluate_returns_summary(evaluator):
    result = evaluator.evaluate(top_k=3)
    assert result["total"] >= 8
    assert 0 <= result["hit_rate"] <= 1
    assert len(result["details"]) == result["total"]


def test_evaluate_hit_rate_reasonable(evaluator):
    """回归基准：V2 混合检索命中率应 >= 0.75（此前 88%）"""
    result = evaluator.evaluate(top_k=3)
    assert result["hit_rate"] >= 0.75, f"命中率 {result['hit_rate']} 低于基准"


def test_evaluate_top_k_affects_hits(evaluator):
    r3 = evaluator.evaluate(top_k=3)
    r1 = evaluator.evaluate(top_k=1)
    assert r3["hits"] >= r1["hits"]
