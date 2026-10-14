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

        def get_capture_bounds(self, region):
            return (0, 0, 40, 30)

        def close(self):
            closed.append(True)

    class OCR:
        def __init__(self, threshold):
            pass

        def recognize(self, frame):
            return []

    monkeypatch.setattr(worker_module, "ScreenCapturer", Capturer)
    monkeypatch.setattr(worker_module, "OCREngine", OCR)
    feedback = []
    monkeypatch.setattr(window.capture_flash, "flash", lambda bounds: feedback.append((bounds, list(captures), window.isVisible())))
    window.request_manual()
    wait_until(app, lambda: window.status_label.text() == "未识别到足够清晰的文字。")
    assert captures == [True]
    assert feedback == [((0, 0, 40, 30), [True], True)]
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


def test_empty_window_is_compact_and_expands_only_for_content(window, app, monkeypatch):
    monkeypatch.setattr(window.worker.queue, "is_current", lambda number: True)
    window.fit_to_content()
    empty_height = window.height()
    assert empty_height < 210
    assert window.scroll.isHidden()
    window.show_results(1, "测试结果", [Explanation("ONNX", "ONNX models", "模型格式，帮助不同框架交换机器学习模型。")])
    window.fit_to_content()
    assert window.height() > empty_height
    assert not window.scroll.isHidden()
    window.mark_mastered("ONNX", window.cards_layout.itemAt(0).widget())
    window.fit_to_content()
    assert window.height() <= empty_height + 10
    assert window.scroll.isHidden()


def test_long_explanations_have_bounded_height_and_scroll(window, monkeypatch):
    monkeypatch.setattr(window.worker.queue, "is_current", lambda number: True)
    window.show_results(1, "测试结果", [
        Explanation(f"术语 {i}", "context", "这是用于测试滚动条的长解释。" * 25) for i in range(3)
    ])
    window.fit_to_content()
    assert window.height() < window.screen().availableGeometry().height() * 0.8
    assert window.cards.minimumHeight() > window.scroll.height()


def test_pointer_over_window_blocks_already_queued_auto_trigger(window, monkeypatch):
    from unittest.mock import Mock
    window.auto_box.blockSignals(True)
    window.auto_box.setChecked(True)
    window.auto_box.blockSignals(False)
    monkeypatch.setattr(window, "pointer_inside", lambda: True)
    request = Mock()
    monkeypatch.setattr(window.worker, "request", request)
    window.request_automatic()
    request.assert_not_called()


def test_native_physical_rect_is_used_and_cleared_when_hidden(window, monkeypatch):
    monkeypatch.setattr("ui.overlay.native_window_rect", lambda handle: (1000, 200, 1500, 700))
    window.sync_excluded_region()
    assert window.monitor._excluded_regions == ((1000, 200, 1500, 700),)
    window.hide()
    assert window.monitor._excluded_regions == ()


def test_orb_collapse_expand_keeps_worker_and_results(window, app, monkeypatch):
    from PySide6.QtCore import QPoint, Qt
    from PySide6.QtTest import QTest
    monkeypatch.setattr(window.worker.queue, "is_current", lambda number: True)
    window.show_results(1, "测试结果", [Explanation("ONNX", "models", "模型格式")])
    window.set_collapsed(True)
    wait_until(app, lambda: window._transition is None)
    assert window.size().width() == window.size().height() == 56
    assert window.surface.isHidden() and window.orb.isVisible()
    assert not window.worker.queue.paused
    QTest.mouseClick(window.orb, Qt.LeftButton, pos=QPoint(28, 28))
    assert window._collapsed
    QTest.mouseDClick(window.orb, Qt.LeftButton, pos=QPoint(28, 28))
    wait_until(app, lambda: window._transition is None and not window._collapsed)
    assert window.width() == 360
    assert window.surface.isVisible() and window.orb.isHidden()
    assert window.cards_layout.count() == 1


def test_collapsed_results_notify_without_auto_expanding(window, app, monkeypatch):
    monkeypatch.setattr(window.worker.queue, "is_current", lambda number: True)
    window.set_collapsed(True, animate=False)
    window.show_results(1, "新结果", [
        Explanation("ONNX", "models", "模型格式"), Explanation("Tensor", "tensor", "多维数据表示"),
    ])
    window.fit_to_content()
    assert window._collapsed and window.width() == 56
    assert window.orb.unread == 2
    assert "2 个新解释" in window.orb.toolTip()
    window.set_collapsed(False)
    wait_until(app, lambda: window._transition is None)
    assert window.orb.unread == 0
    assert window.cards_layout.count() == 2
    assert window.scroll.isVisible()


def test_rapid_collapse_expand_settles_in_latest_mode(window, app):
    window.set_collapsed(True)
    window.set_collapsed(False)
    window.set_collapsed(True)
    wait_until(app, lambda: window._transition is None)
    assert window._collapsed and window.width() == 56
    assert window.orb.isVisible() and window.orb.isEnabled()
    assert window.surface.isHidden()


def test_orb_drag_does_not_expand(window, app):
    from PySide6.QtCore import QEvent, QPoint, QPointF, Qt
    from PySide6.QtGui import QMouseEvent
    from PySide6.QtTest import QSignalSpy
    window.set_collapsed(True, animate=False)
    orb = window.orb
    clicked = QSignalSpy(orb.clicked)
    point = QPoint(28, 28)
    origin = orb.mapToGlobal(point)
    old_position = window.pos()
    for event_type, local, global_point, button, buttons in [
        (QEvent.MouseButtonPress, point, origin, Qt.LeftButton, Qt.LeftButton),
        (QEvent.MouseMove, point + QPoint(-20, -10), origin + QPoint(-20, -10), Qt.NoButton, Qt.LeftButton),
        (QEvent.MouseButtonRelease, point, origin + QPoint(-20, -10), Qt.LeftButton, Qt.NoButton),
    ]:
        QApplication.sendEvent(orb, QMouseEvent(event_type, QPointF(local), QPointF(global_point), button, buttons, Qt.NoModifier))
    assert clicked.count() == 0
    assert window.pos() != old_position
    assert window._collapsed


def test_orb_idle_has_no_persistent_animation(window):
    window.set_collapsed(True, animate=False)
    assert not window.orb._spinner.isActive()
    window.set_busy(True)
    assert window.orb._spinner.isActive()
    window.set_busy(False)
    assert not window.orb._spinner.isActive()


def test_exit_during_transition_releases_worker(window, app):
    window.set_collapsed(True)
    window.close()
    wait_until(app, lambda: window._worker_done)
    assert window._transition is None
    assert not window.worker.isRunning()


def test_results_reveal_and_resize_finish_together(window, app, monkeypatch):
    monkeypatch.setattr(window.worker.queue, "is_current", lambda number: True)
    window.fit_to_content()
    empty_height = window.height()
    window.show_results(1, "新结果", [Explanation("ONNX", "models", "模型格式，帮助不同框架交换模型。")])
    card = window.cards_layout.itemAt(0).widget()
    assert card.graphicsEffect().opacity() == 0
    wait_until(app, lambda: card.graphicsEffect().opacity() == 1 and window._transition is None)
    assert window.height() > empty_height
    assert window.surface.isVisible()


def test_automatic_capture_restores_orb_not_panel(window, app, monkeypatch):
    import core.worker as worker_module
    from unittest.mock import Mock
    captures = []
    capturer = Mock()

    def capture(region):
        captures.append(window.isHidden())
        return np.zeros((30, 40, 3), dtype=np.uint8)

    capturer.grab_screen.side_effect = capture
    ocr = Mock()
    ocr.recognize.return_value = []
    monkeypatch.setattr(worker_module, "ScreenCapturer", lambda *args, **kwargs: capturer)
    monkeypatch.setattr(worker_module, "OCREngine", lambda *args: ocr)
    window.set_collapsed(True, animate=False)
    window.worker.request(manual=False)
    wait_until(app, lambda: window.status_label.text() == "未识别到足够清晰的文字。")
    assert captures == [True]
    assert window._collapsed and window.width() == 56
    assert window.orb.isVisible() and window.surface.isHidden()
    assert not window.orb.busy


def test_orb_exclusion_covers_only_small_window(window, monkeypatch):
    monkeypatch.setattr("ui.overlay.native_window_rect", lambda handle: None)
    window.set_collapsed(True, animate=False)
    left, top, right, bottom = window.monitor._excluded_regions[0]
    assert right - left == bottom - top == 56
    window.set_collapsed(False, animate=False)
    left, top, right, bottom = window.monitor._excluded_regions[0]
    assert right - left == 360


def test_orb_menu_preserves_pause_and_scroll_exclusion(window, app, monkeypatch):
    monkeypatch.setattr("ui.overlay.native_window_rect", lambda handle: None)
    window.set_collapsed(True, animate=False)
    window.show_orb_menu(window.pos())
    wait_until(app, lambda: len(window.monitor._excluded_regions) == 2)
    assert window.pointer_inside()
    window._orb_pause_action.trigger()
    assert window.worker.queue.paused
    assert window.orb.paused
    window._orb_menu.hide()
    wait_until(app, lambda: len(window.monitor._excluded_regions) == 1)


def test_orb_near_screen_edge_expands_inside_desktop(window):
    window.set_collapsed(True, animate=False)
    corner = window.screen().availableGeometry().topLeft()
    window.move_within_screen(corner)
    window.set_collapsed(False, animate=False)
    assert window.screen().availableGeometry().contains(window.geometry())


@pytest.mark.parametrize("has_explanation", [False, True])
def test_manual_result_auto_expands_orb(window, app, monkeypatch, has_explanation):
    monkeypatch.setattr(window.worker.queue, "is_current", lambda number: True)
    monkeypatch.setattr(window.worker, "request", lambda manual=False: True)
    window.set_collapsed(True, animate=False)
    window.request_manual()
    results = [Explanation("ONNX", "models", "模型格式")] if has_explanation else []
    window.show_results(1, "识别完成", results)
    wait_until(app, lambda: window._transition is None and not window._collapsed)
    assert window.width() == 360
    assert window.orb.unread == 0
    assert not window._manual_request


def test_manual_error_expands_to_show_failure(window, app, monkeypatch):
    monkeypatch.setattr(window.worker.queue, "is_current", lambda number: True)
    monkeypatch.setattr(window.worker, "request", lambda manual=False: True)
    window.set_collapsed(True, animate=False)
    window.request_manual()
    window.update_status(1, "LLM 请求超时，可稍后重试。")
    wait_until(app, lambda: window._transition is None and not window._collapsed)
    assert "超时" in window.status_label.text()
    assert not window._manual_request


def test_automatic_trigger_cannot_replace_active_manual_request(window, monkeypatch):
    from unittest.mock import Mock
    request = Mock(return_value=True)
    monkeypatch.setattr(window.worker, "request", request)
    monkeypatch.setattr(window.worker.queue, "is_current", lambda number: True)
    monkeypatch.setattr(window, "pointer_inside", lambda: False)
    window.auto_box.blockSignals(True)
    window.auto_box.setChecked(True)
    window.auto_box.blockSignals(False)
    window.request_manual()
    window.request_automatic()
    assert request.call_count == 1
    window.show_results(1, "完成", [])
    window.request_automatic()
    assert request.call_count == 2


def test_progress_tracks_phase_and_elapsed_then_cleans_up(window, app, monkeypatch):
    monkeypatch.setattr(window.worker, "request", lambda manual=False: True)
    monkeypatch.setattr(window.worker.queue, "is_current", lambda number: True)
    window.request_manual()
    window.fit_to_content()
    assert window.progress.isVisible()
    assert window._progress_timer.isActive()
    start = window._busy_since
    window.update_status(1, "正在筛选值得解释的术语…")
    assert window.stage_label.text() == "术语筛选"
    assert window._busy_since == start
    window._busy_since -= 17
    window.refresh_progress()
    assert "17 秒" in window.elapsed_label.text()
    assert "服务仍在处理" in window.elapsed_label.text()
    window.update_status(1, "正在解释：ONNX")
    assert window.stage_label.text() == "生成解释"
    window.show_results(1, "完成", [])
    assert window.progress.isHidden()
    assert not window._progress_timer.isActive()


def test_busy_orb_keeps_small_size_and_resumes_progress_on_expand(window, app):
    window.set_collapsed(True, animate=False)
    window.set_busy(True)
    window.fit_to_content()
    assert window.width() == window.height() == 56
    assert not window._progress_timer.isActive()
    window.set_collapsed(False, animate=False)
    assert window.progress.isVisible()
    assert window._progress_timer.isActive()
    window.pause_button.setChecked(True)
    assert window.progress.isHidden()
    assert not window._progress_timer.isActive()


def test_error_and_stale_status_do_not_leave_busy_progress(window, monkeypatch):
    monkeypatch.setattr(window.worker.queue, "is_current", lambda number: number == 2)
    window.set_busy(True)
    window.update_status(1, "旧任务失败")
    assert window._busy
    window.update_status(2, "LLM 请求超时，可稍后重试。")
    assert not window._busy
    assert window.progress.isHidden()
    assert not window._progress_timer.isActive()


def test_capture_feedback_is_ignored_for_stale_tasks_and_cleared_before_capture(window, monkeypatch):
    from unittest.mock import Mock
    monkeypatch.setattr(window.worker.queue, "is_current", lambda number: number == 2)
    flash = Mock()
    stop = Mock()
    monkeypatch.setattr(window.capture_flash, "flash", flash)
    monkeypatch.setattr(window.capture_flash, "stop", stop)
    window.show_capture_feedback(1, (0, 0, 40, 30))
    flash.assert_not_called()
    window.show_capture_feedback(2, (0, 0, 40, 30))
    flash.assert_called_once()
    window.prepare_capture(2)
    stop.assert_called_once()
    assert window.isHidden()


def test_failed_capture_restores_window_without_success_flash(window, app, monkeypatch):
    from unittest.mock import Mock
    import core.worker as worker_module
    capturer = Mock()
    capturer.grab_screen.side_effect = RuntimeError("capture failed")
    monkeypatch.setattr(worker_module, "ScreenCapturer", lambda *args, **kwargs: capturer)
    monkeypatch.setattr(worker_module, "OCREngine", lambda *args: Mock())
    flash = Mock()
    monkeypatch.setattr(window.capture_flash, "flash", flash)
    window.request_manual()
    wait_until(app, lambda: "本地截图或 OCR 失败" in window.status_label.text())
    flash.assert_not_called()
    assert window.isVisible()
    assert window.progress.isHidden()
