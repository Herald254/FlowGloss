# e:\code\FlowGloss\core\vision\processor.py
"""
基于OpenCV的图像差分分析。

技术简介：
- 使用OpenCV实现高效的图像对比算法
- 采用像素级差分和结构相似性（SSIM）相结合的策略
- 实现图像重叠检测与拼接算法，识别新增区域

模块功能：
- 对比frame_n与frame_n-1的差异，计算变化率
- 如果差异率低于阈值，则中断流程，避免无效OCR
- 检测图像重叠区域，提取新增内容区域
- 生成变化区域的边界框（bounding_box）

整体作用：
计算过滤器，防止在静止页面反复进行OCR，实现增量识别策略。

对外方法：
- detect_change(old_img, new_img) -> bool, bounding_box: 检测图像变化，返回是否需要处理和变化区域
- find_overlap_region(img1, img2) -> tuple: 识别两帧图像的重叠区域
- stitch_images(img1, img2) -> ndarray: 图像拼接，构建完整视图

联系：
衔接截图与OCR引擎，为OCR引擎提供精确的处理区域。

线程位置：
Vision子进程/主线程。在视觉处理进程中运行，占用CPU计算资源。
"""