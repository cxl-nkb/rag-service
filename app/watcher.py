#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""watchdog 实时监听：目录事件 → debounce 聚合 → 触发增量入库

设计要点：
- debounce（默认 5s）：文件写入是多次事件（create+modify），等待静默后一次性处理，避免半写入状态
- 仅监听配置的数据源目录（递归）
- 事件与轮询互斥：mode=watchdog 时由本模块驱动，polling 不启动
"""
import logging
import threading
import time
from pathlib import Path
from typing import Callable, List, Optional

from watchdog.events import FileSystemEventHandler
from watchdog.observers import Observer

logger = logging.getLogger("rag-service.watcher")

WATCH_EXTENSIONS = {".md", ".markdown", ".docx", ".txt", ".log"}


class DebounceHandler(FileSystemEventHandler):
    def __init__(self, on_change: Callable, debounce_sec: float = 5.0):
        self.on_change = on_change
        self.debounce_sec = debounce_sec
        self._timer: Optional[threading.Timer] = None
        self._lock = threading.Lock()

    def _schedule(self):
        with self._lock:
            if self._timer:
                self._timer.cancel()
            self._timer = threading.Timer(self.debounce_sec, self._fire)
            self._timer.daemon = True
            self._timer.start()

    def _fire(self):
        logger.info("watchdog debounce 触发：执行增量入库")
        try:
            self.on_change()
        except Exception as e:  # noqa: BLE001
            logger.error(f"watchdog 增量入库失败: {e}")

    def _relevant(self, path) -> bool:
        p = Path(path)
        return p.suffix.lower() in WATCH_EXTENSIONS and not any(
            part.startswith(".") for part in p.parts)

    def on_created(self, event):
        if not event.is_directory and self._relevant(event.src_path):
            self._schedule()

    def on_modified(self, event):
        if not event.is_directory and self._relevant(event.src_path):
            self._schedule()

    def on_deleted(self, event):
        if not event.is_directory and self._relevant(event.src_path):
            self._schedule()

    def on_moved(self, event):
        if not event.is_directory:
            self._schedule()


class WatchdogWatcher:
    """管理 Observer：监听所有数据源目录，事件触发增量入库"""

    def __init__(self, datasource_paths: List[str], on_change: Callable, debounce_sec: float = 5.0):
        self.observer = Observer()
        self.handler = DebounceHandler(on_change, debounce_sec)
        self.paths = [str(Path(p).resolve()) for p in datasource_paths]

    def start(self) -> None:
        for p in self.paths:
            if Path(p).exists():
                self.observer.schedule(self.handler, p, recursive=True)
                logger.info(f"watchdog 监听: {p}（recursive）")
        self.observer.start()

    def stop(self) -> None:
        self.observer.stop()
        self.observer.join(timeout=5)
        logger.info("watchdog 已停止")
