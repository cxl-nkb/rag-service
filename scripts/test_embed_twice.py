#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""诊断：fastembed 连续多次 embedding 是否卡住"""
import os
import time

os.environ["HF_ENDPOINT"] = "https://hf-mirror.com"
os.environ["HF_HUB_DISABLE_XET"] = "1"

from fastembed import TextEmbedding

t0 = time.time()
model = TextEmbedding("BAAI/bge-small-zh-v1.5")
print(f"实例化: {time.time()-t0:.1f}s")

t0 = time.time()
r1 = list(model.embed(["第一条内容"]))
print(f"embed 1条: {time.time()-t0:.1f}s dim={len(r1[0])}")

t0 = time.time()
r2 = list(model.embed(["第二条内容", "第三条内容"]))
print(f"embed 2条: {time.time()-t0:.1f}s dim={len(r2[0])}")

t0 = time.time()
r3 = list(model.embed(["再次嵌入"]))
print(f"embed 再1条: {time.time()-t0:.1f}s")
print("ALL OK")
