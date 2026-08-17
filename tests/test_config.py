#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""M1 pytest 验收：config.yaml 加载 + 校验"""
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "app"))

from config import load_config  # noqa: E402

CONFIG = Path(__file__).resolve().parent.parent / "config.yaml"


@pytest.fixture(scope="module")
def cfg():
    return load_config(CONFIG)


def test_datasources_not_empty(cfg):
    assert len(cfg.datasources) >= 1


def test_datasource_fields(cfg):
    for ds in cfg.datasources:
        assert ds.path, f"数据源 {ds.name} 缺 path"
        assert ds.format in ("markdown", "docx", "text"), f"{ds.name} 格式非法"


def test_default_datasources_present(cfg):
    names = [ds.name for ds in cfg.datasources]
    assert "llm-wiki-methods" in names
    assert "system-wiki" in names


def test_search_config(cfg):
    assert cfg.search.top_k_default > 0
    assert 0 < cfg.search.threshold < 1
    assert cfg.search.rrf_k_vector > 0
    assert cfg.search.rrf_k_bm25 > 0


def test_auto_watch_config(cfg):
    assert cfg.auto_watch.mode in ("polling", "manual")
    assert cfg.auto_watch.interval_sec > 0


def test_server_config(cfg):
    assert cfg.server.port > 0
    assert cfg.server.workers >= 1


def test_data_paths_resolved(cfg):
    assert cfg.data.chroma_dir.endswith("chroma")
    assert cfg.data.chunks_json.endswith("chunks.json")
    assert cfg.data.manifest.endswith("manifest.json")


def test_embedding_config(cfg):
    assert cfg.embedding.model
    assert cfg.embedding.dim > 0
