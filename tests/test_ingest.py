#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""M4 pytest 验收：增量导入（哈希比对）+ 变更检测"""
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "app"))

from config import Config, DataSourceConfig, DataConfig, SearchConfig, EmbeddingConfig  # noqa: E402
from ingest import Ingestor  # noqa: E402
from search import Retriever  # noqa: E402


@pytest.fixture()
def setup(tmp_path):
    """构造隔离环境：临时数据源 + 独立数据目录"""
    src = tmp_path / "src"
    src.mkdir()
    data_dir = tmp_path / "data"

    ds = DataSourceConfig(name="test-ds", path=str(src), format="markdown")
    cfg = Config(
        datasources=[ds],
        search=SearchConfig(topic_filter=False),
        embedding=EmbeddingConfig(),
        data=DataConfig(
            chroma_dir=str(data_dir / "chroma"),
            chunks_json=str(data_dir / "chunks.json"),
            manifest=str(data_dir / "manifest.json"),
        ),
    )
    retriever = Retriever(cfg)
    ingestor = Ingestor(cfg, retriever)
    return src, ingestor, retriever


def test_full_rebuild_baseline(setup):
    src, ingestor, retriever = setup
    (src / "a.md").write_text("# 文档 A\n\n内容 A 内容 A", encoding="utf-8")
    r = ingestor.full_rebuild()
    assert r["total_chunks"] == 1
    assert retriever.stats()["chunk_count"] == 1


def test_incremental_no_change(setup):
    src, ingestor, retriever = setup
    (src / "a.md").write_text("# 文档 A\n\n内容 A", encoding="utf-8")
    ingestor.full_rebuild()
    r = ingestor.incremental_update()
    assert r["added"] == 0
    assert r["total_chunks"] == 1


def test_incremental_detect_new_file(setup):
    src, ingestor, retriever = setup
    (src / "a.md").write_text("# 文档 A\n\n内容 A", encoding="utf-8")
    ingestor.full_rebuild()
    # 新增文件 → 局部更新：只加新文件 chunk
    (src / "b.md").write_text("# 文档 B\n\n内容 B 内容 B", encoding="utf-8")
    r = ingestor.incremental_update()
    assert r["mode"] == "partial"
    assert r["added"] == 1  # 只加 b.md 的 1 个 chunk
    assert r["total_chunks"] == 2


def test_incremental_detect_change(setup):
    src, ingestor, retriever = setup
    f = src / "a.md"
    f.write_text("# 文档 A\n\n版本1", encoding="utf-8")
    ingestor.full_rebuild()
    # 修改内容 → 哈希变化 → 局部替换（删旧加新）
    f.write_text("# 文档 A\n\n版本2 版本2", encoding="utf-8")
    r = ingestor.incremental_update()
    assert r["mode"] == "partial"
    assert r["updated"] == 1
    assert r["removed"] == 1
    assert r["added"] == 1
    assert r["total_chunks"] == 1


def test_incremental_detect_removed(setup):
    src, ingestor, retriever = setup
    (src / "a.md").write_text("# 文档 A\n\n内容 A", encoding="utf-8")
    ingestor.full_rebuild()
    (src / "a.md").unlink()
    r = ingestor.incremental_update()
    assert r["removed"] == 1
    assert r["total_chunks"] == 0
