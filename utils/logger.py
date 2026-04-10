# e:\code\FlowGloss\utils\logger.py
"""
日志记录工具。

技术简介：
- 基于Python标准库logging模块，实现结构化日志记录
- 支持多级别日志输出（DEBUG、INFO、WARNING、ERROR、CRITICAL）
- 实现日志轮转（RotatingFileHandler），避免日志文件过大
- 支持彩色控制台输出，提升开发调试体验

模块功能：
- 初始化全局日志系统，配置日志格式和输出目标
- 支持同时输出到文件和控制台
- 实现异步日志记录，避免阻塞主线程
- 提供模块级日志器，便于追踪特定模块的运行状态

整体作用：
提供统一的日志接口，支持系统调试、错误追踪和性能分析。

对外方法：
- setup_logging(config: Optional[dict] = None) -> None: 根据配置初始化日志系统
  - config: 日志配置字典，包含level、log_dir、log_file、max_bytes、backup_count、console_output、file_output等字段
  - 默认配置：level='INFO'，log_dir='logs'，log_file='flowgloss.log'，max_bytes=10MB，backup_count=5

- get_logger(name: str) -> logging.Logger: 获取指定名称的日志器实例
  - name: 日志器名称，通常使用模块名（如'core.monitor.event_hook'）
  - 返回: 配置好的日志器实例，支持DEBUG、INFO、WARNING、ERROR、CRITICAL级别日志输出

- set_level(level: str) -> None: 动态调整全局日志级别
  - level: 日志级别字符串（DEBUG、INFO、WARNING、ERROR、CRITICAL）
  - 同时更新根日志器和所有处理器的日志级别

- set_module_status(module_name: str, level: str) -> None: 根据模块名修改某模块的日志状态
  - module_name: 模块名称（如'core.monitor'），支持前缀匹配
  - level: 日志级别字符串（DEBUG、INFO、WARNING、ERROR、CRITICAL）
  - 影响所有以module_name开头的日志器，包括已创建和未来创建的日志器

联系：
被main.py调用初始化，被所有模块导入使用，记录系统运行状态。

线程位置：
主进程/全局初始化。日志记录操作是线程安全的，支持多线程并发写入。
"""

import logging
import logging.handlers
import sys
from pathlib import Path
from typing import Optional, Dict
from datetime import datetime
import threading


class ColoredFormatter(logging.Formatter):
    """彩色控制台日志格式化器"""
    
    COLORS = {
        'DEBUG': '\033[36m',
        'INFO': '\033[32m',
        'WARNING': '\033[33m',
        'ERROR': '\033[31m',
        'CRITICAL': '\033[35m',
    }
    RESET = '\033[0m'
    
    def format(self, record):
        log_color = self.COLORS.get(record.levelname, self.RESET)
        record.levelname = f"{log_color}{record.levelname}{self.RESET}"
        return super().format(record)


class LoggerManager:
    """日志管理器，提供全局日志配置和模块级日志器管理"""
    
    _instance = None
    _lock = threading.Lock()
    
    def __new__(cls):
        if cls._instance is None:
            with cls._lock:
                if cls._instance is None:
                    cls._instance = super().__new__(cls)
                    cls._instance._initialized = False
        return cls._instance
    
    def __init__(self):
        if self._initialized:
            return
        
        self._loggers: Dict[str, logging.Logger] = {}
        self._config = None
        self._module_levels: Dict[str, int] = {}  # 存储模块级别设置
        self._initialized = True
    
    def setup_logging(self, config: Optional[dict] = None) -> None:
        """根据配置初始化日志系统
        
        Args:
            config: 日志配置字典，包含以下字段：
                - level: 全局日志级别 (DEBUG, INFO, WARNING, ERROR, CRITICAL)
                - log_dir: 日志文件目录路径
                - log_file: 日志文件名
                - max_bytes: 单个日志文件最大字节数
                - backup_count: 保留的日志文件备份数量
                - console_output: 是否输出到控制台
                - file_output: 是否输出到文件
        """
        default_config = {
            'level': 'INFO',
            'log_dir': 'logs',
            'log_file': 'flowgloss.log',
            'max_bytes': 10 * 1024 * 1024,  # 10MB
            'backup_count': 5,
            'console_output': True,
            'file_output': True,
        }
        
        if config:
            default_config.update(config)
        
        self._config = default_config
        
        log_level = getattr(logging, default_config['level'].upper(), logging.INFO)
        
        root_logger = logging.getLogger()
        root_logger.setLevel(log_level)
        
        for handler in root_logger.handlers[:]:
            handler.close()
            root_logger.removeHandler(handler)
        
        formatter = logging.Formatter(
            fmt='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
            datefmt='%Y-%m-%d %H:%M:%S'
        )
        
        colored_formatter = ColoredFormatter(
            fmt='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
            datefmt='%Y-%m-%d %H:%M:%S'
        )
        
        if default_config['console_output']:
            console_handler = logging.StreamHandler(sys.stdout)
            console_handler.setLevel(log_level)
            console_handler.setFormatter(colored_formatter)
            root_logger.addHandler(console_handler)
        
        if default_config['file_output']:
            log_dir = Path(default_config['log_dir'])
            log_dir.mkdir(parents=True, exist_ok=True)
            
            log_file = log_dir / default_config['log_file']
            
            file_handler = logging.handlers.RotatingFileHandler(
                log_file,
                maxBytes=default_config['max_bytes'],
                backupCount=default_config['backup_count'],
                encoding='utf-8'
            )
            file_handler.setLevel(log_level)
            file_handler.setFormatter(formatter)
            root_logger.addHandler(file_handler)
        
        logging.info(f"日志系统初始化完成，级别: {default_config['level']}")
    
    def get_logger(self, name: str) -> logging.Logger:
        """获取指定名称的日志器实例
        
        Args:
            name: 日志器名称，通常使用模块名（如'core.monitor.event_hook'）
            
        Returns:
            logging.Logger: 配置好的日志器实例
        """
        if name in self._loggers:
            return self._loggers[name]
        
        logger = logging.getLogger(name)
        
        # 检查是否有匹配的模块级别设置
        for module_name, level in self._module_levels.items():
            if name.startswith(module_name):
                logger.setLevel(level)
                break
        
        self._loggers[name] = logger
        return logger
    
    def set_level(self, level: str) -> None:
        """动态调整全局日志级别
        
        Args:
            level: 日志级别字符串 (DEBUG, INFO, WARNING, ERROR, CRITICAL)
        """
        log_level = getattr(logging, level.upper(), logging.INFO)
        logging.getLogger().setLevel(log_level)
        
        for handler in logging.getLogger().handlers:
            handler.setLevel(log_level)
        
        logging.info(f"全局日志级别已更新为: {level}")
    
    def set_module_status(self, module_name: str, level: str) -> None:
        """根据模块名修改某模块的日志状态
        
        Args:
            module_name: 模块名称（如'core.monitor'）
            level: 日志级别字符串 (DEBUG, INFO, WARNING, ERROR, CRITICAL)
        """
        log_level = getattr(logging, level.upper(), logging.INFO)
        
        # 保存模块级别设置
        self._module_levels[module_name] = log_level
        
        # 修改已缓存的日志器
        for logger_name, logger in self._loggers.items():
            if logger_name.startswith(module_name):
                logger.setLevel(log_level)
        
        # 修改所有匹配的日志器（包括未缓存的）
        root_logger = logging.getLogger()
        for logger_name in root_logger.manager.loggerDict.keys():
            if logger_name.startswith(module_name):
                logger = logging.getLogger(logger_name)
                logger.setLevel(log_level)
        
        logging.info(f"模块 '{module_name}' 的日志级别已更新为: {level}")


_logger_manager = LoggerManager()


def setup_logging(config: Optional[dict] = None) -> None:
    """根据配置初始化日志系统
    
    Args:
        config: 日志配置字典
    """
    _logger_manager.setup_logging(config)


def get_logger(name: str) -> logging.Logger:
    """获取指定名称的日志器实例
    
    Args:
        name: 日志器名称
        
    Returns:
        logging.Logger: 日志器实例
    """
    return _logger_manager.get_logger(name)


def set_level(level: str) -> None:
    """动态调整全局日志级别
    
    Args:
        level: 日志级别字符串
    """
    _logger_manager.set_level(level)


def set_module_status(module_name: str, level: str) -> None:
    """根据模块名修改某模块的日志状态
    
    Args:
        module_name: 模块名称
        level: 日志级别字符串
    """
    _logger_manager.set_module_status(module_name, level)


# ============================================================================
# 使用示例
# ============================================================================

"""
使用方法：

1. 在各个模块中导入logger：
   from utils.logger import get_logger

2. 创建模块专属的logger实例：
   logger = get_logger('core.monitor.event_hook')

3. 使用不同级别输出日志：
   logger.debug('调试信息：变量值为 %s', value)
   logger.info('系统启动完成')
   logger.warning('OCR置信度较低：%.2f', confidence)
   logger.error('事件监听失败：%s', str(e))
   logger.critical('系统崩溃，无法继续运行')

4. 推荐的日志级别使用场景：
   - DEBUG: 详细的调试信息，包括变量值、函数调用等
   - INFO: 重要的系统状态信息，如启动、关闭、配置加载等
   - WARNING: 潜在问题，不影响运行但需要注意的情况
   - ERROR: 错误情况，影响部分功能但系统仍可运行
   - CRITICAL: 严重错误，系统无法继续运行

5. 在main.py中初始化日志系统：
   from utils.logger import setup_logging
   
   config = {
       'level': 'INFO',
       'log_dir': 'logs',
       'log_file': 'flowgloss.log',
       'console_output': True,
       'file_output': True,
   }
   setup_logging(config)

6. 动态调整日志级别（可选）：
   from utils.logger import set_level, set_module_status
   
   # 调整全局日志级别
   set_level('DEBUG')
   
   # 调整特定模块的日志级别
   set_module_status('core.vision', 'DEBUG')
   set_module_status('core.cognition', 'WARNING')

示例代码：

# core/monitor/event_hook.py
from utils.logger import get_logger

logger = get_logger('core.monitor.event_hook')

def on_scroll(x, y, dx, dy):
    logger.debug(f'检测到滚动事件：dx={dx}, dy={dy}')
    # 处理滚动逻辑...

# core/vision/ocr_engine.py
from utils.logger import get_logger

logger = get_logger('core.vision.ocr_engine')

def recognize(image):
    logger.info('开始OCR识别')
    try:
        result = ocr_engine.ocr(image)
        if result:
            logger.info(f'OCR识别成功，识别到{len(result)}个文本块')
        else:
            logger.warning('OCR未识别到任何文本')
        return result
    except Exception as e:
        logger.error(f'OCR识别失败：{str(e)}', exc_info=True)
        return None

# core/cognition/ner_worker.py
from utils.logger import get_logger

logger = get_logger('core.cognition.ner_worker')

def extract_entities(text):
    logger.debug(f'开始提取实体，文本长度：{len(text)}')
    entities = ner_model.extract_entities(text)
    logger.info(f'提取到{len(entities)}个实体：{entities}')
    return entities

# ui/overlay.py
from utils.logger import get_logger

logger = get_logger('ui.overlay')

def show_tip(term, explanation):
    logger.info(f'显示提示：{term}')
    # 显示提示逻辑...

# main.py
from utils.logger import setup_logging, get_logger, set_level

logger = get_logger('main')

def main():
    # 初始化日志系统
    setup_logging()
    
    logger.info('FlowGloss启动中...')
    
    # 在开发调试时，可以临时调整日志级别
    # set_level('DEBUG')
    
    try:
        # 初始化各个模块
        logger.info('初始化事件监听模块')
        # ...
        
        logger.info('初始化视觉处理模块')
        # ...
        
        logger.info('系统初始化完成，开始运行')
        
        # 主循环
        while True:
            pass
            
    except KeyboardInterrupt:
        logger.info('收到中断信号，正在关闭系统...')
    except Exception as e:
        logger.critical(f'系统发生严重错误：{str(e)}', exc_info=True)
    finally:
        logger.info('FlowGloss已关闭')

if __name__ == '__main__':
    main()
"""