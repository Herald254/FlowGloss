"""截图完成后的屏幕边缘光效；细条窗口不接收输入、不激活桌面。

按原生边界选择显示器，在 Qt 逻辑坐标中绘制，兼容混合 DPI。
每次截图前必须 stop，保证上一轮光效不会进入新截图。
"""

from PySide6.QtCore import QObject, QRect, Qt, QVariantAnimation
from PySide6.QtGui import QColor, QLinearGradient, QPainter
from PySide6.QtWidgets import QApplication, QWidget

from utils.window_geometry import native_monitor_rects


class EdgeStrip(QWidget):
    def __init__(self, side):
        super().__init__()
        self.side = side
        self.strength = 0.0
        self.setWindowFlags(Qt.Tool | Qt.FramelessWindowHint | Qt.WindowStaysOnTopHint
                            | Qt.WindowTransparentForInput | Qt.WindowDoesNotAcceptFocus)
        self.setAttribute(Qt.WA_ShowWithoutActivating)
        self.setAttribute(Qt.WA_TranslucentBackground)
        self.setAttribute(Qt.WA_TransparentForMouseEvents)

    def paintEvent(self, event):
        painter = QPainter(self)
        if self.side == "top":
            gradient = QLinearGradient(0, 0, 0, self.height())
        elif self.side == "bottom":
            gradient = QLinearGradient(0, self.height(), 0, 0)
        elif self.side == "left":
            gradient = QLinearGradient(0, 0, self.width(), 0)
        else:
            gradient = QLinearGradient(self.width(), 0, 0, 0)
        gradient.setColorAt(0, QColor(66, 224, 195, int(190 * self.strength)))
        gradient.setColorAt(1, QColor(66, 224, 195, 0))
        painter.fillRect(self.rect(), gradient)


class CaptureFlash(QObject):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.strips = []
        self.animation = QVariantAnimation(self)
        self.animation.setDuration(380)
        self.animation.setStartValue(0.0)
        self.animation.setKeyValueAt(0.2, 1.0)
        self.animation.setEndValue(0.0)
        self.animation.valueChanged.connect(self._paint_strength)
        self.animation.finished.connect(self.stop)

    def flash(self, bounds):
        self.stop()
        native = native_monitor_rects()
        left, top, right, bottom = bounds
        for screen in QApplication.screens():
            rect = screen.geometry()
            physical = native.get(screen.name())
            if physical is None:
                ratio = screen.devicePixelRatio()
                physical = (rect.x(), rect.y(), rect.x() + rect.width() * ratio,
                            rect.y() + rect.height() * ratio)
            l, t, r, b = physical
            if min(right, r) <= max(left, l) or min(bottom, b) <= max(top, t):
                continue
            thickness = min(12, rect.width() // 2, rect.height() // 2)
            geometries = {
                "top": QRect(rect.x(), rect.y(), rect.width(), thickness),
                "bottom": QRect(rect.x(), rect.bottom() - thickness + 1, rect.width(), thickness),
                "left": QRect(rect.x(), rect.y() + thickness, thickness, rect.height() - 2 * thickness),
                "right": QRect(rect.right() - thickness + 1, rect.y() + thickness, thickness, rect.height() - 2 * thickness),
            }
            for side, geometry in geometries.items():
                strip = EdgeStrip(side)
                strip.setScreen(screen)
                strip.setGeometry(geometry)
                strip.show()
                self.strips.append(strip)
        if self.strips:
            self.animation.start()

    def _paint_strength(self, strength):
        for strip in self.strips:
            strip.strength = strength
            strip.update()

    def stop(self):
        self.animation.stop()
        for strip in self.strips:
            strip.hide()
            strip.deleteLater()
        self.strips.clear()
