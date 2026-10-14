"""阅读流水线与最新任务调度。

工作线程串行执行截图、OCR 和异步网络请求；队列只保留最新任务。
不依赖 Qt，便于验证暂停、去重、缓存和过期结果处理。
"""

from __future__ import annotations

import asyncio
import threading
import time
from dataclasses import dataclass
from typing import Callable

from core.cognition.ranker import get_top_candidates
from core.models import Explanation, Term
from core.vision.processor import ImageChangeDetector
from data.database import KnowledgeDB


@dataclass(frozen=True)
class ReadingTask:
    number: int
    manual: bool


class LatestTaskQueue:
    """有界队列：请求递增编号，暂停/关闭立即使旧任务失效。"""

    def __init__(self, cooldown_seconds: float = 8.0) -> None:
        self._condition = threading.Condition()
        self._pending: ReadingTask | None = None
        self._generation = 0
        self._last_request = float("-inf")
        self.cooldown_seconds = cooldown_seconds
        self.paused = False
        self.closed = False

    def request(self, manual: bool = False) -> ReadingTask | None:
        with self._condition:
            if self.closed or self.paused:
                return None
            now = time.monotonic()
            if not manual and now - self._last_request < self.cooldown_seconds:
                return None
            self._generation += 1
            task = ReadingTask(self._generation, manual)
            self._pending = task
            self._last_request = now
            self._condition.notify_all()
            return task

    def take(self) -> ReadingTask | None:
        with self._condition:
            self._condition.wait_for(lambda: self.closed or self._pending is not None)
            if self.closed:
                return None
            task, self._pending = self._pending, None
            return task

    def is_current(self, number: int) -> bool:
        with self._condition:
            return not self.closed and not self.paused and number == self._generation

    def set_paused(self, paused: bool) -> None:
        with self._condition:
            self.paused = paused
            self._generation += 1
            self._pending = None

    def close(self) -> None:
        with self._condition:
            self.closed = True
            self._generation += 1
            self._pending = None
            self._condition.notify_all()


class ReadingPipeline:
    """画面差分 → OCR → 术语筛选 → 已知过滤 → 缓存/解释。"""

    def __init__(self, config: dict, ocr, llm, database: KnowledgeDB) -> None:
        self.config, self.ocr, self.llm, self.database = config, ocr, llm, database
        self.detector = ImageChangeDetector(config["capture"]["change_threshold"])
        self.last_text = ""
        self.last_terms: list[Term] = []

    async def process(
        self, frame, manual: bool = False, current: Callable[[], bool] = lambda: True,
        status: Callable[[str], None] = lambda message: None,
    ) -> tuple[str, list[Explanation]]:
        def check() -> None:
            if not current():
                raise asyncio.CancelledError

        check()
        if not manual and not self.detector.has_changed(frame):
            return "画面未明显变化，已跳过识别。", []
        status("正在识别屏幕文字…")
        blocks = self.ocr.recognize(frame)
        check()
        text = "\n".join(block.text for block in blocks)
        if len(text.strip()) < self.config["ocr"]["min_text_length"]:
            self.detector.accept(frame)
            return "未识别到足够清晰的文字。", []
        if text == self.last_text:
            if not manual:
                self.detector.accept(frame)
                return "文字内容未变化，已跳过请求。", []
            terms = self.last_terms
        else:
            status("正在筛选值得解释的术语…")
            terms = await self.llm.extract_terms(text)
            check()
        candidates = get_top_candidates(terms, self.database.is_mastered, self.config["llm"]["max_terms"])
        explanations = []
        for term in candidates:
            check()
            key = self.database.cache_key(term.text, term.context, self.llm.signature)
            cached = self.database.get_cached_explanation(key, self.config["storage"]["cache_hours"])
            if cached is None:
                status(f"正在解释：{term.text}")
                answer = await self.llm.get_explanation(term.text, term.context)
                check()
                self.database.cache_explanation(key, answer)
            else:
                answer = cached
            # 用户可以在后台请求期间标记已掌握，再次检查反馈。
            if not self.database.is_mastered(term.text):
                explanations.append(Explanation(term.text, term.context, answer, cached is not None))
        check()
        self.last_text, self.last_terms = text, terms
        self.detector.accept(frame)
        return ("已找到值得解释的概念。" if explanations else "当前没有需要额外解释的概念。"), explanations
