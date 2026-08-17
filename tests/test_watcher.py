#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""V3-3 pytest 验收：watchdog 实时模式"""
import sys
import time
from pathlib import Path
from unittest.mock import Mock

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "app"))

from config import load_config  # noqa: E402
from watcher import DebounceHandler, WATCH_EXTENSIONS  # noqa: E402


def test_watch_extensions_covered():
    assert ".md" in WATCH_EXTENSIONS
    assert ".docx" in WATCH_EXTENSIONS
    assert ".txt" in WATCH_EXTENSIONS


def test_debounce_aggregates_events():
    """多个事件在防抖窗口内只触发一次入库"""
    on_change = Mock()
    handler = DebounceHandler(on_change, debounce_sec=0.5)

    handler.on_created(type("E", (), {"is_directory": False, "src_path": "/tmp/x/a.md"})())
    handler.on_modified(type("E", (), {"is_directory": False, "src_path": "/tmp/x/a.md"})())
    handler.on_modified(type("E", (), {"is_directory": False, "src_path": "/tmp/x/a.md"})())

    assert on_change.call_count == 0  # 防抖窗口内不触发
    time.sleep(0.8)
    assert on_change.call_count == 1  # 静默后只触发一次


def test_debounce_ignores_directories():
    on_change = Mock()
    handler = DebounceHandler(on_change, debounce_sec=5.0)
    handler.on_created(type("E", (), {"is_directory": True, "src_path": "/tmp/x/dir"})())
    time.sleep(0.1)
    assert on_change.call_count == 0


def test_debounce_ignores_unrelated_ext():
    on_change = Mock()
    handler = DebounceHandler(on_change, debounce_sec=5.0)
    handler.on_modified(type("E", (), {"is_directory": False, "src_path": "/tmp/x/a.tmp"})())
    time.sleep(0.1)
    assert on_change.call_count == 0


def test_config_mode_watchdog_accepted(tmp_path):
    """config.yaml mode=watchdog 应被接受"""
    cfg_path = tmp_path / "config.yaml"
    cfg_path.write_text(
        "datasources:\n  - name: t\n    path: /tmp\n    format: markdown\n"
        "auto_watch:\n  enabled: true\n  mode: watchdog\n  debounce_sec: 3\n",
        encoding="utf-8",
    )
    cfg = load_config(cfg_path)
    assert cfg.auto_watch.mode == "watchdog"
    assert cfg.auto_watch.debounce_sec == 3


def test_config_mode_invalid_rejected(tmp_path):
    cfg_path = tmp_path / "config.yaml"
    cfg_path.write_text(
        "datasources:\n  - name: t\n    path: /tmp\n    format: markdown\n"
        "auto_watch:\n  mode: invalid_mode\n",
        encoding="utf-8",
    )
    with pytest.raises(ValueError):
        load_config(cfg_path)
