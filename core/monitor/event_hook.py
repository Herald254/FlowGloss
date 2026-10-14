# e:\code\FlowGloss\core\monitor\event_hook.py
"""
基于pynput的全局事件监听器。

技术简介：
- 使用pynput库实现跨平台的全局键盘鼠标事件捕获
- 采用守护线程模式运行，确保不影响主线程性能
- 实现防抖动机制，计算用户停止操作的"稳定时长"

模块功能：
- 捕获系统级鼠标滚动事件（垂直滚动、水平滚动）
- 监听键盘按键操作（Enter、PageDown、空格等导航键）
- 计算事件间隔时间，判断用户阅读稳定状态
- 生成触发信号，启动后续视觉识别流程

整体作用：
系统的"打火机"，产生触发后续流程的原始信号，实现事件驱动的智能触发机制。

对外方法：
- ScreenEventMonitor(debounce_interval=1.0, on_stable_callback=None, trigger_keys=None, enable_mouse_scroll=True, enable_keyboard=True): 构造事件监听器实例
  - debounce_interval: 防抖间隔时间（秒），检测用户停止操作后等待的时间阈值
  - on_stable_callback: 稳定状态回调函数，当用户停止操作超过防抖间隔时调用
  - trigger_keys: 触发识别的按键集合，默认为导航键集合（空格、回车、翻页键等）
  - enable_mouse_scroll: 是否启用鼠标滚动监听，默认启用
  - enable_keyboard: 是否启用键盘按键监听，默认启用

- start(): 启动事件监听守护线程，初始化鼠标和键盘监听器
- stop(): 停止事件监听，清理所有监听器资源
- set_callback(callback): 动态设置稳定状态回调函数
  - callback: 新的回调函数，替换原有的稳定状态处理逻辑
- notify_activity(): 手动通知用户操作事件，重置防抖定时器
- trigger_now(): 立即触发稳定回调，跳过防抖机制，用于测试或手动触发
- get_status(): 获取监听器运行状态信息
  - 返回: 包含运行状态、事件计数、定时器状态等信息的字典
- running (property): 只读属性，检查监听器是否正在运行
- __enter__() / __exit__(): 支持上下文管理器协议，自动管理资源生命周期

联系：
触发后通过multiprocessing.Event或Queue通知主进程，主进程再通知Vision模块启动识别流程。

线程位置：
独立守护线程（Daemon Thread）。必须保持轻量，确保系统操作不掉帧，避免阻塞用户交互。
"""

import threading
import time
from typing import Callable, Optional, Set

from pynput import keyboard, mouse


from utils.logger import get_logger


logger = get_logger('core.monitor.event_hook')


class ScreenEventMonitor:
    """
    屏幕事件监听器，用于检测用户阅读稳定状态。
    
    实现防抖机制，当用户停止滚动或翻页操作超过指定时间后，
    触发回调通知系统进行截图和OCR识别。
    """
    
    DEFAULT_TRIGGER_KEYS: Set[keyboard.Key | keyboard.KeyCode] = {
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
    
    def __init__(
        self,
        debounce_interval: float = 1.0,
        on_stable_callback: Optional[Callable[[], None]] = None,
        trigger_keys: Optional[Set[keyboard.Key | keyboard.KeyCode]] = None,
        enable_mouse_scroll: bool = True,
        enable_keyboard: bool = True,
    ) -> None:
        """初始化屏幕事件监听器。
        
        Args:
            debounce_interval: 防抖间隔时间（秒），默认1.0秒
            on_stable_callback: 稳定状态回调函数
            trigger_keys: 触发识别的按键集合
            enable_mouse_scroll: 是否启用鼠标滚动监听
            enable_keyboard: 是否启用键盘按键监听
        """
        if debounce_interval <= 0:
            raise ValueError("debounce_interval 必须大于 0")
        
        self.debounce_interval = debounce_interval
        self.on_stable_callback = on_stable_callback
        self.trigger_keys: Set[keyboard.Key | keyboard.KeyCode] = set(
            trigger_keys or self.DEFAULT_TRIGGER_KEYS
        )
        self.enable_mouse_scroll = enable_mouse_scroll
        self.enable_keyboard = enable_keyboard
        
        self._lock = threading.RLock()
        self._timer: Optional[threading.Timer] = None
        self._timer_generation = 0
        self._running = False
        
        self._callback_running = False
        self._callback_pending = False
        self._excluded_regions: tuple[tuple[int, int, int, int], ...] = ()
        
        self.mouse_listener: Optional[mouse.Listener] = None
        self.keyboard_listener: Optional[keyboard.Listener] = None
        
        self.event_count = 0
        self.stable_trigger_count = 0
        
        logger.debug(f"ScreenEventMonitor初始化完成，防抖间隔: {debounce_interval}秒")
    
    @property
    def running(self) -> bool:
        """检查监听器是否正在运行"""
        with self._lock:
            return self._running
    
    def set_callback(self, callback: Optional[Callable[[], None]]) -> None:
        """设置稳定状态回调函数
        
        Args:
            callback: 回调函数，当检测到稳定状态时调用
        """
        with self._lock:
            self.on_stable_callback = callback
        logger.debug("回调函数已更新")
    
    def notify_activity(self) -> None:
        """手动通知一次用户正在操作
        
        这允许主框架把别的事件源也接进来，
        而不必依赖全局键鼠监听。
        """
        self._reset_timer()
        logger.debug("手动触发活动通知")

    def set_excluded_regions(self, regions) -> None:
        """更新不参与自动识别的物理屏幕区域 (left, top, right, bottom)。

        主线程只发布坐标快照，监听线程不访问 Qt 窗口对象。
        """
        with self._lock:
            self._excluded_regions = tuple(tuple(region) for region in regions)
    
    def trigger_now(self) -> None:
        """立即触发一次稳定回调，跳过防抖
        
        用于测试或手动触发场景。
        """
        self._dispatch_callback()
        logger.debug("立即触发稳定回调")
    
    def start(self) -> None:
        """启动事件监听
        
        启动鼠标和键盘监听器，开始检测用户操作。
        """
        with self._lock:
            if self._running:
                logger.warning("监听器已在运行中")
                return
            self._running = True
        
        if self.enable_mouse_scroll:
            self.mouse_listener = mouse.Listener(on_scroll=self._on_scroll)
            self.mouse_listener.daemon = True
            self.mouse_listener.start()
            logger.info("鼠标滚动监听已启动")
        
        if self.enable_keyboard:
            self.keyboard_listener = keyboard.Listener(on_press=self._on_key_press)
            self.keyboard_listener.daemon = True
            self.keyboard_listener.start()
            logger.info("键盘按键监听已启动")
        
        logger.info("ScreenEventMonitor已启动")
    
    def stop(self) -> None:
        """停止事件监听
        
        停止所有监听器并清理资源。
        """
        with self._lock:
            self._running = False
            self._callback_pending = False
            self._cancel_timer_locked()
        
        if self.mouse_listener is not None:
            self.mouse_listener.stop()
            self.mouse_listener = None
            logger.info("鼠标滚动监听已停止")
        
        if self.keyboard_listener is not None:
            self.keyboard_listener.stop()
            self.keyboard_listener = None
            logger.info("键盘按键监听已停止")
        
        logger.info(f"ScreenEventMonitor已停止，共处理{self.event_count}个事件，触发{self.stable_trigger_count}次稳定回调")
    
    def get_status(self) -> dict:
        """获取监听器状态信息
        
        Returns:
            包含运行状态、事件计数等信息的字典
        """
        with self._lock:
            return {
                "running": self._running,
                "event_count": self.event_count,
                "stable_trigger_count": self.stable_trigger_count,
                "timer_active": self._timer is not None,
                "callback_running": self._callback_running,
                "callback_pending": self._callback_pending,
                "mouse_enabled": self.enable_mouse_scroll,
                "keyboard_enabled": self.enable_keyboard,
            }
    
    def _reset_timer(self) -> None:
        """重置防抖定时器
        
        当检测到用户操作时调用，重置定时器。
        如果定时器到期，则认为用户已停止操作，触发稳定回调。
        """
        with self._lock:
            if not self._running:
                return
            
            self.event_count += 1
            self._timer_generation += 1
            generation = self._timer_generation
            self._cancel_timer_locked()
            
            self._timer = threading.Timer(
                self.debounce_interval,
                self._trigger_stable,
                args=(generation,),
            )
            self._timer.daemon = True
            self._timer.start()
    
    def _cancel_timer_locked(self) -> None:
        """取消定时器（需要在锁内调用）"""
        if self._timer is not None:
            self._timer.cancel()
            self._timer = None
    
    def _trigger_stable(self, generation: int) -> None:
        """触发稳定回调
        
        Args:
            generation: 定时器生成号，用于防止过期的定时器触发
        """
        with self._lock:
            if not self._running:
                return
            if generation != self._timer_generation:
                return
            
            self._timer = None
            self.stable_trigger_count += 1
        
        self._dispatch_callback()
    
    def _dispatch_callback(self) -> None:
        """分发回调
        
        使用独立线程执行回调，避免阻塞监听器。
        实现防重入保护，确保同一时间只有一个回调在执行。
        """
        with self._lock:
            if not self._running:
                return
            
            if self._callback_running:
                self._callback_pending = True
                return
            
            self._callback_running = True
            self._callback_pending = False
        
        worker = threading.Thread(
            target=self._callback_worker,
            name="flowgloss-event-callback",
            daemon=True,
        )
        worker.start()
    
    def _callback_worker(self) -> None:
        """回调工作线程
        
        在独立线程中执行回调函数，支持重入机制。
        """
        while True:
            with self._lock:
                if not self._running:
                    self._callback_running = False
                    self._callback_pending = False
                    return
                callback = self.on_stable_callback
            
            if callback is not None:
                try:
                    callback()
                    logger.debug("稳定回调执行成功")
                except Exception as e:
                    logger.error(f"稳定回调执行失败: {str(e)}", exc_info=True)
            
            with self._lock:
                if not self._running:
                    self._callback_running = False
                    self._callback_pending = False
                    return
                
                if self._callback_pending:
                    self._callback_pending = False
                    continue
                
                self._callback_running = False
                return
    
    def _on_scroll(self, x: int, y: int, dx: int, dy: int) -> None:
        """处理鼠标滚动事件
        
        Args:
            x: 鼠标X坐标
            y: 鼠标Y坐标
            dx: 水平滚动距离
            dy: 垂直滚动距离
        """
        if dx != 0 or dy != 0:
            with self._lock:
                if any(left <= x < right and top <= y < bottom for left, top, right, bottom in self._excluded_regions):
                    # 查看解释时也撤销刚才页面滚动留下的防抖任务。
                    self._timer_generation += 1
                    self._cancel_timer_locked()
                    self._callback_pending = False
                    return
            self._reset_timer()
            logger.debug(f"检测到滚动事件: dx={dx}, dy={dy}")
    
    def _on_key_press(self, key: keyboard.Key | keyboard.KeyCode) -> None:
        """处理键盘按键事件
        
        Args:
            key: 按下的键
        """
        if key in self.trigger_keys:
            self._reset_timer()
            logger.debug(f"检测到触发按键: {key}")
    
    def __enter__(self) -> "ScreenEventMonitor":
        """支持上下文管理器协议"""
        self.start()
        return self
    
    def __exit__(self, exc_type, exc_value, traceback) -> None:
        """支持上下文管理器协议"""
        self.stop()



if __name__ == "__main__":
    from utils.logger import setup_logging
    
    setup_logging({'level': 'DEBUG', 'console_output': True, 'file_output': False})
    
    def demo_callback() -> None:
        print("检测到屏幕操作已稳定，可以开始截图/OCR。")
    
    monitor = ScreenEventMonitor(on_stable_callback=demo_callback)
    monitor.start()
    print("事件监听已启动。滚轮或翻页后停顿约 1.0 秒会触发回调。按 Ctrl+C 退出。")
    
    try:
        while True:
            time.sleep(1.0)
    except KeyboardInterrupt:
        monitor.stop()
        print("事件监听已停止。")


# ============================================================================
# 使用示例
# ============================================================================

"""
ScreenEventMonitor 使用指南

ScreenEventMonitor 是一个基于pynput的全局事件监听器，用于检测用户阅读稳定状态。
当用户停止滚动或翻页操作超过指定时间后，触发回调通知系统进行截图和OCR识别。

基本用法：

1. 导入模块并创建监听器实例：
   from core.monitor.event_hook import ScreenEventMonitor
   from utils.logger import get_logger
   
   logger = get_logger('main')
   
   def on_stable():
       logger.info('用户操作已稳定，开始截图和OCR识别')
       # 触发截图和OCR流程
   
   monitor = ScreenEventMonitor(
       debounce_interval=1.0,  # 1秒防抖间隔
       on_stable_callback=on_stable
   )

2. 启动监听器：
   monitor.start()
   logger.info('事件监听器已启动')

3. 在程序退出时停止监听器：
   monitor.stop()
   logger.info('事件监听器已停止')

高级用法：

1. 使用上下文管理器（推荐）：
   with ScreenEventMonitor(on_stable_callback=on_stable) as monitor:
       # 监听器自动启动
       time.sleep(60)  # 运行60秒
       # 监听器自动停止

2. 自定义触发按键：
   from pynput import keyboard
   
   custom_keys = {
       keyboard.Key.space,
       keyboard.Key.page_down,
       keyboard.KeyCode.from_char('f'),  # 自定义按键F
   }
   
   monitor = ScreenEventMonitor(
       trigger_keys=custom_keys,
       on_stable_callback=on_stable
   )

3. 禁用部分事件监听：
   # 只监听键盘事件，禁用鼠标滚动
   monitor = ScreenEventMonitor(
       enable_mouse_scroll=False,
       enable_keyboard=True,
       on_stable_callback=on_stable
   )

4. 手动触发稳定状态：
   # 在某些特定条件下手动触发
   monitor.trigger_now()

5. 获取监听器状态：
   status = monitor.get_status()
   logger.info(f'事件计数: {status["event_count"]}')
   logger.info(f'稳定触发次数: {status["stable_trigger_count"]}')

6. 动态更新回调函数：
   def new_callback():
       logger.info('使用新的回调函数处理稳定状态')
   
   monitor.set_callback(new_callback)

配置参数说明：

- debounce_interval: 防抖间隔时间，建议设置为0.5-2.0秒
  - 过短：容易误触发，用户短暂停顿就被识别为稳定
  - 过长：响应延迟，用户需要等待较长时间才能触发识别

- trigger_keys: 触发按键集合，默认为常用导航键
  - 空格、回车、翻页键、方向键等
  - 可根据具体应用场景调整

- enable_mouse_scroll: 是否监听鼠标滚动
  - 对于阅读类应用，建议启用
  - 对于键盘操作为主的场景，可禁用

- enable_keyboard: 是否监听键盘按键
  - 大多数场景建议启用
  - 对于纯鼠标操作场景，可禁用

集成到主系统：

在main.py中的典型集成方式：

from core.monitor.event_hook import ScreenEventMonitor
from core.vision.ocr_engine import OCRProcessor
from multiprocessing import Queue

def main():
    # 创建进程间通信队列
    event_queue = Queue()
    
    # 创建OCR处理器
    ocr_processor = OCRProcessor()
    
    def on_stable_callback():
        # 触发OCR处理流程
        screenshot = capture_screen()
        text_blocks = ocr_processor.recognize(screenshot)
        
        # 将结果放入队列，供其他模块处理
        event_queue.put({
            'type': 'ocr_result',
            'timestamp': time.time(),
            'text_blocks': text_blocks
        })
    
    # 创建并启动事件监听器
    with ScreenEventMonitor(on_stable_callback=on_stable_callback) as monitor:
        logger.info('系统启动完成，开始监听用户操作')
        
        # 主循环
        while True:
            try:
                # 处理队列中的事件
                if not event_queue.empty():
                    event = event_queue.get()
                    process_event(event)
                
                time.sleep(0.1)  # 避免CPU占用过高
                
            except KeyboardInterrupt:
                logger.info('收到中断信号，正在关闭系统')
                break

注意事项：

1. 权限要求：
   - Windows: 需要管理员权限才能捕获全局事件
   - macOS: 需要在系统偏好设置中授权辅助功能权限
   - Linux: 需要相应的权限配置

2. 性能考虑：
   - 事件监听器运行在独立守护线程中，不影响主线程性能
   - 回调函数应保持轻量，避免阻塞事件处理

3. 错误处理：
   - 监听器启动失败时会抛出异常
   - 回调函数中的异常会被捕获并记录到日志

4. 测试建议：
   - 使用trigger_now()方法进行单元测试
   - 在实际环境中测试不同防抖间隔的效果

示例代码：

# 简单示例
monitor = ScreenEventMonitor(on_stable_callback=lambda: print('稳定状态触发'))
monitor.start()

# 完整示例
import time
from core.monitor.event_hook import ScreenEventMonitor
from utils.logger import get_logger

logger = get_logger('example')

def handle_stable_state():
    '''处理稳定状态'''
    logger.info('检测到用户阅读稳定，开始处理')
    # 执行截图、OCR、实体识别等操作

def main():
    # 创建监听器
    monitor = ScreenEventMonitor(
        debounce_interval=1.5,  # 1.5秒防抖
        on_stable_callback=handle_stable_state
    )
    
    try:
        # 启动监听
        monitor.start()
        logger.info('事件监听器已启动')
        
        # 主循环
        while True:
            status = monitor.get_status()
            logger.debug(f'监听器状态: {status}')
            time.sleep(10)
            
    except KeyboardInterrupt:
        logger.info('正在停止监听器...')
    finally:
        monitor.stop()
        logger.info('事件监听器已停止')

if __name__ == '__main__':
    main()
"""
