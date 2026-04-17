from __future__ import annotations

import argparse
import logging
import sys
import tkinter as tk
from pathlib import Path
from tkinter import filedialog, messagebox, scrolledtext

from ocr_engine import OCREngine


def configure_logging(log_level: str) -> None:
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")
    if hasattr(sys.stderr, "reconfigure"):
        sys.stderr.reconfigure(encoding="utf-8")

    logging.basicConfig(
        level=getattr(logging, log_level.upper(), logging.INFO),
        format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    )


def build_arg_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="FlowGloss OCR 测试工具")
    parser.add_argument(
        "image",
        nargs="?",
        help="要识别的图片路径；不传时会弹出文件选择窗口。",
    )
    parser.add_argument(
        "--log-level",
        default="INFO",
        choices=["DEBUG", "INFO", "WARNING", "ERROR"],
        help="日志级别",
    )
    parser.add_argument(
        "--cli-only",
        action="store_true",
        help="即使未传图片路径，也不要弹出图形窗口。",
    )
    return parser


def choose_image_file() -> Path | None:
    root = tk.Tk()
    root.withdraw()
    root.attributes("-topmost", True)

    try:
        selected = filedialog.askopenfilename(
            title="选择要进行 OCR 测试的图片",
            filetypes=[
                ("Image Files", "*.png *.jpg *.jpeg *.bmp *.webp *.tif *.tiff"),
                ("All Files", "*.*"),
            ],
        )
    finally:
        root.destroy()

    return Path(selected) if selected else None


def show_error_dialog(message: str) -> None:
    root = tk.Tk()
    root.withdraw()
    root.attributes("-topmost", True)

    try:
        messagebox.showerror("FlowGloss OCR 测试", message)
    finally:
        root.destroy()


def show_result_window(image_path: Path, text: str) -> None:
    root = tk.Tk()
    root.title("FlowGloss OCR 测试结果")
    root.geometry("860x640")
    root.configure(bg="#F5F7FA")

    title = tk.Label(
        root,
        text="OCR 识别结果",
        bg="#F5F7FA",
        fg="#1F2937",
        font=("Microsoft YaHei UI", 15, "bold"),
        anchor="w",
        padx=16,
        pady=12,
    )
    title.pack(fill="x")

    path_label = tk.Label(
        root,
        text=f"图片: {image_path}",
        bg="#F5F7FA",
        fg="#4B5563",
        justify="left",
        anchor="w",
        wraplength=820,
        padx=16,
    )
    path_label.pack(fill="x")

    text_box = scrolledtext.ScrolledText(
        root,
        wrap="word",
        font=("Microsoft YaHei UI", 10),
        padx=12,
        pady=12,
    )
    text_box.pack(expand=True, fill="both", padx=16, pady=16)
    text_box.insert("1.0", text if text else "[未识别到文本]")
    text_box.configure(state="disabled")

    root.mainloop()


def run_interactive_test(log_level: str) -> int:
    configure_logging(log_level)

    try:
        engine = OCREngine()
    except Exception as exc:
        show_error_dialog(f"OCR 引擎初始化失败:\n{exc}")
        return 1

    image_path = choose_image_file()
    if image_path is None:
        return 0

    try:
        text = engine.process_image_file(image_path)
    except Exception as exc:
        show_error_dialog(f"OCR 识别失败:\n{exc}")
        return 1

    show_result_window(image_path, text)
    return 0


def run_cli(image_path: str | None, log_level: str, cli_only: bool = False) -> int:
    if image_path is None and not cli_only:
        return run_interactive_test(log_level)

    configure_logging(log_level)

    try:
        engine = OCREngine()
    except Exception as exc:
        print(f"OCR 引擎初始化失败: {exc}", file=sys.stderr)
        return 1

    if not image_path:
        print("OCR 引擎初始化成功。未提供图片路径。")
        return 0

    try:
        text = engine.process_image_file(image_path)
    except Exception as exc:
        print(f"OCR 识别失败: {exc}", file=sys.stderr)
        return 1

    print("OCR 识别完成。")
    print("-" * 40)
    print(text if text else "[未识别到文本]")
    return 0


def main() -> int:
    parser = build_arg_parser()
    args = parser.parse_args()
    return run_cli(args.image, args.log_level, args.cli_only)


if __name__ == "__main__":
    raise SystemExit(main())
