#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Parser 基类：所有格式解析器统一接口"""
from abc import ABC, abstractmethod
from pathlib import Path
from typing import List


class Chunk:
    """一个切分单元"""

    def __init__(self, text: str, file: str, section: str):
        self.text = text
        self.file = file          # 源文件（主标题/文件名）
        self.section = section    # 章节路径

    def to_dict(self):
        return {"text": self.text, "file": self.file, "section": self.section}


class BaseParser(ABC):
    """解析器接口：输入文件路径，输出 Chunk 列表"""

    format_name: str = "base"

    @abstractmethod
    def parse(self, path: Path) -> List[Chunk]:
        raise NotImplementedError

    @classmethod
    def supported_formats(cls) -> list:
        return [cls.format_name]


def build_chunks(path: Path, chunks: List[tuple]) -> List[Chunk]:
    """辅助：把 (text, title, section) 元组列表转成 Chunk 对象"""
    return [Chunk(text=t, file=ti, section=se) for t, ti, se in chunks]
