"""获取 Windows 原生窗口矩形，与 pynput 的物理屏幕坐标一致。

在 GUI 主线程调用，将结果快照交给监听器，避免后台读取 Qt 对象。
其他平台及离屏测试由调用方使用 Qt 坐标回退。
"""

import os


def native_monitor_rects() -> dict[str, tuple[int, int, int, int]]:
    """按设备名获取显示器物理边界，避免混合 DPI 下按 Qt 顺序猜测。"""
    if os.name != "nt":
        return {}
    import ctypes
    from ctypes import wintypes

    class MonitorInfo(ctypes.Structure):
        _fields_ = [("size", wintypes.DWORD), ("monitor", wintypes.RECT),
                    ("work", wintypes.RECT), ("flags", wintypes.DWORD),
                    ("device", wintypes.WCHAR * 32)]

    user32 = ctypes.WinDLL("user32", use_last_error=True)
    callback_type = ctypes.WINFUNCTYPE(wintypes.BOOL, wintypes.HANDLE, wintypes.HDC,
                                      ctypes.POINTER(wintypes.RECT), wintypes.LPARAM)
    user32.GetMonitorInfoW.argtypes = [wintypes.HANDLE, ctypes.POINTER(MonitorInfo)]
    user32.GetMonitorInfoW.restype = wintypes.BOOL
    user32.EnumDisplayMonitors.argtypes = [wintypes.HDC, ctypes.POINTER(wintypes.RECT), callback_type, wintypes.LPARAM]
    result = {}

    @callback_type
    def collect(handle, dc, rect, data):
        info = MonitorInfo()
        info.size = ctypes.sizeof(info)
        if user32.GetMonitorInfoW(handle, ctypes.byref(info)):
            r = info.monitor
            result[info.device] = (r.left, r.top, r.right, r.bottom)
        return True

    user32.EnumDisplayMonitors(None, None, collect, 0)
    return result


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
