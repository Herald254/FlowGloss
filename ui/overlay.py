# e:\code\FlowGloss\ui\overlay.py
"""
基于 PySide6 的置顶伴读窗口。

提供手动识别、自动监听、暂停、退出和已掌握反馈。
通过 Signal/Slot 在主线程更新界面；截图期间隐藏窗口，避免识别自身。
采用不激活窗口属性；当前支持拖动，尚未实现点击穿透、亚克力或托盘。
"""

from __future__ import annotations

from PySide6.QtCore import QObject, Qt, QTimer, Signal, Slot
from PySide6.QtGui import QFont, QCursor
from PySide6.QtWidgets import (
    QApplication, QCheckBox, QFrame, QLabel, QPushButton,
    QScrollArea, QVBoxLayout, QHBoxLayout, QWidget, QSizePolicy, QLayout,
)

from core.monitor.event_hook import ScreenEventMonitor
from core.worker import ReadingWorker
from data.database import KnowledgeDB
from utils.window_geometry import native_window_rect


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
        self.setAttribute(Qt.WA_TranslucentBackground)
        self.setFixedWidth(360)
        self.resize(360, 155)
        self._fit_timer = QTimer(self)
        self._fit_timer.setSingleShot(True)
        self._fit_timer.timeout.connect(self.fit_to_content)
        self.setStyleSheet("""
            QWidget { color: #e8edf5; font-size: 13px; background: transparent; }
            QFrame#surface { background: #141c27; border: 1px solid #344254; border-radius: 14px; }
            QLabel#brand { color: #f1f5fa; font-size: 16px; font-weight: bold; }
            QLabel#status { color: #9eacbf; font-size: 12px; }
            QPushButton { background: #253143; border: 1px solid #35465b; padding: 6px 10px; border-radius: 7px; }
            QPushButton:hover { background: #314159; border-color: #53708e; }
            QPushButton:disabled { color: #63748b; }
            QPushButton#capture { background: #3cc8ae; color: #102b28; border-color: #3cc8ae; font-weight: bold; }
            QPushButton#capture:hover { background: #69dcc6; }
            QPushButton#capture:disabled { background: #274d47; color: #7fa69d; }
            QPushButton#close { background: transparent; border: none; color: #8999ad; padding: 0; font-size: 19px; }
            QPushButton#close:hover { background: #422b34; color: #f7a3aa; }
            QPushButton#mastered { background: transparent; border: none; color: #78d3bf; padding: 3px 0; font-size: 11px; text-align: left; }
            QPushButton#mastered:hover { color: #b2f1e1; }
            QCheckBox { color: #adbbcd; font-size: 12px; spacing: 5px; }
            QCheckBox::indicator { width: 13px; height: 13px; border: 1px solid #607187; border-radius: 4px; background: #202b3a; }
            QCheckBox::indicator:checked { background: #3cc8ae; border-color: #3cc8ae; }
            QScrollArea { border: none; background: transparent; }
            QFrame#card { background: #1d2938; border: 1px solid #2c3c50; border-radius: 9px; }
            QLabel#term { color: #edf3fc; font-size: 15px; font-weight: bold; }
            QLabel#answer { color: #c5d1e2; font-size: 13px; }
            QLabel#badge { color: #8092aa; font-size: 10px; }
            QLabel#footer { color: #63768f; font-size: 10px; }
            QScrollBar:vertical { width: 5px; background: transparent; margin: 2px 0; }
            QScrollBar::handle:vertical { background: #485c73; border-radius: 2px; min-height: 24px; }
            QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical { height: 0; }
            QScrollBar::add-page:vertical, QScrollBar::sub-page:vertical { background: transparent; }
        """)
        outer = QVBoxLayout(self)
        outer.setContentsMargins(0, 0, 0, 0)
        outer.setSizeConstraint(QLayout.SetNoConstraint)
        surface = QFrame()
        surface.setObjectName("surface")
        outer.addWidget(surface)
        layout = QVBoxLayout(surface)
        self._content_layout = layout
        layout.setContentsMargins(14, 12, 14, 10)
        layout.setSpacing(9)
        header = QHBoxLayout()
        brand = QLabel("FlowGloss")
        brand.setObjectName("brand")
        brand.setAttribute(Qt.WA_TransparentForMouseEvents)
        header.addWidget(brand)
        subtitle = QLabel("伴读")
        subtitle.setStyleSheet("color: #70849e; font-size: 11px;")
        subtitle.setAttribute(Qt.WA_TransparentForMouseEvents)
        header.addWidget(subtitle)
        header.addStretch()
        exit_button = QPushButton("×")
        exit_button.setObjectName("close")
        exit_button.setFixedSize(24, 24)
        exit_button.setToolTip("退出 FlowGloss")
        exit_button.clicked.connect(self.close)
        header.addWidget(exit_button)
        layout.addLayout(header)
        controls = QHBoxLayout()
        controls.setSpacing(7)
        self.capture_button = QPushButton("识别当前屏幕")
        self.capture_button.setObjectName("capture")
        self.capture_button.clicked.connect(self.request_manual)
        controls.addWidget(self.capture_button)
        self.pause_button = QPushButton("暂停")
        self.pause_button.setCheckable(True)
        self.pause_button.toggled.connect(self.set_paused)
        controls.addWidget(self.pause_button)
        controls.addStretch()
        self.auto_box = QCheckBox("自动")
        self.auto_box.setToolTip("滚动或翻页停止后识别；窗口内滚动不会触发")
        self.auto_box.toggled.connect(self.set_automatic)
        controls.addWidget(self.auto_box)
        layout.addLayout(controls)
        self.status_label = QLabel("就绪 · 点击识别开始")
        self.status_label.setObjectName("status")
        self.status_label.setTextFormat(Qt.PlainText)
        self.status_label.setWordWrap(True)
        self.status_label.setSizePolicy(QSizePolicy.Preferred, QSizePolicy.Minimum)
        layout.addWidget(self.status_label)
        self.scroll = QScrollArea()
        self.scroll.setWidgetResizable(True)
        self.scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        self.scroll.setSizePolicy(QSizePolicy.Preferred, QSizePolicy.Fixed)
        self.cards = QWidget()
        self.cards_layout = QVBoxLayout(self.cards)
        self.cards_layout.setContentsMargins(0, 0, 0, 0)
        self.cards_layout.setSpacing(8)
        self.cards_layout.setAlignment(Qt.AlignTop)
        self.scroll.setWidget(self.cards)
        self.scroll.hide()
        layout.addWidget(self.scroll)
        disclosure = QLabel("本地 OCR · AI 解释  ·  说明")
        disclosure.setObjectName("footer")
        disclosure.setToolTip(
            "识别时会将所选区域的文字片段发送给配置的 AI 服务。\n"
            f"单次片段最多 {config['llm']['max_context_chars']} 字；本地保存掌握标记和解释缓存。"
        )
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
            self.status_label.setText("请先在项目根目录 .env 中填写 FLOWGLOSS_API_KEY，然后重新启动。")
        self.schedule_fit()

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
        if self._closing or not self.auto_box.isChecked() or self.pause_button.isChecked() or self.pointer_inside():
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
        self.schedule_fit()

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
            self.schedule_fit()

    def clear_cards(self) -> None:
        while self.cards_layout.count():
            item = self.cards_layout.takeAt(0)
            if item.widget():
                item.widget().hide()
                item.widget().deleteLater()
        self.schedule_fit()

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
            body.setContentsMargins(12, 11, 12, 9)
            body.setSpacing(7)
            heading_row = QHBoxLayout()
            heading = QLabel(result.term)
            heading.setObjectName("term")
            heading.setTextFormat(Qt.PlainText)
            heading.setWordWrap(True)
            heading_row.addWidget(heading, 1)
            if result.cached:
                badge = QLabel("缓存")
                badge.setObjectName("badge")
                heading_row.addWidget(badge)
            body.addLayout(heading_row)
            text = QLabel(result.text)
            text.setObjectName("answer")
            text.setTextFormat(Qt.PlainText)
            text.setWordWrap(True)
            text.setTextInteractionFlags(Qt.TextSelectableByMouse)
            body.addWidget(text)
            mastered = QPushButton("已掌握，不再提示")
            mastered.setObjectName("mastered")
            mastered.setSizePolicy(QSizePolicy.Maximum, QSizePolicy.Fixed)
            mastered.clicked.connect(lambda checked=False, term=result.term, widget=card: self.mark_mastered(term, widget))
            body.addWidget(mastered)
            self.cards_layout.addWidget(card)
        self.schedule_fit()

    def mark_mastered(self, term: str, card: QWidget) -> None:
        try:
            self.database.update_word(term)
            card.hide()
            self.schedule_fit()
            self.status_label.setText(f"已记录：{term}")
        except Exception:
            self.status_label.setText("学习记录保存失败，请检查数据库文件权限。")

    def schedule_fit(self) -> None:
        self._fit_timer.start(0)

    def fit_to_content(self) -> None:
        """空闲时只显示工具条；解释按实际高度展开，超出上限才滚动。"""
        screen = self.screen().availableGeometry()
        visible_cards = any(
            self.cards_layout.itemAt(index).widget() is not None
            and not self.cards_layout.itemAt(index).widget().isHidden()
            for index in range(self.cards_layout.count())
        )
        bottom = self.geometry().bottom() + 1
        if visible_cards:
            # 预留滚动条宽度，使长文字在出现滚动条前后保持相同换行。
            body_width = self.width() - 28 - 6
            self.cards_layout.invalidate()
            body_height = max(1, self.cards_layout.totalHeightForWidth(body_width))
            maximum = max(80, min(420, int(screen.height() * 0.65) - 150))
            self.cards.setMinimumHeight(body_height)
            self.scroll.setFixedHeight(min(body_height, maximum))
            self.scroll.show()
        else:
            self.cards.setMinimumHeight(0)
            self.scroll.hide()
            self.scroll.setFixedHeight(0)
        self._content_layout.invalidate()
        self._content_layout.activate()
        self.layout().invalidate()
        self.layout().activate()
        height = self._content_layout.totalHeightForWidth(self.width())
        if height < 0:
            height = self._content_layout.sizeHint().height()
        self.resize(self.width(), max(125, height))
        top = max(screen.top() + 12, min(bottom - self.height(), screen.bottom() - self.height() - 12))
        self.move(self.x(), top)
        self.sync_excluded_region()

    def pointer_inside(self) -> bool:
        return self.isVisible() and self.frameGeometry().contains(QCursor.pos())

    def sync_excluded_region(self) -> None:
        """GUI 主线程发布原生物理坐标，兼容 Windows 显示缩放。"""
        if not hasattr(self, "monitor"):
            return
        if not self.isVisible():
            self.monitor.set_excluded_regions([])
            return
        bounds = native_window_rect(int(self.winId()))
        if bounds is None:
            rect = self.frameGeometry()
            bounds = (rect.left(), rect.top(), rect.right() + 1, rect.bottom() + 1)
        self.monitor.set_excluded_regions([bounds])

    def showEvent(self, event) -> None:
        super().showEvent(event)
        self.sync_excluded_region()

    def hideEvent(self, event) -> None:
        super().hideEvent(event)
        self.sync_excluded_region()

    def moveEvent(self, event) -> None:
        super().moveEvent(event)
        self.sync_excluded_region()

    def resizeEvent(self, event) -> None:
        super().resizeEvent(event)
        self.sync_excluded_region()

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
