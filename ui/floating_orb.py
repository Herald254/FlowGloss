"""悬浮球：轻量绘制、双击/拖动区分、忙碌环和新结果提醒。

仅在忙碌或短暂提示动画期间重绘，空闲时不启动常驻动画。
"""

from PySide6.QtCore import QPoint, QRectF, Qt, QTimer, Signal, Property, QPropertyAnimation, QEasingCurve
from PySide6.QtGui import QColor, QFont, QPainter, QPen, QRadialGradient
from PySide6.QtWidgets import QApplication, QWidget


class FloatingOrb(QWidget):
    clicked = Signal()
    double_clicked = Signal()
    moved = Signal(QPoint)
    context_requested = Signal(QPoint)

    def __init__(self, parent=None) -> None:
        super().__init__(parent)
        self.setFixedSize(56, 56)
        self.setCursor(Qt.PointingHandCursor)
        self.busy = False
        self.unread = 0
        self.paused = False
        self.error = False
        self._hovered = False
        self._pulse = 0.0
        self._phase = 0
        self._press = None
        self._dragged = False
        self._spinner = QTimer(self)
        self._spinner.setInterval(32)
        self._spinner.timeout.connect(self._tick)
        self._notification = QPropertyAnimation(self, b"pulse", self)
        self._notification.setDuration(520)
        self._notification.setKeyValueAt(0, 0.0)
        self._notification.setKeyValueAt(0.45, 1.0)
        self._notification.setKeyValueAt(1, 0.0)
        self._notification.setEasingCurve(QEasingCurve.InOutSine)

    def get_pulse(self) -> float:
        return self._pulse

    def set_pulse(self, value: float) -> None:
        self._pulse = value
        self.update()

    pulse = Property(float, get_pulse, set_pulse)

    def set_state(self, busy=False, unread=0, paused=False, error=False) -> None:
        self.busy, self.unread, self.paused, self.error = busy, unread, paused, error
        self._sync_spinner()
        self.update()

    def notify_result(self) -> None:
        self._notification.stop()
        self._notification.start()

    def _sync_spinner(self) -> None:
        if self.busy and self.isVisible():
            self._spinner.start()
        else:
            self._spinner.stop()

    def _tick(self) -> None:
        self._phase = (self._phase + 10) % 360
        self.update()

    def showEvent(self, event) -> None:
        super().showEvent(event)
        self._sync_spinner()

    def hideEvent(self, event) -> None:
        super().hideEvent(event)
        self._spinner.stop()
        self._notification.stop()
        self.set_pulse(0)

    def enterEvent(self, event) -> None:
        self._hovered = True
        self.update()

    def leaveEvent(self, event) -> None:
        self._hovered = False
        self.update()

    def paintEvent(self, event) -> None:
        painter = QPainter(self)
        painter.setRenderHint(QPainter.Antialiasing)
        accent = QColor("#83a198" if self.paused else "#65dbc2")
        halo = QColor(accent)
        halo.setAlpha(int(28 + self._pulse * 105))
        painter.setPen(QPen(halo, 2))
        painter.setBrush(Qt.NoBrush)
        painter.drawEllipse(QRectF(2, 2, 52, 52))
        gradient = QRadialGradient(22, 18, 40)
        gradient.setColorAt(0, QColor("#314957" if self._hovered else "#263d49"))
        gradient.setColorAt(1, QColor("#131e2b"))
        painter.setBrush(gradient)
        painter.setPen(QPen(QColor("#446b70"), 1))
        painter.drawEllipse(QRectF(4, 4, 48, 48))
        if self.busy:
            painter.setPen(QPen(accent, 2.2, Qt.SolidLine, Qt.RoundCap))
            painter.setBrush(Qt.NoBrush)
            painter.drawArc(QRectF(5, 5, 46, 46), -self._phase * 16, 100 * 16)
        font = QFont("Microsoft YaHei UI")
        font.setPixelSize(21)
        font.setBold(True)
        painter.setFont(font)
        painter.setPen(accent)
        painter.drawText(QRectF(4, 3, 48, 48), Qt.AlignCenter, "F")
        if self.unread or self.error:
            painter.setPen(QPen(QColor("#14202c"), 2))
            painter.setBrush(QColor("#e5b174" if self.error else "#65dbc2"))
            painter.drawEllipse(QRectF(37, 2, 17, 17))
            if self.unread and not self.error:
                font.setPixelSize(10)
                painter.setFont(font)
                painter.setPen(QColor("#102b28"))
                painter.drawText(QRectF(37, 2, 17, 17), Qt.AlignCenter, str(min(self.unread, 9)))

    def mousePressEvent(self, event) -> None:
        if event.button() == Qt.LeftButton:
            self._press = event.globalPosition().toPoint()
            self._origin = self.window().pos()
            self._dragged = False
            event.accept()

    def mouseMoveEvent(self, event) -> None:
        if self._press is not None and event.buttons() & Qt.LeftButton:
            delta = event.globalPosition().toPoint() - self._press
            if delta.manhattanLength() >= QApplication.startDragDistance():
                self._dragged = True
            if self._dragged:
                self.moved.emit(self._origin + delta)
            event.accept()

    def mouseReleaseEvent(self, event) -> None:
        if event.button() == Qt.LeftButton and self._press is not None:
            clicked = not self._dragged
            self._press = None
            if clicked:
                self.clicked.emit()
            event.accept()

    def mouseDoubleClickEvent(self, event) -> None:
        if event.button() == Qt.LeftButton:
            self._press = None
            self.double_clicked.emit()
            event.accept()

    def contextMenuEvent(self, event) -> None:
        self.context_requested.emit(event.globalPos())
        event.accept()
