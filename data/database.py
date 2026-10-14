# e:\code\FlowGloss\data\database.py
"""
SQLite 学习记录和解释缓存。

模块功能：保存已掌握标记；按术语、语境、服务、模型、用户背景与提示词缓存解释。
所有连接操作使用锁；不保存完整截图或整屏 OCR 文本。
学习记录与缓存跨重启保留，知识图谱和学习历史统计尚未接入。
"""

from __future__ import annotations

import hashlib
import json
import sqlite3
import threading
import time
from pathlib import Path

from core.cognition.ranker import normalize_term


class KnowledgeDB:
    """线程安全的学习记录与语境缓存，不保存整屏 OCR 文本。"""

    def __init__(self, path: str | Path) -> None:
        path = Path(path)
        path.parent.mkdir(parents=True, exist_ok=True)
        self._lock = threading.RLock()
        self._connection = sqlite3.connect(path, check_same_thread=False)
        with self._connection:
            self._connection.executescript("""
                CREATE TABLE IF NOT EXISTS words (
                    word TEXT PRIMARY KEY, display_word TEXT NOT NULL,
                    mastered INTEGER NOT NULL DEFAULT 0, updated_at REAL NOT NULL
                );
                CREATE TABLE IF NOT EXISTS explanations (
                    cache_key TEXT PRIMARY KEY, explanation TEXT NOT NULL,
                    created_at REAL NOT NULL
                );
            """)

    @staticmethod
    def cache_key(term: str, context: str, signature: str) -> str:
        data = json.dumps([normalize_term(term), " ".join(context.split()), signature], ensure_ascii=False)
        return hashlib.sha256(data.encode("utf-8")).hexdigest()

    def is_mastered(self, word: str) -> bool:
        with self._lock:
            row = self._connection.execute("SELECT mastered FROM words WHERE word = ?", (normalize_term(word),)).fetchone()
        return bool(row and row[0])

    def update_word(self, word: str, mastered: bool = True) -> None:
        with self._lock, self._connection:
            self._connection.execute(
                "INSERT INTO words VALUES (?, ?, ?, ?) ON CONFLICT(word) DO UPDATE SET mastered=excluded.mastered, updated_at=excluded.updated_at",
                (normalize_term(word), word, int(mastered), time.time()),
            )

    def get_cached_explanation(self, key: str, max_age_hours: float) -> str | None:
        if max_age_hours <= 0:
            return None
        with self._lock:
            row = self._connection.execute("SELECT explanation, created_at FROM explanations WHERE cache_key = ?", (key,)).fetchone()
        if row and time.time() - row[1] < max_age_hours * 3600:
            return row[0]
        return None

    def cache_explanation(self, key: str, explanation: str) -> None:
        with self._lock, self._connection:
            self._connection.execute("INSERT OR REPLACE INTO explanations VALUES (?, ?, ?)", (key, explanation, time.time()))

    def close(self) -> None:
        with self._lock:
            self._connection.close()
