# FlowGloss 项目架构说明 (V1.0)

## 项目概述

FlowGloss 是一个基于屏幕监听和AI技术的智能词汇学习助手，通过监听用户屏幕内容，自动识别和提取新词汇，并提供即时翻译和学习功能。

## 目录结构

```text
FlowGloss/
├── main.py                      # 主入口文件
├── requirements.txt             # 项目依赖说明
├── requirements-cpu.txt         # CPU版本依赖
├── requirements-gpu.txt         # GPU版本依赖
├── install.py                  # 智能安装脚本
├── README.md                    # 项目说明
├── .gitignore                   # Git忽略文件
├── commit_templates.json        # Git提交模板
├── docs/                        # 项目说明文档
│   ├── architecture.md          # 架构说明文档（本文件）
│   ├── project_overview_v1.md  # V1.0项目概览文档
│   ├── project_overview_v2.md  # V2.0项目概览文档
│   └── project_overview_v3.md  # V3.0项目概览文档
├── config/                      # 配置文件目录
│   ├── settings.yaml            # 系统配置文件
│   └── prompts.yaml             # 提示词配置文件
├── core/                        # 核心功能模块
│   ├── __init__.py
│   ├── monitor/                 # 监听器模块
│   │   └── event_hook.py        # 事件监听器
│   ├── vision/                  # 视觉处理模块
│   │   └── ocr_engine.py        # OCR引擎
│   ├── cognition/               # 认知模块
│   │   ├── ner_worker.py        # NER工作器
│   │   └── ranker.py            # 排序器
│   └── glossary/                # 词汇表模块
│       └── llm_client.py        # LLM客户端
├── data/                        # 数据模块
│   └── database.py              # 数据库定义
├── src/                         # 源代码目录
│   ├── config.py               # 配置管理
│   └── main.py                # 主程序入口
├── tests/                       # 测试目录
│   ├── test_event_hook.py       # 事件监听器测试
│   └── test_logger.py          # 日志工具测试
├── ui/                          # 用户界面模块
│   ├── __init__.py
│   └── overlay.py               # 悬浮窗
├── utils/                       # 工具模块
│   ├── __init__.py
│   ├── logger.py                # 日志工具
│   └── gpu_utils.py             # GPU工具
└── logs/                        # 日志目录
    └── flowgloss.log           # 运行日志
```

## 模块说明

### 1. 主入口 (main.py)

- 程序启动入口
- 初始化各个模块
- 协调各模块之间的交互

### 2. 配置模块 (config/)

- **settings.yaml**: 存储系统配置参数，如API密钥、模型路径、监听设置等
- **prompts.yaml**: 存储AI模型的提示词模板

### 3. 核心模块 (core/)

#### 3.1 监听器模块 (monitor/)

- **event_hook.py**: 监听系统事件，如键盘快捷键、鼠标操作等，触发截图和识别流程

#### 3.2 视觉处理模块 (vision/)

- **ocr_engine.py**: OCR文字识别引擎，将图像转换为文本（支持GPU加速）

#### 3.3 认知模块 (cognition/)

- **ner_worker.py**: 命名实体识别，从文本中提取词汇和术语
- **ranker.py**: 词汇排序和筛选，根据重要性和相关性排序

#### 3.4 词汇表模块 (glossary/)

- **llm_client.py**: LLM客户端，调用大语言模型进行翻译和解释（支持异步和流式输出）

### 4. 数据模块 (data/)

- **database.py**: 数据库操作，存储词汇、翻译、学习记录等数据

### 5. 用户界面模块 (ui/)

- **overlay.py**: 悬浮窗界面，显示识别结果和翻译内容

### 6. 工具模块 (utils/)

- **logger.py**: 日志记录工具（支持多级别、模块级别控制、彩色输出）
- **gpu_utils.py**: GPU加速工具，优化模型推理性能

## 工作流程

1. **监听阶段**: event_hook 监听用户触发事件
2. **识别阶段**: ocr_engine 识别屏幕文本内容
3. **提取阶段**: ner_worker 提取关键词汇
4. **排序阶段**: ranker 对词汇进行重要性排序
5. **翻译阶段**: llm_client 调用LLM进行翻译和解释
6. **显示阶段**: overlay 在悬浮窗中显示结果
7. **存储阶段**: database 保存学习记录

## 技术栈

### 当前实际使用的技术栈

- **编程语言**: Python 3.8+
- **事件监听**: pynput (全局键盘鼠标事件捕获)
- **日志工具**: logging (Python标准库)
- **并发处理**: threading, multiprocessing (Python标准库)
- **类型系统**: typing (Python标准库)
- **单元测试**: unittest (Python标准库)

### 计划使用的技术栈（V2.0+）

- **OCR引擎**: PaddleOCR (支持GPU加速)
- **NER模型**: GLiNER (本地零样本实体识别)
- **LLM**: OpenAI GPT / Claude / 本地模型
- **GUI框架**: PySide6 + PyQt-Fluent-Widgets
- **数据库**: SQLite + Peewee ORM
- **图像处理**: OpenCV
- **异步I/O**: httpx

### V3.0计划技术栈

- **语义相似度**: SBERT (Sentence-BERT)
- **向量检索**: FAISS (CPU/GPU版本)
- **多语种检测**: FastText
- **知识图谱**: NetworkX + WordNet
- **深度学习**: PyTorch (NER模型)

## 开发规范

- 遵循PEP 8代码规范
- 使用类型注解
- 编写单元测试
- 完善的文档注释
- 版本控制使用Git

## 依赖管理

### 当前依赖状态

- **已实现**: pynput, logging, threading, multiprocessing, unittest, typing, pathlib, datetime, asyncio
- **计划中**: PaddleOCR, GLiNER, PySide6, httpx, SQLite, Peewee
- **未实现**: OpenCV, PyTorch, FAISS, FastText, NetworkX, SBERT

### 安装方式

由于PaddleOCR和FAISS存在CPU/GPU版本冲突，请使用以下方式安装：

1. 推荐方式：使用项目提供的安装脚本

   python install.py  # 自动检测硬件并选择合适版本

2. 手动安装：根据你的硬件选择对应的requirements文件

   CPU用户: pip install -r requirements-cpu.txt
   GPU用户: pip install -r requirements-gpu.txt

3. 分步安装：先安装核心依赖，再根据需要安装GPU依赖

   pip install -r requirements.txt  # 安装核心依赖
   pip install paddlepaddle-gpu  # GPU用户额外安装

注意事项：

- PaddlePaddle CPU和GPU版本不能同时安装

- FAISS CPU和GPU版本不能同时安装
- PyTorch和PaddlePaddle可以同时安装，但会占用大量显存
- 建议使用虚拟环境隔离不同项目的依赖

## 版本规划

### V1.0 (当前阶段）

- 目标：验证核心链路连通性

- 特点：单进程多线程架构，基础功能验证
- 技术栈：pynput + Python标准库

### V2.0 (下一阶段）

- 目标：引入多进程隔离、本地AI推理和SQLite持久化

- 特点：多进程架构，静默触发，本地NER，知识图谱
- 技术栈：PaddleOCR + GLiNER + PySide6 + httpx + SQLite

### V3.0 (未来阶段）

- 目标：行为数据挖掘、语义关联网络、自适应学习

- 特点：保持多进程基座，行为校验，多语种支持，动态Prompt
- 技术栈：PaddleOCR + GLiNER + SBERT + FAISS + FastText + NetworkX
