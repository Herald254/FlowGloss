# e:\code\FlowGloss\ui\overlay.py
"""
基于 PySide6 的置顶伴读窗口。

提供手动识别、自动监听、暂停、退出和已掌握反馈。
通过 Signal/Slot 在主线程更新界面；截图期间隐藏窗口，避免识别自身。
采用不激活窗口属性；当前支持拖动，尚未实现点击穿透、亚克力或托盘。
"""

from __future__ import annotations

from PySide6.QtCore import QObject, Qt, QTimer, Signal, Slot
from PySide6.QtGui import QFont
from PySide6.QtWidgets import (
    QApplication, QCheckBox, QFrame, QLabel, QPushButton,
    QScrollArea, QVBoxLayout, QHBoxLayout, QWidget,
)

from core.monitor.event_hook import ScreenEventMonitor
from core.worker import ReadingWorker
from data.database import KnowledgeDB


class MonitorSignals(QObject):
    stable = Signal()


class OverlayWindow(QWidget):
    """可拖动的伴读提示窗；按钮控制识别、暂停和已掌握反馈。

    使用 Qt 信号在 GUI 主线程更新界面，不在事件监听回调中操作窗口。
    """

    def __init__(self, config: dict, prompts: dict) -> None:
        super().__init__()
        self.config = config
        self._closing = False
        self._worker_done = False
        self._capture_hidden = False
        self._drag_offset = None
        self.database = KnowledgeDB(config["storage"]["database_path"])
        self.setWindowTitle("FlowGloss")
        self.setFont(QFont("Microsoft YaHei UI", 10))
        self.setWindowFlags(Qt.Tool | Qt.FramelessWindowHint | Qt.WindowStaysOnTopHint | Qt.WindowDoesNotAcceptFocus)
        self.setAttribute(Qt.WA_ShowWithoutActivating)
        self.setWindowOpacity(config["ui"]["opacity"])
        self.resize(400, 430)
        self.setStyleSheet("""
            QWidget { background: #202734; color: #e7edf5; font-size: 13px; }
            QPushButton { background: #36445a; border: none; padding: 8px 10px; border-radius: 5px; }
            QPushButton:hover { background: #475b77; }
            QPushButton:disabled { color: #8793a4; }
            QLabel { background: transparent; }
            QScrollArea { border: none; }
            QFrame#card { background: #293446; border-radius: 7px; }
        """)
        layout = QVBoxLayout(self)
        title = QLabel("FlowGloss · 伴读助手")
        title.setStyleSheet("font-size: 17px; font-weight: bold; padding: 6px;")
        title.setAttribute(Qt.WA_TransparentForMouseEvents)
        layout.addWidget(title)
        controls = QHBoxLayout()
        self.capture_button = QPushButton("识别当前屏幕")
        self.capture_button.clicked.connect(self.request_manual)
        controls.addWidget(self.capture_button)
        self.pause_button = QPushButton("暂停")
        self.pause_button.setCheckable(True)
        self.pause_button.toggled.connect(self.set_paused)
        controls.addWidget(self.pause_button)
        exit_button = QPushButton("退出")
        exit_button.clicked.connect(self.close)
        controls.addWidget(exit_button)
        layout.addLayout(controls)
        self.auto_box = QCheckBox("滚动或翻页停止后自动识别")
        self.auto_box.toggled.connect(self.set_automatic)
        layout.addWidget(self.auto_box)
        self.status_label = QLabel("就绪。点击“识别当前屏幕”开始。")
        self.status_label.setWordWrap(True)
        layout.addWidget(self.status_label)
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        self.cards = QWidget()
        self.cards_layout = QVBoxLayout(self.cards)
        self.cards_layout.setAlignment(Qt.AlignTop)
        scroll.setWidget(self.cards)
        layout.addWidget(scroll, 1)
        disclosure = QLabel(
            "识别时会将所选屏幕区域的文字片段发送给配置的 AI 服务。\n"
            f"单次屏幕文本片段最多 {config['llm']['max_context_chars']} 字；本地保存掌握标记和解释缓存。"
        )
        disclosure.setWordWrap(True)
        disclosure.setStyleSheet("color: #adb9c9; font-size: 11px;")
        layout.addWidget(disclosure)
        self.worker = ReadingWorker(config, prompts, self.database, self)
        self.worker.capture_needed.connect(self.prepare_capture)
        self.worker.captured.connect(self.restore_after_capture)
        self.worker.status_changed.connect(self.update_status)
        self.worker.result_ready.connect(self.show_results)
        self.worker.finished.connect(self.finish_shutdown)
        self.monitor_signals = MonitorSignals(self)
        self.monitor_signals.stable.connect(self.request_automatic)
        self.monitor = ScreenEventMonitor(
            debounce_interval=config["capture"]["debounce_seconds"],
            on_stable_callback=self.monitor_signals.stable.emit,
        )
        self.worker.start()
        screen = QApplication.primaryScreen().availableGeometry()
        self.move(screen.right() - self.width() - 20, screen.bottom() - self.height() - 20)
        self.auto_box.setChecked(config["ui"]["auto_start"])
        if not config["llm"]["api_key"].strip():
            self.status_label.setText("请先设置 FLOWGLOSS_API_KEY 或 config/settings.local.yaml，然后重新启动。")

    def _has_key(self) -> bool:
        if not self.config["llm"]["api_key"].strip():
            self.status_label.setText("尚未配置 API 密钥，请设置后重新启动。")
            return False
        return True

    @Slot()
    def request_manual(self) -> None:
        if self._has_key() and self.worker.request(manual=True):
            self.clear_cards()
            self.status_label.setText("正在准备识别…")

    @Slot()
    def request_automatic(self) -> None:
        if self._closing or not self.auto_box.isChecked() or self.pause_button.isChecked():
            return
        if self._has_key() and self.worker.request():
            self.clear_cards()
            self.status_label.setText("页面已稳定，正在准备识别…")

    @Slot(bool)
    def set_automatic(self, enabled: bool) -> None:
        if enabled and not self.pause_button.isChecked():
            try:
                self.monitor.start()
            except Exception:
                self.monitor.stop()
                self.auto_box.setChecked(False)
                self.status_label.setText("全局监听启动失败；仍可手动识别。")
        else:
            self.monitor.stop()

    @Slot(bool)
    def set_paused(self, paused: bool) -> None:
        self.worker.set_paused(paused)
        self.capture_button.setEnabled(not paused)
        self.pause_button.setText("继续" if paused else "暂停")
        self.set_automatic(self.auto_box.isChecked() and not paused)
        self.clear_cards()
        self.status_label.setText("已暂停，不进行截图和请求。" if paused else "已继续。")

    @Slot(int)
    def prepare_capture(self, number: int) -> None:
        if not self.worker.queue.is_current(number) or self._closing:
            self.worker.permit_capture(number)
            return
        self._capture_hidden = True
        self.hide()
        # 等桌面合成器移除本窗口，避免 OCR 读到自己的解释。
        QTimer.singleShot(150, lambda: self.worker.permit_capture(number))

    @Slot(int)
    def restore_after_capture(self, number: int) -> None:
        if self._capture_hidden:
            self._capture_hidden = False
            if not self._closing:
                self.show()

    @Slot(int, str)
    def update_status(self, number: int, message: str) -> None:
        if self.worker.queue.is_current(number):
            self.status_label.setText(message)

    def clear_cards(self) -> None:
        while self.cards_layout.count():
            item = self.cards_layout.takeAt(0)
            if item.widget():
                item.widget().deleteLater()

    @Slot(int, str, object)
    def show_results(self, number: int, message: str, results: list) -> None:
        if not self.worker.queue.is_current(number):
            return
        self.clear_cards()
        self.status_label.setText(message)
        for result in results:
            if self.database.is_mastered(result.term):
                continue
            card = QFrame()
            card.setObjectName("card")
            body = QVBoxLayout(card)
            heading = QLabel(result.term + (" · 缓存" if result.cached else ""))
            heading.setTextFormat(Qt.PlainText)
            heading.setWordWrap(True)
            heading.setStyleSheet("font-weight: bold; font-size: 15px;")
            body.addWidget(heading)
            text = QLabel(result.text)
            text.setTextFormat(Qt.PlainText)
            text.setWordWrap(True)
            body.addWidget(text)
            mastered = QPushButton("已掌握，不再提示")
            mastered.clicked.connect(lambda checked=False, term=result.term, widget=card: self.mark_mastered(term, widget))
            body.addWidget(mastered)
            self.cards_layout.addWidget(card)

    def mark_mastered(self, term: str, card: QWidget) -> None:
        try:
            self.database.update_word(term)
            card.hide()
            self.status_label.setText(f"已记录：{term}")
        except Exception:
            self.status_label.setText("学习记录保存失败，请检查数据库文件权限。")

    def mousePressEvent(self, event) -> None:
        if event.button() == Qt.LeftButton and event.position().y() < 50:
            self._drag_offset = event.globalPosition().toPoint() - self.pos()

    def mouseMoveEvent(self, event) -> None:
        if self._drag_offset is not None and event.buttons() & Qt.LeftButton:
            self.move(event.globalPosition().toPoint() - self._drag_offset)

    def mouseReleaseEvent(self, event) -> None:
        self._drag_offset = None

    def closeEvent(self, event) -> None:
        if self._worker_done:
            event.accept()
            return
        event.ignore()
        if not self._closing:
            self._closing = True
            self.monitor.stop()
            self.worker.stop()
            self.capture_button.setEnabled(False)
            self.auto_box.setEnabled(False)
            self.pause_button.setEnabled(False)
            self.status_label.setText("正在释放识别资源…")

    @Slot()
    def finish_shutdown(self) -> None:
        self.database.close()
        self._worker_done = True
        self.close()
        QApplication.quit()
