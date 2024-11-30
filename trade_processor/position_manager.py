from typing import Dict, List, Optional, Any
import logging
import asyncio
from datetime import datetime
from .position import Position, PositionStatus 
from .round_manager import RoundManager, TradeRound, RoundStatus, TPLevel  # 添加这行
from .layer_manager import SmartLayerManager, LayerDistributionType
from .trade_manager import TradeManager


class PositionManager:
    def __init__(self, trade_manager: TradeManager):
        self.trade_manager = trade_manager
        self.layer_manager = SmartLayerManager(trade_manager)
        self.round_manager = RoundManager(trade_manager.connection, trade_manager)
        self._initialized = False
        self._message_handler = None  

    @property
    def message_handler(self):
        return self.trade_manager.message_handler if self.trade_manager else None

    @message_handler.setter
    def message_handler(self, value):
        self._message_handler = value

    async def _send_notification(self, event_type: str, data: dict):
        if not self.message_handler:
            logging.info("Using trade_manager's message_handler for notification")
            if self.trade_manager and self.trade_manager.message_handler:
                await self.trade_manager._send_notification(event_type, data)
            else:
                logging.error("No message handler available")
            return

        try:
            notification_msg = self.message_handler.format_trade_notification(
                event_type,
                data
            )
            await self.message_handler.send_trade_notification(notification_msg)
        except Exception as e:
            logging.error(f"Error sending notification: {e}", exc_info=True)

    async def initialize(self):
        """Initialize position manager and all sub-components"""
        try:
            if self._initialized:
                return True
            
            logging.info("Starting position manager initialization...")
            
            # Initialize trade manager first
            if not self.trade_manager._initialized:
                logging.info("Initializing trade manager...")
                success = await self.trade_manager.initialize()
                if not success:
                    logging.error("Failed to initialize trade manager")
                    raise Exception("Failed to initialize trade manager")
                logging.info("Trade manager initialized successfully")

            # Wait for trade manager to be fully ready
            if not self.trade_manager.sync_complete.is_set():
                logging.info("Waiting for trade manager synchronization...")
                success = await self.trade_manager.wait_synchronized()
                if not success:
                    logging.error("Trade manager synchronization failed")
                    raise Exception("Trade manager synchronization failed")
                logging.info("Trade manager synchronized successfully")

            # Initialize round manager
            if not self.round_manager._initialized:
                logging.info("Initializing round manager...")
                success = await self.round_manager.initialize()
                if not success:
                    logging.error("Failed to initialize round manager")
                    raise Exception("Failed to initialize round manager")
                logging.info("Round manager initialized successfully")

            self._initialized = True
            logging.info("Position manager initialization completed successfully")
            return True
        
        except Exception as e:
            logging.error(f"Error initializing position manager: {e}")
            return False


    async def create_layered_positions(self, signal: Dict[str, Any]) -> Optional[str]:
        """创建分层仓位"""
        try:
            # 获取账户信息用于仓位计算
            terminal_state = self.trade_manager.connection.terminal_state
            account_info = terminal_state.account_information

            # 创建 LayerConfig
            config = LayerConfig(
                entry_price=signal.get('entry_price') or (
                    terminal_state.price(signal['symbol'])['ask' 
                    if signal['action'] == 'buy' else 'bid']
                ),
                stop_loss=signal.get('stop_loss'),
                base_tp=signal['take_profits'][0] if signal.get('take_profits') else None,
                risk_points=abs(signal.get('entry_price', 0) - signal.get('stop_loss', 0)),
                num_layers=signal['layers'].get('count', 3),
                distribution_type=LayerDistributionType[
                    signal['layers'].get('distribution', 'EQUAL').upper()
                ],
                volume_profile={'base_volume': 0.01}  # 可以根据需要调整
            )

            # 获取市场数据
            market_data = {
                'account_size': float(account_info['balance']),
                'risk_percent': 0.02,  # 可以从配置或信号中获取
                'momentum': 0,  # 可以从市场分析中获取
                'volatility': 0.001  # 可以从市场分析中获取
            }

            # 计算智能分层
            layers = await self.layer_manager.calculate_smart_layers(
                symbol=signal['symbol'],
                direction=signal['action'],
                config=config,
                market_data=market_data
            )

            if not layers:
                logging.error("Failed to calculate layers")
                return None

            # 创建仓位
            positions = []
            for layer in layers:
                order_result = await self.trade_manager.place_order(
                    symbol=signal['symbol'],
                    direction=signal['action'],
                    volume=layer.volume,
                    entry_type=signal['entry_type'],
                    entry_price=layer.entry_price,
                    stop_loss=layer.stop_loss,
                    take_profits=layer.take_profits
                )

                if order_result:
                    position = Position(
                        id=order_result['orderId'],
                        symbol=signal['symbol'],
                        direction=signal['action'],
                        volume=layer.volume,
                        entry_type=signal['entry_type'],
                        entry_price=layer.entry_price,
                        stop_loss=layer.stop_loss,
                        take_profits=layer.take_profits,
                        layer_index=layer.index,
                        metadata={
                            'creation_time': datetime.now().isoformat(),
                            'layer_info': {
                                'total_layers': len(layers),
                                'layer_index': layer.index,
                                'risk_reward_ratio': layer.risk_reward_ratio
                            }
                        }
                    )
                    positions.append(position)

            if positions:
                # 创建交易round
                round_id = await self.round_manager.create_round(signal, positions)
                return round_id

            return None

        except Exception as e:
            logging.error(f"Error creating layered positions: {e}")
            return None

    async def update_positions_config(self, round_id: str, config: Dict[str, Any]) -> bool:
        """Update positions configuration for a specific round"""
        try:
            # Get terminal state
            terminal_state = self.trade_manager.connection.terminal_state
            
            # Get trade round
            trade_round = self.round_manager.rounds.get(round_id)
            if not trade_round:
                logging.error(f"Trade round {round_id} not found")
                return False
                
            # Update trailing stop if specified
            if config.get('trailing_stop'):
                for position_id in trade_round.active_positions:
                    await self.trade_manager.modify_position(
                        position_id=position_id,
                        trailing_stop=config['trailing_stop']
                    )
            
            # Update other parameters
            await self.round_manager.update_round_config(round_id, config)
            return True
            
        except Exception as e:
            logging.error(f"Error updating positions config: {e}")
            return False

    async def handle_market_update(self, symbol: str, price_data: Dict[str, Any]):
        """Handle market price updates"""
        try:
            # Forward update to round manager
            terminal_state = self.trade_manager.connection.terminal_state
            current_price = terminal_state.price(symbol)
            
            if current_price:
                for round_id, trade_round in self.round_manager.rounds.items():
                    if trade_round.symbol == symbol:
                        await self.round_manager._handle_price_update(round_id, current_price)
                    
        except Exception as e:
            logging.error(f"Error handling market update: {e}")

    async def handle_position_update(self, position_data: Dict[str, Any]):
        """Handle position updates"""
        try:
            await self.round_manager._handle_position_update(position_data)
        except Exception as e:
            logging.error(f"Error handling position update: {e}")

    async def get_round_status(self, round_id: str) -> Optional[Dict[str, Any]]:
        """Get status of a specific trading round"""
        try:
            terminal_state = self.trade_manager.connection.terminal_state
            if round_id not in self.round_manager.rounds:
                return None
                
            trade_round = self.round_manager.rounds[round_id]
            
            active_positions = []
            closed_positions = []
            for pos_id in trade_round.positions:
                position = next(
                    (p for p in terminal_state.positions if p['id'] == pos_id), 
                    None
                )
                if position:
                    if position.get('state') == 'CLOSED':
                        closed_positions.append(position)
                    else:
                        active_positions.append(position)
            
            return {
                'status': trade_round.status.value,
                'symbol': trade_round.symbol,
                'direction': trade_round.direction,
                'active_positions': len(active_positions),
                'closed_positions': len(closed_positions),
                'tp_levels': [
                    {
                        'price': tp.price,
                        'hit_count': tp.hit_count,
                        'active': tp.active
                    }
                    for tp in trade_round.tp_levels
                ],
                'stop_loss': trade_round.stop_loss,
                'created_at': trade_round.created_at.isoformat(),
                'total_profit': sum(p.get('profit', 0) for p in closed_positions)
            }
            
        except Exception as e:
            logging.error(f"Error getting round status: {e}")
            return None

    async def cleanup(self):
        """Cleanup resources"""
        try:
            await self.round_manager.cleanup()
            
            # Unsubscribe from all symbols
            terminal_state = self.trade_manager.connection.terminal_state
            if terminal_state:
                symbols = {round_data.symbol 
                          for round_data in self.round_manager.rounds.values()}
                for symbol in symbols:
                    await self.trade_manager.connection.unsubscribe_from_market_data(symbol)
            
        except Exception as e:
            logging.error(f"Error in position manager cleanup: {e}")

    async def create_single_position(self, signal: Dict[str, Any]) -> Optional[str]:
        """创建单个仓位"""
        try:
            # 获取账户信息
            terminal_state = self.trade_manager.connection.terminal_state
            if not terminal_state:
                logging.error("Terminal state not available")
                return None
                
            account_info = terminal_state.account_information
            if not account_info:
                logging.error("Account information not available")
                return None
                
            account_size = float(account_info.get('balance', 0))
            if account_size <= 0:
                logging.error("Invalid account balance")
                return None

            # 获取当前价格
            entry_price = signal.get('entry_price')
            if not entry_price and signal['entry_type'] == 'market':
                price_info = terminal_state.price(signal['symbol'])
                if price_info:
                    entry_price = price_info['ask'] if signal['action'] == 'buy' else price_info['bid']
                else:
                    await self.trade_manager.connection.subscribe_to_market_data(
                        signal['symbol'],
                        [{'type': 'quotes'}]
                    )
                    for _ in range(10):  # Wait up to 10 times
                        await asyncio.sleep(0.1)
                        price_info = terminal_state.price(signal['symbol'])
                        if price_info:
                            entry_price = price_info['ask'] if signal['action'] == 'buy' else price_info['bid']
                            break

            if not entry_price:
                logging.error(f"Unable to determine entry price for {signal['symbol']}")
                return None

            # 设置默认止损
            if not signal.get('stop_loss'):
                stop_distance = entry_price * 0.01  # 1% stop loss distance
                signal['stop_loss'] = entry_price - stop_distance if signal['action'] == 'buy' else entry_price + stop_distance

            # 计算交易量
            volume = self.trade_manager.config.min_lot_size

            # 创建round_id
            round_id = f"R_{signal['symbol']}_{int(datetime.now().timestamp())}"

            # 下单
            order_result = await self.trade_manager.place_order(
                symbol=signal['symbol'],
                direction=signal['action'],
                volume=volume,
                entry_type=signal['entry_type'],
                entry_price=signal.get('entry_price'),
                stop_loss=signal.get('stop_loss'),
                take_profits=signal.get('take_profits', []),
                round_id=round_id
            )

            if not order_result:
                logging.error("Failed to place order")
                if self.message_handler:
                    error_data = {
                        'error_type': 'Order Placement Error',
                        'error_message': 'Failed to place order',
                        'symbol': signal['symbol'],
                        'details': f"Entry: {entry_price}, Volume: {volume}, Type: {signal['entry_type']}"
                    }
                    error_msg = self.message_handler.format_trade_notification('error', error_data)
                    await self._send_notification('error', error_data)
                return None

            # Send order opened notification
            if self.message_handler:
                order_data = {
                    'symbol': signal['symbol'],
                    'type': signal['action'],
                    'volume': volume,
                    'entry_price': entry_price,
                    'stop_loss': signal['stop_loss'],
                    'take_profit': signal['take_profits'][0] if signal['take_profits'] else None
                }
                order_msg = self.message_handler.format_trade_notification('order_opened', order_data)
                await self._send_notification('order_opened', order_data)

            # Create Position object
            position = Position(
                id=order_result['orderId'],
                symbol=signal['symbol'],
                direction=signal['action'],
                volume=volume,
                entry_type=signal['entry_type'],
                entry_price=signal.get('entry_price'),
                stop_loss=signal.get('stop_loss'),
                take_profits=signal.get('take_profits', []),
                layer_index=0,
                round_id=round_id,
                metadata={
                    'creation_time': datetime.now().isoformat(),
                    'single_position': True
                }
            )

            # Create trade round
            round_id = await self.round_manager.create_round(signal, [position])
            if not round_id:
                logging.error("Failed to create trade round")
                return None

            # Setup price monitoring
            await self.round_manager._setup_price_monitoring(signal['symbol'])

            logging.info(f"Created single position with round_id: {round_id}")
            return round_id

        except Exception as e:
            logging.error(f"Error creating single position: {e}")
            if self.message_handler:
                error_data = {
                    'error_type': 'Position Creation Error',
                    'error_message': str(e),
                    'symbol': signal.get('symbol', 'Unknown'),
                    'details': 'Failed to create position'
                }
                await self._send_notification('error', error_data)
            return None



    async def handle_round_update(self, round_id: str, update_data: Dict[str, Any]):
        """处理round更新"""
        try:
            async with self.round_manager.lock:
                trade_round = self.round_manager.rounds.get(round_id)
                if not trade_round:
                    logging.error(f"Round {round_id} not found")
                    return False

                # 更新round状态
                if 'status' in update_data:
                    trade_round.status = RoundStatus(update_data['status'])

                # 更新止损
                if 'stop_loss' in update_data:
                    trade_round.stop_loss = update_data['stop_loss']

                # 更新获利目标
                if 'take_profits' in update_data:
                    trade_round.tp_levels = [
                        TPLevel(price=tp) for tp in update_data['take_profits']
                    ]

                return True

        except Exception as e:
            logging.error(f"Error updating round: {e}")
            return False