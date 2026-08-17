#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""配置加载：YAML + 校验 + 默认值"""
from __future__ import annotations

import os
from dataclasses import dataclass, field
from pathlib import Path
from typing import List, Optional

import yaml

DEFAULT_CONFIG_PATH = Path(__file__).resolve().parent.parent / "config.yaml"


@dataclass
class DataSourceConfig:
    name: str
    path: str
    format: str = "markdown"
    include: List[str] = field(default_factory=list)
    exclude: List[str] = field(default_factory=list)


@dataclass
class SearchConfig:
    top_k_default: int = 3
    threshold: float = 0.15
    rrf_k_vector: int = 10
    rrf_k_bm25: int = 3
    topic_filter: bool = True


@dataclass
class EmbeddingConfig:
    model: str = "BAAI/bge-small-zh-v1.5"
    dim: int = 512
    hf_endpoint: str = "https://hf-mirror.com"
    disable_xet: bool = True


@dataclass
class AutoWatchConfig:
    enabled: bool = True
    mode: str = "polling"  # polling | watchdog | manual
    interval_sec: int = 60
    debounce_sec: float = 5.0   # watchdog 防抖秒数
    incremental: bool = True


@dataclass
class ServerConfig:
    host: str = "127.0.0.1"
    port: int = 8931
    workers: int = 1
    log_level: str = "info"


@dataclass
class ResourcesConfig:
    """资源限制（可配置，控制内存/CPU 占用）"""
    embedding_threads: int = 2    # onnxruntime 推理线程数（越大越快但越吃内存）
    memory_max: str = "2G"        # systemd MemoryMax（install.sh 生成 Drop-in 时写入）
    embedding_batch: int = 32     # 批量 embedding 的批次大小（降低峰值内存）


@dataclass
class DataConfig:
    chroma_dir: str = "data/chroma"
    chunks_json: str = "data/chunks.json"
    manifest: str = "data/manifest.json"


@dataclass
class Config:
    datasources: List[DataSourceConfig]
    search: SearchConfig = field(default_factory=SearchConfig)
    embedding: EmbeddingConfig = field(default_factory=EmbeddingConfig)
    auto_watch: AutoWatchConfig = field(default_factory=AutoWatchConfig)
    server: ServerConfig = field(default_factory=ServerConfig)
    data: DataConfig = field(default_factory=DataConfig)
    resources: ResourcesConfig = field(default_factory=ResourcesConfig)

    def resolve_paths(self, base: Path | None = None) -> None:
        """将相对路径解析为绝对路径"""
        base = base or Path(__file__).resolve().parent.parent
        for ds in self.datasources:
            p = Path(ds.path)
            if not p.is_absolute():
                ds.path = str(base / p)
        for attr in ("chroma_dir", "chunks_json", "manifest"):
            p = Path(getattr(self.data, attr))
            if not p.is_absolute():
                setattr(self.data, attr, str(base / p))


def load_config(path: str | Path | None = None) -> Config:
    # 支持 RAG_CONFIG 环境变量指定配置文件（systemd/部署场景）
    if path is None:
        path = os.environ.get("RAG_CONFIG") or DEFAULT_CONFIG_PATH
    path = Path(path) if path else DEFAULT_CONFIG_PATH
    if not path.exists():
        raise FileNotFoundError(f"配置文件不存在: {path}")

    raw = yaml.safe_load(path.read_text(encoding="utf-8")) or {}

    # 数据源
    dss = []
    for item in raw.get("datasources", []):
        name = item.get("name") or item.get("path")
        if not name:
            raise ValueError("数据源必须含 name 或 path")
        dss.append(DataSourceConfig(
            name=name,
            path=item["path"],
            format=item.get("format", "markdown"),
            include=item.get("include", []),
            exclude=item.get("exclude", []),
        ))
    if not dss:
        raise ValueError("config.yaml 至少需要一个数据源")

    # 检索
    s = raw.get("search", {})
    search = SearchConfig(
        top_k_default=s.get("top_k_default", 3),
        threshold=s.get("threshold", 0.15),
        rrf_k_vector=s.get("rrf_k_vector", 10),
        rrf_k_bm25=s.get("rrf_k_bm25", 3),
        topic_filter=s.get("topic_filter", True),
    )

    # Embedding
    e = raw.get("embedding", {})
    embedding = EmbeddingConfig(
        model=e.get("model", "BAAI/bge-small-zh-v1.5"),
        dim=e.get("dim", 512),
        hf_endpoint=e.get("hf_endpoint", "https://hf-mirror.com"),
        disable_xet=e.get("disable_xet", True),
    )

    # 自动更新
    aw = raw.get("auto_watch", {})
    mode = aw.get("mode", "polling")
    if mode not in ("polling", "watchdog", "manual"):
        raise ValueError(f"auto_watch.mode 非法: {mode}（支持 polling/watchdog/manual）")
    auto_watch = AutoWatchConfig(
        enabled=aw.get("enabled", True),
        mode=mode,
        interval_sec=aw.get("interval_sec", 60),
        debounce_sec=aw.get("debounce_sec", 5.0),
        incremental=aw.get("incremental", True),
    )

    # 服务
    sv = raw.get("server", {})
    server = ServerConfig(
        host=sv.get("host", "127.0.0.1"),
        port=sv.get("port", 8931),
        workers=sv.get("workers", 1),
        log_level=sv.get("log_level", "info"),
    )

    # 资源限制
    rs = raw.get("resources", {})
    resources = ResourcesConfig(
        embedding_threads=rs.get("embedding_threads", 2),
        memory_max=rs.get("memory_max", "2G"),
        embedding_batch=rs.get("embedding_batch", 32),
    )

    # 数据目录
    d = raw.get("data", {})
    data = DataConfig(
        chroma_dir=d.get("chroma_dir", "data/chroma"),
        chunks_json=d.get("chunks_json", "data/chunks.json"),
        manifest=d.get("manifest", "data/manifest.json"),
    )

    cfg = Config(datasources=dss, search=search, embedding=embedding,
                 auto_watch=auto_watch, server=server, data=data,
                 resources=resources)
    cfg.resolve_paths()

    # RAG_DATA 环境变量覆盖数据目录（标准部署：/var/lib/rag-service）
    rag_data = os.environ.get("RAG_DATA")
    if rag_data:
        cfg.data.chroma_dir = os.path.join(rag_data, "chroma")
        cfg.data.chunks_json = os.path.join(rag_data, "chunks.json")
        cfg.data.manifest = os.path.join(rag_data, "manifest.json")
    return cfg


if __name__ == "__main__":
    import json
    c = load_config()
    print("✅ 配置加载成功")
    print("数据源:")
    for ds in c.datasources:
        print(f"  - {ds.name}: {ds.path} ({ds.format})")
    print(json.dumps({
        "search": c.search.__dict__,
        "server": c.server.__dict__,
        "auto_watch": c.auto_watch.__dict__,
    }, ensure_ascii=False, indent=2))
