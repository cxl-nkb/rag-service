#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""embedding 封装：接收外部模型实例（单例），避免每次重建"""
from typing import List

from chromadb.api.types import Documents, Embeddings, EmbeddingFunction


class BGEEmbeddingFunction(EmbeddingFunction[Documents]):
    """包一层外部注入的 fastembed 模型实例（进程内单例，线程由调用方锁保护）"""

    def __init__(self, model):
        self._model = model

    def __call__(self, input: Documents) -> Embeddings:
        return [e.tolist() for e in self._model.embed(list(input))]
