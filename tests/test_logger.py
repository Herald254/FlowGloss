# e:\code\FlowGloss\tests\test_logger.py
"""
logger模块的单元测试。

测试内容：
- 日志系统初始化
- 日志器实例获取
- 全局日志级别调整
- 模块级日志控制
- 不同级别日志输出
- 日志文件输出
- 日志轮转功能
"""

import unittest
import logging
import sys
import tempfile
import shutil
from pathlib import Path
from io import StringIO
import time

import sys
sys.path.insert(0, str(Path(__file__).parent.parent))

from utils.logger import (
    setup_logging,
    get_logger,
    set_level,
    set_module_status,
    LoggerManager
)
from utils.logger import ColoredFormatter


class TestColoredFormatter(unittest.TestCase):
    def test_console_color_does_not_modify_shared_record(self):
        record = logging.LogRecord("test", logging.INFO, __file__, 1, "message", (), None)
        ColoredFormatter("%(levelname)s").format(record)
        self.assertEqual(record.levelname, "INFO")
        self.assertEqual(logging.Formatter("%(levelname)s").format(record), "INFO")


def cleanup_logging():
    """清理日志资源，关闭所有handlers"""
    root_logger = logging.getLogger()
    for handler in root_logger.handlers[:]:
        handler.close()
        root_logger.removeHandler(handler)


class TestLoggerManager(unittest.TestCase):
    """测试LoggerManager单例模式"""
    
    def test_singleton_pattern(self):
        """测试LoggerManager的单例模式"""
        manager1 = LoggerManager()
        manager2 = LoggerManager()
        self.assertIs(manager1, manager2)
    
    def test_logger_caching(self):
        """测试日志器实例缓存"""
        logger1 = get_logger('test.module')
        logger2 = get_logger('test.module')
        self.assertIs(logger1, logger2)


class TestLoggingSetup(unittest.TestCase):
    """测试日志系统初始化"""
    
    def setUp(self):
        """每个测试前的设置"""
        self.temp_dir = tempfile.mkdtemp()
        self.log_dir = Path(self.temp_dir) / 'logs'
        self.log_file = self.log_dir / 'test.log'
    
    def tearDown(self):
        """每个测试后的清理"""
        root_logger = logging.getLogger()
        for handler in root_logger.handlers[:]:
            handler.close()
            root_logger.removeHandler(handler)
        shutil.rmtree(self.temp_dir)
    
    def test_default_setup(self):
        """测试默认配置初始化"""
        setup_logging()
        root_logger = logging.getLogger()
        self.assertEqual(root_logger.level, logging.INFO)
    
    def test_custom_setup(self):
        """测试自定义配置初始化"""
        config = {
            'level': 'DEBUG',
            'log_dir': str(self.log_dir),
            'log_file': 'test.log',
            'console_output': False,
            'file_output': True,
        }
        setup_logging(config)
        
        root_logger = logging.getLogger()
        self.assertEqual(root_logger.level, logging.DEBUG)
        self.assertTrue(self.log_file.exists())
    
    def test_log_file_creation(self):
        """测试日志文件创建"""
        config = {
            'log_dir': str(self.log_dir),
            'log_file': 'test.log',
            'console_output': False,
            'file_output': True,
        }
        setup_logging(config)
        
        logger = get_logger('test')
        logger.info('Test message')
        
        self.assertTrue(self.log_file.exists())
        content = self.log_file.read_text(encoding='utf-8')
        self.assertIn('Test message', content)


class TestLoggerOutput(unittest.TestCase):
    """测试日志输出功能"""
    
    def setUp(self):
        """每个测试前的设置"""
        self.temp_dir = tempfile.mkdtemp()
        self.log_dir = Path(self.temp_dir) / 'logs'
        self.log_file = self.log_dir / 'test.log'
        
        config = {
            'level': 'DEBUG',
            'log_dir': str(self.log_dir),
            'log_file': 'test.log',
            'console_output': False,
            'file_output': True,
        }
        setup_logging(config)
    
    def tearDown(self):
        """每个测试后的清理"""
        root_logger = logging.getLogger()
        for handler in root_logger.handlers[:]:
            handler.close()
            root_logger.removeHandler(handler)
        shutil.rmtree(self.temp_dir)
    
    def test_debug_output(self):
        """测试DEBUG级别输出"""
        logger = get_logger('test.debug')
        logger.debug('Debug message')
        
        content = self.log_file.read_text(encoding='utf-8')
        self.assertIn('DEBUG', content)
        self.assertIn('Debug message', content)
    
    def test_info_output(self):
        """测试INFO级别输出"""
        logger = get_logger('test.info')
        logger.info('Info message')
        
        content = self.log_file.read_text(encoding='utf-8')
        self.assertIn('INFO', content)
        self.assertIn('Info message', content)
    
    def test_warning_output(self):
        """测试WARNING级别输出"""
        logger = get_logger('test.warning')
        logger.warning('Warning message')
        
        content = self.log_file.read_text(encoding='utf-8')
        self.assertIn('WARNING', content)
        self.assertIn('Warning message', content)
    
    def test_error_output(self):
        """测试ERROR级别输出"""
        logger = get_logger('test.error')
        logger.error('Error message')
        
        content = self.log_file.read_text(encoding='utf-8')
        self.assertIn('ERROR', content)
        self.assertIn('Error message', content)
    
    def test_critical_output(self):
        """测试CRITICAL级别输出"""
        logger = get_logger('test.critical')
        logger.critical('Critical message')
        
        content = self.log_file.read_text(encoding='utf-8')
        self.assertIn('CRITICAL', content)
        self.assertIn('Critical message', content)
    
    def test_logger_name_in_output(self):
        """测试日志器名称在输出中"""
        logger = get_logger('test.module.name')
        logger.info('Test message')
        
        content = self.log_file.read_text(encoding='utf-8')
        self.assertIn('test.module.name', content)


class TestLogLevelControl(unittest.TestCase):
    """测试日志级别控制"""
    
    def setUp(self):
        """每个测试前的设置"""
        self.temp_dir = tempfile.mkdtemp()
        self.log_dir = Path(self.temp_dir) / 'logs'
        self.log_file = self.log_dir / 'test.log'
        
        config = {
            'level': 'INFO',
            'log_dir': str(self.log_dir),
            'log_file': 'test.log',
            'console_output': False,
            'file_output': True,
        }
        setup_logging(config)
    
    def tearDown(self):
        """每个测试后的清理"""
        cleanup_logging()
        shutil.rmtree(self.temp_dir)
    
    def test_set_level_debug(self):
        """测试设置为DEBUG级别"""
        set_level('DEBUG')
        root_logger = logging.getLogger()
        self.assertEqual(root_logger.level, logging.DEBUG)
    
    def test_set_level_info(self):
        """测试设置为INFO级别"""
        set_level('INFO')
        root_logger = logging.getLogger()
        self.assertEqual(root_logger.level, logging.INFO)
    
    def test_set_level_warning(self):
        """测试设置为WARNING级别"""
        set_level('WARNING')
        root_logger = logging.getLogger()
        self.assertEqual(root_logger.level, logging.WARNING)
    
    def test_set_level_error(self):
        """测试设置为ERROR级别"""
        set_level('ERROR')
        root_logger = logging.getLogger()
        self.assertEqual(root_logger.level, logging.ERROR)
    
    def test_level_filtering(self):
        """测试级别过滤功能"""
        set_level('WARNING')
        
        logger = get_logger('test.filter')
        logger.debug('Debug message')  # 不应该输出
        logger.info('Info message')     # 不应该输出
        logger.warning('Warning message')  # 应该输出
        logger.error('Error message')      # 应该输出
        
        content = self.log_file.read_text(encoding='utf-8')
        self.assertNotIn('Debug message', content)
        self.assertNotIn('Info message', content)
        self.assertIn('Warning message', content)
        self.assertIn('Error message', content)


class TestModuleStatusControl(unittest.TestCase):
    """测试模块级日志控制"""
    
    def setUp(self):
        """每个测试前的设置"""
        self.temp_dir = tempfile.mkdtemp()
        self.log_dir = Path(self.temp_dir) / 'logs'
        self.log_file = self.log_dir / 'test.log'
        
        config = {
            'level': 'WARNING',
            'log_dir': str(self.log_dir),
            'log_file': 'test.log',
            'console_output': False,
            'file_output': True,
        }
        setup_logging(config)
    
    def tearDown(self):
        """每个测试后的清理"""
        cleanup_logging()
        shutil.rmtree(self.temp_dir)
    
    def test_set_module_status_debug(self):
        """测试设置模块为DEBUG级别"""
        set_module_status('test.module', 'DEBUG')
        
        logger = get_logger('test.module.submodule')
        self.assertEqual(logger.level, logging.DEBUG)
    
    def test_set_module_status_info(self):
        """测试设置模块为INFO级别"""
        set_module_status('test.module', 'INFO')
        
        logger = get_logger('test.module.submodule')
        self.assertEqual(logger.level, logging.INFO)
    
    def test_module_level_filtering(self):
        """测试模块级别过滤"""
        # 设置全局级别为DEBUG，这样handler也会输出DEBUG消息
        set_level('DEBUG')
        
        # 设置特定模块为ERROR级别
        set_module_status('test.error_module', 'ERROR')
        
        debug_logger = get_logger('test.debug_module')
        error_logger = get_logger('test.error_module')
        
        debug_logger.debug('Debug message')  # 应该输出
        debug_logger.info('Info message')    # 应该输出
        error_logger.debug('Debug message')  # 不应该输出
        error_logger.info('Info message')    # 不应该输出
        error_logger.error('Error message')   # 应该输出
        
        content = self.log_file.read_text(encoding='utf-8')
        
        # debug_module应该有debug和info消息
        self.assertIn('test.debug_module', content)
        self.assertIn('Debug message', content)
        self.assertIn('Info message', content)
        
        # error_module应该只有error消息
        self.assertIn('test.error_module', content)
        # 检查error_module的debug和info消息不应该出现
        lines = content.split('\n')
        error_module_lines = [line for line in lines if 'test.error_module' in line]
        error_module_debug_lines = [line for line in error_module_lines if 'Debug message' in line]
        error_module_info_lines = [line for line in error_module_lines if 'Info message' in line]
        self.assertEqual(len(error_module_debug_lines), 0)
        self.assertEqual(len(error_module_info_lines), 0)


class TestLogRotation(unittest.TestCase):
    """测试日志轮转功能"""
    
    def setUp(self):
        """每个测试前的设置"""
        self.temp_dir = tempfile.mkdtemp()
        self.log_dir = Path(self.temp_dir) / 'logs'
        self.log_file = self.log_dir / 'test.log'
        
        config = {
            'level': 'INFO',
            'log_dir': str(self.log_dir),
            'log_file': 'test.log',
            'max_bytes': 1024,  # 1KB
            'backup_count': 3,
            'console_output': False,
            'file_output': True,
        }
        setup_logging(config)
    
    def tearDown(self):
        """每个测试后的清理"""
        cleanup_logging()
        shutil.rmtree(self.temp_dir)
    
    def test_log_rotation(self):
        """测试日志文件轮转"""
        logger = get_logger('test.rotation')
        
        for i in range(100):
            logger.info(f'This is a test message number {i} with some additional text to fill up the log file')
        
        log_files = list(self.log_dir.glob('test.log*'))
        self.assertGreater(len(log_files), 1, '应该创建多个日志文件')
        self.assertLessEqual(len(log_files), 4, '不应该超过备份数量+1')


class TestColoredOutput(unittest.TestCase):
    """测试彩色控制台输出"""
    
    def test_colored_formatter(self):
        """测试彩色格式化器"""
        from utils.logger import ColoredFormatter
        
        formatter = ColoredFormatter('%(levelname)s - %(message)s')
        
        record = logging.LogRecord(
            name='test',
            level=logging.INFO,
            pathname='test.py',
            lineno=1,
            msg='Test message',
            args=(),
            exc_info=None
        )
        
        formatted = formatter.format(record)
        self.assertIn('INFO', formatted)
        self.assertIn('Test message', formatted)
        self.assertIn('\033[', formatted)  # ANSI颜色代码


class TestIntegration(unittest.TestCase):
    """集成测试"""
    
    def setUp(self):
        """每个测试前的设置"""
        self.temp_dir = tempfile.mkdtemp()
        self.log_dir = Path(self.temp_dir) / 'logs'
        self.log_file = self.log_dir / 'test.log'
    
    def tearDown(self):
        """每个测试后的清理"""
        cleanup_logging()
        shutil.rmtree(self.temp_dir)
    
    def test_full_workflow(self):
        """测试完整工作流程"""
        config = {
            'level': 'DEBUG',
            'log_dir': str(self.log_dir),
            'log_file': 'test.log',
            'console_output': False,
            'file_output': True,
        }
        setup_logging(config)
        
        logger1 = get_logger('core.monitor')
        logger2 = get_logger('core.vision')
        logger3 = get_logger('core.cognition')
        
        logger1.debug('Monitor started')
        logger2.info('Screenshot captured')
        logger3.warning('OCR confidence low')
        logger1.error('Event hook failed')
        
        content = self.log_file.read_text(encoding='utf-8')
        
        self.assertIn('Monitor started', content)
        self.assertIn('Screenshot captured', content)
        self.assertIn('OCR confidence low', content)
        self.assertIn('Event hook failed', content)
        
        self.assertIn('core.monitor', content)
        self.assertIn('core.vision', content)
        self.assertIn('core.cognition', content)


if __name__ == '__main__':
    unittest.main(verbosity=2)
