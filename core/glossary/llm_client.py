# e:\code\FlowGloss\core\glossary\llm_client.py
"""
异步API客户端（基于httpx或openai-python）。

技术简介：
- 使用asyncio异步I/O框架，实现非阻塞的API调用
- 支持流式响应（Streaming），实时接收生成内容
- 实现请求重试、超时控制、错误处理机制
- 支持多种LLM后端（OpenAI、Claude、本地模型）

模块功能：
- 向大模型发起请求，包含"生词+上下文"的Prompt
- 实现流式输出，边生成边显示，提升用户体验
- 处理API限流和错误重试，确保服务稳定性
- 管理解释缓存，减少重复API调用

整体作用：
知识生成的终点，负责内容的广度和深度，将原始词汇转化为可理解的知识点。

对外方法：
- async get_explanation(term, context): 异步获取词汇解释，支持流式输出
- async stream_explanation(term, context): 流式生成解释内容
- check_cache(term): 检查解释缓存
- update_cache(term, explanation): 更新解释缓存

联系：
接收Ranker的候选词汇，将生成的流式数据通过PySide6 Signal推送到UI模块。

线程位置：
异步I/O线程池（Asyncio Loop）。在主进程中运行，使用异步事件循环处理并发请求。
"""