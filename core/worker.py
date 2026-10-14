"""Qt 工作线程桥接：所有截图对象和 OCR 模型在本线程创建与使用。

通过信号请求主线程暂时隐藏提示窗，截图完成立即恢复。
后台网络任务可取消，窗口退出等待资源自然清理，不强制终止线程。
"""

from __future__ import annotations

import asyncio
import logging
import threading

from PySide6.QtCore import QThread, Signal

from core.glossary.llm_client import LLMClient, LLMError
from core.pipeline import LatestTaskQueue, ReadingPipeline
from core.vision.capturer import ScreenCapturer
from core.vision.ocr_engine import OCREngine

logger = logging.getLogger(__name__)


class ReadingWorker(QThread):
    capture_needed = Signal(int)
    captured = Signal(int)
    capture_feedback = Signal(int, object)
    status_changed = Signal(int, str)
    result_ready = Signal(int, str, object)

    def __init__(self, config: dict, prompts: dict, database, parent=None) -> None:
        super().__init__(parent)
        self.config, self.prompts, self.database = config, prompts, database
        self.queue = LatestTaskQueue(config["capture"]["cooldown_seconds"])
        self.capture_permit = threading.Event()
        self._async_lock = threading.Lock()
        self._loop = None
        self._async_task = None
        self._async_number = None
        self._capture_number = None

    def request(self, manual: bool = False) -> bool:
        task = self.queue.request(manual)
        if task is not None:
            self.cancel_network()
        return task is not None

    def cancel_network(self) -> None:
        with self._async_lock:
            if self._loop is not None and self._async_task is not None and not self.queue.is_current(self._async_number):
                self._loop.call_soon_threadsafe(self._async_task.cancel)

    def permit_capture(self, number: int) -> None:
        """只放行对应截图，避免旧定时器放行下一轮截图。"""
        if self._capture_number == number:
            self.capture_permit.set()

    def set_paused(self, paused: bool) -> None:
        self.queue.set_paused(paused)
        self.cancel_network()
        self.capture_permit.set()

    def stop(self) -> None:
        self.queue.close()
        self.cancel_network()
        self.capture_permit.set()

    async def _process(self, pipeline, frame, task):
        with self._async_lock:
            self._loop = asyncio.get_running_loop()
            self._async_task = asyncio.current_task()
            self._async_number = task.number
        try:
            return await pipeline.process(
                frame, task.manual, lambda: self.queue.is_current(task.number),
                lambda message: self.status_changed.emit(task.number, message),
            )
        finally:
            with self._async_lock:
                self._loop = self._async_task = None
                self._async_number = None

    def run(self) -> None:
        capturer = None
        pipeline = None
        try:
            while (task := self.queue.take()) is not None:
                if not self.queue.is_current(task.number):
                    continue
                try:
                    if pipeline is None:
                        self.status_changed.emit(task.number, "正在加载本地 OCR 模型…")
                        capturer = ScreenCapturer(self.config["capture"]["monitor_index"], max_fps=10)
                        pipeline = ReadingPipeline(
                            self.config, OCREngine(self.config["ocr"]["confidence_threshold"]),
                            LLMClient(self.config["llm"], self.prompts), self.database,
                        )
                    if not self.queue.is_current(task.number):
                        continue
                    self.capture_permit.clear()
                    self._capture_number = task.number
                    self.capture_needed.emit(task.number)
                    permitted = self.capture_permit.wait(timeout=3)
                    try:
                        if not permitted:
                            raise RuntimeError("界面暂未响应截图请求，请重试。")
                        if not self.queue.is_current(task.number):
                            continue
                        region = self.config["capture"]["region"]
                        frame = capturer.grab_screen(tuple(region) if region else None)
                    finally:
                        self._capture_number = None
                        self.captured.emit(task.number)
                    # 只在像素捕获成功后通知光效，保持光效不进入 OCR 输入。
                    bounds_getter = getattr(capturer, "get_capture_bounds", None)
                    if bounds_getter is not None and self.queue.is_current(task.number):
                        bounds = bounds_getter(tuple(region) if region else None)
                        if isinstance(bounds, tuple) and len(bounds) == 4:
                            self.capture_feedback.emit(task.number, bounds)
                    message, results = asyncio.run(self._process(pipeline, frame, task))
                    if self.queue.is_current(task.number):
                        self.result_ready.emit(task.number, message, results)
                except asyncio.CancelledError:
                    continue
                except Exception as exc:
                    if pipeline is None and capturer is not None:
                        capturer.close()
                        capturer = None
                    # 不记录异常请求体、屏幕内容或服务返回正文。
                    logger.warning("识别任务 %s 失败：%s", task.number, type(exc).__name__)
                    if self.queue.is_current(task.number):
                        message = str(exc) if isinstance(exc, LLMError) else "本地截图或 OCR 失败，请检查依赖、显示器和截图区域。"
                        self.status_changed.emit(task.number, message)
        finally:
            if capturer is not None:
                capturer.close()
