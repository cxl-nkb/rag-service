#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""V3-2 pytest 验收：局部增量重建（只重处理变更文件，不整库重建）"""
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "app"))

from config import Config, DataSourceConfig, DataConfig, SearchConfig, EmbeddingConfig  # noqa: E402
from ingest import Ingestor, file_hash, path_id  # noqa: E402
from search import Retriever  # noqa: E402


@pytest.fixture()
def setup(tmp_path):
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


def test_full_rebuild_assigns_stable_ids(setup):
    src, ingestor, retriever = setup
    (src / "a.md").write_text("# 文档 A\n\n内容 A", encoding="utf-8")
    r = ingestor.full_rebuild()
    assert r["mode"] == "full"
    assert r["total_chunks"] == 1
    # id 应为 文件前缀-idx 格式
    cid = retriever._chunks[0]["id"]
    assert "-0" in cid


def test_incremental_partial_add(setup):
    src, ingestor, retriever = setup
    (src / "a.md").write_text("# 文档 A\n\n内容 A", encoding="utf-8")
    ingestor.full_rebuild()
    (src / "b.md").write_text("# 文档 B\n\n内容 B", encoding="utf-8")
    r = ingestor.incremental_update()
    assert r["mode"] == "partial", "新增文件应走局部更新"
    assert r["added"] == 1
    assert r["updated"] == 1
    assert r["total_chunks"] == 2


def test_incremental_partial_change_replaces(setup):
    src, ingestor, retriever = setup
    f = src / "a.md"
    f.write_text("# 文档 A\n\n版本1", encoding="utf-8")
    ingestor.full_rebuild()
    old_ids = retriever._chunks[0]["id"]
    f.write_text("# 文档 A\n\n版本2 版本2", encoding="utf-8")
    r = ingestor.incremental_update()
    assert r["mode"] == "partial"
    assert r["removed"] == 1  # 旧 chunk 被删
    assert r["added"] == 1    # 新 chunk 加入
    assert r["total_chunks"] == 1
    # 新 id 应与旧 id 相同前缀（同文件）但内容已更新
    new_id = retriever._chunks[0]["id"]
    assert new_id.split("-")[0] == old_ids.split("-")[0]


def test_incremental_partial_removed(setup):
    src, ingestor, retriever = setup
    (src / "a.md").write_text("# 文档 A\n\n内容 A", encoding="utf-8")
    ingestor.full_rebuild()
    (src / "a.md").unlink()
    r = ingestor.incremental_update()
    assert r["mode"] == "partial"
    assert r["removed"] == 1
    assert r["total_chunks"] == 0


def test_search_works_after_partial(setup):
    """局部更新后检索仍可用且命中新内容"""
    src, ingestor, retriever = setup
    (src / "a.md").write_text("# 常绿笔记\n\n常绿笔记是原子化观点笔记", encoding="utf-8")
    ingestor.full_rebuild()
    (src / "b.md").write_text("# PARA 方法\n\nPARA 按可行动性分类", encoding="utf-8")
    ingestor.incremental_update()

    r1 = retriever.search("常绿笔记是什么", top_k=2)
    assert r1["hits"], "原内容应可检索"
    r2 = retriever.search("PARA 方法", top_k=2)
    assert r2["hits"], "新增内容应可检索"
    assert any("PARA" in h["text"] for h in r2["hits"])
