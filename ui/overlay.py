# e:\code\FlowGloss\ui\overlay.py
"""
基于 PySide6 的置顶伴读窗口。

提供手动识别、自动监听、暂停、退出和已掌握反馈。
支持收起为悬浮球；主动识别展开结果，自动识别只提醒。
通过 Signal/Slot 在主线程更新界面；截图期间隐藏窗口，避免识别自身。
采用不激活窗口属性；当前支持拖动，尚未实现点击穿透、亚克力或托盘。
"""

from __future__ import annotations

from PySide6.QtCore import (
    QObject, QPoint, QRect, Qt, QTimer, Signal, Slot, QPropertyAnimation,
    QParallelAnimationGroup, QSequentialAnimationGroup, QPauseAnimation, QEasingCurve,
)
from PySide6.QtGui import QFont, QCursor
from PySide6.QtWidgets import (
    QApplication, QCheckBox, QFrame, QLabel, QPushButton,
    QScrollArea, QVBoxLayout, QHBoxLayout, QWidget, QSizePolicy, QLayout,
    QGraphicsOpacityEffect, QMenu,
)

from core.monitor.event_hook import ScreenEventMonitor
from core.worker import ReadingWorker
from data.database import KnowledgeDB
from utils.window_geometry import native_window_rect
from ui.floating_orb import FloatingOrb


class MonitorSignals(QObject):
    stable = Signal()


class OverlayWindow(QWidget):
    """可拖动的伴读提示窗；按钮控制识别、暂停和已掌握反馈。

    使用 Qt 信号在 GUI 主线程更新界面，不在事件监听回调中操作窗口。
    """

    PANEL_WIDTH = 360
    ORB_SIZE = 56

    def __init__(self, config: dict, prompts: dict) -> None:
        super().__init__()
        self.config = config
        self._closing = False
        self._worker_done = False
        self._capture_hidden = False
        self._drag_offset = None
        self._collapsed = False
        self._busy = False
        self._manual_request = False
        self._orb_error = False
        self._unread_count = 0
        self._expanded_height = 155
        self._transition = None
        self._transition_kind = None
        self._motion_target = None
        self.database = KnowledgeDB(config["storage"]["database_path"])
        self.setWindowTitle("FlowGloss")
        self.setFont(QFont("Microsoft YaHei UI", 10))
        self.setWindowFlags(Qt.Tool | Qt.FramelessWindowHint | Qt.WindowStaysOnTopHint | Qt.WindowDoesNotAcceptFocus)
        self.setAttribute(Qt.WA_ShowWithoutActivating)
        self.setWindowOpacity(config["ui"]["opacity"])
        self.setAttribute(Qt.WA_TranslucentBackground)
        self.resize(360, 155)
        self._fit_timer = QTimer(self)
        self._fit_timer.setSingleShot(True)
        self._fit_timer.timeout.connect(lambda: self.fit_to_content(animate=True))
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
        self.surface = surface
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
        self.collapse_button = QPushButton("−")
        self.collapse_button.setObjectName("close")
        self.collapse_button.setFixedSize(24, 24)
        self.collapse_button.setToolTip("收起为悬浮球")
        self.collapse_button.clicked.connect(lambda: self.set_collapsed(True))
        header.addWidget(self.collapse_button)
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
        self._panel_effect = QGraphicsOpacityEffect(surface)
        self._panel_effect.setOpacity(1)
        surface.setGraphicsEffect(self._panel_effect)
        self.orb = FloatingOrb(self)
        self._orb_effect = QGraphicsOpacityEffect(self.orb)
        self._orb_effect.setOpacity(1)
        self.orb.setGraphicsEffect(self._orb_effect)
        self.orb.double_clicked.connect(lambda: self.set_collapsed(False))
        self.orb.moved.connect(self.move_within_screen)
        self.orb.context_requested.connect(self.show_orb_menu)
        self.orb.hide()
        self._orb_menu = QMenu(self)
        self._orb_menu.addAction("展开", lambda: self.set_collapsed(False))
        self._orb_menu.addAction("识别当前屏幕", self.request_manual)
        self._orb_pause_action = self._orb_menu.addAction("暂停", self.pause_button.toggle)
        self._orb_auto_action = self._orb_menu.addAction("自动识别")
        self._orb_auto_action.setCheckable(True)
        self._orb_auto_action.triggered.connect(self.auto_box.setChecked)
        self._orb_menu.addSeparator()
        self._orb_menu.addAction("退出", self.close)
        self._orb_menu.aboutToShow.connect(lambda: QTimer.singleShot(0, self.sync_excluded_region))
        self._orb_menu.aboutToHide.connect(lambda: QTimer.singleShot(0, self.sync_excluded_region))
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
        self.update_orb()

    def _has_key(self) -> bool:
        if not self.config["llm"]["api_key"].strip():
            self.status_label.setText("尚未配置 API 密钥，请设置后重新启动。")
            self.set_busy(False, error=True)
            self.schedule_fit()
            return False
        return True

    @Slot()
    def request_manual(self) -> None:
        if self._has_key() and self.worker.request(manual=True):
            self._manual_request = True
            self.clear_cards()
            self.status_label.setText("正在准备识别…")
            self.set_busy(True)

    @Slot()
    def request_automatic(self) -> None:
        if self._closing or self._manual_request or not self.auto_box.isChecked() or self.pause_button.isChecked() or self.pointer_inside():
            return
        if self._has_key() and self.worker.request():
            self.clear_cards()
            self.status_label.setText("页面已稳定，正在准备识别…")
            self.set_busy(True)

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
        self._manual_request = False
        self.worker.set_paused(paused)
        self.capture_button.setEnabled(not paused)
        self.pause_button.setText("继续" if paused else "暂停")
        self.set_automatic(self.auto_box.isChecked() and not paused)
        self.clear_cards()
        self.status_label.setText("已暂停，不进行截图和请求。" if paused else "已继续。")
        self.set_busy(False)
        self.schedule_fit()

    @Slot(int)
    def prepare_capture(self, number: int) -> None:
        if not self.worker.queue.is_current(number) or self._closing:
            self.worker.permit_capture(number)
            return
        self._capture_hidden = True
        self.stop_motion(complete=True)
        self._orb_menu.hide()
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
            if not message.startswith("正在"):
                self.set_busy(False, error=True)
                if self._manual_request:
                    self._manual_request = False
                    if self._collapsed:
                        self.fit_to_content()
                        self.set_collapsed(False)
            self.schedule_fit()

    def clear_cards(self) -> None:
        self._unread_count = 0
        self.update_orb()
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
        manual = self._manual_request
        self._manual_request = False
        self.clear_cards()
        self.status_label.setText(message)
        self.set_busy(False)
        count = 0
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
            if not self._collapsed and self.isVisible():
                self.reveal_card(card, count)
            count += 1
        if self._collapsed and count and not manual:
            self._unread_count = count
            self.update_orb()
            self.orb.notify_result()
        self.schedule_fit()
        if manual and self._collapsed:
            self.fit_to_content()
            self.set_collapsed(False)

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

    def fit_to_content(self, animate: bool = False) -> None:
        """空闲时只显示工具条；解释按实际高度展开，超出上限才滚动。"""
        self._fit_timer.stop()
        screen = self.screen().availableGeometry()
        visible_cards = any(
            self.cards_layout.itemAt(index).widget() is not None
            and not self.cards_layout.itemAt(index).widget().isHidden()
            for index in range(self.cards_layout.count())
        )
        if visible_cards:
            # 预留滚动条宽度，使长文字在出现滚动条前后保持相同换行。
            body_width = self.PANEL_WIDTH - 28 - 6
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
        height = self._content_layout.totalHeightForWidth(self.PANEL_WIDTH)
        if height < 0:
            height = self._content_layout.sizeHint().height()
        self._expanded_height = max(125, height)
        if self._collapsed:
            return
        target = self.target_rect(self.PANEL_WIDTH, self._expanded_height)
        if animate and self.isVisible() and not self._capture_hidden:
            kind = "expand" if self._transition_kind == "expand" else "resize"
            self.start_motion(target, kind)
        else:
            self.stop_motion()
            self.setGeometry(target)
            self.finish_display_mode()

    def target_rect(self, width: int, height: int) -> QRect:
        """沿右下角展开，并保证完整窗口留在可见桌面内。"""
        screen = self.screen().availableGeometry()
        anchor = self.geometry().bottomRight()
        x = max(screen.left() + 8, min(anchor.x() - width + 1, screen.right() - width - 7))
        y = max(screen.top() + 8, min(anchor.y() - height + 1, screen.bottom() - height - 7))
        return QRect(x, y, width, height)

    def set_collapsed(self, collapsed: bool, animate: bool = True) -> None:
        if self._closing or collapsed == self._collapsed:
            return
        self._fit_timer.stop()
        # 先计算隐藏面板的目标高度，收起状态也可以接收新结果。
        if not self._collapsed:
            self.fit_to_content()
        self._collapsed = collapsed
        width, height = (self.ORB_SIZE, self.ORB_SIZE) if collapsed else (self.PANEL_WIDTH, self._expanded_height)
        target = self.target_rect(width, height)
        if animate and self.isVisible() and not self._capture_hidden:
            self.start_motion(target, "collapse" if collapsed else "expand")
        else:
            self.stop_motion()
            self.setGeometry(target)
            self.finish_display_mode()

    def start_motion(self, target: QRect, kind: str) -> None:
        self.stop_motion()
        if self.geometry() == target and kind == "resize":
            self.finish_display_mode()
            return
        self.layout().setEnabled(False)
        if self.surface.isHidden():
            self._panel_effect.setOpacity(0)
        self.surface.show()
        if kind in ("collapse", "expand"):
            if self.orb.isHidden():
                self._orb_effect.setOpacity(0)
            self.orb.show()
            self.orb.raise_()
            self.orb.setEnabled(False)
        self.collapse_button.setEnabled(False)
        self._motion_target = QRect(target)
        self._transition_kind = kind
        self.position_layers()
        group = QParallelAnimationGroup(self)
        self._transition = group
        geometry = QPropertyAnimation(self, b"geometry", group)
        geometry.setStartValue(self.geometry())
        geometry.setEndValue(target)
        geometry.setDuration(220 if kind != "resize" else 180)
        geometry.setEasingCurve(QEasingCurve.OutCubic)
        group.addAnimation(geometry)
        for effect, end in ((self._panel_effect, 0.0 if self._collapsed else 1.0), (self._orb_effect, 1.0 if self._collapsed else 0.0)):
            fade = QPropertyAnimation(effect, b"opacity", group)
            fade.setStartValue(effect.opacity())
            fade.setEndValue(end)
            fade.setDuration(180)
            fade.setEasingCurve(QEasingCurve.InOutQuad)
            group.addAnimation(fade)

        def finish() -> None:
            if self._transition is group:
                self._transition = None
                self._transition_kind = None
                self._motion_target = None
                self.finish_display_mode()
                group.deleteLater()

        group.finished.connect(finish)
        group.start()

    def stop_motion(self, complete: bool = False) -> None:
        target = self._motion_target
        if self._transition is not None:
            self._transition.stop()
            self._transition.deleteLater()
            self._transition = None
        self._transition_kind = None
        self._motion_target = None
        if complete and target is not None:
            self.setGeometry(target)
            self.finish_display_mode()

    def position_layers(self) -> None:
        if not hasattr(self, "orb"):
            return
        self.orb.move(self.width() - self.ORB_SIZE, self.height() - self.ORB_SIZE)
        if self._transition_kind is not None:
            self.surface.setGeometry(0, 0, self.PANEL_WIDTH, self._expanded_height)

    def finish_display_mode(self) -> None:
        self.surface.setVisible(not self._collapsed)
        self.orb.setVisible(self._collapsed)
        self.orb.setEnabled(True)
        self.collapse_button.setEnabled(True)
        self._panel_effect.setOpacity(1)
        self._orb_effect.setOpacity(1)
        self.layout().setEnabled(not self._collapsed)
        if not self._collapsed:
            self.layout().activate()
            self._unread_count = 0
        self.position_layers()
        self.update_orb()
        self.sync_excluded_region()

    def reveal_card(self, card: QWidget, index: int) -> None:
        """尺寸变化与轻微错峰淡入衔接，不移动正文造成阅读跳动。"""
        effect = QGraphicsOpacityEffect(card)
        effect.setOpacity(0)
        card.setGraphicsEffect(effect)
        group = QSequentialAnimationGroup(card)
        group.addAnimation(QPauseAnimation(60 + index * 35, group))
        fade = QPropertyAnimation(effect, b"opacity", group)
        fade.setStartValue(0.0)
        fade.setEndValue(1.0)
        fade.setDuration(180)
        fade.setEasingCurve(QEasingCurve.OutCubic)
        group.addAnimation(fade)
        group.finished.connect(group.deleteLater)
        group.start()

    def set_busy(self, busy: bool, error: bool = False) -> None:
        self._busy, self._orb_error = busy, error
        self.update_orb()

    def update_orb(self) -> None:
        if not hasattr(self, "orb"):
            return
        paused = self.pause_button.isChecked()
        self.orb.set_state(self._busy, self._unread_count, paused, self._orb_error)
        if paused:
            message = "已暂停 · 双击展开，右键继续"
        elif self._busy:
            message = self.status_label.text()
        elif self._unread_count:
            message = f"有 {self._unread_count} 个新解释 · 双击查看"
        elif self._orb_error:
            message = self.status_label.text() + " · 双击展开"
        else:
            message = "FlowGloss · 双击展开，按住拖动，右键功能栏"
        self.orb.setToolTip(message)

    @Slot(QPoint)
    def move_within_screen(self, position: QPoint) -> None:
        self.stop_motion(complete=True)
        screen = QApplication.screenAt(position + QPoint(self.width() // 2, self.height() // 2)) or self.screen()
        rect = screen.availableGeometry()
        x = max(rect.left() + 4, min(position.x(), rect.right() - self.width() - 3))
        y = max(rect.top() + 4, min(position.y(), rect.bottom() - self.height() - 3))
        self.move(x, y)

    @Slot(QPoint)
    def show_orb_menu(self, position: QPoint) -> None:
        self._orb_pause_action.setText("继续" if self.pause_button.isChecked() else "暂停")
        self._orb_auto_action.setChecked(self.auto_box.isChecked())
        self._orb_menu.popup(position)

    def pointer_inside(self) -> bool:
        return self._orb_menu.isVisible() or (self.isVisible() and self.frameGeometry().contains(QCursor.pos()))

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
        regions = [bounds]
        if self._orb_menu.isVisible():
            menu_bounds = native_window_rect(int(self._orb_menu.winId()))
            if menu_bounds is None:
                rect = self._orb_menu.frameGeometry()
                menu_bounds = (rect.left(), rect.top(), rect.right() + 1, rect.bottom() + 1)
            regions.append(menu_bounds)
        self.monitor.set_excluded_regions(regions)

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
        self.position_layers()
        self.sync_excluded_region()

    def mousePressEvent(self, event) -> None:
        if event.button() == Qt.LeftButton and event.position().y() < 50:
            self.stop_motion(complete=True)
            self._drag_offset = event.globalPosition().toPoint() - self.pos()

    def mouseMoveEvent(self, event) -> None:
        if self._drag_offset is not None and event.buttons() & Qt.LeftButton:
            self.move_within_screen(event.globalPosition().toPoint() - self._drag_offset)

    def mouseReleaseEvent(self, event) -> None:
        self._drag_offset = None

    def closeEvent(self, event) -> None:
        if self._worker_done:
            event.accept()
            return
        event.ignore()
        if not self._closing:
            self._closing = True
            self._fit_timer.stop()
            self.stop_motion(complete=True)
            self._orb_menu.hide()
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
