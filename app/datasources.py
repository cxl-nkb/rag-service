#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""数据源适配层：按配置遍历文件、过滤、选 parser、产出 Chunk"""
import fnmatch
from pathlib import Path
from typing import Dict, List, Type

from config import DataSourceConfig
from parsers.base import BaseParser, Chunk
from parsers.docx import DocxParser
from parsers.markdown import MarkdownParser
from parsers.text import TextParser

# 格式 → 解析器注册表（新增格式在这里注册）
PARSER_REGISTRY: Dict[str, Type[BaseParser]] = {
    "markdown": MarkdownParser,
    "docx": DocxParser,
    "text": TextParser,
}

# 格式 → 默认 include 通配符（配置未指定时按格式推断）
FORMAT_DEFAULT_INCLUDE = {
    "markdown": ["*.md", "*.markdown"],
    "docx": ["*.docx"],
    "text": ["*.txt", "*.log"],
}


def get_parser(format_name: str) -> BaseParser:
    cls = PARSER_REGISTRY.get(format_name.lower())
    if cls is None:
        raise ValueError(f"不支持的格式: {format_name}（支持: {list(PARSER_REGISTRY)}）")
    return cls()


def collect_files(ds: DataSourceConfig) -> List[Path]:
    """按数据源配置收集文件（include/exclude 通配符过滤）"""
    root = Path(ds.path)
    if not root.exists():
        raise FileNotFoundError(f"数据源路径不存在: {ds.path}")

    includes = ds.include or FORMAT_DEFAULT_INCLUDE.get(ds.format, ["*"])
    excludes = ds.exclude or []

    files = []
    for p in root.rglob("*"):
        if not p.is_file():
            continue
        rel = p.relative_to(root)
        if any(fnmatch.fnmatch(p.name, pat) or fnmatch.fnmatch(str(rel), pat) for pat in excludes):
            continue
        if any(fnmatch.fnmatch(p.name, pat) for pat in includes):
            files.append(p)
    return sorted(files)


def parse_datasource(ds: DataSourceConfig) -> List[Chunk]:
    """解析整个数据源 → Chunk 列表"""
    parser = get_parser(ds.format)
    files = collect_files(ds)
    chunks: List[Chunk] = []
    for f in files:
        try:
            chunks.extend(parser.parse(f))
        except Exception as e:
            print(f"  ⚠️ 解析失败 {f}: {e}")
    return chunks


def parse_all_datasources(dss: List[DataSourceConfig]) -> List[Chunk]:
    all_chunks: List[Chunk] = []
    for ds in dss:
        cs = parse_datasource(ds)
        print(f"  {ds.name}: {len(cs)} chunks（{ds.path}）")
        all_chunks.extend(cs)
    return all_chunks
