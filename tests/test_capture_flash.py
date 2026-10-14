"""验证屏幕光效的显示器匹配、输入穿透及自然清理，不捕获桌面。"""

import os
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtCore import QAbstractAnimation, QRect, Qt
from PySide6.QtWidgets import QApplication
from PySide6.QtTest import QTest

from ui.capture_flash import CaptureFlash


def test_flash_matches_physical_screen_and_is_input_transparent(monkeypatch):
    app = QApplication.instance() or QApplication([])
    class Screen:
        def name(self):
            return "scaled"
        def geometry(self):
            return QRect(100, 0, 600, 400)

    monkeypatch.setattr("ui.capture_flash.native_monitor_rects", lambda: {"scaled": (100, 0, 1000, 600)})
    monkeypatch.setattr("ui.capture_flash.QApplication.screens", lambda: [Screen()])
    monkeypatch.setattr("ui.capture_flash.EdgeStrip.setScreen", lambda strip, screen: None)
    flash = CaptureFlash()
    flash.flash((800, 0, 950, 500))
    assert len(flash.strips) == 4
    assert all(strip.isVisible() for strip in flash.strips)
    assert all(strip.windowFlags() & Qt.WindowTransparentForInput for strip in flash.strips)
    assert all(strip.windowFlags() & Qt.WindowDoesNotAcceptFocus for strip in flash.strips)
    assert all(Screen().geometry().contains(strip.geometry()) for strip in flash.strips)
    QTest.qWait(450)
    assert not flash.strips
    flash.flash((1100, 0, 1200, 500))
    assert not flash.strips


def test_interrupted_flash_destroys_old_windows(monkeypatch):
    app = QApplication.instance() or QApplication([])
    monkeypatch.setattr("ui.capture_flash.native_monitor_rects", lambda: {})
    flash = CaptureFlash()
    screen = app.primaryScreen().geometry()
    bounds = (screen.left(), screen.top(), screen.right() + 1, screen.bottom() + 1)
    flash.flash(bounds)
    old = list(flash.strips)
    assert old
    flash.stop()
    assert all(strip.isHidden() for strip in old)
    assert not flash.strips
    assert flash.animation.state() == QAbstractAnimation.Stopped
