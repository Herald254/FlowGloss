# e:\code\FlowGloss\core\vision\capturer.py
"""
基于mss的极速屏幕截图。

技术简介：
- 使用mss（Multiple Screen Shots）库实现高性能屏幕捕获
- 支持多显示器环境下的精确区域截图
- 返回numpy数组格式，便于后续OpenCV处理

模块功能：
- 截取指定屏幕区域的像素数据（支持坐标和尺寸参数）
- 实现屏幕分辨率自适应，处理DPI缩放问题
- 提供帧率控制，避免过高的截图频率消耗资源

整体作用：
数据原材料供应，为后续图像处理和OCR识别提供原始视觉数据。

对外方法：
- grab_screen(region: tuple) -> ndarray: 截取指定区域，返回BGR格式的numpy数组
- get_screen_size() -> tuple: 获取主屏幕分辨率
- capture_full_screen() -> ndarray: 全屏截图

联系：
供processor.py调用，提供图像差分分析的输入数据。

线程位置：
Vision子进程/主线程。在独立的视觉处理进程中运行，避免阻塞主进程。
"""