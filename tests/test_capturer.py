from __future__ import annotations

import argparse
import sys
from pathlib import Path

from PIL import Image

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from core.vision.capturer import ScreenCapturer


def build_arg_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="ScreenCapturer test utility")
    parser.add_argument("--monitor", type=int, default=1, help="Monitor index, 0 means virtual desktop.")
    parser.add_argument("--max-fps", type=int, default=10, help="Maximum capture FPS.")
    parser.add_argument(
        "--region",
        nargs=4,
        type=int,
        metavar=("LEFT", "TOP", "WIDTH", "HEIGHT"),
        help="Optional region tuple. Relative to the selected monitor when monitor > 0.",
    )
    parser.add_argument(
        "--output",
        default="capturer_test_output.png",
        help="Output image path for the captured frame.",
    )
    return parser


def save_bgr_image(frame, output_path: Path) -> None:
    rgb = frame[:, :, ::-1]
    Image.fromarray(rgb).save(output_path)


def main() -> int:
    parser = build_arg_parser()
    args = parser.parse_args()

    region = tuple(args.region) if args.region else None
    output_path = Path(args.output).resolve()

    with ScreenCapturer(monitor_index=args.monitor, max_fps=args.max_fps) as capturer:
        primary_size = capturer.get_screen_size()
        frame = capturer.grab_screen(region=region) if region else capturer.capture_full_screen()

    save_bgr_image(frame, output_path)

    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")

    print("Capture complete.")
    print(f"Primary screen size: {primary_size}")
    print(f"Captured frame shape: {frame.shape}")
    print(f"Saved to: {output_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
