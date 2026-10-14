#!/usr/bin/env python3
"""FlowGloss V1.0 安装入口，使用当前解释器的 pip。

保留 --cpu/--gpu/--dev 参数；当前 GPU 入口使用 CPU 依赖，
不自动安装未接入的 Paddle、Torch 或多个 ONNX Runtime。
"""

from __future__ import annotations

import argparse
import subprocess
import sys
from pathlib import Path


def main() -> int:
    for stream in (sys.stdout, sys.stderr):
        if hasattr(stream, "reconfigure"):
            stream.reconfigure(encoding="utf-8")
    parser = argparse.ArgumentParser(description="安装 FlowGloss V1.0 依赖")
    group = parser.add_mutually_exclusive_group()
    group.add_argument("--cpu", action="store_true", help="安装 CPU 依赖（默认）")
    group.add_argument("--gpu", action="store_true", help="兼容旧入口，当前仍安装 CPU 依赖")
    parser.add_argument("--dev", action="store_true", help="同时安装测试依赖")
    args = parser.parse_args()
    if sys.version_info < (3, 11):
        print("FlowGloss V1.0 需要 Python 3.11 或以上。", file=sys.stderr)
        return 1
    if args.gpu:
        print("V1.0 尚未启用 GPU 推理，本次安装 CPU 后端。")
    filename = "requirements-dev.txt" if args.dev else "requirements-cpu.txt"
    requirements = Path(__file__).resolve().with_name(filename)
    result = subprocess.run([sys.executable, "-m", "pip", "install", "-r", str(requirements)], check=False)
    if result.returncode:
        print("安装失败，请检查上面的 pip 输出。", file=sys.stderr)
        return result.returncode
    print("安装完成。设置 API 密钥后执行 python main.py。")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
