# main.py
import asyncio
import logging
import os
import signal
import sys
from telegram.ext import Application, CommandHandler
from telethon import TelegramClient, events
from database import Database
from channel_manager import ChannelManager
from config import Config
from message_handler import MyMessageHandler
from commands import BotCommands
from telegram import (
    Update,
    InlineKeyboardButton,
    InlineKeyboardMarkup,
    CallbackQuery
)
from telegram.ext import (
    ContextTypes,
    ConversationHandler,
    CallbackQueryHandler,
    MessageHandler,
    CommandHandler,
    filters
)
from locales import get_text

class ForwardBot:
    def __init__(self, config):
        self.config = config
        self.db = Database(config.DATABASE_NAME)

        # Initialize Telegram bot
        self.application = Application.builder().token(config.TELEGRAM_TOKEN).build()

        # Initialize Telethon client
        self.client = TelegramClient(
            config.SESSION_NAME,
            config.API_ID,
            config.API_HASH
        )

        # Initialize components
        self.channel_manager = ChannelManager(self.db, config, self.client)
        self.message_handler = MyMessageHandler(self.db, self.client, self.application.bot)

        # Setup handlers
        self.setup_handlers()

    def setup_handlers(self):
        """设置消息处理器"""
        # 命令处理器
        self.application.add_handler(CommandHandler("start", self.start_command))
        self.application.add_handler(CommandHandler("channels", self.channels_command))
        self.application.add_handler(CommandHandler("language", self.language_command))
        self.application.add_handler(CommandHandler("help", self.help_command))

        # 添加频道管理处理器
        for handler in self.channel_manager.get_handlers():
            self.application.add_handler(handler)

        # 添加错误处理器
        self.application.add_error_handler(self.error_handler)


    async def error_handler(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """处理错误"""
        logging.error(f"Update {update} caused error {context.error}")
        try:
            if update and update.effective_chat:
                lang = self.db.get_user_language(update.effective_chat.id)
                if update.callback_query:
                    await update.callback_query.message.reply_text(
                        get_text(lang, 'error_occurred')
                    )
                elif update.message:
                    await update.message.reply_text(
                        get_text(lang, 'error_occurred')
                    )
        except Exception as e:
            logging.error(f"Error in error handler: {e}")

    async def start_command(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """处理 /start 命令"""
        if update.effective_user.id != self.config.OWNER_ID:
            lang = self.db.get_user_language(update.effective_user.id)
            await update.message.reply_text(get_text(lang, 'unauthorized'))
            return

        lang = self.db.get_user_language(update.effective_user.id)
        await update.message.reply_text(get_text(lang, 'welcome'))

    async def help_command(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """处理 /help 命令"""
        if update.effective_user.id != self.config.OWNER_ID:
            lang = self.db.get_user_language(update.effective_user.id)
            await update.message.reply_text(get_text(lang, 'unauthorized'))
            return

        lang = self.db.get_user_language(update.effective_user.id)
        help_text = get_text(lang, 'help_message')

        try:
            await update.message.reply_text(
                help_text,
                parse_mode='Markdown',
                reply_markup=InlineKeyboardMarkup([[
                    InlineKeyboardButton(
                        get_text(lang, 'channel_management'),
                        callback_data="channel_management"
                    )
                ]])
            )
        except Exception as e:
            logging.error(f"Error sending help message: {e}")
            # 如果Markdown解析失败，尝试发送纯文本
            try:
                await update.message.reply_text(
                    help_text,
                    parse_mode=None,
                    reply_markup=InlineKeyboardMarkup([[
                        InlineKeyboardButton(
                            get_text(lang, 'channel_management'),
                            callback_data="channel_management"
                        )
                    ]])
                )
            except Exception as e2:
                logging.error(f"Error sending plain text help message: {e2}")
                await update.message.reply_text(
                    get_text(lang, 'error_occurred')
                )

    async def language_command(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """处理 /language 命令"""
        if update.effective_user.id != self.config.OWNER_ID:
            lang = self.db.get_user_language(update.effective_user.id)
            await update.message.reply_text(get_text(lang, 'unauthorized'))
            return

        await self.channel_manager.show_language_settings(update, context)

    async def channels_command(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """处理 /channels 命令"""
        if update.effective_user.id != self.config.OWNER_ID:
            lang = self.db.get_user_language(update.effective_user.id)
            await update.message.reply_text(get_text(lang, 'unauthorized'))
            return

        await self.channel_manager.show_channel_management(update, context)

    async def initialize(self):
        """初始化机器人配置"""
        try:
            # 设置命令列表
            await BotCommands.setup_commands(self.application)
            logging.info("Successfully initialized bot commands")
        except Exception as e:
            logging.error(f"Failed to initialize bot: {e}")
            raise

    async def start(self):
        """启动机器人"""
        try:
            # 初始化配置
            await self.initialize()

            # 启动 Telethon 客户端
            await self.client.start(phone=self.config.PHONE_NUMBER)

            # 启动清理任务
            await self.message_handler.start_cleanup_task()

            # 注册消息处理器
            @self.client.on(events.NewMessage)
            async def handle_new_message(event):
                await self.message_handler.handle_channel_message(event)

            # 注册消息编辑处理器
            @self.client.on(events.MessageEdited)
            async def handle_edited_message(event):
                await self.message_handler.handle_edited_message(event)

            # 注册消息删除处理器
            @self.client.on(events.MessageDeleted)
            async def handle_deleted_message(event):
                await self.message_handler.handle_deleted_message(event)

            # 启动机器人
            await self.application.initialize()
            await self.application.start()
            await self.application.updater.start_polling()

            print("Bot started successfully!")

            # 保持运行
            await self.client.run_until_disconnected()

        except Exception as e:
            logging.error(f"Error starting bot: {e}")
            raise
        finally:
            # 清理资源
            await self.stop()

    async def stop(self):
        """停止机器人"""
        try:
            logging.info("正在停止机器人...")

            # 取消清理任务
            if self.message_handler.cleanup_task:
                logging.info("取消清理任务")
                self.message_handler.cleanup_task.cancel()

            # 取消内存管理任务
            if self.message_handler.memory_management_task:
                logging.info("取消内存管理任务")
                self.message_handler.memory_management_task.cancel()

            # 清理所有剩余的临时文件
            logging.info(f"清理临时文件，数量: {len(self.message_handler.temp_files)}")
            for file_path in list(self.message_handler.temp_files.keys()):
                await self.message_handler.cleanup_file(file_path)

            # 释放内存
            logging.info("清理内存缓存")
            self.message_handler.media_cache.clear()
            self.message_handler.processed_media_groups.clear()

            # 关闭WebSocket客户端
            if hasattr(self.message_handler, 'enable_ws_forwarding') and self.message_handler.enable_ws_forwarding:
                try:
                    logging.info("关闭WebSocket客户端")
                    self.message_handler.ws_client.close()
                    logging.info("WebSocket客户端已关闭")
                except Exception as e:
                    logging.error(f"关闭WebSocket客户端时出错: {e}")

            # 主动请求垃圾回收
            import gc
            gc.collect()

            # 停止应用和客户端
            logging.info("停止Telegram应用")
            await self.application.stop()
            logging.info("断开Telethon客户端")
            await self.client.disconnect()
            logging.info("清理数据库连接")
            self.db.cleanup()

            logging.info("机器人已成功停止!")
            print("Bot stopped successfully!")
        except Exception as e:
            logging.error(f"Error stopping bot: {e}")
            import traceback
            logging.error(traceback.format_exc())

# 全局变量保存机器人实例，便于信号处理
_bot_instance = None

async def signal_handler():
    """处理系统信号，优雅地关闭机器人"""
    global _bot_instance
    if _bot_instance:
        logging.info("收到系统信号，正在优雅地关闭机器人...")
        await _bot_instance.stop()
        logging.info("机器人已安全关闭")
    sys.exit(0)

def setup_signal_handlers(loop):
    """设置系统信号处理器"""
    # 处理 SIGINT (Ctrl+C) 和 SIGTERM (系统终止信号)
    for sig in (signal.SIGINT, signal.SIGTERM):
        loop.add_signal_handler(
            sig,
            lambda: asyncio.create_task(signal_handler())
        )
    logging.info("系统信号处理器已设置")

async def main():
    """主函数"""
    global _bot_instance

    # 设置日志
    # 确保日志目录存在
    log_dir = "logs"
    os.makedirs(log_dir, exist_ok=True)

    # 生成日志文件路径
    log_file = os.path.join(log_dir, 'bot.log')

    logging.basicConfig(
        level=logging.INFO,
        format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
        handlers=[
            logging.StreamHandler(),
            logging.FileHandler(log_file)
        ]
    )

    # 设置信号处理器
    loop = asyncio.get_running_loop()
    setup_signal_handlers(loop)

    try:
        # 初始化配置
        config = Config()

        # 创建并启动机器人
        _bot_instance = ForwardBot(config)
        await _bot_instance.start()

    except Exception as e:
        logging.error(f"Critical error: {e}")
        import traceback
        logging.error(f"Traceback:\n{traceback.format_exc()}")
        raise

if __name__ == "__main__":
    asyncio.run(main())