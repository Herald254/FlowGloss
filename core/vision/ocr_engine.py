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