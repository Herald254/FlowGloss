# e:\code\FlowGloss\core\vision\ocr_engine.py
"""
基于 RapidOCR / ONNX Runtime 的本地 OCR 引擎。

模块功能：recognize 返回 TextBlock（文字、坐标、置信度）；
process_image 和 process_image_file 保留纯文本兼容接口。
运行位置：固定工作线程。V1.0 使用 CPU，不做模型切换或显存调度。
识别故障向调用方抛出，避免与空白图片混淆。
"""
#created by herald
from __future__ import annotations

import logging
from pathlib import Path

import numpy as np
from PIL import Image

from core.models import TextBlock

try:
    from rapidocr_onnxruntime import RapidOCR
except ImportError as exc:  # pragma: no cover - depends on local env
    RapidOCR = None
    RAPIDOCR_IMPORT_ERROR = exc
else:
    RAPIDOCR_IMPORT_ERROR = None


logger = logging.getLogger("core.vision.ocr_engine")


class OCREngine:
    """
    基于 RapidOCR 的 OCR 模块。

    这个文件只负责提供可导入的 OCR 能力，
    不包含命令行入口、弹窗测试或其他运行时副作用。
    """

    def __init__(self, confidence_threshold: float = 0.5) -> None:
        if not 0 <= confidence_threshold <= 1:
            raise ValueError("置信度阈值必须在 0～1 之间")
        self.confidence_threshold = confidence_threshold
        if RapidOCR is None:
            raise EnvironmentError(
                "rapidocr_onnxruntime 未安装或导入失败。"
                "请先执行: pip install rapidocr_onnxruntime onnxruntime"
            ) from RAPIDOCR_IMPORT_ERROR

        logger.info("正在初始化 RapidOCR (ONNX) 引擎...")
        try:
            self.engine = RapidOCR()
            logger.info("RapidOCR 引擎加载成功。")
        except Exception as exc:
            logger.error("RapidOCR 初始化失败。", exc_info=True)
            raise EnvironmentError(f"OCR 引擎加载失败: {exc}") from exc

    def recognize(self, image: Image.Image | np.ndarray) -> list[TextBlock]:
        """返回文本、坐标、置信度；故障向上抛出，与空白画面区分。

        ndarray 输入为截图模块的 BGR 数据；PIL 输入转换为 BGR。
        """
        if isinstance(image, Image.Image):
            image = np.asarray(image.convert("RGB"))[:, :, ::-1].copy()
        if not isinstance(image, np.ndarray) or image.ndim != 3 or image.shape[2] != 3 or image.size == 0:
            raise ValueError("OCR 输入必须是非空的三通道图片")
        result, _ = self.engine(image)
        return [
            TextBlock(
                text=str(text).strip(),
                bbox=tuple(tuple(float(v) for v in point) for point in bbox),
                confidence=float(confidence),
            )
            for bbox, text, confidence in (result or [])
            if str(text).strip() and float(confidence) >= self.confidence_threshold
        ]

    def process_image(self, image: Image.Image) -> str:
        """
        从 PIL 图像对象中提取文本。
        """
        if image is None:
            return ""

        return "\n".join(block.text for block in self.recognize(image))

    def process_image_file(self, image_path: str | Path) -> str:
        """
        从图片文件中提取文本。
        """
        path = Path(image_path)
        if not path.exists():
            raise FileNotFoundError(f"图片不存在: {path}")

        with Image.open(path) as image:
            return self.process_image(image)
