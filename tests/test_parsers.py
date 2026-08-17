#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""M2 pytest 验收：Parser 适配层（markdown/docx/text）"""
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "app"))

from config import load_config  # noqa: E402
from datasources import PARSER_REGISTRY, collect_files, get_parser, parse_all_datasources  # noqa: E402

CONFIG = Path(__file__).resolve().parent.parent / "config.yaml"


@pytest.fixture(scope="module")
def cfg():
    return load_config(CONFIG)


def test_parser_registry_has_three_formats():
    assert set(PARSER_REGISTRY) >= {"markdown", "docx", "text"}


def test_parser_instantiation():
    assert get_parser("markdown") is not None
    assert get_parser("docx") is not None
    assert get_parser("text") is not None
    with pytest.raises(ValueError):
        get_parser("pdf")


def test_collect_files_markdown(cfg):
    ds = next(d for d in cfg.datasources if d.name == "llm-wiki-methods")
    files = collect_files(ds)
    assert len(files) > 0, "方法论数据源应能收集到文件"
    assert all(f.suffix in (".md", ".markdown") for f in files)


def test_collect_files_exclude(cfg):
    ds = next(d for d in cfg.datasources if d.name == "system-wiki")
    files = collect_files(ds)
    # 排除规则应生效：不含 .llm-wiki / raw 目录段（文件名含 raw 子串不算排除）
    for f in files:
        parts = f.relative_to(ds.path).parts
        assert ".llm-wiki" not in parts
        assert "raw" not in parts
        assert ".obsidian" not in parts


def test_markdown_parse_produces_chunks(cfg):
    ds = next(d for d in cfg.datasources if d.name == "llm-wiki-methods")
    parser = get_parser("markdown")
    files = collect_files(ds)
    chunks = parser.parse(files[0])
    assert len(chunks) > 0
    assert all(c.text and c.file for c in chunks)


def test_parse_all_datasources(cfg):
    chunks = parse_all_datasources(cfg.datasources)
    assert len(chunks) > 100, "两个数据源应产出 100+ chunk（此前为 638）"
    # chunk 结构完整
    sample = chunks[0]
    assert sample.text and sample.file and hasattr(sample, "section")
