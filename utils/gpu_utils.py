# e:\code\FlowGloss\utils\gpu_utils.py
"""
GPU加速工具。

技术简介：
- 使用PyTorch CUDA接口管理GPU资源
- 实现显存监控和分配优化
- 支持多GPU环境下的设备选择和负载均衡
- 实现模型加载的顺序控制，避免显存冲突

模块功能：
- 检测GPU可用性和显存容量
- 管理OCR和NER模型的显存分配
- 实现顺序启动逻辑：先初始化OCR引擎，稳定后再加载NER模型
- 监控GPU使用率，提供性能优化建议

整体作用：
优化GPU资源利用，确保RTX 5060显卡性能最大化，避免显存溢出和资源竞争。

对外方法：
- check_gpu_available(): 检测CUDA可用性
- get_gpu_memory_info(): 获取显存使用情况
- allocate_model_memory(model_size): 预分配模型显存
- sequential_model_loading(models): 顺序加载模型，避免显存冲突

联系：
被Vision模块的OCR引擎和Cognition模块的NER工作器调用，管理GPU资源分配。

线程位置：
主进程/初始化阶段。在模型加载时调用，运行时提供GPU状态查询接口。

注意事项：
- RTX 5060虽然性能强劲，但OCR和NER同时初始化可能导致显存瞬间飙升
- 建议在系统启动时按顺序加载模型，确保显存分配稳定
- 监控显存使用情况，及时清理未使用的模型缓存
"""