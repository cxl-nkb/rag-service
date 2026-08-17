#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""检索核心：混合检索（向量 + BM25 + RRF）+ 线程安全封装（单例模型/锁）"""
import json
import re
import threading
from pathlib import Path
from typing import Dict, List, Optional

import chromadb
from rank_bm25 import BM25Okapi

from config import Config

# ---------- CJK 分词（与 V1 一致） ----------
def cjk_tokenize(text: str) -> list:
    tokens = []
    for w in re.findall(r"[a-zA-Z0-9][a-zA-Z0-9._\-/]*", text):
        tokens.append(w.lower())
    for han in re.findall(r"[\u4e00-\u9fff]+", text):
        if len(han) <= 4:
            tokens.append(han)
        for i in range(len(han) - 1):
            tokens.append(han[i : i + 2])
        if len(han) > 2:
            tokens.append(han)
    return tokens


# ---------- 主题域过滤（与 V1 一致，可配开关） ----------
TOPIC_KEYWORDS = [
    "wiki", "笔记", "知识", "常绿", "evergreen", "para", "jit",
    "projects", "areas", "archives", "resources", "方法论", "密度",
    "工作流", "tiago", "andy", "simon", "role", "角色", "记忆",
    "决策", "记录", "存储", "分类", "索引", "目录", "引用", "摘抄",
    "原子", "连接", "工具", "分工", "方案", "集成", "触发",
    "kv", "cache", "缓存", "冷启动", "token", "推理", "模型", "prompt",
    "p8", "pattern", "模式", "mcp", "kanban", "hermes", "claude", "codex",
    "agent", "profile", "变量", "协议", "差异", "加载", "早退", "early",
    "评估", "评测", "基准", "测试", "成本", "部署", "windows", "网络",
    "加速", "memory", "环境", "api", "框架", "对比", "结论", "发现",
]


class Retriever:
    """线程安全的混合检索器：模型/Chroma 单例 + 锁保护"""

    def __init__(self, cfg: Config):
        self.cfg = cfg
        self._lock = threading.Lock()
        self._model = None       # embedding 模型单例
        self._client = None      # chroma client 单例
        self._col = None
        self._chunks: List[dict] = []
        self._doc_ids: List[str] = []
        self._bm25 = None

    # ---- 懒加载单例（线程安全） ----
    def _get_model(self):
        if self._model is None:
            import os
            if self.cfg.embedding.hf_endpoint:
                os.environ["HF_ENDPOINT"] = self.cfg.embedding.hf_endpoint
            if self.cfg.embedding.disable_xet:
                os.environ["HF_HUB_DISABLE_XET"] = "1"
            from fastembed import TextEmbedding
            # 限制 onnxruntime 线程数（默认用满所有核 → 内存峰值高）
            self._model = TextEmbedding(self.cfg.embedding.model,
                                        threads=self.cfg.resources.embedding_threads)
        return self._model

    def _get_collection(self):
        if self._col is None:
            from utils.embedding_fn_lib import BGEEmbeddingFunction  # 自定义封装
            self._client = chromadb.PersistentClient(path=self.cfg.data.chroma_dir)
            self._col = self._client.get_or_create_collection(
                "rag-service", embedding_function=BGEEmbeddingFunction(self._get_model()))
        return self._col

    # ---- 索引加载 / 重建 ----
    def load_chunks(self, chunks: List[dict]) -> None:
        """从内存 chunks 重建 BM25（由 ingest 调用）；空语料跳过（rank_bm25 对空集除零）"""
        self._chunks = chunks
        self._doc_ids = [c["id"] for c in chunks]   # 与 chroma id（{file_hash8}-{idx}）统一，RRF 才能真正融合
        self._bm25 = BM25Okapi([cjk_tokenize(c["text"]) for c in chunks]) if chunks else None

    def load_from_chunks_json(self, path: str) -> None:
        p = Path(path)
        if not p.exists():
            raise FileNotFoundError(f"chunks 文件不存在: {path}")
        with open(p, encoding="utf-8") as f:
            chunks = json.load(f)
        self.load_chunks(chunks)

    # ---- 检索（线程安全） ----
    def search(self, query: str, top_k: Optional[int] = None,
               threshold: Optional[float] = None) -> Dict:
        cfg = self.cfg.search
        top_k = top_k or cfg.top_k_default
        threshold = threshold if threshold is not None else cfg.threshold

        # 主题过滤（可配）
        if cfg.topic_filter and not any(kw in query.lower() for kw in TOPIC_KEYWORDS):
            return {"hits": [], "filtered": True}

        with self._lock:  # 保护 chroma + embedding + bm25（共享资源）
            if not self._doc_ids:
                # 懒加载：内存无索引时尝试从 chunks.json 加载（服务重启后首次查询）
                chunks_json = Path(self.cfg.data.chunks_json)
                if chunks_json.exists():
                    self.load_from_chunks_json(str(chunks_json))
                else:
                    return {"hits": [], "filtered": False}
            if self._bm25 is None:
                self.load_from_chunks_json(self.cfg.data.chunks_json)
            col = self._get_collection()
            model = self._get_model()

            # 向量路
            vec = col.query(query_texts=[query], n_results=len(self._doc_ids))
            vec_rank = list(vec["ids"][0])
            # BM25 路
            bm25_scores = self._bm25.get_scores(cjk_tokenize(query))
            bm25_rank = [self._doc_ids[i] for i in sorted(range(len(bm25_scores)), key=lambda i: -bm25_scores[i])]
            # RRF 融合
            k_vec, k_bm25 = cfg.rrf_k_vector, cfg.rrf_k_bm25
            scores: Dict[str, float] = {}
            for rank, did in enumerate(vec_rank):
                scores[did] = scores.get(did, 0.0) + 1.0 / (k_vec + rank + 1)
            for rank, did in enumerate(bm25_rank):
                scores[did] = scores.get(did, 0.0) + 1.0 / (k_bm25 + rank + 1)
            fused = sorted(scores.items(), key=lambda x: -x[1])

        # 阈值过滤 + 组装结果（锁外组装，减少持锁时间）
        hits = []
        for did, score in fused:
            if score < threshold:
                break
            idx = self._doc_ids.index(did)
            c = self._chunks[idx]
            hits.append({
                "text": c["text"], "file": c["file"], "section": c["section"],
                "score": round(score, 4),
            })
            if len(hits) >= top_k:
                break
        return {"hits": hits, "filtered": False}

    def stats(self) -> Dict:
        return {
            "chunk_count": len(self._chunks),
            "model": self.cfg.embedding.model,
            "chroma_dir": self.cfg.data.chroma_dir,
            "threshold": self.cfg.search.threshold,
            "topic_filter": self.cfg.search.topic_filter,
        }
