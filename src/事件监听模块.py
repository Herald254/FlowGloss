import logging
import threading
from typing import Callable, Optional, Set

from pynput import keyboard, mouse


logger = logging.getLogger(__name__)


class ScreenEventMonitor:
    """
    FlowGloss 事件监听模块。

    作用：
    1. 监听全局鼠标滚轮与常见翻页按键。
    2. 使用 debounce 机制判断“用户已经停下来”。
    3. 在画面稳定后触发一个轻量回调，供主框架决定是否截图、OCR 或调用模型。

    设计原则：
    - 本模块只负责“感知稳定时机”，不直接做重型任务。
    - 回调运行在线程中，并带有防重入保护。
    - 停止监听后，不再触发任何新的回调。
    """

    DEFAULT_TRIGGER_KEYS: Set[keyboard.Key] = {
        keyboard.Key.space,
        keyboard.Key.enter,
        keyboard.Key.page_down,
        keyboard.Key.page_up,
        keyboard.Key.up,
        keyboard.Key.down,
        keyboard.Key.left,
        keyboard.Key.right,
        keyboard.Key.home,
        keyboard.Key.end,
    }

    def __init__(
        self,
        debounce_interval: float = 0.8,
        on_stable_callback: Optional[Callable[[], None]] = None,
        trigger_keys: Optional[Set[keyboard.Key | keyboard.KeyCode]] = None,
        enable_mouse_scroll: bool = True,
        enable_keyboard: bool = True,
    ) -> None:
        if debounce_interval <= 0:
            raise ValueError("debounce_interval 必须大于 0")

        self.debounce_interval = debounce_interval
        self.on_stable_callback = on_stable_callback
        self.trigger_keys: Set[keyboard.Key | keyboard.KeyCode] = set(
            trigger_keys or self.DEFAULT_TRIGGER_KEYS
        )
        self.enable_mouse_scroll = enable_mouse_scroll
        self.enable_keyboard = enable_keyboard

        self._lock = threading.RLock()
        self._timer: Optional[threading.Timer] = None
        self._timer_generation = 0
        self._running = False

        self._callback_running = False
        self._callback_pending = False

        self.mouse_listener: Optional[mouse.Listener] = None
        self.keyboard_listener: Optional[keyboard.Listener] = None

        self.event_count = 0
        self.stable_trigger_count = 0

    @property
    def running(self) -> bool:
        with self._lock:
            return self._running

    def set_callback(self, callback: Optional[Callable[[], None]]) -> None:
        with self._lock:
            self.on_stable_callback = callback

    def notify_activity(self) -> None:
        """
        手动通知一次“用户正在操作”。

        这允许主框架把别的事件源也接进来，而不必依赖全局键鼠监听。
        """
        self._reset_timer()

    def trigger_now(self) -> None:
        """
        立即触发一次稳定回调，跳过 debounce。
        """
        self._dispatch_callback()

    def start(self) -> None:
        with self._lock:
            if self._running:
                return
            self._running = True

        if self.enable_mouse_scroll:
            self.mouse_listener = mouse.Listener(on_scroll=self._on_scroll)
            self.mouse_listener.daemon = True
            self.mouse_listener.start()

        if self.enable_keyboard:
            self.keyboard_listener = keyboard.Listener(on_release=self._on_key_release)
            self.keyboard_listener.daemon = True
            self.keyboard_listener.start()

    def stop(self) -> None:
        with self._lock:
            self._running = False
            self._callback_pending = False
            self._cancel_timer_locked()

        if self.mouse_listener is not None:
            self.mouse_listener.stop()
            self.mouse_listener = None

        if self.keyboard_listener is not None:
            self.keyboard_listener.stop()
            self.keyboard_listener = None

    def get_status(self) -> dict:
        with self._lock:
            return {
                "running": self._running,
                "event_count": self.event_count,
                "stable_trigger_count": self.stable_trigger_count,
                "timer_active": self._timer is not None,
                "callback_running": self._callback_running,
                "callback_pending": self._callback_pending,
                "mouse_enabled": self.enable_mouse_scroll,
                "keyboard_enabled": self.enable_keyboard,
            }

    def _reset_timer(self) -> None:
        with self._lock:
            if not self._running:
                return

            self.event_count += 1
            self._timer_generation += 1
            generation = self._timer_generation
            self._cancel_timer_locked()

            self._timer = threading.Timer(
                self.debounce_interval,
                self._trigger_stable,
                args=(generation,),
            )
            self._timer.daemon = True
            self._timer.start()

    def _cancel_timer_locked(self) -> None:
        if self._timer is not None:
            self._timer.cancel()
            self._timer = None

    def _trigger_stable(self, generation: int) -> None:
        with self._lock:
            if not self._running:
                return
            if generation != self._timer_generation:
                return

            self._timer = None
            self.stable_trigger_count += 1

        self._dispatch_callback()

    def _dispatch_callback(self) -> None:
        with self._lock:
            if not self._running:
                return

            if self._callback_running:
                self._callback_pending = True
                return

            self._callback_running = True
            self._callback_pending = False

        worker = threading.Thread(
            target=self._callback_worker,
            name="flowgloss-event-callback",
            daemon=True,
        )
        worker.start()

    def _callback_worker(self) -> None:
        while True:
            with self._lock:
                if not self._running:
                    self._callback_running = False
                    self._callback_pending = False
                    return
                callback = self.on_stable_callback

            if callback is not None:
                try:
                    callback()
                except Exception:
                    logger.exception("ScreenEventMonitor 回调执行失败")

            with self._lock:
                if not self._running:
                    self._callback_running = False
                    self._callback_pending = False
                    return

                if self._callback_pending:
                    self._callback_pending = False
                    continue

                self._callback_running = False
                return

    def _on_scroll(self, x: int, y: int, dx: int, dy: int) -> None:
        self._reset_timer()

    def _on_key_release(self, key: keyboard.Key | keyboard.KeyCode) -> None:
        if key in self.trigger_keys:
            self._reset_timer()

    def __enter__(self) -> "ScreenEventMonitor":
        self.start()
        return self

    def __exit__(self, exc_type, exc_value, traceback) -> None:
        self.stop()


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")

    def demo_callback() -> None:
        print("检测到屏幕操作已稳定，可以开始截图/OCR。")

    monitor = ScreenEventMonitor(on_stable_callback=demo_callback)
    monitor.start()
    print("事件监听已启动。滚轮或翻页后停顿约 0.8 秒会触发回调。按 Ctrl+C 退出。")

    try:
        while True:
            threading.Event().wait(1.0)
    except KeyboardInterrupt:
        monitor.stop()
        print("事件监听已停止。")
