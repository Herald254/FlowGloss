# e:\code\FlowGloss\tests\test_event_hook.py
"""
ScreenEventMonitor模块的单元测试。

测试内容：
- 事件监听器初始化
- 防抖机制测试
- 鼠标滚动监听测试
- 键盘按键监听测试
- 回调机制测试
- 线程安全测试
- 上下文管理器测试
- 集成测试
"""

import unittest
import time
import threading
from pathlib import Path
from unittest.mock import Mock, patch, MagicMock

import sys

# 添加项目根目录到Python路径
sys.path.insert(0, str(Path(__file__).parent.parent))

from core.monitor.event_hook import ScreenEventMonitor
from pynput import keyboard, mouse



class TestScreenEventMonitorInit(unittest.TestCase):
    """测试ScreenEventMonitor初始化"""
    
    def test_default_initialization(self):
        """测试默认参数初始化"""
        monitor = ScreenEventMonitor()
        
        self.assertEqual(monitor.debounce_interval, 1.0)
        self.assertIsNone(monitor.on_stable_callback)
        self.assertTrue(monitor.enable_mouse_scroll)
        self.assertTrue(monitor.enable_keyboard)
        self.assertFalse(monitor.running)
    
    def test_custom_initialization(self):
        """测试自定义参数初始化"""
        callback = Mock()
        monitor = ScreenEventMonitor(
            debounce_interval=0.5,
            on_stable_callback=callback,
            enable_mouse_scroll=False,
            enable_keyboard=False,
        )
        
        self.assertEqual(monitor.debounce_interval, 0.5)
        self.assertEqual(monitor.on_stable_callback, callback)
        self.assertFalse(monitor.enable_mouse_scroll)
        self.assertFalse(monitor.enable_keyboard)
    
    def test_invalid_debounce_interval(self):
        """测试无效的防抖间隔"""
        with self.assertRaises(ValueError):
            ScreenEventMonitor(debounce_interval=0)
        
        with self.assertRaises(ValueError):
            ScreenEventMonitor(debounce_interval=-1)
    
    def test_default_trigger_keys(self):
        """测试默认触发键"""
        monitor = ScreenEventMonitor()
        
        expected_keys = {
            keyboard.Key.space,
            keyboard.Key.enter,
            keyboard.Key.page_down,
            keyboard.Key.page_up,
            keyboard.Key.up,
            keyboard.Key.down,
            keyboard.Key.left,
            keyboard.Key.right,
            keyboard.Key.home,
            keyboard.Key.end,
        }
        self.assertEqual(monitor.trigger_keys, expected_keys)
    
    def test_custom_trigger_keys(self):
        """测试自定义触发键"""
        custom_keys = {keyboard.Key.space, keyboard.Key.enter}
        monitor = ScreenEventMonitor(trigger_keys=custom_keys)
        
        self.assertEqual(monitor.trigger_keys, custom_keys)


class TestScreenEventMonitorBasic(unittest.TestCase):
    """测试ScreenEventMonitor基本功能"""
    
    def setUp(self):
        """每个测试前的设置"""
        self.monitor = ScreenEventMonitor()
    
    def tearDown(self):
        """每个测试后的清理"""
        if self.monitor.running:
            self.monitor.stop()
    
    def test_running_property(self):
        """测试running属性"""
        self.assertFalse(self.monitor.running)
        
        self.monitor.start()
        self.assertTrue(self.monitor.running)
        
        self.monitor.stop()
        self.assertFalse(self.monitor.running)
    
    def test_set_callback(self):
        """测试设置回调函数"""
        callback = Mock()
        self.monitor.set_callback(callback)
        
        self.assertEqual(self.monitor.on_stable_callback, callback)
    
    def test_get_status(self):
        """测试获取状态信息"""
        status = self.monitor.get_status()
        
        self.assertIsInstance(status, dict)
        self.assertIn('running', status)
        self.assertIn('event_count', status)
        self.assertIn('stable_trigger_count', status)
        self.assertIn('timer_active', status)
        self.assertIn('callback_running', status)
        self.assertIn('callback_pending', status)
        self.assertIn('mouse_enabled', status)
        self.assertIn('keyboard_enabled', status)
        
        self.assertFalse(status['running'])
        self.assertEqual(status['event_count'], 0)
        self.assertEqual(status['stable_trigger_count'], 0)


class TestDebounceMechanism(unittest.TestCase):
    """测试防抖机制"""
    
    def setUp(self):
        """每个测试前的设置"""
        self.callback = Mock()
        self.monitor = ScreenEventMonitor(
            debounce_interval=0.1,  # 使用较短的间隔便于测试
            on_stable_callback=self.callback,
            enable_mouse_scroll=False,
            enable_keyboard=False,
        )
    
    def tearDown(self):
        """每个测试后的清理"""
        if self.monitor.running:
            self.monitor.stop()
    
    def test_debounce_timer_reset(self):
        """测试防抖定时器重置"""
        self.monitor.start()
        
        # 模拟用户操作
        self.monitor.notify_activity()
        
        status = self.monitor.get_status()
        self.assertTrue(status['timer_active'])
        self.assertEqual(status['event_count'], 1)
        
        # 再次操作，应该重置定时器
        time.sleep(0.05)  # 等待一半时间
        self.monitor.notify_activity()
        
        status = self.monitor.get_status()
        self.assertTrue(status['timer_active'])
        self.assertEqual(status['event_count'], 2)
        
        # 等待定时器到期
        time.sleep(0.15)
        
        # 回调应该被调用一次
        self.callback.assert_called_once()
    
    def test_trigger_now(self):
        """测试立即触发
        
        需要先启动monitor才能正确设置回调机制。
        """
        self.monitor.start()
        
        # 立即触发
        self.monitor.trigger_now()
        
        # 等待回调执行
        time.sleep(0.05)
        
        # 回调应该被调用一次
        self.callback.assert_called_once()
    
    def test_callback_not_called_before_timeout(self):
        """测试超时前不调用回调"""
        self.monitor.start()
        
        self.monitor.notify_activity()
        
        # 等待一半时间
        time.sleep(0.05)
        
        # 回调不应该被调用
        self.callback.assert_not_called()
    
    def test_callback_called_after_timeout(self):
        """测试超时后调用回调"""
        self.monitor.start()
        
        self.monitor.notify_activity()
        
        # 等待超时
        time.sleep(0.15)
        
        # 回调应该被调用
        self.callback.assert_called_once()


class TestMouseScroll(unittest.TestCase):
    """测试鼠标滚动监听"""
    
    def setUp(self):
        """每个测试前的设置"""
        self.callback = Mock()
        self.monitor = ScreenEventMonitor(
            debounce_interval=0.1,
            on_stable_callback=self.callback,
            enable_keyboard=False,
        )
    
    def tearDown(self):
        """每个测试后的清理"""
        if self.monitor.running:
            self.monitor.stop()
    
    def test_mouse_scroll_detection(self):
        """测试鼠标滚动检测"""
        self.monitor.start()
        
        # 模拟鼠标滚动
        self.monitor._on_scroll(100, 100, 0, 10)  # 垂直滚动
        
        status = self.monitor.get_status()
        self.assertEqual(status['event_count'], 1)
        
        # 等待超时
        time.sleep(0.15)
        
        # 回调应该被调用
        self.callback.assert_called_once()
    
    def test_horizontal_scroll(self):
        """测试水平滚动"""
        self.monitor.start()
        
        # 模拟水平滚动
        self.monitor._on_scroll(100, 100, 10, 0)
        
        status = self.monitor.get_status()
        self.assertEqual(status['event_count'], 1)
    
    def test_no_scroll(self):
        """测试无滚动时不触发"""
        self.monitor.start()
        
        # 模拟无滚动
        self.monitor._on_scroll(100, 100, 0, 0)
        
        status = self.monitor.get_status()
        self.assertEqual(status['event_count'], 0)


class TestExcludedScroll(unittest.TestCase):
    """窗口内滚动不触发识别，并撤销尚未到期的页面滚动任务。"""

    def setUp(self):
        self.callback = Mock()
        self.monitor = ScreenEventMonitor(
            debounce_interval=0.1, on_stable_callback=self.callback,
            enable_keyboard=False, enable_mouse_scroll=False,
        )
        self.monitor.set_excluded_regions([(100, 100, 400, 500)])
        self.monitor.start()

    def tearDown(self):
        self.monitor.stop()

    def test_internal_vertical_and_horizontal_scroll_are_ignored(self):
        self.monitor._on_scroll(200, 200, 0, -3)
        self.monitor._on_scroll(200, 200, 3, 0)
        self.assertEqual(self.monitor.event_count, 0)
        self.assertIsNone(self.monitor._timer)

    def test_external_scroll_still_triggers(self):
        self.monitor._on_scroll(50, 50, 0, -3)
        time.sleep(0.15)
        self.callback.assert_called_once()

    def test_internal_scroll_cancels_pending_external_trigger(self):
        self.monitor._on_scroll(50, 50, 0, -3)
        self.monitor._on_scroll(200, 200, 0, -3)
        time.sleep(0.15)
        self.callback.assert_not_called()

    def test_moving_or_hiding_window_updates_exclusion(self):
        self.monitor.set_excluded_regions([(500, 500, 800, 900)])
        self.monitor._on_scroll(200, 200, 0, -3)
        self.assertEqual(self.monitor.event_count, 1)
        self.monitor.set_excluded_regions([])
        self.monitor._on_scroll(600, 600, 0, -3)
        self.assertEqual(self.monitor.event_count, 2)


class TestKeyboardEvents(unittest.TestCase):
    """测试键盘事件监听"""
    
    def setUp(self):
        """每个测试前的设置"""
        self.callback = Mock()
        self.monitor = ScreenEventMonitor(
            debounce_interval=0.1,
            on_stable_callback=self.callback,
            enable_mouse_scroll=False,
        )
    
    def tearDown(self):
        """每个测试后的清理"""
        if self.monitor.running:
            self.monitor.stop()
    
    def test_trigger_key_detection(self):
        """测试触发键检测
        
        注意：这个测试直接调用内部方法，因为pynput的监听器
        需要实际的键盘输入才能触发。在生产环境中，
        pynput会自动调用_on_key_press方法。
        """
        self.monitor.start()
        
        # 模拟pynput会传递给_on_key_press的按键事件
        # 参数格式：on_press(key)
        self.monitor._on_key_press(keyboard.Key.space)
        
        status = self.monitor.get_status()
        self.assertEqual(status['event_count'], 1)
        
        # 等待防抖超时
        time.sleep(0.15)
        
        # 回调应该被调用一次
        self.callback.assert_called_once()
    
    def test_non_trigger_key(self):
        """测试非触发键
        
        测试不在触发键列表中的按键不会触发事件。
        """
        self.monitor.start()
        
        # 模拟按下非触发键（字母A）
        self.monitor._on_key_press(keyboard.KeyCode.from_char('a'))
        
        status = self.monitor.get_status()
        self.assertEqual(status['event_count'], 0)
    
    def test_page_down_key(self):
        """测试PageDown键
        
        PageDown是常见的翻页键，应该触发事件。
        """
        self.monitor.start()
        
        self.monitor._on_key_press(keyboard.Key.page_down)
        
        status = self.monitor.get_status()
        self.assertEqual(status['event_count'], 1)
    
    def test_enter_key(self):
        """测试Enter键
        
        Enter键常用于确认操作，应该触发事件。
        """
        self.monitor.start()
        
        self.monitor._on_key_press(keyboard.Key.enter)
        
        status = self.monitor.get_status()
        self.assertEqual(status['event_count'], 1)
    
    def test_all_default_trigger_keys(self):
        """测试所有默认触发键
        
        验证所有默认的触发键都能正确工作。
        """
        self.monitor.start()
        
        trigger_keys = [
            keyboard.Key.space,
            keyboard.Key.enter,
            keyboard.Key.page_down,
            keyboard.Key.page_up,
            keyboard.Key.up,
            keyboard.Key.down,
            keyboard.Key.left,
            keyboard.Key.right,
            keyboard.Key.home,
            keyboard.Key.end,
        ]
        
        for key in trigger_keys:
            self.monitor._on_key_press(key)
        
        status = self.monitor.get_status()
        self.assertEqual(status['event_count'], len(trigger_keys))
    
    def test_multiple_key_events(self):
        """测试多次按键事件
        
        模拟用户连续按键，验证防抖机制
        是否正确重置定时器。
        """
        self.monitor.start()
        
        # 模拟连续按键
        for i in range(3):
            self.monitor._on_key_press(keyboard.Key.space)
            time.sleep(0.03)  # 每次按键间隔30ms
        
        status = self.monitor.get_status()
        self.assertEqual(status['event_count'], 3)
        
        # 等待最后一次按键的超时
        time.sleep(0.15)
        
        # 应该只触发一次回调（防抖机制）
        self.callback.assert_called_once()


class TestCallbackMechanism(unittest.TestCase):
    """测试回调机制"""
    
    def setUp(self):
        """每个测试前的设置"""
        self.callback = Mock()
        self.monitor = ScreenEventMonitor(
            debounce_interval=0.1,
            on_stable_callback=self.callback,
            enable_mouse_scroll=False,
            enable_keyboard=False,
        )
    
    def tearDown(self):
        """每个测试后的清理"""
        if self.monitor.running:
            self.monitor.stop()
    
    def test_callback_execution(self):
        """测试回调执行"""
        self.monitor.start()
        self.monitor.trigger_now()
        
        # 等待回调执行
        time.sleep(0.05)
        
        self.callback.assert_called_once()
    
    def test_callback_exception_handling(self):
        """测试回调异常处理"""
        # 创建一个会抛出异常的回调
        def failing_callback():
            raise Exception("Test exception")
        
        self.monitor.set_callback(failing_callback)
        self.monitor.start()
        
        # 应该不会抛出异常
        self.monitor.trigger_now()
        time.sleep(0.05)
    
    def test_callback_reentry_protection(self):
        """测试回调重入保护
        
        重入保护机制的实际行为：
        - _callback_pending是布尔值，不是计数器
        - 当回调正在执行时，新的触发会设置_callback_pending=True
        - 但多次触发只会记住最后一次（布尔值覆盖）
        - 快速触发3次时，回调会执行2次（第一次 + pending的一次）
        """
        call_count = [0]
        
        def slow_callback():
            call_count[0] += 1
            time.sleep(0.2)  # 模拟慢回调
        
        self.monitor.set_callback(slow_callback)
        self.monitor.start()
        
        # 快速触发3次
        self.monitor.trigger_now()
        self.monitor.trigger_now()
        self.monitor.trigger_now()
        
        # 等待所有回调完成
        time.sleep(0.5)
        
        # 根据重入保护机制，应该执行2次回调
        # 第一次触发：立即执行
        # 第二、三次触发：设置pending标志（覆盖）
        # 第一次回调完成后：执行pending回调（只有一次）
        self.assertEqual(call_count[0], 2)


class TestThreadSafety(unittest.TestCase):
    """测试线程安全"""
    
    def setUp(self):
        """每个测试前的设置"""
        self.callback = Mock()
        self.monitor = ScreenEventMonitor(
            debounce_interval=0.1,
            on_stable_callback=self.callback,
            enable_mouse_scroll=False,
            enable_keyboard=False,
        )
    
    def tearDown(self):
        """每个测试后的清理"""
        if self.monitor.running:
            self.monitor.stop()
    
    def test_concurrent_notify_activity(self):
        """测试并发notify_activity调用"""
        self.monitor.start()
        
        # 创建多个线程同时调用notify_activity
        threads = []
        for _ in range(10):
            thread = threading.Thread(target=self.monitor.notify_activity)
            thread.start()
            threads.append(thread)
        
        # 等待所有线程完成
        for thread in threads:
            thread.join()
        
        # 等待超时
        time.sleep(0.15)
        
        # 应该只触发一次回调
        self.callback.assert_called_once()
    
    def test_concurrent_start_stop(self):
        """测试并发启动和停止"""
        threads = []
        
        # 创建多个线程同时启动和停止
        for _ in range(5):
            start_thread = threading.Thread(target=self.monitor.start)
            stop_thread = threading.Thread(target=self.monitor.stop)
            threads.extend([start_thread, stop_thread])
        
        # 启动所有线程
        for thread in threads:
            thread.start()
        
        # 等待所有线程完成
        for thread in threads:
            thread.join()
        
        # 最终状态应该是停止的
        self.assertFalse(self.monitor.running)


class TestContextManager(unittest.TestCase):
    """测试上下文管理器"""
    
    def test_context_manager(self):
        """测试上下文管理器协议"""
        with ScreenEventMonitor(enable_mouse_scroll=False, enable_keyboard=False) as monitor:
            self.assertTrue(monitor.running)
        
        # 退出上下文后应该停止
        self.assertFalse(monitor.running)
    
    def test_context_manager_with_exception(self):
        """测试上下文管理器异常处理"""
        try:
            with ScreenEventMonitor(enable_mouse_scroll=False, enable_keyboard=False) as monitor:
                self.assertTrue(monitor.running)
                raise ValueError("Test exception")
        except ValueError:
            pass
        
        # 即使有异常，也应该停止
        self.assertFalse(monitor.running)


class TestIntegration(unittest.TestCase):
    """集成测试"""
    
    def test_full_workflow(self):
        """测试完整工作流程"""
        callback = Mock()
        
        with ScreenEventMonitor(
            debounce_interval=0.1,
            on_stable_callback=callback,
        ) as monitor:
            # 模拟用户操作
            monitor._on_scroll(100, 100, 0, 10)
            
            # 等待超时
            time.sleep(0.15)
            
            # 回调应该被调用
            self.assertEqual(callback.call_count, 1)
            
            # 再次操作
            monitor._on_key_press(keyboard.Key.space)
            
            # 等待超时
            time.sleep(0.15)
            
            # 回调应该被调用两次
            self.assertEqual(callback.call_count, 2)
        
        # 退出后应该停止
        self.assertFalse(monitor.running)
    
    def test_status_tracking(self):
        """测试状态跟踪"""
        with ScreenEventMonitor(
            debounce_interval=0.1,
            enable_mouse_scroll=False,
            enable_keyboard=False,
        ) as monitor:
            # 初始状态
            status = monitor.get_status()
            self.assertEqual(status['event_count'], 0)
            self.assertEqual(status['stable_trigger_count'], 0)
            
            # 多次操作
            for i in range(3):
                monitor.notify_activity()
                time.sleep(0.15)
            
            # 检查状态
            status = monitor.get_status()
            self.assertEqual(status['event_count'], 3)
            self.assertEqual(status['stable_trigger_count'], 3)



if __name__ == '__main__':
    unittest.main(verbosity=2)
