# FlowGloss 项目架构说明

## 项目概述
FlowGloss 是一个基于屏幕监听和AI技术的智能词汇学习助手，通过监听用户屏幕内容，自动识别和提取新词汇，并提供即时翻译和学习功能。

## 目录结构

```
FlowGloss/
├── main.py                      # 主入口文件
├── requirements.txt             # 项目依赖
├── docs/                        # 项目说明文档
│   └── architecture.md          # 架构说明文档
├── config/                      # 配置文件目录
│   ├── settings.yaml            # 系统配置文件
│   └── prompts.yaml             # 提示词配置文件
├── core/                        # 核心功能模块
│   ├── __init__.py
│   ├── monitor/                 # 监听器模块
│   │   └── event_hook.py        # 事件监听器
│   ├── vision/                  # 视觉处理模块
│   │   ├── capturer.py          # 屏幕截图
│   │   ├── processor.py         # 图像处理
│   │   └── ocr_engine.py        # OCR引擎
│   ├── cognition/               # 认知模块
│   │   ├── ner_worker.py        # NER工作器
│   │   └── ranker.py            # 排序器
│   └── glossary/                # 词汇表模块
│       └── llm_client.py        # LLM客户端
├── data/                        # 数据模块
│   └── database.py              # 数据库定义
├── ui/                          # 用户界面模块
│   ├── __init__.py
│   └── overlay.py               # 悬浮窗
└── utils/                       # 工具模块
    ├── logger.py                # 日志工具
    └── gpu_utils.py             # GPU工具
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
- **capturer.py**: 负责屏幕截图功能，支持指定区域截图
- **processor.py**: 图像预处理，如缩放、降噪、增强等
- **ocr_engine.py**: OCR文字识别引擎，将图像转换为文本

#### 3.3 认知模块 (cognition/)
- **ner_worker.py**: 命名实体识别，从文本中提取词汇和术语
- **ranker.py**: 词汇排序和筛选，根据重要性和相关性排序

#### 3.4 词汇表模块 (glossary/)
- **llm_client.py**: LLM客户端，调用大语言模型进行翻译和解释

### 4. 数据模块 (data/)
- **database.py**: 数据库操作，存储词汇、翻译、学习记录等数据

### 5. 用户界面模块 (ui/)
- **overlay.py**: 悬浮窗界面，显示识别结果和翻译内容

### 6. 工具模块 (utils/)
- **logger.py**: 日志记录工具
- **gpu_utils.py**: GPU加速工具，优化模型推理性能

## 工作流程

1. **监听阶段**: event_hook 监听用户触发事件
2. **截图阶段**: capturer 截取屏幕内容
3. **处理阶段**: processor 对截图进行预处理
4. **识别阶段**: ocr_engine 识别文本内容
5. **提取阶段**: ner_worker 提取关键词汇
6. **排序阶段**: ranker 对词汇进行重要性排序
7. **翻译阶段**: llm_client 调用LLM进行翻译和解释
8. **显示阶段**: overlay 在悬浮窗中显示结果
9. **存储阶段**: database 保存学习记录

## 技术栈

- **编程语言**: Python
- **OCR引擎**: Tesseract / PaddleOCR
- **NER模型**: spaCy / Hugging Face Transformers
- **LLM**: OpenAI GPT / Claude / 本地模型
- **GUI框架**: PyQt / Tkinter
- **数据库**: SQLite / PostgreSQL
- **图像处理**: OpenCV / PIL

## 开发规范

- 遵循PEP 8代码规范
- 使用类型注解
- 编写单元测试
- 完善的文档注释
- 版本控制使用Git

## 依赖管理

所有依赖包在 requirements.txt 中声明，使用 pip 安装：

```bash
pip install -r requirements.txt
```