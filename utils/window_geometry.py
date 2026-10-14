"""获取 Windows 原生窗口矩形，与 pynput 的物理屏幕坐标一致。

在 GUI 主线程调用，将结果快照交给监听器，避免后台读取 Qt 对象。
其他平台及离屏测试由调用方使用 Qt 坐标回退。
"""

import os


def native_window_rect(window_id: int) -> tuple[int, int, int, int] | None:
    if os.name != "nt":
        return None
    import ctypes
    from ctypes import wintypes

    user32 = ctypes.WinDLL("user32", use_last_error=True)
    get_rect = user32.GetWindowRect
    get_rect.argtypes = [wintypes.HWND, ctypes.POINTER(wintypes.RECT)]
    get_rect.restype = wintypes.BOOL
    rect = wintypes.RECT()
    if get_rect(window_id, ctypes.byref(rect)) and rect.right > rect.left and rect.bottom > rect.top:
        return rect.left, rect.top, rect.right, rect.bottom
    return None
