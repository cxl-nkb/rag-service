#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""RAG Service V2 — FastAPI 入口
路由：/search /ingest /health /stats
并发：检索核心线程安全（单例模型 + Chroma 锁）；请求无状态天然并行
"""
import logging
import threading
from contextlib import asynccontextmanager
from pathlib import Path
from typing import Optional

from fastapi import FastAPI
from pydantic import BaseModel, Field

import sys
sys.path.insert(0, str(Path(__file__).resolve().parent))

from config import load_config
from ask import AskService
from evaluate import Evaluator
from ingest import Ingestor
from search import Retriever
from watcher import WatchdogWatcher

logger = logging.getLogger("rag-service")
logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")


class SearchRequest(BaseModel):
    query: str = Field(..., min_length=1, max_length=500, description="查询内容")
    top_k: Optional[int] = Field(None, ge=1, le=20, description="返回条数（默认取配置）")


class SearchHit(BaseModel):
    text: str
    file: str
    section: str
    score: float


class SearchResponse(BaseModel):
    hits: list[SearchHit]
    filtered: bool
    query: str


class IngestResponse(BaseModel):
    ok: bool = True
    added: int
    updated: int
    removed: int
    total_chunks: int


class StatsResponse(BaseModel):
    chunk_count: int
    model: str
    chroma_dir: str
    threshold: float
    topic_filter: bool
    auto_watch: dict


# ---------- 全局单例 ----------
retriever: Retriever = None
ingestor: Ingestor = None
evaluator: Evaluator = None
ask_service: AskService = None
cfg = None
_watcher_thread = None
_watchdog: WatchdogWatcher = None
_stop_event = threading.Event()


@asynccontextmanager
async def lifespan(app: FastAPI):
    global retriever, ingestor, evaluator, ask_service, cfg, _watcher_thread
    cfg = load_config()
    retriever = Retriever(cfg)
    ingestor = Ingestor(cfg, retriever)
    ask_service = AskService(retriever)
    eval_set_path = Path(__file__).resolve().parent.parent / "eval_set.yaml"
    evaluator = Evaluator(retriever, eval_set_path)

    # 启动时：若索引不存在则构建一次；否则加载现有 chunks
    if not Path(cfg.data.chunks_json).exists():
        logger.info("首次启动：构建索引…")
        ingestor.full_rebuild()
    else:
        retriever.load_from_chunks_json(cfg.data.chunks_json)
        logger.info(f"索引已加载：{retriever.stats()['chunk_count']} chunks")

    # 启动自动更新（polling 或 watchdog，二选一）
    if cfg.auto_watch.enabled:
        if cfg.auto_watch.mode == "watchdog":
            global _watchdog
            _watchdog = WatchdogWatcher(
                [ds.path for ds in cfg.datasources],
                on_change=lambda: ingestor.incremental_update(),
                debounce_sec=5.0,
            )
            _watchdog.start()
            logger.info("自动更新已启动：watchdog 实时监听")
        elif cfg.auto_watch.mode == "polling":
            _watcher_thread = threading.Thread(target=_polling_loop, daemon=True)
            _watcher_thread.start()
            logger.info(f"自动更新已启动：轮询 {cfg.auto_watch.interval_sec}s")

    yield

    _stop_event.set()
    if _watchdog:
        _watchdog.stop()
    logger.info("服务关闭")


def _polling_loop():
    """后台轮询线程：周期性增量导入"""
    while not _stop_event.is_set():
        _stop_event.wait(cfg.auto_watch.interval_sec)
        if _stop_event.is_set():
            break
        try:
            result = ingestor.incremental_update()
            if result["total_chunks"] > 0:
                logger.info(f"轮询增量：added={result['added']} updated={result['updated']} "
                            f"removed={result['removed']} total={result['total_chunks']}")
        except Exception as e:
            logger.error(f"轮询增量失败: {e}")


app = FastAPI(title="RAG Service V2", version="2.0.0", lifespan=lifespan)


@app.get("/health")
def health():
    return {"status": "ok", "chunks": retriever.stats()["chunk_count"]}


@app.get("/stats", response_model=StatsResponse)
def stats():
    s = retriever.stats()
    return StatsResponse(
        chunk_count=s["chunk_count"], model=s["model"], chroma_dir=s["chroma_dir"],
        threshold=s["threshold"], topic_filter=s["topic_filter"],
        auto_watch={"enabled": cfg.auto_watch.enabled, "mode": cfg.auto_watch.mode,
                    "interval_sec": cfg.auto_watch.interval_sec},
    )


@app.post("/search", response_model=SearchResponse)
def search(req: SearchRequest):
    result = retriever.search(req.query, top_k=req.top_k)
    hits = [SearchHit(**h) for h in result["hits"]]
    return SearchResponse(hits=hits, filtered=result["filtered"], query=req.query)


@app.post("/ingest", response_model=IngestResponse)
def ingest_manual():
    """手动触发全量/增量入库（对应 auto_watch.mode=manual 场景）"""
    result = ingestor.incremental_update()
    return IngestResponse(**result)


class EvalRequest(BaseModel):
    top_k: int = Field(3, ge=1, le=10)


class EvalDetail(BaseModel):
    query: str
    expect: str
    hit: bool
    top_files: list[str]
    filtered: bool


class EvalResponse(BaseModel):
    total: int
    hits: int
    hit_rate: float
    top_k: int
    details: list[EvalDetail]


@app.post("/eval", response_model=EvalResponse)
def run_eval(req: EvalRequest):
    """批量评测：按 eval_set.yaml 的评测集计算命中率与明细"""
    return evaluator.evaluate(top_k=req.top_k)


class AskRequest(BaseModel):
    query: str = Field(..., min_length=1, max_length=500)
    top_k: int = Field(3, ge=1, le=10)


class AskSource(BaseModel):
    file: str
    section: str
    score: float


class AskResponse(BaseModel):
    query: str
    answer: str
    sources: list[AskSource]
    retrieval: dict


# ------------------------------------------------------------
# /ask 为"可选完整模式"（降级）：内置 LLM 汇总需自备 ARK_API_KEY。
# 产品主路径是 /search（检索即服务，供 agent 作为工具集成），
# /ask 仅作为一体化的可选演示，不参与主架构。
# ------------------------------------------------------------
@app.post("/ask", response_model=AskResponse)
def ask(req: AskRequest):
    """[可选] 完整 RAG：检索 + 内置 LLM 汇总（需配置 ARK_API_KEY）。
    主路径请用 /search + agent 自带 LLM 集成（见文档『Agent 集成』）。"""
    return ask_service.ask(req.query, top_k=req.top_k)
