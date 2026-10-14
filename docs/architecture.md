# FlowGloss V1.0 当前架构

本文件描述实际实现；V2/V3 设计稿保留为未来方向。

## 模块分工

| 文件 | 当前职责 |
| --- | --- |
| main.py | 唯一启动入口、配置与日志初始化 |
| utils/config_loader.py | 默认/本地 YAML、项目 .env、进程环境变量与参数校验 |
| core/models.py | TextBlock、Term、Explanation 数据对象 |
| core/monitor/event_hook.py | 键鼠事件与稳定状态防抖 |
| core/worker.py | 固定 Qt 工作线程、截图握手、网络任务取消与资源清理 |
| core/pipeline.py | 最新任务队列与串行阅读流水线 |
| core/vision/capturer.py | 多显示器 BGR 截图、DPI、限帧 |
| core/vision/processor.py | 降采样像素变化判断 |
| core/vision/ocr_engine.py | RapidOCR CPU 识别与结构化结果 |
| core/cognition/ranker.py | 去重、已掌握过滤、数量限制 |
| core/glossary/llm_client.py | 候选提取和解释、JSON 验证、有限重试与整体期限 |
| data/database.py | SQLite 掌握标记与按语境隔离的解释缓存 |
| ui/overlay.py | 置顶提示、识别/暂停/退出、反馈 |
| ui/floating_orb.py | 56px 悬浮球、拖动/双击/右键、忙碌与新结果提示 |

`src/main.py` 与 `src/config.py` 是历史空占位，当前不参与运行。
`core/cognition/ner_worker.py` 是实验模块，不导入主流程。
`utils/gpu_utils.py` 仍为未来规划，当前不调用。

## 线程与任务生命周期

GUI 在主线程；监听器回调通过 Qt Signal 通知 GUI。
工作线程按序初始化和使用截图对象及 OCR，网络调用运行在该线程的 asyncio 事件循环。
新请求替换待处理任务，并使旧任务编号失效；若旧任务正在等待网络，则取消协程。
结果到达 GUI 时再次检查任务编号，避免显示过期页面的解释。

窗口收到截图请求后隐藏，延迟 150ms 放行截图；截图完成后恢复。
窗口移动、缩放、展开和隐藏时更新滚轮排除区域；Windows 使用原生物理坐标，与全局鼠标事件一致。
窗口内滚动会撤销尚未到期的防抖触发，GUI 还会阻止鼠标位于窗口内时收到的自动请求。
暂停清空待处理任务、取消网络并停止监听。退出等待工作线程完成，关闭截图对象及数据库。
OCR 原生推理无法中途取消，所以关闭时可能需要等待当前推理结束。

## 悬浮球与动画

面板与悬浮球共享同一个顶层窗口，收起后实际窗口大小为 56×56，不保留不可见的大块命中区域。
顶层窗口不安装布局，显式使用 56×56 的最小尺寸；布局仅用于内部面板。
这样避免 Windows 在动画中按文字的 heightForWidth 强制增高窗口、把窗口推到屏幕外。
单击不展开，按住拖动，双击展开，右键功能栏。收起不暂停后台识别。
主动请求完成后展开结果或错误；自动请求完成后保持悬浮球，用计数徽标和短暂光环提醒。
主动请求等待期间不接受自动请求替换，暂停则仍会取消当前请求。

窗口几何动画约 220ms，内容高度变化约 180ms，卡片按顺序淡入。
快速切换停止旧动画，并按最新目标状态收尾；截图前完成当前切换，隐藏并恢复原有形态。
隐藏时停止悬浮球动画，空闲时没有常驻重绘定时器。动画中的尺寸变化也更新滚动排除区域。
尺寸回归同时覆盖 offscreen 和完全透明的原生 Windows 测试窗口，验证实际像素大小、缩放和屏幕边界。

## 去重与恢复

自动任务先比较画面，画面未变化则跳过 OCR；识别文字未变化则跳过 LLM。
仅在任务成功处理后记录画面和文本，网络/识别错误不会让同一画面永久无法重试。
手动任务可以重试同一页面，仍会过滤已掌握术语并使用缓存。

数据库键包含规范化术语、上下文和服务/模型/知识背景/提示词签名。
每次模型请求最多重试一次暂时性网络错误、429 或 5xx；认证和格式错误不自动重试。
配置期限覆盖整个请求及重试，不让逐段网络读取无限拖延。
DeepSeek 官方服务的短解释请求关闭思考并启用 JSON 模式；对长度截断、空回答和格式错误分别提示。

## 尚未实现

图像拼接、局部增量识别、本地 NER、多进程、GPU 调度、知识图谱、学习历史统计、
流式解释、系统托盘、点击穿透与高级视觉效果。

## 实现参考

- [Qt 线程与 QObject](https://doc.qt.io/qtforpython-6.10/overviews/qtdoc-threads-qobject.html)
- [HTTPX 异步接口](https://www.python-httpx.org/async/) 与 [网络超时](https://www.python-httpx.org/advanced/timeouts/)
- [DeepSeek 思考模式](https://api-docs.deepseek.com/guides/thinking_mode/) 与 [JSON 输出](https://api-docs.deepseek.com/guides/json_mode/)
