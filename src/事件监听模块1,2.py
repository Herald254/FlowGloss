import logging
import threading
from typing import Callable, Iterable, Optional, Set

from pynput import keyboard, mouse


logger = logging.getLogger(__name__)


# 这里就是默认监听列表，你后续只需要改这一个列表即可。
# 可用项：
# - "mouse_scroll"
# - "space", "enter"
# - "page_down", "page_up"
# - "up", "down", "left", "right"
# - "home", "end"
DEFAULT_MONITORED_OPERATIONS = [
    "mouse_scroll",
    "space",
    "enter",
    "page_down",
    "page_up",
    "up",
    "down",
    "left",
    "right",
    "home",
    "end",
]


KEY_NAME_MAP = {
    "space": keyboard.Key.space,
    "enter": keyboard.Key.enter,
    "page_down": keyboard.Key.page_down,
    "page_up": keyboard.Key.page_up,
    "up": keyboard.Key.up,
    "down": keyboard.Key.down,
    "left": keyboard.Key.left,
    "right": keyboard.Key.right,
    "home": keyboard.Key.home,
    "end": keyboard.Key.end,
}

MOUSE_OPERATION_NAMES = {"mouse_scroll", "scroll", "wheel"}


class ScreenEventMonitor:
    """
    FlowGloss 事件监听模块。

    这个模块只负责监听用户操作，并在操作稳定后触发回调。
    它不直接做截图、OCR 或 LLM 调用。
    """

    def __init__(
        self,
        debounce_interval: float = 0.8,
        on_stable_callback: Optional[Callable[[], None]] = None,
        monitored_operations: Optional[Iterable[str]] = None,
    ) -> None:
        if debounce_interval <= 0:
            raise ValueError("debounce_interval 必须大于 0")

        self.debounce_interval = debounce_interval
        self.on_stable_callback = on_stable_callback

        self.monitored_operations = self._normalize_operations(
            monitored_operations or DEFAULT_MONITORED_OPERATIONS
        )
        self.enable_mouse_scroll, self.trigger_keys = self._parse_operations(
            self.monitored_operations
        )
        self.enable_keyboard = bool(self.trigger_keys)

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

    def set_monitored_operations(self, operations: Iterable[str]) -> None:
        """
        动态更新监听项列表。

        示例：
        monitor.set_monitored_operations(["mouse_scroll", "page_down", "page_up"])
        """
        normalized = self._normalize_operations(operations)
        enable_mouse_scroll, trigger_keys = self._parse_operations(normalized)

        was_running = self.running
        if was_running:
            self.stop()

        with self._lock:
            self.monitored_operations = normalized
            self.enable_mouse_scroll = enable_mouse_scroll
            self.trigger_keys = trigger_keys
            self.enable_keyboard = bool(trigger_keys)

        if was_running:
            self.start()

    def get_monitored_operations(self) -> list[str]:
        with self._lock:
            return list(self.monitored_operations)

    def notify_activity(self) -> None:
        self._reset_timer()

    def trigger_now(self) -> None:
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
                "monitored_operations": list(self.monitored_operations),
            }

    def _normalize_operations(self, operations: Iterable[str]) -> list[str]:
        normalized = []
        seen = set()

        for item in operations:
            name = str(item).strip().lower()
            if not name or name in seen:
                continue
            normalized.append(name)
            seen.add(name)

        if not normalized:
            raise ValueError("monitored_operations 不能为空")

        return normalized

    def _parse_operations(
        self, operations: Iterable[str]
    ) -> tuple[bool, Set[keyboard.Key | keyboard.KeyCode]]:
        enable_mouse_scroll = False
        trigger_keys: Set[keyboard.Key | keyboard.KeyCode] = set()
        invalid_names = []

        for name in operations:
            if name in MOUSE_OPERATION_NAMES:
                enable_mouse_scroll = True
            elif name in KEY_NAME_MAP:
                trigger_keys.add(KEY_NAME_MAP[name])
            else:
                invalid_names.append(name)

        if invalid_names:
            valid_names = sorted(list(MOUSE_OPERATION_NAMES) + list(KEY_NAME_MAP.keys()))
            raise ValueError(
                f"未知监听项: {invalid_names}。可用项: {valid_names}"
            )

        return enable_mouse_scroll, trigger_keys

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
        print("检测到操作已稳定，可以开始截图或 OCR。")

    monitor = ScreenEventMonitor(on_stable_callback=demo_callback)
    monitor.start()
    print("事件监听已启动。")
    print(f"当前监听列表: {monitor.get_monitored_operations()}")
    print("滚轮或监听列表中的按键触发后，停顿约 0.8 秒会执行回调。按 Ctrl+C 退出。")

    try:
        while True:
            threading.Event().wait(1.0)
    except KeyboardInterrupt:
        monitor.stop()
        print("事件监听已停止。")
