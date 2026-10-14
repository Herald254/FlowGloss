"""无桌面窗口测试：截图握手、反馈、暂停和安全退出。"""

import os
import asyncio
import threading
import time

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import numpy as np
import pytest
from PySide6.QtWidgets import QApplication

from core.models import Explanation, TextBlock
from ui.overlay import OverlayWindow
from utils.config_loader import load_config, load_prompts


@pytest.fixture(scope="module")
def app():
    application = QApplication.instance() or QApplication([])
    application.setQuitOnLastWindowClosed(False)
    return application


def wait_until(app, predicate, timeout=5):
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        app.processEvents()
        if predicate():
            return
        time.sleep(0.005)
    pytest.fail("Qt task did not finish in time")


@pytest.fixture
def window(app, tmp_path):
    config = load_config()
    config["storage"]["database_path"] = str(tmp_path / "ui.db")
    config["ui"]["auto_start"] = False
    config["llm"]["api_key"] = "test-key"
    widget = OverlayWindow(config, load_prompts())
    widget.show()
    yield widget
    widget.close()
    wait_until(app, lambda: widget._worker_done)
    assert not widget.worker.isRunning()


def test_mastered_card_is_removed_and_feedback_saved(window, app, monkeypatch):
    # 不提交工作任务；该测试只验证结果显示与反馈。
    monkeypatch.setattr(window.worker.queue, "is_current", lambda number: True)
    window.show_results(1, "测试结果", [Explanation("ONNX", "ONNX models", "模型格式")])
    assert window.cards_layout.count() == 1
    card = window.cards_layout.itemAt(0).widget()
    window.mark_mastered("ONNX", card)
    assert window.database.is_mastered("onnx")
    assert card.isHidden()


def test_pause_prevents_manual_requests(window):
    window.pause_button.setChecked(True)
    assert window.worker.queue.paused
    assert not window.capture_button.isEnabled()
    assert not window.worker.request(True)


def test_capture_hides_window_and_worker_closes_resources(window, app, monkeypatch):
    import core.worker as worker_module

    captures = []
    closed = []

    class Capturer:
        def __init__(self, *args, **kwargs):
            pass

        def grab_screen(self, region):
            captures.append(window.isHidden())
            return np.zeros((30, 40, 3), dtype=np.uint8)

        def close(self):
            closed.append(True)

    class OCR:
        def __init__(self, threshold):
            pass

        def recognize(self, frame):
            return []

    monkeypatch.setattr(worker_module, "ScreenCapturer", Capturer)
    monkeypatch.setattr(worker_module, "OCREngine", OCR)
    window.request_manual()
    wait_until(app, lambda: window.status_label.text() == "未识别到足够清晰的文字。")
    assert captures == [True]
    assert window.isVisible()
    window.close()
    wait_until(app, lambda: window._worker_done)
    assert closed == [True]


def test_pause_cancels_inflight_network_without_showing_stale_result(window, app, monkeypatch):
    import core.worker as worker_module

    started = threading.Event()
    cancelled = threading.Event()

    class Capturer:
        def __init__(self, *args, **kwargs):
            pass

        def grab_screen(self, region):
            return np.zeros((30, 40, 3), dtype=np.uint8)

        def close(self):
            pass

    class OCR:
        def __init__(self, threshold):
            pass

        def recognize(self, frame):
            return [TextBlock("ONNX accelerates model inference.", (), 1)]

    class LLM:
        signature = "test"

        def __init__(self, *args):
            pass

        async def extract_terms(self, text):
            started.set()
            try:
                await asyncio.sleep(60)
            except asyncio.CancelledError:
                cancelled.set()
                raise

    monkeypatch.setattr(worker_module, "ScreenCapturer", Capturer)
    monkeypatch.setattr(worker_module, "OCREngine", OCR)
    monkeypatch.setattr(worker_module, "LLMClient", LLM)
    window.request_manual()
    wait_until(app, started.is_set)
    window.pause_button.setChecked(True)
    wait_until(app, cancelled.is_set)
    assert window.cards_layout.count() == 0
    assert "已暂停" in window.status_label.text()
