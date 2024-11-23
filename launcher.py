# launcher.py
import argparse
import asyncio
import logging
import json
from aiohttp import web
from pathlib import Path
from typing import Optional, Dict, Any

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
        self.trade_config = TradeConfig(meta_api_token=self.config.META_API_TOKEN,account_id=self.config.ACCOUNT_ID,openai_api_key=self.config.OPENAI_API_KEY)
        self.initialized = False
        self.trade_manager = None
        self.position_manager = None
        self.signal_processor = None
        self.ai_analyzer = None
        self._bot = None

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
            # Initialize trading system components
            self.trade_manager = await self.get_trade_manager()
            
            if not self.ai_analyzer:
                self.ai_analyzer = AIAnalyzer(self.trade_config)
            
            if not self.position_manager:
                self.position_manager = PositionManager(self.trade_manager)
                await self.position_manager.initialize()
            
            if not self.signal_processor:
                self.signal_processor = SignalProcessor(
                    self.trade_config,
                    self.ai_analyzer,
                    self.position_manager
                )

            self.initialized = True
            logging.info("Trading components initialized successfully")
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
        if not await self.initialize_components():
            logging.error("Failed to initialize components for Telegram mode")
            return

        try:
            if not self._bot:
                # 创建 bot 实例时传入已初始化的组件
                self._bot = ForwardBot(
                    config=self.config,
                    trade_manager=self.trade_manager,
                    position_manager=self.position_manager,
                    signal_processor=self.signal_processor,
                    ai_analyzer=self.ai_analyzer
                )
            
            await self._bot.start()
            
        except Exception as e:
            logging.error(f"Error in Telegram mode: {e}")

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

    async def stop(self):
        """Stop all components"""
        try:
            if self.position_manager:
                await self.position_manager.cleanup()
            if self.trade_manager:
                await self.trade_manager.cleanup()
            if self._bot:
                await self._bot.stop()
        except Exception as e:
            logging.error(f"Error stopping components: {e}")

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