# e:\code\FlowGloss\core\vision\capturer.py
"""
基于mss的极速屏幕截图。

技术简介：
- 使用mss（Multiple Screen Shots）库实现高性能屏幕捕获
- 支持多显示器环境下的精确区域截图
- 返回numpy数组格式，便于后续OpenCV处理

模块功能：
- 截取指定屏幕区域的像素数据（支持坐标和尺寸参数）
- 实现屏幕分辨率自适应，处理DPI缩放问题
- 提供帧率控制，避免过高的截图频率消耗资源

整体作用：
数据原材料供应，为后续图像处理和OCR识别提供原始视觉数据。

对外方法：
- grab_screen(region: tuple) -> ndarray: 截取指定区域，返回BGR格式的numpy数组
- get_screen_size() -> tuple: 获取主屏幕分辨率
- capture_full_screen() -> ndarray: 全屏截图

联系：
供processor.py调用，提供图像差分分析的输入数据。

线程位置：
Vision子进程/主线程。在独立的视觉处理进程中运行，避免阻塞主进程。
"""

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
        try:
            self.monitor_index = self._validate_monitor_index(monitor_index)
        except Exception:
            self._sct.close()
            raise

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

    def get_capture_bounds(self, region=None) -> tuple[int, int, int, int]:
        """返回截图的原生物理边界，供 GUI 匹配显示器，不传递屏幕内容。"""
        rect = self._build_capture_region(region)
        return rect["left"], rect["top"], rect["left"] + rect["width"], rect["top"] + rect["height"]

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
