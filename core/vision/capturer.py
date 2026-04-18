from __future__ import annotations

import logging
import platform
import threading
import time
from typing import Optional, Tuple

import mss
import numpy as np


logger = logging.getLogger("core.vision.capturer")


def _enable_windows_dpi_awareness() -> None:
    """
    Best-effort DPI awareness setup for Windows.

    Prefer per-monitor awareness when available so multi-display coordinates stay
    accurate under mixed scaling ratios.
    """
    if platform.system() != "Windows":
        return

    try:
        import ctypes

        user32 = ctypes.windll.user32
        shcore = getattr(ctypes.windll, "shcore", None)

        # Windows 10+ per-monitor v2 awareness.
        if hasattr(user32, "SetProcessDpiAwarenessContext"):
            per_monitor_v2 = ctypes.c_void_p(-4)
            if user32.SetProcessDpiAwarenessContext(per_monitor_v2):
                return

        # Windows 8.1 per-monitor awareness.
        if shcore and hasattr(shcore, "SetProcessDpiAwareness"):
            shcore.SetProcessDpiAwareness(2)
            return

        # Legacy fallback.
        if hasattr(user32, "SetProcessDPIAware"):
            user32.SetProcessDPIAware()
    except Exception as exc:  # pragma: no cover - platform-specific best effort
        logger.warning("Failed to enable Windows DPI awareness: %s", exc)


_enable_windows_dpi_awareness()


class ScreenCapturer:
    """
    High-performance screen capturer based on mss.

    Responsibilities:
    - Capture full-screen or region screenshots.
    - Return OpenCV-friendly BGR numpy arrays.
    - Support multi-monitor environments with precise region capture.
    - Apply frame-rate limiting to avoid wasting CPU resources.

    Coordinate semantics:
    - If monitor_index == 0, region is treated as virtual-desktop coordinates.
    - If monitor_index >= 1, region is treated as coordinates relative to that
      specific monitor.
    """

    def __init__(self, monitor_index: int = 1, max_fps: int = 10) -> None:
        if max_fps < 0:
            raise ValueError("max_fps must be >= 0")

        self._lock = threading.Lock()
        self._sct = mss.mss()
        self._last_capture_time = 0.0

        self.max_fps = max_fps
        self._min_interval = 1.0 / max_fps if max_fps > 0 else 0.0
        self.monitor_index = self._validate_monitor_index(monitor_index)

        logger.info(
            "ScreenCapturer initialized. monitor_index=%s, max_fps=%s",
            self.monitor_index,
            self.max_fps,
        )

    def _validate_monitor_index(self, monitor_index: int) -> int:
        if not isinstance(monitor_index, int):
            raise TypeError("monitor_index must be an int")

        max_index = len(self._sct.monitors) - 1
        if monitor_index < 0 or monitor_index > max_index:
            raise ValueError(
                f"Invalid monitor_index={monitor_index}. "
                f"Available range is 0..{max_index}."
            )
        return monitor_index

    def get_screen_size(self) -> Tuple[int, int]:
        """
        Return the primary monitor resolution as (width, height).
        """
        primary_monitor = self._sct.monitors[1]
        return primary_monitor["width"], primary_monitor["height"]

    def capture_full_screen(self) -> np.ndarray:
        """
        Capture the full target screen and return a BGR numpy array.

        If monitor_index == 0, this captures the entire virtual desktop.
        Otherwise, it captures the selected physical monitor.
        """
        return self.grab_screen(region=None)

    def grab_screen(self, region: Optional[Tuple[int, int, int, int]] = None) -> np.ndarray:
        """
        Capture a screen region and return a BGR numpy array.

        Args:
            region: Optional tuple of (left, top, width, height).
                - For monitor_index == 0, uses virtual-desktop coordinates.
                - For monitor_index >= 1, uses coordinates relative to the
                  selected monitor.
                - If None, captures the entire target screen.
        """
        self._enforce_framerate_limit()

        monitor_dict = self._build_capture_region(region)

        try:
            screenshot = self._sct.grab(monitor_dict)
        except Exception as exc:
            logger.error("Screen capture failed: %s", exc, exc_info=True)
            raise RuntimeError(f"Screen capture failed: {exc}") from exc

        bgra = np.frombuffer(screenshot.bgra, dtype=np.uint8).reshape(
            screenshot.height, screenshot.width, 4
        )
        return bgra[:, :, :3].copy()

    def _build_capture_region(self, region: Optional[Tuple[int, int, int, int]]) -> dict:
        if region is None:
            monitor = self._sct.monitors[self.monitor_index]
            return {
                "left": monitor["left"],
                "top": monitor["top"],
                "width": monitor["width"],
                "height": monitor["height"],
            }

        if len(region) != 4:
            raise ValueError("region must be a tuple of (left, top, width, height)")

        left, top, width, height = region
        if width <= 0 or height <= 0:
            raise ValueError("region width and height must be > 0")

        if self.monitor_index == 0:
            absolute_left = left
            absolute_top = top
        else:
            monitor = self._sct.monitors[self.monitor_index]
            absolute_left = monitor["left"] + left
            absolute_top = monitor["top"] + top

        return {
            "left": int(absolute_left),
            "top": int(absolute_top),
            "width": int(width),
            "height": int(height),
        }

    def _enforce_framerate_limit(self) -> None:
        if self._min_interval <= 0:
            return

        with self._lock:
            current_time = time.monotonic()
            elapsed = current_time - self._last_capture_time
            if elapsed < self._min_interval:
                time.sleep(self._min_interval - elapsed)
            self._last_capture_time = time.monotonic()

    def close(self) -> None:
        if getattr(self, "_sct", None) is not None:
            self._sct.close()
            self._sct = None

    def __enter__(self) -> "ScreenCapturer":
        return self

    def __exit__(self, exc_type, exc_val, exc_tb) -> None:
        self.close()
