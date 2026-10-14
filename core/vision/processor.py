# e:\code\FlowGloss\core\vision\processor.py
"""
画面变化过滤器：降采样后比较像素变化比例。

连接截图与 OCR，成功处理后才记住画面，失败任务允许重试。
V1.0 尚未实现滚动拼接、SSIM 或局部增量识别。
"""

from __future__ import annotations

import numpy as np


class ImageChangeDetector:
    """用降采样画面判断是否值得 OCR；V1.0 暂不做拼接和局部裁切。"""

    def __init__(self, threshold: float = 0.02) -> None:
        self.threshold = threshold
        self.previous: np.ndarray | None = None

    @staticmethod
    def sample(frame: np.ndarray) -> np.ndarray:
        step = max(1, max(frame.shape[:2]) // 320)
        return frame[::step, ::step].astype(np.int16)

    def has_changed(self, frame: np.ndarray) -> bool:
        current = self.sample(frame)
        if self.previous is None or self.previous.shape != current.shape:
            return True
        changed = np.max(np.abs(current - self.previous), axis=2) > 20
        return bool(np.mean(changed) > self.threshold)

    def accept(self, frame: np.ndarray) -> None:
        """只有成功处理后才记住画面，使失败任务可以重试。"""
        self.previous = self.sample(frame)
