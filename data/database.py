# e:\code\FlowGloss\data\database.py
"""
基于SQLite的轻量级数据库。

技术简介：
- 使用SQLite3嵌入式数据库，无需独立数据库服务
- 实现ORM（对象关系映射）层，简化数据访问
- 支持事务处理，确保数据一致性
- 实现连接池管理，优化并发访问性能

模块功能：
- 存储用户词典（词汇、解释、上下文）
- 记录熟练度等级（-1到1的连续值，表示从未见到到完全掌握）
- 维护解释缓存（词汇→解释的映射关系）
- 跟踪学习历史（访问时间、交互次数）

整体作用：
实现"越用越聪明"的持久化层，支持个性化推荐和长期学习跟踪。

对外方法：
- update_word(word, delta): 更新词汇熟练度（delta为增量值）
- query_history(word): 查询词汇学习历史
- get_proficiency(word): 获取词汇熟练度
- cache_explanation(word, explanation): 缓存解释内容
- get_cached_explanation(word): 获取缓存的解释

联系：
被Ranker查询用户知识库，被UI反馈功能更新用户数据。

线程位置：
主进程/I/O线程。使用线程安全的数据库连接，支持多线程并发访问。
"""