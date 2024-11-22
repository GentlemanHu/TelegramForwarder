import argparse
import asyncio
import logging
import json
from aiohttp import web
from pathlib import Path
from typing import Optional, Dict, Any
from main import ForwardBot, Config
from trade_processor.ai_analyzer import AIAnalyzer
from trade_processor.position_manager import PositionManager
from trade_processor.signal_processor import SignalProcessor
from trade_processor.trade_config import TradeConfig
from trade_processor.trade_manager import TradeManager

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
        self.initialized = False
        self.trade_config = None
        self.trade_manager = None
        self.ai_analyzer = None
        self.position_manager = None
        self.signal_processor = None

    async def initialize_components(self):
        """Initialize all trading components"""
        if self.initialized:
            return

        try:
            # Initialize trading system components
            self.trade_config = TradeConfig(
                meta_api_token=self.config.META_API_TOKEN,
                account_id=self.config.ACCOUNT_ID,
                openai_api_key=self.config.OPENAI_API_KEY,
                openai_base_url=self.config.OPENAI_BASE_URL,
                default_risk_percent=self.config.DEFAULT_RISK_PERCENT,
                max_layers=self.config.MAX_LAYERS,
                min_lot_size=self.config.MIN_LOT_SIZE
            )
            self.trade_manager = TradeManager(self.trade_config)
            self.ai_analyzer = AIAnalyzer(self.trade_config)
            self.position_manager = PositionManager(self.trade_manager)
            self.signal_processor = SignalProcessor(
                self.trade_config,
                self.ai_analyzer,
                self.position_manager
            )
            # Initialize trading system
            success = await self.trade_manager.initialize()
            if not success:
                logging.error("Failed to initialize trading system")
                return False

            # Wait for synchronization
            sync_success = await self.trade_manager.wait_synchronized()
            if not sync_success:
                logging.warning("Trading system initialized but synchronization timed out")
            else:
                logging.info("Trading system initialized and synchronized successfully")

            self.initialized = True
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

        bot = ForwardBot(self.config)
        await bot.start()

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

async def main():
    parser = argparse.ArgumentParser(description='Trading Bot Launcher')
    parser.add_argument('--mode', 
                       choices=['telegram', 'ui'], 
                       default='telegram',
                       help='Run mode: telegram (listen to Telegram) or ui (local UI interface)')

    args = parser.parse_args()
    launcher = AsyncBotLauncher()

    try:
        if args.mode == 'telegram':
            await launcher.run_telegram_mode()
        else:
            await launcher.run_ui_mode()
    except Exception as e:
        logging.error(f"Fatal error: {e}")
        raise

if __name__ == "__main__":
    logging.basicConfig(
        level=logging.INFO,
        format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
        handlers=[
            logging.StreamHandler(),
            logging.FileHandler('web_ui.log')
        ]
    )
    asyncio.run(main())