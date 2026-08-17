#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""导入管线：全量重建 + 局部增量更新（只重处理变更文件）

chunk id 方案：{file_hash8}-{idx}（file_hash8 = 文件相对路径 sha256 前 8 位）
→ 局部更新时可精确定位某文件的所有旧 chunk 并替换。
manifest 记录每个文件的 {hash, chunk_ids}，用于删除与增量。
"""
import hashlib
import json
import threading
from pathlib import Path
from typing import Dict, List, Tuple

from config import Config
from datasources import collect_files, get_parser
from search import Retriever


def file_hash(path: Path) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for block in iter(lambda: f.read(65536), b""):
            h.update(block)
    return h.hexdigest()[:16]


def path_id(path: Path, ds_path: Path) -> str:
    """文件稳定 id：相对数据源路径的 sha256 前 8 位"""
    rel = str(path.relative_to(ds_path))
    return hashlib.sha256(rel.encode()).hexdigest()[:8]


class Ingestor:
    def __init__(self, cfg: Config, retriever: Retriever):
        self.cfg = cfg
        self.retriever = retriever
        # RLock：incremental_update 内部可能调用 full_rebuild（嵌套加锁）
        self._ingest_lock = threading.RLock()

    # ---------- manifest ----------
    def _load_manifest(self) -> Dict:
        p = Path(self.cfg.data.manifest)
        if p.exists():
            return json.loads(p.read_text(encoding="utf-8"))
        return {}

    def _save_manifest(self, manifest: Dict) -> None:
        Path(self.cfg.data.manifest).parent.mkdir(parents=True, exist_ok=True)
        Path(self.cfg.data.manifest).write_text(
            json.dumps(manifest, ensure_ascii=False, indent=1), encoding="utf-8")

    # ---------- 全量重建 ----------
    def full_rebuild(self) -> Dict:
        with self._ingest_lock:
            all_chunks = []       # (id, chunk_dict)
            manifest = {}
            for ds in self.cfg.datasources:
                parser = get_parser(ds.format)
                ds_root = Path(ds.path)
                for f in collect_files(ds):
                    fid = path_id(f, ds_root)
                    cs = [c.to_dict() for c in parser.parse(f)]
                    ids = [f"{fid}-{i}" for i in range(len(cs))]
                    for cid, c in zip(ids, cs):
                        c["id"] = cid
                    all_chunks.extend(zip(ids, cs))
                    manifest[str(f)] = {"hash": file_hash(f), "chunk_ids": ids}

            self._write_index(all_chunks)
            self._save_manifest(manifest)
            return {"added": len(all_chunks), "updated": 0, "removed": 0,
                    "total_chunks": len(all_chunks), "mode": "full"}

    # ---------- 局部增量 ----------
    def incremental_update(self) -> Dict:
        with self._ingest_lock:
            manifest = self._load_manifest()
            # 扫描当前文件集合与变更
            changed: List[Tuple[Path, Path]] = []   # (file, ds_root)
            current_keys = set()
            for ds in self.cfg.datasources:
                ds_root = Path(ds.path)
                parser = get_parser(ds.format)
                for f in collect_files(ds):
                    key = str(f)
                    current_keys.add(key)
                    h = file_hash(f)
                    old = manifest.get(key)
                    if old is None or old["hash"] != h:
                        changed.append((f, ds_root))

            removed_keys = [k for k in manifest if k not in current_keys]

            if not changed and not removed_keys:
                if not self.retriever._chunks and Path(self.cfg.data.chunks_json).exists():
                    self.retriever.load_from_chunks_json(self.cfg.data.chunks_json)
                return {"added": 0, "updated": 0, "removed": 0,
                        "total_chunks": len(self.retriever._chunks), "mode": "none"}

            # 局部更新：只处理变更/删除文件
            return self._apply_partial(changed, removed_keys, manifest, current_keys)

    def _apply_partial(self, changed, removed_keys, manifest, current_keys) -> Dict:
        """局部应用：删旧 chunk → 解析变更文件 → 加新 chunk → 更新 manifest"""
        # 1. 收集要删除的旧 chunk ids（变更文件的旧 ids + 已删除文件的 ids）
        old_ids_to_delete = []
        for key in removed_keys:
            old_ids_to_delete.extend(manifest.get(key, {}).get("chunk_ids", []))
        for key, _ in changed:
            # key 是 Path 对象，manifest 的 key 是 str —— 必须 str() 转换
            old_ids_to_delete.extend(manifest.get(str(key), {}).get("chunk_ids", []))

        # 2. 解析变更文件 → 新 chunk
        new_items = []   # (id, chunk_dict)
        new_manifest_entries = {}
        for f, ds_root in changed:
            fid = path_id(f, ds_root)
            ds = next(d for d in self.cfg.datasources if Path(d.path) == ds_root)
            parser = get_parser(ds.format)
            cs = [c.to_dict() for c in parser.parse(f)]
            ids = [f"{fid}-{i}" for i in range(len(cs))]
            for cid, c in zip(ids, cs):
                c["id"] = cid
            new_items.extend(zip(ids, cs))
            new_manifest_entries[str(f)] = {"hash": file_hash(f), "chunk_ids": ids}

        # 3. 向量库局部更新（删旧 + 加新）
        col = self.retriever._get_collection()
        if old_ids_to_delete:
            col.delete(old_ids_to_delete)
        if new_items:
            col.add(ids=[i for i, _ in new_items],
                    documents=[c["text"] for _, c in new_items],
                    metadatas=[{"file": c["file"], "section": c["section"]} for _, c in new_items])

        # 4. 更新 manifest（删掉移除项、更新变更项）
        for key in removed_keys:
            manifest.pop(key, None)
        manifest.update(new_manifest_entries)
        self._save_manifest(manifest)

        # 5. 重写 chunks.json + 重建内存 BM25（全量，内存级，快）
        self._rebuild_in_memory()

        added = len(new_items)
        removed = len(old_ids_to_delete)
        return {"added": added, "updated": len(changed), "removed": removed,
                "total_chunks": len(self.retriever._chunks), "mode": "partial"}

    # ---------- 索引写入 ----------
    def _write_index(self, items) -> None:
        """全量写入：chunks.json + chroma 全量 + 内存 BM25"""
        chunks = [c for _, c in items]
        Path(self.cfg.data.chunks_json).parent.mkdir(parents=True, exist_ok=True)
        Path(self.cfg.data.chunks_json).write_text(
            json.dumps(chunks, ensure_ascii=False, indent=1), encoding="utf-8")

        col = self.retriever._get_collection()
        existing = col.get()["ids"]
        if existing:
            col.delete(existing)
        if chunks:
            col.add(ids=[c["id"] for c in chunks],
                    documents=[c["text"] for c in chunks],
                    metadatas=[{"file": c["file"], "section": c["section"]} for c in chunks])

        self.retriever.load_chunks(chunks)

    def _rebuild_in_memory(self) -> None:
        """从当前 manifest + 文件系统重建 chunks.json 与内存 BM25（局部更新后调用）"""
        manifest = self._load_manifest()
        chunks = []
        for ds in self.cfg.datasources:
            ds_root = Path(ds.path)
            parser = get_parser(ds.format)
            for f in collect_files(ds):
                key = str(f)
                entry = manifest.get(key)
                if not entry:
                    continue
                cs = [c.to_dict() for c in parser.parse(f)]
                for i, c in enumerate(cs):
                    c["id"] = f"{path_id(f, ds_root)}-{i}"
                chunks.extend(cs)
        Path(self.cfg.data.chunks_json).write_text(
            json.dumps(chunks, ensure_ascii=False, indent=1), encoding="utf-8")
        self.retriever.load_chunks(chunks)
