from telethon import TelegramClient, events
import os
import logging
import traceback
from typing import Optional, BinaryIO, Set
from tempfile import NamedTemporaryFile
import asyncio
from datetime import datetime, timedelta
from locales import get_text

from trade_processor import (
    SignalProcessor,
    TradeManager,
    AIAnalyzer,
    PositionManager,
    TradeConfig
)


class StandardizedEvent:
    """标准化的事件对象"""
    def __init__(self, message, chat=None):
        self.message = message
        self._chat = chat
        
    @property
    def text(self) -> str:
        """获取消息文本"""
        if hasattr(self.message, 'text'):
            return self.message.text
        return str(self.message)

    async def get_chat(self):
        """获取聊天对象"""
        return self._chat

    @classmethod
    async def from_telegram_event(cls, event):
        """从Telegram事件创建标准化事件"""
        chat = await event.get_chat()
        return cls(event.message, chat)

class MyMessageHandler:
    def __init__(self, db, client: TelegramClient, bot, config, 
                 trade_manager=None, position_manager=None, 
                 signal_processor=None, ai_analyzer=None):
        """初始化消息处理器
        
        Args:
            db: 数据库实例
            client: Telethon客户端
            bot: Telegram bot
            config: 配置对象
            trade_manager: 可选，已初始化的TradeManager实例
            position_manager: 可选，已初始化的PositionManager实例
            signal_processor: 可选，已初始化的SignalProcessor实例
            ai_analyzer: 可选，已初始化的AIAnalyzer实例
        """
        self.db = db
        self.client = client
        self.bot = bot
        self.config = config
        self.temp_files = {}
        self.cleanup_task = None
        self.signal_tasks: Set[asyncio.Task] = set()

        # 使用已初始化的组件或设置为None
        self.trade_manager = trade_manager
        self.position_manager = position_manager
        self.signal_processor = signal_processor
        self.ai_analyzer = ai_analyzer

        # 用于文件清理的锁
        self._cleanup_lock = asyncio.Lock()

    async def handle_channel_message(self, event):
        """处理频道消息"""
        try:
            # 创建标准化事件
            std_event = await StandardizedEvent.from_telegram_event(event)
            chat = await std_event.get_chat()
            
            channel_info = self.db.get_channel_info(chat.id)
            if not channel_info or not channel_info.get('is_active'):
                return

            # 处理交易信号
            if std_event.text and channel_info['channel_type'] == 'MONITOR':
                logging.info(f"Processing signal from channel {chat.id}")
                
                # 清理已完成的任务
                self.cleanup_finished_tasks()
                
                # 创建新的信号处理任务
                task = asyncio.create_task(
                    self.process_signal_task(std_event)
                )
                self.signal_tasks.add(task)
                task.add_done_callback(lambda t: self.signal_tasks.discard(t))

            # 处理转发消息
            forward_channels = self.db.get_all_forward_channels(chat.id)
            if forward_channels:
                for channel in forward_channels:
                    try:
                        await self.handle_forward_message(
                            std_event.message, 
                            chat,
                            channel
                        )
                    except Exception as e:
                        logging.error(f"Error forwarding to channel {channel.get('channel_id')}: {e}")

        except Exception as e:
            logging.error(f"Error handling channel message: {e}")
            if hasattr(e, '__dict__'):
                logging.error(f"Error details: {e.__dict__}")

    def cleanup_finished_tasks(self):
        """清理已完成的任务"""
        done_tasks = {task for task in self.signal_tasks if task.done()}
        for task in done_tasks:
            if task.exception():
                logging.error(f"Task failed with exception: {task.exception()}")
            self.signal_tasks.remove(task)

    async def handle_forward_message(self, message, from_chat, to_channel):
        """处理消息转发"""
        try:
            if not message or not from_chat or not to_channel:
                logging.error("Missing parameters for message forwarding")
                return

            channel_id = to_channel.get('channel_id')
            channel_id = int(f"-100{channel_id}")

            # 尝试直接转发
            try:
                await self.bot.forward_message(
                    chat_id=channel_id,
                    from_chat_id=from_chat.id,
                    message_id=message.id
                )
                logging.info(f"Successfully forwarded message to channel {channel_id}")
                return
            except Exception as e:
                logging.warning(f"Direct forward failed, trying alternative method: {e}")

            # 处理媒体消息
            if message.media:
                await self.handle_media_forward(message, from_chat, channel_id)
            # 处理文本消息
            elif message.text:
                await self.handle_text_forward(message, from_chat, channel_id)

        except Exception as e:
            logging.error(f"Error in handle_forward_message: {e}")

    async def handle_media_forward(self, message, from_chat, channel_id):
        """处理媒体消息转发"""
        try:
            media_type = self.get_media_type(message)
            if not media_type:
                return

            await self.handle_media_send(
                message=message,
                channel_id=channel_id,
                from_chat=from_chat,
                media_type=media_type
            )

        except Exception as e:
            logging.error(f"Error handling media forward: {e}")

    def get_media_type(self, message):
        """获取媒体类型"""
        if hasattr(message, 'photo') and message.photo:
            return 'photo'
        elif hasattr(message, 'video') and message.video:
            return 'video'
        elif hasattr(message, 'document') and message.document:
            return 'document'
        return None

    async def cleanup_file(self, file_path: str):
        """清理单个文件"""
        async with self._cleanup_lock:
            try:
                if file_path and os.path.exists(file_path):
                    os.remove(file_path)
                    self.temp_files.pop(file_path, None)
                    logging.info(f"Cleaned up file: {file_path}")
            except Exception as e:
                logging.error(f"Error cleaning up file {file_path}: {e}")

    async def start_cleanup_task(self):
        """启动清理任务"""
        if self.cleanup_task is None:
            self.cleanup_task = asyncio.create_task(self._cleanup_old_files())

    async def _cleanup_old_files(self):
        """定期清理过期的临时文件"""
        while True:
            try:
                current_time = datetime.now()
                async with self._cleanup_lock:
                    files_to_remove = [
                        file_path
                        for file_path, timestamp in self.temp_files.items()
                        if current_time - timestamp > timedelta(hours=1)
                    ]
                    
                    for file_path in files_to_remove:
                        await self.cleanup_file(file_path)

            except Exception as e:
                logging.error(f"Error in cleanup task: {e}")
            
            await asyncio.sleep(3600)  # 每小时运行一次

    async def cleanup(self):
        """清理资源"""
        try:
            # 取消清理任务
            if self.cleanup_task:
                self.cleanup_task.cancel()
                
            # 清理所有临时文件
            async with self._cleanup_lock:
                for file_path in list(self.temp_files.keys()):
                    await self.cleanup_file(file_path)
                    
            # 等待所有信号处理任务完成
            if self.signal_tasks:
                await asyncio.gather(*self.signal_tasks, return_exceptions=True)
                
        except Exception as e:
            logging.error(f"Error during cleanup: {e}")

    async def _send_message(self, chat_id: int, text: str, parse_mode: str = None):
        """统一的消息发送方法，支持UI模式
        
        Args:
            chat_id: 目标聊天ID
            text: 消息文本
            parse_mode: 消息解析模式（可选）
        """
        # 在UI模式下，只记录日志
        if not self.bot:
            logging.info(f"[UI Mode] Message to {chat_id}: {text}")
            return

        # 正常模式下发送消息
        try:
            await self.bot.send_message(
                chat_id=chat_id,
                text=text,
                parse_mode=parse_mode
            )
        except Exception as e:
            logging.error(f"Error sending message: {e}")

    async def send_trade_notification(self, message: str, parse_mode: str = 'HTML'):
        """Send trade notification to the bot owner
        
        Args:
            message: The notification message
            parse_mode: Message parse mode (HTML/Markdown)
        """
        await self._send_message(
            chat_id=self.config.OWNER_ID,
            text=message,
            parse_mode=parse_mode
        )

    async def handle_text_forward(self, message, from_chat, channel_id):
        """处理文本消息转发"""
        try:
            # 构建转发消息标题
            forward_title = await self._build_forward_title(from_chat, message)
            
            # 发送文本消息
            await self._send_message(
                chat_id=channel_id,
                text=forward_title
            )
            logging.info(f"Successfully forwarded text message to channel {channel_id}")
            
        except Exception as e:
            logging.error(f"Error in handle_text_forward: {e}")
            raise

    async def handle_media_send(self, message, channel_id, from_chat, media_type: str):
        """处理媒体发送"""
        tmp = None
        file_path = None
        
        try:
            tmp = NamedTemporaryFile(delete=False)
            file_path = await self.client.download_media(
                message.media, 
                file=tmp.name,
                progress_callback=self.download_progress_callback
            )
            
            if not file_path:
                raise Exception(get_text('en', 'media_download_failed'))

            # 构建转发消息标题
            forward_title = await self._build_forward_title(from_chat, message)
            
            # 记录临时文件
            self.temp_files[file_path] = datetime.now()
            
            if not os.path.exists(file_path):
                raise Exception(get_text('en', 'downloaded_file_not_found', 
                                       file_path=file_path))

            # 发送媒体文件
            with open(file_path, 'rb') as media_file:
                if media_type == 'photo':
                    await self.bot.send_photo(
                        chat_id=channel_id,
                        photo=media_file,
                        caption=forward_title
                    )
                elif media_type == 'video':
                    await self.bot.send_video(
                        chat_id=channel_id,
                        video=media_file,
                        caption=forward_title
                    )
                elif media_type == 'document':
                    await self.bot.send_document(
                        chat_id=channel_id,
                        document=media_file,
                        caption=forward_title
                    )

            logging.info(get_text('en', 'media_send_success', 
                                media_type=media_type, 
                                channel_id=channel_id))
            
            await self.cleanup_file(file_path)
            
        except Exception as e:
            logging.error(get_text('en', 'media_send_error', 
                                 media_type=media_type, 
                                 error=str(e)))
            if file_path:
                await self.cleanup_file(file_path)
            raise
        finally:
            if tmp and not tmp.closed:
                tmp.close()

    async def _build_forward_title(self, chat, message) -> str:
        """构建转发消息的标题"""
        try:
            channel_title = getattr(chat, 'title', 'Unknown Channel')
            chat_username = getattr(chat, 'username', None)
            chat_type = self._get_chat_type(chat)
            
            source_info = get_text('en', f'chat_type_{chat_type}')
            if chat_username:
                source_info = f"{source_info}\n@{chat_username}"

            return get_text('en', 'forwarded_message_template',
                title=channel_title,
                source_info=source_info,
                separator='_' * 30,
                content=getattr(message, 'text', '')
            )
        except Exception as e:
            logging.error(f"Error building forward title: {e}")
            return get_text('en', 'forwarded_from', channel="Unknown")

    def _get_chat_type(self, chat) -> str:
        """获取聊天类型"""
        if hasattr(chat, 'username') and chat.username:
            return 'public_channel'
        elif hasattr(chat, 'invite_link') and chat.invite_link:
            return 'private_channel_with_link'
        elif hasattr(chat, '_type'):
            return chat._type
        return 'private_channel'

    async def cleanup_old_files(self):
        """定期清理过期的临时文件"""
        while True:
            try:
                current_time = datetime.now()
                files_to_remove = []
                
                for file_path, timestamp in list(self.temp_files.items()):
                    if current_time - timestamp > timedelta(hours=1):
                        await self.cleanup_file(file_path)
                        files_to_remove.append(file_path)

                for file_path in files_to_remove:
                    self.temp_files.pop(file_path, None)

            except Exception as e:
                logging.error(get_text('en', 'cleanup_task_error', error=str(e)))
            
            await asyncio.sleep(3600)  # 每小时运行一次

    async def download_progress_callback(self, current, total):
        """下载进度回调"""
        if total:
            percentage = current * 100 / total
            if percentage % 20 == 0:  # 每20%记录一次
                logging.info(get_text('en', 'download_progress', percentage=percentage))

    async def initialize(self) -> bool:
        """初始化所有组件"""
        if self._initialized:
            return True
            
        try:
            # 启动清理任务
            await self.start_cleanup_task()
            
            self._initialized = True
            self.sync_complete.set()
            self.initialized_event.set()
            
            logging.info("Message handler initialized successfully")
            return True
            
        except Exception as e:
            logging.error(f"Error during initialization: {e}")
            return False


    async def wait_initialized(self, timeout: float = 300) -> bool:
        """等待初始化完成"""
        try:
            await asyncio.wait_for(
                self.initialized_event.wait(),
                timeout=timeout
            )
            return True
        except asyncio.TimeoutError:
            logging.error("Initialization timeout")
            return False;

    async def process_signal_task(self, event):
        """单独的信号处理任务"""
        try:
            await self.signal_processor.handle_channel_message(event)
        except Exception as e:
            logging.error(f"Error in signal processing task: {e}")
            logging.error(traceback.format_exc())
        finally:
            # 任务完成后从集合中移除
            for task in self.signal_tasks:
                if task.done():
                    self.signal_tasks.remove(task)

    def format_trade_notification(self, event_type: str, data: dict) -> str:
        """Format trade notification messages based on event type
        
        Args:
            event_type: Type of trade event (order_opened, order_closed, order_modified, etc)
            data: Dictionary containing event data
            
        Returns:
            Formatted notification message
        """
        try:
            templates = {
                'order_opened': (
                    "🟢 <b>New Position Opened</b>\n"
                    "Symbol: {symbol}\n"
                    "Type: {type}\n" 
                    "Volume: {volume}\n"
                    "Entry Price: {entry_price:.5f}\n"
                    "Stop Loss: {stop_loss:.5f}\n"
                    "Take Profit: {take_profit:.5f}"
                ),
                'order_closed': (
                    "🔴 <b>Position Closed</b>\n"
                    "Symbol: {symbol}\n"
                    "Type: {type}\n"
                    "Volume: {volume}\n"
                    "Entry Price: {entry_price:.5f}\n"
                    "Close Price: {close_price:.5f}\n"
                    "Profit: {profit:.2f} ({profit_pct:.2f}%)\n"
                    "Duration: {duration}"
                ),
                'order_modified': (
                    "🔄 <b>Position Modified</b>\n"
                    "Symbol: {symbol}\n"
                    "Type: {type}\n"
                    "Volume: {volume}\n"
                    "{changes}"
                ),
                'order_failed': (
                    "❌ <b>Order Failed</b>\n"
                    "Symbol: {symbol}\n"
                    "Type: {type}\n"
                    "Volume: {volume}\n"
                    "Error: {error}"
                ),
                'sl_modified': (
                    "🛡️ <b>Stop Loss Modified</b>\n"
                    "Symbol: {symbol}\n"
                    "Type: {type}\n"
                    "Old SL: {old_sl:.5f}\n"
                    "New SL: {new_sl:.5f}"
                ),
                'tp_modified': (
                    "🎯 <b>Take Profit Modified</b>\n"
                    "Symbol: {symbol}\n"
                    "Type: {type}\n"
                    "Old TP: {old_tp:.5f}\n"
                    "New TP: {new_tp:.5f}"
                ),
                'system_startup': (
                    "🚀 <b>Trading Bot Started</b>\n"
                    "Account: {account_id}\n"
                    "Balance: {balance:.2f}\n"
                    "Active Trades: {active_trades}\n"
                    "Server Time: {server_time}"
                ),
                'system_shutdown': (
                    "🔌 <b>Trading Bot Stopped</b>\n"
                    "Account: {account_id}\n"
                    "Final Balance: {balance:.2f}\n"
                    "Profit Today: {daily_profit:.2f}\n"
                    "Server Time: {server_time}"
                ),
                'system_error': (
                    "⚠️ <b>System Error</b>\n"
                    "Error Type: {error_type}\n"
                    "Message: {error_message}\n"
                    "Time: {error_time}"
                )
            }
            
            template = templates.get(event_type)
            if not template:
                return f"Unknown event type: {event_type}"
                
            # Handle optional fields with default values
            for key in ['stop_loss', 'take_profit', 'profit', 'profit_pct']:
                if key not in data:
                    data[key] = 0.0
                    
            # Format numbers to avoid scientific notation
            for key, value in data.items():
                if isinstance(value, float):
                    data[key] = float(f"{value:.5f}")
                    
            return template.format(**data)
            
        except Exception as e:
            logging.error(f"Error formatting trade notification: {e}")
            return f"Error formatting notification for {event_type}"
