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
from datetime import datetime
import psutil
import platform

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
        
        # Initialize message handler
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
        
        # Set message handler to components
        if self.trade_manager:
            self.trade_manager.message_handler = self.message_handler
        
        # Initialize channel manager
        self.channel_manager = ChannelManager(self.db, config, self.client)
        
        # Setup handlers
        self.setup_handlers()

    async def initialize(self):
        """Initialize bot components"""
        try:
            # Set up commands
            await BotCommands.setup_commands(self.application)
            
            # Initialize message handler
            if not await self.message_handler.initialize():
                raise Exception("Failed to initialize message handler")
            
            logging.info("Bot components initialized successfully")
            return True
            
        except Exception as e:
            logging.error(f"Error initializing bot: {e}")
            return False

    async def get_system_info(self):
        """获取系统信息"""
        try:
            cpu_percent = psutil.cpu_percent(interval=1)
            memory = psutil.virtual_memory()
            disk = psutil.disk_usage('/')
            
            return {
                'cpu_percent': cpu_percent,
                'memory_used': memory.percent,
                'memory_available': memory.available / (1024 * 1024 * 1024),  # GB
                'disk_used': disk.percent,
                'disk_free': disk.free / (1024 * 1024 * 1024),  # GB
                'platform': platform.platform(),
                'python_version': platform.python_version()
            }
        except Exception as e:
            logging.error(f"Error getting system info: {e}")
            return {}

    async def get_account_info(self):
        """获取账户信息"""
        try:
            if not self.trade_manager:
                return {}
                
            account_info = await self.trade_manager.get_account_info()
            positions = await self.trade_manager.get_positions()
            
            return {
                'account': account_info,
                'positions': positions
            }
        except Exception as e:
            logging.error(f"Error getting account info: {e}")
            return {}

    async def start(self):
        """Start the bot"""
        try:
            # Initialize bot
            if not await self.initialize():
                raise Exception("Failed to initialize bot")
            
            # Start Telethon client
            await self.client.start(phone=self.config.PHONE_NUMBER)
            
            # Register message handler
            @self.client.on(events.NewMessage)
            async def handle_new_message(event):
                await self.message_handler.handle_channel_message(event)
            
            # Start bot
            await self.application.initialize()
            await self.application.start()
            await self.application.updater.start_polling()
            
            # 获取系统信息
            sys_info = await self.get_system_info()
            
            # 发送启动通知
            await self.message_handler.send_trade_notification(
                "🚀 Trading System Online\n\n"
                "💻 System Information:\n"
                f"CPU Usage: <code>{sys_info.get('cpu_percent', 'N/A')}%</code>\n"
                f"Memory Usage: <code>{sys_info.get('memory_used', 'N/A')}%</code>\n"
                f"Free Memory: <code>{sys_info.get('memory_available', 'N/A'):.1f} GB</code>\n"
                f"Disk Usage: <code>{sys_info.get('disk_used', 'N/A')}%</code>\n"
                f"Free Disk: <code>{sys_info.get('disk_free', 'N/A'):.1f} GB</code>\n"
                f"Platform: <code>{sys_info.get('platform', 'N/A')}</code>\n"
                f"Python: <code>{sys_info.get('python_version', 'N/A')}</code>\n\n"
                f"⏰ Start Time: <code>{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}</code>"
            )
            
            # 等待账户连接就绪并获取账户信息
            if self.trade_manager and self.trade_manager.connection:
                # 等待连接就绪
                await self.trade_manager.connection.connect()
                await self.trade_manager.connection.wait_synchronized()
                
                # 获取并发送账户信息
                await self._send_account_status()
            
            logging.info("Bot started successfully!")
            
            # Keep running
            await self.client.run_until_disconnected()
            
        except Exception as e:
            logging.error(f"Error starting bot: {e}")
            raise
        finally:
            await self.stop()

    async def _send_account_status(self):
        """发送账户状态信息"""
        try:
            if not self.trade_manager or not self.trade_manager.connection:
                logging.warning("Trade manager or connection not available")
                return
                
            # 获取账户信息
            terminal_state = self.trade_manager.connection.terminal_state
            if not terminal_state:
                logging.warning("Terminal state not available")
                return
                
            account = terminal_state.account_information
            positions = terminal_state.positions
            
            if not account:
                logging.warning("Account information not available")
                return
                
            # 格式化账户信息
            account_str = (
                "💰 Account Information:\n"
                f"Balance: <code>${account.get('balance', 0):.2f}</code>\n"
                f"Equity: <code>${account.get('equity', 0):.2f}</code>\n"
                f"Margin Level: <code>{account.get('marginLevel', 0):.2f}%</code>\n"
                f"Free Margin: <code>${account.get('freeMargin', 0):.2f}</code>"
            )
            
            # 格式化持仓信息
            positions_str = "No open positions"
            if positions:
                positions_str = "📊 Current Positions:\n" + "\n".join([
                    f"• {p.get('symbol', 'Unknown')}: {p.get('type', 'Unknown')} "
                    f"{p.get('volume', 0)} lots @ {p.get('openPrice', 0):.5f} "
                    f"(P/L: ${p.get('profit', 0):.2f})"
                    for p in positions
                ])
            
            # 发送账户状态通知
            await self.message_handler.send_trade_notification(
                f"{account_str}\n\n{positions_str}",
                parse_mode='HTML'
            )
            
        except Exception as e:
            logging.error(f"Error sending account status: {e}")
            if hasattr(e, '__dict__'):
                logging.error(f"Error details: {e.__dict__}")

    async def stop(self):
        """Stop the bot"""
        try:
            # Send shutdown notification
            if self.message_handler:
                try:
                    await self.message_handler.send_trade_notification(
                        "� Trading System Offline\n\n"
                        f"⏰ Stop Time: <code>{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}</code>"
                    )
                except:
                    pass
                
            # Stop components
            if hasattr(self.application, 'stop'):
                await self.application.stop()
            if hasattr(self.client, 'disconnect'):
                await self.client.disconnect()
            
        except Exception as e:
            logging.error(f"Error stopping bot: {e}")

    def setup_handlers(self):
        """设置消息处理器"""
        # 命令处理器
        self.application.add_handler(CommandHandler("start", self.start_command))
        self.application.add_handler(CommandHandler("help", self.help_command))
        self.application.add_handler(CommandHandler("language", self.language_command))
        self.application.add_handler(CommandHandler("channels", self.channels_command))
        self.application.add_handler(CommandHandler("positions", self.positions_command))
        self.application.add_handler(CommandHandler("breakeven", self.breakeven_command))
        self.application.add_handler(CommandHandler("closeall", self.closeall_command))
        
        # 添加closeall回调处理器
        self.application.add_handler(CallbackQueryHandler(self.closeall_callback, pattern='^closeall_'))
        
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

    async def positions_command(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """查询所有持仓信息汇总"""
        try:
            lang = self.db.get_user_language(update.effective_user.id)
            
            if not self.trade_manager:
                await update.message.reply_text(get_text(lang, 'trade_manager_error'))
                return
                
            positions = await self.trade_manager.get_positions()
            if not positions:
                await update.message.reply_text(get_text(lang, 'no_positions'))
                return
                
            # 计算总体统计信息
            total_profit = sum(float(p.get('profit', 0)) for p in positions)
            total_volume = sum(float(p.get('volume', 0)) for p in positions)
            
            # 构建详细信息
            details = []
            for pos in positions:
                profit = float(pos.get('profit', 0))
                emoji = "🟢" if profit >= 0 else "🔴"
                details.append(get_text(
                    lang, 'position_info',
                    emoji=emoji,
                    symbol=pos['symbol'],
                    volume=pos['volume'],
                    price=float(pos['openPrice']),
                    profit=profit,
                    type=pos.get('type', 'Unknown')
                ))
            
            # 构建消息
            message = (
                f"<b>{get_text(lang, 'positions_title')}</b>\n\n"
                f"{get_text(lang, 'total_positions', count=len(positions))}\n"
                f"{get_text(lang, 'total_volume', volume=total_volume)}\n"
                f"{get_text(lang, 'total_pl', profit=total_profit)}\n\n"
                f"<b>{get_text(lang, 'position_details')}</b>\n" + 
                "\n".join(details)
            )
            
            await update.message.reply_text(message, parse_mode='HTML')
            
        except Exception as e:
            logging.error(f"Error in positions command: {e}")
            await update.message.reply_text(f"❌ Error: {str(e)}")

    async def breakeven_command(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """一键设置所有盈利仓位的sl到入场价"""
        try:
            lang = self.db.get_user_language(update.effective_user.id)
            
            if not self.trade_manager:
                await update.message.reply_text(get_text(lang, 'trade_manager_error'))
                return
        
            positions = await self.trade_manager.get_positions()
            if not positions:
                await update.message.reply_text(get_text(lang, 'no_positions'))
                return
        
            # 筛选盈利仓位并设置止损
            modified_count = 0
            for pos in positions:
                try:
                    # 获取当前价格
                    terminal_state = self.trade_manager.connection.terminal_state
                    if not terminal_state:
                        logging.error("Terminal state not available")
                        continue
                    
                    price_info = terminal_state.price(pos['symbol'])
                    if not price_info:
                        logging.error(f"Price info not available for {pos['symbol']}")
                        continue
                    
                    current_price = price_info['ask'] if pos['type'] == 'buy' else price_info['bid']
                    entry_price = float(pos['openPrice'])
                    is_long = pos['type'] == 'buy'
                
                    # 检查是否盈利
                    is_profitable = (is_long and current_price > entry_price) or (not is_long and current_price < entry_price)
                
                    if is_profitable:
                        # 获取当前止损
                        current_sl = pos.get('stopLoss')
                    
                        # 设置止损到入场价
                        success = await self.trade_manager.modify_position_sl(
                            pos['id'],
                            entry_price
                        )
                    
                        if success:
                            modified_count += 1
                            logging.info(f"Position {pos['id']} breakeven set:"
                                       f"\n  Symbol: {pos['symbol']}"
                                       f"\n  Type: {pos['type']}"
                                       f"\n  Entry: {entry_price}"
                                       f"\n  Current: {current_price}"
                                       f"\n  Old SL: {current_sl}"
                                       f"\n  New SL: {entry_price}"
                                       f"\n  Volume: {pos.get('volume')}"
                                       f"\n  Profit: {pos.get('profit')}"
                                       f"\n  Profit %: {pos.get('profitPercent')}%")
                        else:
                            logging.error(f"Failed to modify position {pos['id']}:"
                                        f"\n  Symbol: {pos['symbol']}"
                                        f"\n  Type: {pos['type']}"
                                        f"\n  Entry: {entry_price}"
                                        f"\n  Current: {current_price}"
                                        f"\n  Old SL: {current_sl}")
                    else:
                        logging.info(f"Position {pos['id']} not profitable:"
                                   f"\n  Symbol: {pos['symbol']}"
                                   f"\n  Type: {pos['type']}"
                                   f"\n  Entry: {entry_price}"
                                   f"\n  Current: {current_price}"
                                   f"\n  Profit: {pos.get('profit')}"
                                   f"\n  Profit %: {pos.get('profitPercent')}%")
                    
                except Exception as e:
                    logging.error(f"Error processing position {pos['id']}: {e}")
        
            await update.message.reply_text(
                get_text(lang, 'breakeven_success', count=modified_count)
            )
        
        except Exception as e:
            logging.error(f"Error in breakeven command: {e}")
            await update.message.reply_text(f"❌ Error: {str(e)}")

    async def closeall_command(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """关闭所有持仓"""
        try:
            lang = self.db.get_user_language(update.effective_user.id)
            
            if not self.trade_manager:
                await update.message.reply_text(get_text(lang, 'trade_manager_error'))
                return
                
            # 添加确认按钮
            keyboard = [
                [
                    InlineKeyboardButton("Yes ✅", callback_data='closeall_confirm'),
                    InlineKeyboardButton("No ❌", callback_data='closeall_cancel')
                ]
            ]
            reply_markup = InlineKeyboardMarkup(keyboard)
            
            await update.message.reply_text(
                get_text(lang, 'closeall_confirm'),
                reply_markup=reply_markup
            )
            
        except Exception as e:
            logging.error(f"Error in closeall command: {e}")
            await update.message.reply_text(f"❌ Error: {str(e)}")

    async def closeall_callback(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """处理关闭所有持仓的确认回调"""
        query = update.callback_query
        await query.answer()
        
        lang = self.db.get_user_language(query.from_user.id)
        
        if query.data == 'closeall_cancel':
            await query.edit_message_text(get_text(lang, 'closeall_cancelled'))
            return
            
        if query.data == 'closeall_confirm':
            try:
                positions = await self.trade_manager.get_positions()
                if not positions:
                    await query.edit_message_text(get_text(lang, 'no_positions'))
                    return
                    
                closed_count = 0
                for pos in positions:
                    try:
                        await self.trade_manager.close_position(pos['id'])
                        closed_count += 1
                    except Exception as e:
                        logging.error(f"Error closing position {pos['id']}: {e}")
                
                await query.edit_message_text(
                    get_text(lang, 'closeall_success', count=closed_count)
                )
                
            except Exception as e:
                logging.error(f"Error in closeall callback: {e}")
                await query.edit_message_text(f"❌ Error: {str(e)}")

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
        
        # 创建交易管理器
        trade_config = TradeConfig(
            meta_api_token=config.META_API_TOKEN,
            account_id=config.ACCOUNT_ID
        )
        trade_manager = TradeManager(trade_config)
        
        # 创建仓位管理器
        position_manager = PositionManager(trade_manager)
        
        # 创建信号处理器
        signal_processor = SignalProcessor(trade_manager, position_manager)
        
        # 创建AI分析器
        ai_analyzer = AIAnalyzer(config.OPENAI_API_KEY)
        
        # 创建并启动机器人
        bot = ForwardBot(
            config,
            trade_manager=trade_manager,
            position_manager=position_manager,
            signal_processor=signal_processor,
            ai_analyzer=ai_analyzer
        )
        
        # 启动机器人
        await bot.start()
        
    except Exception as e:
        logging.error(f"Critical error: {e}")
        import traceback
        logging.error(f"Traceback:\n{traceback.format_exc()}")
        raise

if __name__ == "__main__":
    asyncio.run(main())