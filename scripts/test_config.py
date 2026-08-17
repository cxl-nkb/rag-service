#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""M1 验收：验证 config.yaml 加载 + 校验"""
import sys
sys.path.insert(0, "/root/ubuntu-manage/chat/rag-service/app")

from config import load_config


def main():
    c = load_config("/root/ubuntu-manage/chat/rag-service/config.yaml")
    assert len(c.datasources) >= 1, "至少一个数据源"
    for ds in c.datasources:
        assert ds.path, f"数据源 {ds.name} 缺 path"
        assert ds.format in ("markdown", "docx", "text"), f"{ds.name} 格式非法"
        print(f"  ✓ {ds.name}: {ds.path} ({ds.format})")
    assert c.search.top_k_default > 0
    assert c.server.port > 0
    assert c.auto_watch.interval_sec > 0
    assert c.data.chroma_dir.endswith("chroma")
    print("✅ M1 验收通过：config.yaml 加载 + 校验 OK")
    print(f"  检索: top_k={c.search.top_k_default}, 阈值={c.search.threshold}")
    print(f"  自动更新: enabled={c.auto_watch.enabled}, mode={c.auto_watch.mode}, 间隔={c.auto_watch.interval_sec}s")
    print(f"  服务: {c.server.host}:{c.server.port}")
    print(f"  数据: {c.data.chroma_dir}")


if __name__ == "__main__":
    main()
