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



class MyMessageHandler:
    def __init__(self, db, client: TelegramClient, bot, config):
        self.db = db
        self.client = client
        self.bot = bot
        self.temp_files = {}
        self.cleanup_task = None
        self.signal_tasks: Set[asyncio.Task] = set()
        self._initialized = False
        self.sync_complete = asyncio.Event()

        # 初始化交易系统组件
        self.trade_config = TradeConfig(
            meta_api_token=config.META_API_TOKEN,
            account_id=config.ACCOUNT_ID,
            openai_api_key=config.OPENAI_API_KEY,
            openai_base_url=config.OPENAI_BASE_URL,
            default_risk_percent=config.DEFAULT_RISK_PERCENT,
            max_layers=config.MAX_LAYERS,
            min_lot_size=config.MIN_LOT_SIZE
        )
        
        self.trade_manager = TradeManager(self.trade_config)
        self.ai_analyzer = AIAnalyzer(self.trade_config)
        self.initialized_event = asyncio.Event()

    async def initialize(self):
        """初始化所有组件"""
        if self._initialized:
            return True
            
        try:
            # 初始化交易管理器
            success = await self.trade_manager.initialize()
            if not success:
                logging.error("Failed to initialize trading manager")
                return False

            # 等待同步完成
            sync_success = await self.trade_manager.wait_synchronized()
            if not sync_success:
                logging.warning("Trading system initialized but synchronization timed out")
            else:
                logging.info("Trading system synchronized successfully")

            # 初始化 position manager
            self.position_manager = PositionManager(self.trade_manager)
            pos_success = await self.position_manager.initialize()
            if not pos_success:
                logging.error("Failed to initialize position manager")
                return False

            # 初始化 signal processor
            self.signal_processor = SignalProcessor(
                self.trade_config,
                self.ai_analyzer,
                self.position_manager
            )

            # 启动清理任务
            await self.start_cleanup_task()
            
            self._initialized = True
            self.initialized_event.set()
            self.sync_complete.set()
            
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
            return False

    async def handle_channel_message(self, event):
        """处理频道消息"""
        try:
            # 确保已初始化
            if not self._initialized:
                success = await self.initialize()
                if not success:
                    logging.error("Failed to initialize message handler")
                    return

            # 等待初始化完成
            if not await self.wait_initialized():
                logging.error("Timeout waiting for initialization")
                return

            chat = await event.get_chat()
            channel_info = self.db.get_channel_info(chat.id)
            
            if not channel_info or not channel_info.get('is_active'):
                return

            # 处理交易信号
            if event.message.text:
                if channel_info['channel_type'] == 'MONITOR':
                    logging.info(f"Processing signal from channel {chat.id}")
                    
                    # 清理已完成的任务
                    self.cleanup_finished_tasks()
                    
                    # 创建新的信号处理任务
                    task = asyncio.create_task(
                        self.signal_processor.handle_channel_message(event)
                    )
                    self.signal_tasks.add(task)
                    task.add_done_callback(lambda t: self.signal_tasks.discard(t))

            # 转发消息处理
            forward_channels = self.db.get_all_forward_channels(chat.id)
            if not forward_channels:
                return

            for channel in forward_channels:
                try:
                    await self.handle_forward_message(
                        event.message, 
                        chat, 
                        channel
                    )
                except Exception as e:
                    logging.error(f"Error forwarding to channel {channel.get('channel_id')}: {e}")

        except Exception as e:
            logging.error(f"Error handling channel message: {e}")
            if hasattr(e, '__dict__'):
                logging.error(f"Error details: {e.__dict__}")



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

    def cleanup_finished_tasks(self):
        """清理已完成的任务"""
        done_tasks = {task for task in self.signal_tasks if task.done()}
        for task in done_tasks:
            # 检查任务是否有异常
            if task.exception():
                logging.error(f"Task failed with exception: {task.exception()}")
            self.signal_tasks.remove(task)

    async def cleanup(self):
        """清理资源"""
        try:
            # 等待所有信号处理任务完成
            if self.signal_tasks:
                await asyncio.gather(*self.signal_tasks, return_exceptions=True)
            
            # 清理交易系统
            await self.trade_manager.cleanup()
            
            # 清理临时文件
            if self.cleanup_task:
                self.cleanup_task.cancel()
            for file_path in list(self.temp_files.keys()):
                await self.cleanup_file(file_path)
                
        except Exception as e:
            logging.error(f"Error during cleanup: {e}")





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

    async def handle_forward_message(self, message, from_chat, to_channel):
        """处理消息转发"""
        if not message or not from_chat or not to_channel:
            logging.error(get_text('en', 'missing_parameters'))
            return

        try:
            channel_id = to_channel.get('channel_id')
            channel_id = int(f"-100{channel_id}")
            if not channel_id:
                logging.error(get_text('en', 'invalid_channel_id'))
                return

            # 尝试直接转发
            try:
                await self.bot.forward_message(
                    chat_id=channel_id,
                    from_chat_id=from_chat.id,
                    message_id=message.id
                )
                logging.info(get_text('en', 'forward_success', channel_id=channel_id))
                return
            except Exception as e:
                logging.warning(get_text('en', 'direct_forward_failed', error=str(e)))

            # 处理媒体消息
            if message.media:
                if hasattr(message, 'photo') and message.photo:
                    await self.handle_media_send(message, channel_id, from_chat, 'photo')
                elif hasattr(message, 'video') and message.video:
                    await self.handle_media_send(message, channel_id, from_chat, 'video')
                elif hasattr(message, 'document') and message.document:
                    await self.handle_media_send(message, channel_id, from_chat, 'document')
            # 处理文本消息
            elif message.text:
                forward_title = await self._build_forward_title(from_chat, message)
                await self.bot.send_message(
                    chat_id=channel_id,
                    text=forward_title,
                    disable_web_page_preview=True
                )
                logging.info(get_text('en', 'text_send_success', channel_id=channel_id))

        except Exception as e:
            logging.error(get_text('en', 'forward_message_error', error=str(e)))
            raise

    async def cleanup_file(self, file_path: str):
        """清理单个文件"""
        try:
            if file_path and os.path.exists(file_path):
                os.remove(file_path)
                self.temp_files.pop(file_path, None)
                logging.info(get_text('en', 'file_cleanup_success', file_path=file_path))
        except Exception as e:
            logging.error(get_text('en', 'file_cleanup_error', 
                                 file_path=file_path, 
                                 error=str(e)))

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

    async def start_cleanup_task(self):
        """启动清理任务"""
        if self.cleanup_task is None:
            self.cleanup_task = asyncio.create_task(self.cleanup_old_files())

    async def download_progress_callback(self, current, total):
        """下载进度回调"""
        if total:
            percentage = current * 100 / total
            if percentage % 20 == 0:  # 每20%记录一次
                logging.info(get_text('en', 'download_progress', percentage=percentage))
