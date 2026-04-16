# e:\code\FlowGloss\core\vision\ocr_engine.py
"""
封装PaddleOCR（GPU版）。

技术简介：
- 基于PaddleOCR深度学习框架，支持GPU加速推理
- 使用CUDA后端优化RTX 5060显卡性能
- 实现文本检测（DBNet）和文本识别（CRNN）的端到端处理

模块功能：
- 执行光学字符识别，输出文本行及其对应的屏幕坐标
- 支持多语言识别（中英文混合）
- 提供置信度过滤，过滤低质量识别结果
- 返回结构化的文本块信息（文本内容、位置坐标、置信度）

整体作用：
将视觉信号转变为数字信号，为后续NLP处理提供文本数据。

对外方法：
- recognize(image_patch) -> list: 对图像区域进行OCR，返回包含text和coordinates的字典列表
- set_language(lang): 设置识别语言
- get_confidence_threshold(): 获取当前置信度阈值

联系：
将结果通过IPC（multiprocessing.Queue）发回主进程，供Cognition模块使用。

线程位置：
Vision子进程/主线程。直接占用GPU显存，需要在gpu_utils.py中管理显存分配。
"""
#created by herald
from __future__ import annotations

import logging
from pathlib import Path

import numpy as np
from PIL import Image

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

    def __init__(self) -> None:
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

    def process_image(self, image: Image.Image) -> str:
        """
        从 PIL 图像对象中提取文本。
        """
        if image is None:
            return ""

        try:
            if image.mode != "RGB":
                image = image.convert("RGB")

            img_array = np.array(image)
            logger.debug("开始执行 RapidOCR 识别...")
            result, _ = self.engine(img_array)

            if not result:
                return ""

            extracted_texts = [item[1] for item in result if len(item) > 1 and item[1]]
            clean_text = "\n".join(extracted_texts).strip()
            logger.debug("识别完成，提取文本长度: %s", len(clean_text))
            return clean_text
        except Exception as exc:
            logger.error("图像处理过程中发生错误: %s", exc, exc_info=True)
            return ""

    def process_image_file(self, image_path: str | Path) -> str:
        """
        从图片文件中提取文本。
        """
        path = Path(image_path)
        if not path.exists():
            raise FileNotFoundError(f"图片不存在: {path}")

        with Image.open(path) as image:
            return self.process_image(image)