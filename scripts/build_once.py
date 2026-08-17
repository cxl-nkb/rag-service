#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""一次性构建索引：解析数据源 → 切分 → embedding 入库 → 写 chunks/manifest
用法: ./venv-rag/bin/python rag-service/scripts/build_once.py
"""
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "app"))

from config import load_config  # noqa: E402
from ingest import Ingestor  # noqa: E402
from search import Retriever  # noqa: E402

if __name__ == "__main__":
    cfg = load_config()
    retriever = Retriever(cfg)
    ingestor = Ingestor(cfg, retriever)

    t0 = time.time()
    print("开始全量构建…")
    result = ingestor.full_rebuild()
    print(f"✅ 构建完成: total_chunks={result['total_chunks']} 耗时 {time.time()-t0:.0f}s")
    print(f"   chunks: {cfg.data.chunks_json}")
    print(f"   chroma: {cfg.data.chroma_dir}")
