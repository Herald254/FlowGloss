# FlowGloss

FlowGloss 是一个为桌面阅读提供少量术语解释的 Python 伴读助手。
当前 V1.0 已接通：手动/事件触发 → 截图 → 画面变化过滤 → 本地 OCR → LLM 术语筛选 → 已掌握过滤 → 缓存/解释 → 悬浮窗。

## 环境与安装

目前主要面向 Windows，使用 Python 3.11+、RapidOCR CPU 后端和 PySide6。
无需安装 Tesseract、PaddlePaddle、PyTorch 或 NER 模型。

```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
python install.py --cpu --dev
```

也可执行 `python -m pip install -r requirements-dev.txt`。
`--gpu` 保留为兼容入口，目前仍安装 CPU 依赖，不代表已支持 GPU 推理。

## 配置与启动

共享默认值在 `config/settings.yaml`，提示词在 `config/prompts.yaml`。
LLM 配置使用项目根目录的 `.env`，从示例复制后填写密钥：

```powershell
Copy-Item .env.example .env
```

```dotenv
FLOWGLOSS_API_KEY=你的密钥
FLOWGLOSS_BASE_URL=https://api.deepseek.com
FLOWGLOSS_MODEL=deepseek-flash
```

程序自动读取项目根目录 `.env`，从其他目录启动也有效。修改后重启程序。
配置优先级：进程环境变量 > `.env` > `config/settings.local.yaml` > 默认 YAML。
`.env` 已被 Git 忽略；`.env.example` 只保存无密钥示例。

截图区域和用户知识背景等设置仍可在 `config/settings.local.yaml` 中覆盖：

```yaml
llm:
  user_profile: 熟悉 Python，但不了解机器学习术语。
capture:
  monitor_index: 1
  region: null
```

服务需支持 OpenAI 兼容的 `/chat/completions` 接口；提示词要求返回 JSON。
使用 DeepSeek 官方地址时，程序自动关闭思考并启用 JSON 输出，避免短解释的输出预算被思考耗尽。

```powershell
python main.py --check-config
python main.py
# 指定其他本地覆盖文件：
python main.py --config path/to/settings.local.yaml
```

没有密钥也能打开界面，但不会截图或发送请求。

## 使用方式

- 点击“识别当前屏幕”进行一次手动识别；结果为最多 3 个概念卡片。
- 勾选“滚动或翻页停止后自动识别”开启监听。默认关闭自动识别。
- 点击“暂停”停止截图与请求，取消当前网络任务；“继续”恢复。
- 点击“已掌握，不再提示”保存反馈，之后过滤该术语。
- 拖动窗口标题移动位置；“退出”停止监听并释放后台资源。

`monitor_index: 1` 为第一个显示器，`0` 为整个虚拟桌面。
`region: [left, top, width, height]` 限定截图区域；显示器编号大于 0 时坐标相对该显示器。
自动触发有 1 秒防抖和 8 秒请求冷却；手动触发可跳过画面/文字去重。
后台只保留最新任务，过期页面的结果不会显示。
截图时窗口短暂隐藏，避免识别自己的提示内容。

## 数据与请求

OCR 在本地运行。候选术语筛选会发送最多 `max_context_chars` 字的屏幕文字；
每个未掌握且无缓存的术语会再发送其上下文以生成解释。
默认每轮最多 1 次筛选和 3 次解释请求。不要在敏感页面开启自动识别。

`data/flowgloss.db` 保存已掌握标记与解释缓存，不保存截图或完整屏幕文本。
缓存包含术语、上下文、服务、模型、用户背景与提示词版本，默认有效期为 24 小时。
日志在 `logs/`，不记录密钥、屏幕文字和服务响应正文。
本机配置、数据库和日志均不纳入 Git。

## 验证

```powershell
python -m pytest tests -q
python tests/test_capturer.py --output capture.png
python tests/test_ocr_engine.py image.png --cli-only
```

自动测试用模拟 HTTP，不需要密钥、不产生 API 费用。
Qt 窗口测试使用 offscreen 平台；截图和 OCR 的独立工具用于真实桌面/图片手动验收。

## 当前限制与后续计划

- V1.0 使用单进程和固定工作线程，网络请求异步执行；不支持多进程隔离。
- 画面差分是整帧过滤，尚无滚动拼接和局部增量 OCR。
- NER 尚属实验代码，未接入主流程；个性化目前基于固定知识背景和已掌握标记。
- 尚无流式输出、托盘、点击穿透、亚克力效果或掌握记录管理界面。
- 已掌握标记可通过数据库接口撤销，当前窗口仅提供标记入口。

当前架构与剩余工作见 [架构说明](docs/architecture.md) 和 [推进记录](docs/development_plan_v1.md)。
`docs/project_overview_v1/v2/v3.md` 是历史设计稿，不能视为已实现功能。
