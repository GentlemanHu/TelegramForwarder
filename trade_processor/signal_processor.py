from typing import Optional, Dict, Any, List
import logging
import asyncio
from datetime import datetime


class SignalProcessor:
    def __init__(self, config: 'TradeConfig', 
                 ai_analyzer: 'AIAnalyzer',
                 position_manager: 'PositionManager'):
        self.config = config
        self.ai_analyzer = ai_analyzer
        self.position_manager = position_manager
        self.processing_lock = asyncio.Lock()
        self.active_signals: Dict[str, Dict[str, Any]] = {}

    async def handle_channel_message(self, event):
        """处理频道消息入口方法"""
        try:
            message = event.message
            if not message or not message.text:
                return

            # 处理消息
            await self.process_message(message.text)
            
        except Exception as e:
            logging.error(f"Error handling channel message: {e}")
            if hasattr(e, '__dict__'):
                logging.error(f"Error details: {e.__dict__}")

    async def process_message(self, message: str):
        """处理频道消息"""
        async with self.processing_lock:
            try:
                # 使用AI分析信号
                signal = await self.ai_analyzer.analyze_signal(message)
                if not signal:
                    logging.info("No valid trading signal detected in message")
                    return

                logging.info(f"Detected signal type: {signal.get('type')}")
                logging.info(f"Signal details: {signal}")

                if signal['type'] == 'entry':
                    await self._handle_entry_signal(signal)
                elif signal['type'] == 'modify':
                    await self._handle_modify_signal(signal)
                elif signal['type'] == 'exit':
                    await self._handle_exit_signal(signal)
                else:
                    logging.warning(f"Unknown signal type: {signal['type']}")

            except Exception as e:
                logging.error(f"Error processing message: {e}")
                logging.error(f"Original message: {message}")
                if hasattr(e, '__dict__'):
                    logging.error(f"Error details: {e.__dict__}")

    async def _handle_entry_signal(self, signal: Dict[str, Any]):
        """处理入场信号"""
        try:
            if signal['layers']['enabled']:
                # 使用分层交易
                round_id = await self.position_manager.create_layered_positions(signal)
            else:
                # 单次交易
                round_id = await self.position_manager.create_single_position(signal)

            if round_id:
                # 记录信号信息
                self.active_signals[round_id] = {
                    'signal': signal,
                    'timestamp': datetime.now().isoformat(),
                    'status': 'active'
                }
                logging.info(f"Created new trading round: {round_id}")
            else:
                logging.error("Failed to create positions")

        except Exception as e:
            logging.error(f"Error handling entry signal: {e}")
            if hasattr(e, '__dict__'):
                logging.error(f"Error details: {e.__dict__}")

    async def _handle_modify_signal(self, signal: Dict[str, Any]):
        """处理修改信号"""
        try:
            active_rounds = self.position_manager.get_active_rounds()
            
            for round_id in active_rounds:
                original_signal = self.active_signals.get(round_id, {}).get('signal')
                if not original_signal:
                    continue
                
                # 验证是否是同一个交易品种
                if original_signal.get('symbol') == signal.get('symbol'):
                    await self.position_manager.modify_positions(round_id, signal)
                    logging.info(f"Modified positions for round: {round_id}")
                    
                    # 更新信号状态
                    self.active_signals[round_id]['last_modification'] = {
                        'signal': signal,
                        'timestamp': datetime.now().isoformat()
                    }

        except Exception as e:
            logging.error(f"Error handling modify signal: {e}")
            if hasattr(e, '__dict__'):
                logging.error(f"Error details: {e.__dict__}")

    async def _handle_exit_signal(self, signal: Dict[str, Any]):
        """处理出场信号"""
        try:
            active_rounds = self.position_manager.get_active_rounds()
            
            for round_id in active_rounds:
                original_signal = self.active_signals.get(round_id, {}).get('signal')
                if not original_signal:
                    continue
                
                if original_signal.get('symbol') == signal.get('symbol'):
                    close_type = signal.get('close_type', 'all')
                    success = await self.position_manager.close_positions(round_id, close_type)
                    
                    if success:
                        logging.info(f"Closed positions for round: {round_id}")
                        
                        if close_type == 'all':
                            self.active_signals[round_id]['status'] = 'closed'
                            self.active_signals[round_id]['close_signal'] = {
                                'signal': signal,
                                'timestamp': datetime.now().isoformat()
                            }
                    else:
                        logging.error(f"Failed to close positions for round: {round_id}")

        except Exception as e:
            logging.error(f"Error handling exit signal: {e}")
            if hasattr(e, '__dict__'):
                logging.error(f"Error details: {e.__dict__}")