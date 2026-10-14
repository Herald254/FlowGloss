"""视觉模块接口验证，不访问真实桌面、不加载 OCR 模型。"""

from unittest.mock import Mock, patch

import numpy as np
import pytest
from PIL import Image

from core.vision.capturer import ScreenCapturer
from core.vision.ocr_engine import OCREngine


def test_invalid_monitor_closes_capture_resource():
    resource = Mock()
    resource.monitors = [{}, {"width": 100, "height": 100}]
    with patch("core.vision.capturer.mss.mss", return_value=resource):
        with pytest.raises(ValueError):
            ScreenCapturer(monitor_index=5)
    resource.close.assert_called_once()


def test_ocr_preserves_coordinates_confidence_and_pil_channel_order():
    raw = Mock(return_value=([
        [[[1, 2], [11, 2], [11, 12], [1, 12]], "ONNX", 0.9],
        [[[1, 2], [11, 2], [11, 12], [1, 12]], "noise", 0.1],
    ], None))
    with patch("core.vision.ocr_engine.RapidOCR", return_value=raw):
        engine = OCREngine(0.5)
    blocks = engine.recognize(Image.new("RGB", (20, 20), (255, 0, 0)))
    assert [block.text for block in blocks] == ["ONNX"]
    assert blocks[0].confidence == 0.9
    assert blocks[0].bbox[0] == (1, 2)
    assert tuple(raw.call_args.args[0][0, 0]) == (0, 0, 255)
