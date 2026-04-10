# e:\code\FlowGloss\ui\overlay.py
"""
基于PySide6的置顶窗口。

技术简介：
- 使用PySide6（Qt for Python）框架实现跨平台GUI
- 实现亚克力模糊效果（Windows 11）或毛玻璃效果（macOS）
- 支持窗口穿透（Click-through），允许用户操作底层应用
- 使用Qt Signal/Slot机制实现线程间通信

模块功能：
- 渲染亚克力模糊效果的置顶窗口
- 实现流式文字动画，逐字显示解释内容
- 提供用户反馈按钮（"已理解"、"需要更多解释"等）
- 支持窗口位置自适应，避免遮挡重要内容

整体作用：
用户交互的唯一窗口，提供非侵入式的知识提示界面。

对外方法：
- show_tip(term, explanation): 显示词汇提示窗口
- hide_tip(): 隐藏提示窗口
- set_position(x, y): 设置窗口位置
- set_opacity(value): 设置窗口透明度

参数：
- opacity（透明度）: 0.0-1.0，控制窗口透明程度
- position（弹窗坐标）: (x, y)元组，指定窗口屏幕位置

联系：
接收llm_client.py的流式数据，通过Qt Signal机制异步更新UI内容。

线程位置：
主GUI线程。绝对禁止在此执行耗时计算，所有数据处理应在工作线程完成。

窗口属性设置：
self.setWindowFlags(Qt.WindowStaysOnTopHint | Qt.FramelessWindowHint | Qt.Tool)
self.setAttribute(Qt.WA_TranslucentBackground)
"""