# main.py
import asyncio
import logging
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
    def __init__(self, config, trade_manager=None, position_manager=None, 
                 signal_processor=None, ai_analyzer=None):
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
        
        # 使用传入的组件或创建新的
        self.trade_manager = trade_manager
        self.position_manager = position_manager
        self.signal_processor = signal_processor
        self.ai_analyzer = ai_analyzer
        
        # Initialize bot first, then message handler
        self.message_handler = None  # Will be initialized after bot setup
        
        # Initialize channel manager
        self.channel_manager = ChannelManager(self.db, config, self.client)
        
        # Setup handlers
        self.setup_handlers()

    async def initialize(self):
        """Initialize bot components"""
        try:
            # Initialize application first
            await self.application.initialize()
            await self.application.start()
            await self.application.updater.start_polling()
            
            # Now initialize message handler with the initialized bot
            self.message_handler = MyMessageHandler(
                self.db, 
                self.client,
                self.application.bot,
                self.config,
                trade_manager=self.trade_manager,
                position_manager=self.position_manager,
                signal_processor=self.signal_processor,
                ai_analyzer=self.ai_analyzer
            )
            
            # Set up commands
            await BotCommands.setup_commands(self.application)
            logging.info("Bot commands initialized successfully")
            
            return True
            
        except Exception as e:
            logging.error(f"Error initializing bot: {e}")
            return False

    async def start(self):
        """Start the bot"""
        try:
            # Initialize bot and message handler
            await self.initialize()
            
            # Start Telethon client
            await self.client.start(phone=self.config.PHONE_NUMBER)
            
            # Register message handler
            @self.client.on(events.NewMessage)
            async def handle_new_message(event):
                if self.message_handler:  # Check if handler is initialized
                    await self.message_handler.handle_channel_message(event)
            
            print("Bot started successfully!")
            
            # Keep running
            await self.client.run_until_disconnected()
            
        except Exception as e:
            logging.error(f"Error starting bot: {e}")
            raise
        finally:
            await self.stop()

    async def stop(self):
        """Stop the bot"""
        try:
            if self.message_handler:
                await self.message_handler.cleanup()
            await self.application.stop()
            await self.client.disconnect()
            self.db.cleanup()
        except Exception as e:
            logging.error(f"Error stopping bot: {e}")
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

# main.py (部分更新)

async def main():
    """主函数"""
    # 设置日志
    logging.basicConfig(
        level=logging.INFO,
        format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
        handlers=[
            logging.StreamHandler(),
            logging.FileHandler('bot.log')
        ]
    )

    try:
        # 初始化配置
        config = Config()
        
        # 创建并启动机器人
        bot = ForwardBot(config)
        
        # 启动机器人
        await bot.start()
        
    except Exception as e:
        logging.error(f"Critical error: {e}")
        import traceback
        logging.error(f"Traceback:\n{traceback.format_exc()}")
        raise

if __name__ == "__main__":
    asyncio.run(main())