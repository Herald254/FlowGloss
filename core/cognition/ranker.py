# e:\code\FlowGloss\core\cognition\ranker.py
"""
启发式排序与知识对比逻辑。

技术简介：
- 基于用户知识画像的个性化排序算法
- 采用多维度评分机制（新颖性、重要性、相关性）
- 实现增量式知识库更新和查询优化

模块功能：
- 对比本地User_Profile.db，查询用户已掌握词汇
- 如果词汇已标记为"掌握"（熟练度>=阈值），则剔除
- 如果是新词，则根据出现频率、上下文重要性排序
- 实现去重逻辑，避免重复解释相同概念

整体作用：
决策中心，决定最终向用户弹窗的内容，实现个性化推荐。

对外方法：
- get_top_candidates(entities: list) -> list: 对实体列表进行排序，返回top-k候选词
- update_user_feedback(word, score): 更新用户对词汇的反馈评分
- calculate_importance(entity, context) -> float: 计算实体重要性得分

联系：
频繁查询data/database.py，读取用户知识库和解释缓存。

线程位置：
主进程/计算密集型子线程。需要快速响应，建议使用线程池处理批量排序任务。
"""