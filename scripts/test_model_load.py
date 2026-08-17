#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""诊断：BGE 模型加载路径与耗时（确认是否需联网）"""
import os
import time

os.environ["HF_ENDPOINT"] = "https://hf-mirror.com"
os.environ["HF_HUB_DISABLE_XET"] = "1"

print("HOME:", os.environ.get("HOME"))
print("XDG_CACHE_HOME:", os.environ.get("XDG_CACHE_HOME"))

t0 = time.time()
from fastembed import TextEmbedding  # noqa: E402
model = TextEmbedding("BAAI/bge-small-zh-v1.5")
t1 = time.time()
print(f"模型实例化耗时: {t1-t0:.1f}s")

vec = list(model.embed(["测试一下"]))
print(f"embedding OK, dim={len(vec[0])}, 总耗时 {time.time()-t0:.1f}s")
