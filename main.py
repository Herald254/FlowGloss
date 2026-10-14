# e:\code\FlowGloss\main.py
"""
系统主入口，加载配置、日志与 PySide6 界面。

运行位置：GUI 主线程。截图、OCR 和网络请求由 core/worker.py 调度。
当前为单进程工作线程架构，多进程隔离留待性能测量后引入。
"""

from __future__ import annotations

import argparse
import sys

from utils.config_loader import PROJECT_ROOT, load_config, load_prompts
from utils.logger import setup_logging


def main() -> int:
    """启动唯一 GUI 入口；--check-config 可在无桌面环境校验配置。"""
    for stream in (sys.stdout, sys.stderr):
        if hasattr(stream, "reconfigure"):
            stream.reconfigure(encoding="utf-8")
    parser = argparse.ArgumentParser(description="FlowGloss V1.0 桌面伴读助手")
    parser.add_argument("--config", help="本地 YAML 配置文件路径")
    parser.add_argument("--check-config", action="store_true", help="只校验配置，不启动界面")
    args = parser.parse_args()
    try:
        config = load_config(args.config)
        prompts = load_prompts()
        if args.check_config:
            print("配置校验通过。API 密钥：" + ("已配置" if config["llm"]["api_key"].strip() else "未配置"))
            return 0
        from PySide6.QtWidgets import QApplication
        from ui.overlay import OverlayWindow
        setup_logging({"log_dir": str(PROJECT_ROOT / "logs")})
        app = QApplication(sys.argv[:1])
        window = OverlayWindow(config, prompts)
        window.show()
        return app.exec()
    except (ValueError, OSError, ImportError) as exc:
        print(f"启动失败：{exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
