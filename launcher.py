# launcher.py
import argparse
import asyncio
import logging
import json
from aiohttp import web
from pathlib import Path
from typing import Optional, Dict, Any
from datetime import datetime

# 本地导入
from config import Config
from main import ForwardBot
from trade_processor import (
    TradeManager,
    PositionManager,
    SignalProcessor,
    TradeConfig,
    AIAnalyzer
)


class SimulatedEvent:
    def __init__(self, message_text: str, channel_id: str):
        self.message = SimulatedMessage(message_text)
        self._chat = SimulatedChat(channel_id)
        
    async def get_chat(self):
        return self._chat

class SimulatedMessage:
    def __init__(self, text: str):
        self.text = text
        self.id = 1

class SimulatedChat:
    def __init__(self, channel_id: str):
        self.id = int(channel_id)
        self.title = "Simulated Channel"



class AsyncBotLauncher:
    def __init__(self):
        self.config = Config()
        self.trade_config = TradeConfig(
            meta_api_token=self.config.META_API_TOKEN,
            account_id=self.config.ACCOUNT_ID,
            openai_api_key=self.config.OPENAI_API_KEY
        )
        self.initialized = False
        self.trade_manager = None
        self.position_manager = None
        self.signal_processor = None
        self.ai_analyzer = None
        self._bot = None
        self.start_time = None
        self.run_mode = 'telegram'  # 默认为telegram模式

    async def get_trade_manager(self) -> TradeManager:
        """获取或创建 TradeManager 单例"""
        if not self.trade_manager:
            self.trade_manager = TradeManager(self.trade_config)
            await self.trade_manager.initialize()
            await self.trade_manager.wait_synchronized()
        return self.trade_manager

    async def initialize_components(self):
        """Initialize all trading components"""
        if self.initialized:
            return True

        try:
            # 1. 初始化交易管理器
            self.trade_manager = await self.get_trade_manager()
            if not self.trade_manager:
                raise Exception("Failed to initialize trade manager")
            
            # 2. 初始化AI分析器
            if not self.ai_analyzer:
                self.ai_analyzer = AIAnalyzer(self.trade_config)
            
            # 3. 初始化持仓管理器
            if not self.position_manager:
                self.position_manager = PositionManager(self.trade_manager)
                await self.position_manager.initialize()
            
            # 4. 初始化信号处理器
            if not self.signal_processor:
                self.signal_processor = SignalProcessor(
                    self.trade_config,
                    self.ai_analyzer,
                    self.position_manager
                )
            
            # 5. 根据模式初始化bot
            if self.run_mode == 'telegram' and not self._bot:
                self._bot = ForwardBot(
                    config=self.config,
                    trade_manager=self.trade_manager,
                    position_manager=self.position_manager,
                    signal_processor=self.signal_processor,
                    ai_analyzer=self.ai_analyzer
                )
                # 初始化bot
                await self._bot.initialize()
                # 启动bot
                await self._bot.start()

            self.initialized = True
            logging.info("All components initialized successfully")
            return True

        except Exception as e:
            logging.error(f"Error during initialization: {e}")
            return False

    async def handle_channel_message(self, request):
        """Handle incoming channel messages via HTTP"""
        try:
            data = await request.json()
            message = data.get('message')
            channel_id = data.get('channelId', '123')

            if not message:
                return web.Response(
                    status=400,
                    text=json.dumps({"error": "Message is required"}),
                    content_type='application/json'
                )

            # Create simulated event
            event = SimulatedEvent(message, channel_id)
            
            # Process signal
            await self.signal_processor.handle_channel_message(event)
            
            return web.Response(
                text=json.dumps({"status": "success"}),
                content_type='application/json'
            )
            
        except Exception as e:
            logging.error(f"Error processing message: {e}")
            return web.Response(
                status=500,
                text=json.dumps({"error": str(e)}),
                content_type='application/json'
            )

    async def handle_index(self, request):
        """Serve the index.html page"""
        return web.FileResponse('index.html')


    async def run_telegram_mode(self):
        """Run in Telegram mode"""
        self.run_mode = 'telegram'
        # 等待直到被中断
        try:
            while True:
                await asyncio.sleep(1)
        except asyncio.CancelledError:
            pass

    async def run_ui_mode(self):
        """Run in UI mode with async web server"""
        if not await self.initialize_components():
            logging.error("Failed to initialize components for UI mode")
            return

        # Create web application
        app = web.Application()
        app.router.add_get('/', self.handle_index)
        app.router.add_post('/api/channel/message', self.handle_channel_message)
        
        # Start the server
        runner = web.AppRunner(app)
        await runner.setup()
        site = web.TCPSite(runner, 'localhost', 8000)
        
        print("Server started at http://localhost:8000")
        await site.start()
        
        # Keep the server running
        try:
            while True:
                await asyncio.sleep(3600)
        except asyncio.CancelledError:
            await runner.cleanup()

    async def run_hft_mode(self):
        """Run in HFT mode"""
        if not await self.initialize_components():
            logging.error("Failed to initialize components for HFT mode")
            return
            
        try:
            # 启用HFT模式
            self.trade_config.hft.enabled = True
            
            # 启动HFT
            if not await self.trade_manager.start_hft_mode():
                logging.error("Failed to start HFT mode")
                return
                
            logging.info(f"HFT mode started with symbols: {self.trade_config.hft.symbols}")
            
            # 保持运行
            while True:
                await asyncio.sleep(60)  # 每分钟检查一次
                
        except Exception as e:
            logging.error(f"Error in HFT mode: {e}")
            if hasattr(e, '__dict__'):
                logging.error(f"Error details: {e.__dict__}")
            raise
        finally:
            # 确保停止HFT模式
            if self.trade_manager:
                await self.trade_manager.stop_hft_mode()

    async def start(self):
        """Start the bot"""
        try:
            self.start_time = datetime.now()
            
            # Initialize components
            if not await self.initialize_components():
                raise Exception("Failed to initialize components")

            # 只在telegram模式下发送启动通知
            if self.run_mode == 'telegram' and self._bot and self._bot.message_handler:
                #TODO - 手动重新设置message_handler到trademanager; 需要优化
                logging.info(f"Setting message_handler to trade_manager: {self._bot.message_handler}")
                self.trade_manager.message_handler = self._bot.message_handler
                
                account_info = {}
                active_trades = 0
                if self.trade_manager:
                    account_info = await self.trade_manager.get_account_info()
                    positions = await self.trade_manager.get_positions()
                    active_trades = len(positions) if positions else 0
                
                await self._bot.message_handler.send_trade_notification(
                    "🚀 Trading Bot Started\n\n"
                    f"💼 Account: {self.config.ACCOUNT_ID}\n"
                    f"💰 Balance: ${account_info.get('balance', 0) if account_info else 0:.2f}\n"
                    f"📊 Active Trades: {active_trades}\n"
                    f"⏰ Time: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}"
                )

            logging.info("Bot started successfully")

        except Exception as e:
            logging.error(f"Error starting bot: {e}")
            if self.run_mode == 'telegram' and self._bot and self._bot.message_handler:
                await self._bot.message_handler.send_trade_notification(
                    f"⚠️ System Error\n\n"
                    f"Type: Startup Error\n"
                    f"Message: {str(e)}\n"
                    f"Time: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}"
                )
            raise

    async def stop(self):
        """Stop the bot"""
        try:
            # 只在telegram模式下发送关闭通知
            if self.run_mode == 'telegram' and self._bot and self._bot.message_handler:
                account_info = {}
                daily_profit = 0
                if self.trade_manager:
                    account_info = await self.trade_manager.get_account_info()
                    # Calculate daily profit if start time is available
                    if self.start_time and account_info:
                        initial_balance = account_info.get('balance', 0) - account_info.get('profit', 0)
                        daily_profit = account_info.get('balance', 0) - initial_balance
                
                await self._bot.message_handler.send_trade_notification(
                    "🔄 Trading Bot Stopped\n\n"
                    f"💼 Account: {self.config.ACCOUNT_ID}\n"
                    f"💰 Final Balance: ${account_info.get('balance', 0) if account_info else 0:.2f}\n"
                    f"📈 Daily P/L: ${daily_profit:.2f}\n"
                    f"⏰ Time: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}"
                )

            # Cleanup components in reverse order
            if self._bot:
                await self._bot.stop()
            if self.position_manager:
                await self.position_manager.cleanup()
            if self.trade_manager:
                await self.trade_manager.cleanup()
            
            logging.info("Bot stopped successfully")

        except Exception as e:
            logging.error(f"Error stopping bot: {e}")
            if self.run_mode == 'telegram' and self._bot and self._bot.message_handler:
                await self._bot.message_handler.send_trade_notification(
                    f"⚠️ System Error\n\n"
                    f"Type: Shutdown Error\n"
                    f"Message: {str(e)}\n"
                    f"Time: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}"
                )
            raise

async def main():
    parser = argparse.ArgumentParser(description='Trading Bot Launcher')
    parser.add_argument('--mode', 
                       choices=['telegram', 'ui', 'hft'], 
                       default='telegram',
                       help='Run mode: telegram (listen to Telegram), ui (local UI interface), or hft (High Frequency Trading)')
    parser.add_argument('--symbols', type=str, help='Trading symbols for HFT mode (comma-separated)')
    
    args = parser.parse_args()
    launcher = AsyncBotLauncher()

    try:
        # 设置日志
        logging.basicConfig(
            level=logging.INFO,
            format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
            handlers=[
                logging.StreamHandler(),
                logging.FileHandler(f'{args.mode}.log')
            ]
        )

        await launcher.start()

        if args.mode == 'hft':
            # 如果指定了交易对，更新配置
            if args.symbols:
                launcher.trade_config.hft.symbols = args.symbols.split(',')
            await launcher.run_hft_mode()
        elif args.mode == 'telegram':
            await launcher.run_telegram_mode()
        else:
            await launcher.run_ui_mode()
            
    except Exception as e:
        logging.error(f"Fatal error: {e}")
        raise
    finally:
        await launcher.stop()

if __name__ == "__main__":
    asyncio.run(main())