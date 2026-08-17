#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""文本解析器：通用兜底，按空行分段（每段一个 chunk，或整文件）"""
from pathlib import Path
from typing import List

from parsers.base import BaseParser, Chunk


class TextParser(BaseParser):
    format_name = "text"

    def parse(self, path: Path) -> List[Chunk]:
        text = path.read_text(encoding="utf-8", errors="ignore").strip()
        if not text:
            return []
        # 按空行分段；每段限长 800 字符（超出按句子折半）
        chunks = []
        segments = [s.strip() for s in text.split("\n\n") if s.strip()]
        for i, seg in enumerate(segments):
            while len(seg) > 800:
                cut = seg.rfind("。", 0, 800)
                if cut < 400:
                    cut = 800
                chunks.append(Chunk(text=f"【{path.stem}】\n{seg[:cut+1]}", file=path.stem, section=""))
                seg = seg[cut + 1:].strip()
            if seg:
                chunks.append(Chunk(text=f"【{path.stem}】\n{seg}", file=path.stem, section=""))
        return chunks
