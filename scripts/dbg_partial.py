#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""调试：局部增量 removed=0 问题"""
import json
import sys
import tempfile
from pathlib import Path

sys.path.insert(0, "/root/ubuntu-manage/chat/rag-service/app")

from config import Config, DataSourceConfig, DataConfig, SearchConfig, EmbeddingConfig
from ingest import Ingestor
from search import Retriever

tmp = Path(tempfile.mkdtemp())
src = tmp / "src"
src.mkdir()
data = tmp / "data"

ds = DataSourceConfig(name="t", path=str(src), format="markdown")
cfg = Config(datasources=[ds], search=SearchConfig(topic_filter=False),
             embedding=EmbeddingConfig(),
             data=DataConfig(chroma_dir=str(data/"c"), chunks_json=str(data/"chunks.json"),
                             manifest=str(data/"manifest.json")))
rt = Retriever(cfg)
ing = Ingestor(cfg, rt)

f = src / "a.md"
f.write_text("# A\n\n版本1", encoding="utf-8")
r1 = ing.full_rebuild()
print("full:", r1)
print("manifest:", json.loads(Path(cfg.data.manifest).read_text()))

f.write_text("# A\n\n版本2 版本2", encoding="utf-8")
r2 = ing.incremental_update()
print("incr:", r2)
print("manifest after:", json.loads(Path(cfg.data.manifest).read_text()))
