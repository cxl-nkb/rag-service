#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Markdown 解析器：按 # / ## / ### 标题切分，chunk = 【标题路径】前缀 + 正文"""
import re
from pathlib import Path
from typing import List

from parsers.base import BaseParser, Chunk


class MarkdownParser(BaseParser):
    format_name = "markdown"

    def parse(self, path: Path) -> List[Chunk]:
        lines = path.read_text(encoding="utf-8").splitlines()
        # 跳过 YAML frontmatter（--- 开头到下一个 ---）
        if lines and lines[0].strip() == "---":
            try:
                end = lines[1:].index("---") + 1
                lines = lines[end + 1:]
            except ValueError:
                pass

        chunks = []
        cur_title = ""
        cur_section = ""
        cur_sub = ""
        buf = []

        def heading_path():
            if cur_sub:
                return f"{cur_title} / {cur_section} / {cur_sub}" if cur_section else f"{cur_title} / {cur_sub}"
            return f"{cur_title} / {cur_section}" if cur_section else cur_title

        def flush():
            if buf:
                text = "\n".join(buf).strip()
                if text:
                    hp = heading_path()
                    chunks.append(Chunk(text=f"【{hp}】\n{text}", file=cur_title or path.stem, section=hp))

        for line in lines:
            m1 = re.match(r"^#\s+(.*)", line)
            m2 = re.match(r"^##\s+(.*)", line)
            m3 = re.match(r"^###\s+(.*)", line)
            if m1:
                flush(); buf = []; cur_title = m1.group(1).strip(); cur_section = ""; cur_sub = ""
            elif m2:
                flush(); buf = []; cur_section = m2.group(1).strip(); cur_sub = ""
            elif m3:
                flush(); buf = []; cur_sub = m3.group(1).strip()
            else:
                buf.append(line)
        flush()

        # 若文件无任何标题（裸文本），整文件作为一个 chunk
        if not chunks:
            text = path.read_text(encoding="utf-8").strip()
            if text:
                chunks.append(Chunk(text=text, file=path.stem, section=""))
        return chunks
