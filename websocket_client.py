import json
import asyncio
import logging
import websockets
import uuid
from datetime import datetime
from queue import Queue, Empty
import threading
import time
import concurrent.futures

class WebSocketClient:
    def __init__(self, server_url="ws://localhost:8765", reconnect_interval=5,
                 max_queue_size=10000, max_workers=2, connect_timeout=10):
        self.server_url = server_url
        self.reconnect_interval = reconnect_interval
        self.connect_timeout = connect_timeout
        self.websocket = None
        self.connected = False
        self.running = True
        self.message_queue = Queue(maxsize=max_queue_size)  # 限制队列大小防止内存泄漏
        self.logger = logging.getLogger("WebSocketClient")

        # 创建线程池用于处理消息发送
        self.thread_pool = concurrent.futures.ThreadPoolExecutor(max_workers=max_workers)

        # 创建事件循环
        self.loop = asyncio.new_event_loop()

        # 启动发送线程
        self.sender_thread = threading.Thread(target=self._sender_loop)
        self.sender_thread.daemon = True
        self.sender_thread.start()

        # 统计信息
        self.stats = {
            "messages_sent": 0,
            "messages_failed": 0,
            "last_success": None,
            "last_error": None,
            "reconnect_count": 0
        }

    def _sender_loop(self):
        """消息发送循环"""
        asyncio.set_event_loop(self.loop)

        # 初始化连接
        self.loop.run_until_complete(self._connect())

        while self.running:
            try:
                # 如果连接断开，尝试重连
                if not self.connected:
                    self.stats["reconnect_count"] += 1
                    # 使用指数退避策略计算重连间隔
                    backoff = min(60, self.reconnect_interval * (2 ** min(8, self.stats["reconnect_count"]-1)))
                    self.logger.info(f"将在 {backoff} 秒后尝试重连...")
                    time.sleep(backoff)
                    self.loop.run_until_complete(self._connect())
                    continue

                # 非阻塞地获取消息
                try:
                    # 批量处理消息，最多取出10条
                    messages = []
                    for _ in range(10):
                        if self.message_queue.empty():
                            break
                        messages.append(self.message_queue.get_nowait())

                    if messages:
                        # 异步发送所有消息
                        results = self.loop.run_until_complete(
                            asyncio.gather(*[self._send_message(msg) for msg in messages],
                                          return_exceptions=True)
                        )

                        # 处理结果
                        for i, result in enumerate(results):
                            if isinstance(result, Exception):
                                self.logger.error(f"发送消息时出错: {result}")
                                self.stats["messages_failed"] += 1
                                # 如果队列未满，将消息放回队列
                                try:
                                    self.message_queue.put_nowait(messages[i])
                                except:
                                    self.logger.warning("消息队列已满，丢弃消息")
                            elif result:
                                self.message_queue.task_done()
                                self.stats["messages_sent"] += 1
                            else:
                                # 发送失败但非异常，可能是连接断开
                                self.connected = False
                                # 将消息放回队列
                                try:
                                    self.message_queue.put_nowait(messages[i])
                                except:
                                    self.logger.warning("消息队列已满，丢弃消息")
                except Empty:
                    # 队列为空，正常情况
                    pass
                except Exception as e:
                    self.logger.error(f"处理消息队列时出错: {e}")

                # 短暂休眠，避免CPU占用过高
                time.sleep(0.01)  # 减少睡眠时间以提高响应速度
            except Exception as e:
                self.logger.error(f"发送线程错误: {e}")
                self.stats["last_error"] = str(e)
                self.connected = False

    async def _connect(self):
        """连接到WebSocket服务器"""
        try:
            # 设置连接超时
            self.websocket = await asyncio.wait_for(
                websockets.connect(self.server_url),
                timeout=self.connect_timeout
            )
            self.connected = True
            self.stats["reconnect_count"] = 0  # 重置重连计数

            # 发送客户端类型标识
            await self.websocket.send(json.dumps({
                "client_type": "forwarder",
                "version": "1.0",
                "timestamp": datetime.now().isoformat()
            }))

            self.logger.info(f"已连接到WebSocket服务器: {self.server_url}")
            return True
        except asyncio.TimeoutError:
            self.logger.error(f"连接到WebSocket服务器超时")
            self.connected = False
            return False
        except Exception as e:
            self.logger.error(f"连接到WebSocket服务器失败: {e}")
            self.connected = False
            return False

    async def _send_message(self, message):
        """发送消息到WebSocket服务器"""
        try:
            if not self.connected or not self.websocket:
                return False

            # 设置发送超时
            await asyncio.wait_for(
                self.websocket.send(json.dumps(message)),
                timeout=5  # 5秒超时
            )

            self.stats["last_success"] = datetime.now().isoformat()
            self.logger.debug(f"消息已发送: {message.get('id', 'unknown')}")
            return True
        except asyncio.TimeoutError:
            self.logger.warning(f"发送消息超时: {message.get('id', 'unknown')}")
            # 超时不一定意味着连接断开，所以不改变connected状态
            return False
        except websockets.exceptions.ConnectionClosed:
            self.logger.warning("WebSocket连接已关闭")
            self.connected = False
            return False
        except Exception as e:
            self.logger.error(f"发送消息时出错: {e}")
            self.stats["last_error"] = str(e)
            self.connected = False
            return False

    def send_message(self, message_data):
        """将消息添加到发送队列"""
        try:
            # 生成唯一消息ID
            message_id = str(uuid.uuid4())

            # 准备消息数据
            message = {
                "id": message_id,
                "timestamp": datetime.now().isoformat(),
                "type": "telegram_message",  # 标识消息类型
                **message_data
            }

            # 非阻塞地添加到发送队列
            try:
                self.message_queue.put_nowait(message)
                self.logger.debug(f"消息已加入队列: {message_id}")
                return True
            except:
                # 队列已满，丢弃最旧的消息并重试
                try:
                    # 丢弃一个消息腾出空间
                    old_message = self.message_queue.get_nowait()
                    self.logger.warning(f"队列已满，丢弃旧消息: {old_message.get('id', 'unknown')}")
                    self.message_queue.put_nowait(message)
                    self.logger.debug(f"消息已加入队列: {message_id}")
                    return True
                except:
                    self.logger.error("无法将消息添加到队列")
                    return False
        except Exception as e:
            self.logger.error(f"准备消息时出错: {e}")
            return False

    def get_stats(self):
        """获取统计信息"""
        stats = self.stats.copy()
        stats["queue_size"] = self.message_queue.qsize()
        stats["is_connected"] = self.connected
        return stats

    def close(self):
        """关闭WebSocket连接"""
        self.running = False

        # 等待发送线程结束
        if hasattr(self, 'sender_thread') and self.sender_thread.is_alive():
            self.sender_thread.join(timeout=2)

        # 关闭WebSocket连接
        if self.websocket:
            try:
                self.loop.run_until_complete(self.websocket.close())
            except:
                pass

        # 关闭线程池
        if hasattr(self, 'thread_pool'):
            self.thread_pool.shutdown(wait=False)

        # 关闭事件循环
        if hasattr(self, 'loop') and self.loop.is_running():
            self.loop.stop()

        self.logger.info("WebSocket客户端已关闭")
