"""真实 Windows 后端的尺寸回归，不以 offscreen 模拟代替原生约束。

测试窗口完全透明，不抢焦点；只测试动画，不截图或调用 AI 服务。
"""

import json
import os
from pathlib import Path
import subprocess
import sys

import pytest


NATIVE_CHECK = r'''
import json, tempfile
from PySide6.QtCore import QTimer, qInstallMessageHandler
from PySide6.QtWidgets import QApplication
from ui.overlay import OverlayWindow
from utils.config_loader import load_config, load_prompts
from utils.window_geometry import native_window_rect
from ui.capture_flash import EdgeStrip

warnings = []
def message(kind, context, text):
    if 'setGeometry' in text:
        warnings.append(text)
qInstallMessageHandler(message)
app = QApplication([])
with tempfile.TemporaryDirectory() as directory:
    config = load_config()
    config['storage']['database_path'] = directory + '/geometry.db'
    config['ui']['auto_start'] = False
    config['llm']['api_key'] = ''
    window = OverlayWindow(config, load_prompts())
    window.setWindowOpacity(0)
    window.show()
    window.set_busy(True)
    # 光效窗口使用真实原生后端，但保持完全透明，不干扰正在使用的桌面。
    original_show = EdgeStrip.show
    def transparent_show(strip):
        strip.setWindowOpacity(0)
        original_show(strip)
    EdgeStrip.show = transparent_show
    from utils.window_geometry import native_monitor_rects
    flash_rects = []
    bounds = native_monitor_rects()
    if bounds:
        screen_bounds = (min(r[0] for r in bounds.values()), min(r[1] for r in bounds.values()),
                         max(r[2] for r in bounds.values()), max(r[3] for r in bounds.values()))
        window.capture_flash.flash(screen_bounds)
        for strip in window.capture_flash.strips:
            native = native_window_rect(int(strip.winId()))
            flash_rects.append({'native': native, 'logical': [strip.width(), strip.height()], 'dpr': strip.devicePixelRatioF()})
    snapshots = []
    def snapshot(name):
        snapshots.append({
            'state': name, 'size': [window.width(), window.height()],
            'native': native_window_rect(int(window.winId())),
            'dpr': window.devicePixelRatioF(),
            'inside': window.screen().availableGeometry().contains(window.geometry()),
        })
    QTimer.singleShot(100, lambda: window.set_collapsed(True))
    QTimer.singleShot(500, lambda: snapshot('collapsed'))
    QTimer.singleShot(600, lambda: window.set_collapsed(False))
    QTimer.singleShot(1000, lambda: snapshot('expanded'))
    QTimer.singleShot(1100, window.close)
    QTimer.singleShot(2500, app.quit)
    app.exec()
    window.worker.wait(2000)
    print(json.dumps({'platform': app.platformName(), 'snapshots': snapshots, 'warnings': warnings, 'closed': window._worker_done, 'flash': flash_rects, 'screen_count': len(app.screens())}))
'''


@pytest.mark.skipif(sys.platform != "win32", reason="需要真实 Windows Qt 后端")
@pytest.mark.parametrize("scale", ["1", "1.5"])
def test_native_collapse_size_matches_dpi_without_geometry_warnings(scale):
    environment = os.environ.copy()
    environment["QT_QPA_PLATFORM"] = "windows"
    environment["QT_SCALE_FACTOR"] = scale
    environment["PYTHONIOENCODING"] = "utf-8"
    result = subprocess.run(
        [sys.executable, "-B", "-c", NATIVE_CHECK],
        cwd=Path(__file__).resolve().parent.parent,
        env=environment, capture_output=True, text=True, encoding="utf-8", timeout=20,
        creationflags=subprocess.CREATE_NO_WINDOW,
    )
    assert result.returncode == 0, result.stderr
    data = json.loads(result.stdout)
    assert data["platform"] == "windows"
    assert data["warnings"] == []
    assert data["closed"]
    assert len(data["flash"]) == 4 * data["screen_count"]
    for strip in data["flash"]:
        l, t, r, b = strip["native"]
        assert abs((r - l) - strip["logical"][0] * strip["dpr"]) <= 1
        assert abs((b - t) - strip["logical"][1] * strip["dpr"]) <= 1
    collapsed, expanded = data["snapshots"]
    assert collapsed["size"] == [56, 56]
    assert collapsed["inside"] and expanded["inside"]
    assert expanded["size"][0] == 360
    left, top, right, bottom = collapsed["native"]
    assert abs((right - left) - 56 * collapsed["dpr"]) <= 1
    assert abs((bottom - top) - 56 * collapsed["dpr"]) <= 1
