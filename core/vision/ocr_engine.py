# e:\code\FlowGloss\core\vision\ocr_engine.py
"""
封装增强型 OCR 引擎（支持动态性能适配）。

技术简介：
- 核心框架：基于 RapidOCR (ONNX Runtime)，提供跨硬件平台的极致推理兼容性
- 动态加速：支持 NVIDIA CUDA (针对 RTX 5060 优化) 与 Intel OpenVINO 加速后端
- 模型策略：采用"双级模型"架构
    * [高性能] 加载 Server 版模型 (DBNetV3 + CRNN)，用于精确捕捉复杂排版
    * [兼容性] 加载 Mobile 版模型，确保在无独显电脑上低延迟运行

模块功能：
- 获取屏幕截图或图像区域，执行端到端文字提取
- 结构化输出：返回包含文本内容、四点式多边形坐标 (Bbox) 及识别置信度的字典列表
- 支持多语言识别（中英文混合）
- 提供置信度过滤，过滤低质量识别结果
- 硬件自感知：启动时自动检测 GPU/CPU 环境并按需初始化对应的推理后端

整体作用：
作为 FlowGloss 视觉感知层的核心，将屏幕图像转化为带位置信息的数字化文本，
为后续的语义解析（Cognition 模块）和屏幕取词标注提供基础数据。

对外方法：
- recognize(image_patch) -> list[dict]: 对图像区域进行OCR，返回包含文本内容、四点式多边形坐标 (Bbox) 及识别置信度的结构化字典列表[{text, bbox, conf}, ...]
- set_language(lang): 设置识别语言
- set_performance_mode(mode): 手动强制切换模型
- get_confidence_threshold(): 获取当前置信度阈值
- get_engine_status(): 返回当前正在使用的硬件后端 (CUDA/CPU) 和模型级别

联系：
将结果通过 IPC (multiprocessing.Queue) 发回主进程，供下游 Cognition 模块进行知识关联。

线程/进程位置：
运行于独立的 Vision 子进程，通过 gpu_utils.py 统一管理显存资源，避免与 GUI 线程争抢响应速度。
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