# e:\code\FlowGloss\ui\__init__.py
"""
用户界面模块包。

技术简介：
- 基于PySide6的GUI框架，实现跨平台用户界面
- 采用MVC（Model-View-Controller）架构模式
- 支持主题切换和国际化（i18n）

模块功能：
- 导出UI组件的主要类和函数
- 初始化Qt应用程序环境
- 提供UI主题和样式配置接口
- 实现窗口管理和事件分发

整体作用：
作为用户界面模块的统一入口，管理所有GUI组件的创建和交互。

子模块：
- overlay: 悬浮窗组件
- components: 可复用UI组件（按钮、卡片等）
- resources: UI资源文件（图标、样式表等）

联系：
被main.py导入，用于初始化和启动用户界面。

线程位置：
主GUI线程。所有UI操作必须在主线程中执行，使用Signal/Slot机制进行线程间通信。
"""