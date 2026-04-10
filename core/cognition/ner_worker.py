# e:\code\FlowGloss\core\cognition\ner_worker.py
"""
本地轻量级命名实体识别（GLiNER）。

技术简介：
- 基于GLiNER（Generalist Language Model for Named Entity Recognition）
- 支持零样本和少样本学习，无需大量标注数据
- 使用PyTorch后端，可配置CPU/GPU推理模式

模块功能：
- 从OCR结果中提取具有"实体性"的专有名词
- 识别技术术语、专业概念、缩写词等
- 过滤通用词汇和停用词
- 返回实体及其类型标签（如技术术语、人名、机构名等）

整体作用：
从海量文本中筛选出"潜在知识点"，为后续解释生成提供候选词。

对外方法：
- extract_entities(text: str) -> list: 从文本中提取命名实体，返回实体列表
- load_model(model_path): 加载预训练模型
- set_confidence_threshold(threshold): 设置识别置信度阈值

联系：
输入来自OCR模块的文本数据，输出传给Ranker进行排序和过滤。

线程位置：
独立子进程或主进程子线程。计算密集型任务，建议独立进程运行以避免阻塞主线程。
"""