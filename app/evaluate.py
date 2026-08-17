#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""评测模块：加载评测集 → 批量检索 → 计算命中率与明细"""
from pathlib import Path
from typing import Dict, List, Optional

import yaml

from search import Retriever


class Evaluator:
    def __init__(self, retriever: Retriever, eval_set_path: str | Path):
        self.retriever = retriever
        self.eval_set_path = Path(eval_set_path)

    def load_eval_set(self) -> List[Dict]:
        if not self.eval_set_path.exists():
            raise FileNotFoundError(f"评测集不存在: {self.eval_set_path}")
        raw = yaml.safe_load(self.eval_set_path.read_text(encoding="utf-8")) or {}
        items = raw.get("eval_set", [])
        if not items:
            raise ValueError("评测集为空")
        return items

    def evaluate(self, top_k: int = 3, threshold: Optional[float] = None) -> Dict:
        items = self.load_eval_set()
        details = []
        hits = 0
        for item in items:
            q = item["query"]
            expect = item["expect"]
            result = self.retriever.search(q, top_k=top_k, threshold=threshold)
            hit_files = [h["file"] for h in result["hits"]]
            hit = any(expect in (f or "") for f in hit_files)
            hits += 1 if hit else 0
            details.append({
                "query": q,
                "expect": expect,
                "hit": hit,
                "top_files": hit_files[:top_k],
                "filtered": result["filtered"],
            })
        return {
            "total": len(items),
            "hits": hits,
            "hit_rate": round(hits / len(items), 4),
            "top_k": top_k,
            "details": details,
        }
