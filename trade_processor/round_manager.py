import asyncio
import logging
from dataclasses import dataclass
from datetime import datetime
from typing import Dict, List, Optional, Any
from enum import Enum
from .position import Position, PositionStatus
from .signal_tracker import SignalTracker


class RoundStatus(Enum):
    PENDING = "pending"
    ACTIVE = "active"
    PARTIALLY_CLOSED = "partially_closed"
    CLOSED = "closed"

@dataclass
class TPLevel:
    price: float
    hit_count: int = 0
    active: bool = True

@dataclass
class TradeRound:
    id: str
    symbol: str
    direction: str  # 'buy' or 'sell'
    created_at: datetime
    positions: Dict[str, 'Position']  # position_id -> Position
    tp_levels: List[TPLevel]
    stop_loss: Optional[float] = None
    status: RoundStatus = RoundStatus.PENDING
    metadata: Dict[str, Any] = None
    
    @property
    def active_positions(self):
        return {id: pos for id, pos in self.positions.items() 
                if pos.status == 'active'}
    
    @property
    def closed_positions(self):
        return {id: pos for id, pos in self.positions.items() 
                if pos.status == 'closed'}

class RoundManager:
    def __init__(self, connection: 'StreamingMetaApiConnection', trade_manager: 'TradeManager'):
        self.connection = connection
        self.trade_manager = trade_manager
        self.rounds: Dict[str, TradeRound] = {}
        self._price_listeners = {}
        self._order_listeners = {}
        self.lock = asyncio.Lock()
                # 添加动态止盈管理器
        self.tp_manager = DynamicTPManager(self)
        
    async def initialize(self):
        """Initialize round manager and set up listeners"""
        try:
            # Subscribe to order updates
            self.connection.add_order_update_listener(self._handle_order_update)
            self.connection.add_position_update_listener(self._handle_position_update)
            logging.info("RoundManager initialized successfully")
        except Exception as e:
            logging.error(f"Error initializing RoundManager: {e}")
            raise




    async def create_round(self, signal: Dict[str, Any], positions: List[Position]) -> Optional[str]:
        """创建交易轮次"""
        try:
            round_id = signal.get('round_id') or f"R_{signal['symbol']}_{int(datetime.now().timestamp())}"
            
            trade_round = TradeRound(
                id=round_id,
                symbol=signal['symbol'],
                direction=signal['action'],
                created_at=datetime.now(),
                positions={pos.id: pos for pos in positions},
                tp_levels=[TPLevel(price=tp) for tp in signal.get('take_profits', [])],
                stop_loss=signal.get('stop_loss'),
                status=RoundStatus.PENDING,
                metadata={
                    'signal': signal,
                    'creation_time': datetime.now().isoformat()
                }
            )

            async with self.lock:
                self.rounds[round_id] = trade_round
                await self._setup_price_monitoring(trade_round)
                
                # 设置止盈水平
                if signal.get('take_profits'):
                    await self.tp_manager.update_round_tps(
                        round_id,
                        signal['take_profits'],
                        [pos.to_dict() for pos in positions]
                    )

            return round_id

        except Exception as e:
            logging.error(f"Error creating round: {e}")
            return None

    async def _handle_price_update(self, round_id: str, price_data: Dict[str, Any]):
        """处理价格更新"""
        try:
            async with self.lock:
                trade_round = self.rounds.get(round_id)
                if not trade_round:
                    return

                current_price = price_data['bid' if trade_round.direction == 'sell' else 'ask']

                # 检查止盈触发
                actions = await self.tp_manager.handle_tp_hit(
                    round_id,
                    current_price,
                    [pos.to_dict() for pos in trade_round.positions.values()]
                )

                # 执行止盈动作
                for action in actions:
                    if action['action'] == 'close_position':
                        await self.trade_manager.close_position(action['position_id'])
                    elif action['action'] == 'modify_position':
                        await self.trade_manager.modify_position(
                            position_id=action['position_id'],
                            stop_loss=action.get('stop_loss'),
                            take_profit=action.get('take_profit')
                        )

                # 更新轮次状态
                await self._update_round_status(trade_round)

        except Exception as e:
            logging.error(f"Error handling price update: {e}")

    async def _update_round_status(self, trade_round: TradeRound):
        """更新轮次状态"""
        try:
            terminal_state = self.connection.terminal_state
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

            if not active_positions and closed_positions:
                trade_round.status = RoundStatus.CLOSED
            elif closed_positions:
                trade_round.status = RoundStatus.PARTIALLY_CLOSED
            elif active_positions:
                trade_round.status = RoundStatus.ACTIVE

        except Exception as e:
            logging.error(f"Error updating round status: {e}")


    async def update_round_config(self, round_id: str, config: Dict[str, Any]):
        """Update round configuration (stop loss, take profits, etc)"""
        async with self.lock:
            if round_id not in self.rounds:
                logging.error(f"Round {round_id} not found")
                return False
                
            trade_round = self.rounds[round_id]
            
            try:
                # Update stop loss if provided
                if 'stop_loss' in config:
                    trade_round.stop_loss = config['stop_loss']
                    await self._update_positions_sl(trade_round, config['stop_loss'])
                
                # Update take profits if provided
                if 'take_profits' in config:
                    new_tps = config['take_profits']
                    await self._update_positions_tp(trade_round, new_tps)
                    
                # Update trade round status
                if config.get('status'):
                    trade_round.status = RoundStatus(config['status'])
                    
                return True
                
            except Exception as e:
                logging.error(f"Error updating round config: {e}")
                return False

    async def _setup_price_monitoring(self, trade_round: TradeRound):
        """Set up price monitoring for a trade round"""
        symbol = trade_round.symbol
        
        async def price_listener(price_data: Dict[str, Any]):
            await self._handle_price_update(trade_round.id, price_data)
        
        # Subscribe to price updates
        if symbol not in self._price_listeners:
            await self.connection.subscribe_to_market_data(
                symbol=symbol,
                subscriptions=['quotes']
            )
            self._price_listeners[symbol] = price_listener
            
        await self.connection.add_price_change_listener(
            symbol,
            price_listener
        )


    async def _handle_tp_hit(self, trade_round: TradeRound, tp_level: TPLevel, terminal_state):
        """Handle take profit hit"""
        try:
            # Mark TP level as hit
            tp_level.hit_count += 1
            
            # Find positions to close
            positions_to_close = []
            remaining_positions = []
            
            for pos_id in trade_round.positions:
                position = next(
                    (p for p in terminal_state.positions if p['id'] == pos_id),
                    None
                )
                if not position:
                    continue
                    
                # Check if position's take profit matches current level
                if position.get('takeProfit') == tp_level.price:
                    positions_to_close.append(position)
                else:
                    remaining_positions.append(position)
                        
            # Close positions at this TP level
            for position in positions_to_close:
                await self.trade_manager.close_position(position['id'])
                    
            # Cancel remaining limit orders if this was the last TP
            if not any(tp.active for tp in trade_round.tp_levels if tp != tp_level):
                # Cancel pending orders
                for order in terminal_state.orders:
                    if order.get('positionId') in trade_round.positions:
                        await self.trade_manager.cancel_order(order['id'])
                    
            # Set breakeven for remaining positions if needed
            if positions_to_close and remaining_positions:
                await self._set_positions_breakeven(remaining_positions)
                    
        except Exception as e:
            logging.error(f"Error handling TP hit: {e}")

    async def _set_positions_breakeven(self, positions: List[Dict]):
        """Set positions to breakeven"""
        try:
            for position in positions:
                entry_price = position.get('openPrice')
                if entry_price:
                    await self.trade_manager.modify_position(
                        position_id=position['id'],
                        stop_loss=entry_price
                    )
        except Exception as e:
            logging.error(f"Error setting positions to breakeven: {e}")

    async def _cancel_pending_orders(self, trade_round: TradeRound):
        """Cancel pending limit orders"""
        try:
            positions = trade_round.active_positions.values()
            for pos in positions:
                if pos.entry_type == 'limit' and pos.status == 'pending':
                    await self.trade_manager.cancel_order(pos.id)
        except Exception as e:
            logging.error(f"Error canceling pending orders: {e}")

    async def _set_positions_breakeven(self, positions: List['Position']):
        """Set positions to breakeven"""
        try:
            for pos in positions:
                await self.trade_manager.modify_position(
                    position_id=pos.id,
                    stop_loss=pos.entry_price
                )
        except Exception as e:
            logging.error(f"Error setting positions to breakeven: {e}")

    async def _handle_order_update(self, order_data: Dict[str, Any]):
        """Handle order updates"""
        position_id = order_data.get('positionId')
        if not position_id:
            return
            
        async with self.lock:
            # Find the round containing this position
            for round_id, trade_round in self.rounds.items():
                if position_id in trade_round.positions:
                    await self._update_round_status(trade_round)
                    break

    async def _handle_position_update(self, position_data: Dict[str, Any]):
        """Handle position updates"""
        position_id = position_data.get('id')
        if not position_id:
            return
            
        async with self.lock:
            # Update position in relevant round
            for round_id, trade_round in self.rounds.items():
                if position_id in trade_round.positions:
                    # Update position data
                    trade_round.positions[position_id].update(position_data)
                    await self._update_round_status(trade_round)
                    break


    def __init__(self, connection, trade_manager: 'TradeManager'):
        self.connection = connection
        self.trade_manager = trade_manager
        self.rounds: Dict[str, TradeRound] = {}
        self.lock = asyncio.Lock()
        self.signal_tracker = SignalTracker()

    async def handle_signal(self, signal: Dict[str, Any]) -> Optional[str]:
        """处理交易信号"""
        try:
            symbol = signal.get('symbol')
            if not symbol:
                logging.error("Signal missing symbol")
                return None

            # 添加到信号跟踪系统
            round_id = self.signal_tracker.add_signal(symbol, signal)

            if signal.get('type') == 'entry':
                return await self._handle_entry_signal(signal, round_id)
            elif signal.get('type') == 'modify':
                return await self._handle_modify_signal(signal, round_id)
            elif signal.get('type') == 'update':
                return await self._handle_update_signal(signal, round_id)
            else:
                logging.error(f"Unknown signal type: {signal.get('type')}")
                return None

        except Exception as e:
            logging.error(f"Error handling signal: {e}")
            return None

    async def _handle_entry_signal(self, signal: Dict[str, Any], round_id: str) -> Optional[str]:
        """处理入场信号"""
        try:
            # 检查是否是已有round的更新
            existing_round = self.rounds.get(round_id)
            if existing_round:
                # 更新现有round的配置
                await self._update_round_config(round_id, signal)
                return round_id

            # 创建新round
            trade_round = TradeRound(
                id=round_id,
                symbol=signal['symbol'],
                direction=signal['action'],
                created_at=datetime.now(),
                positions={},
                tp_levels=[TPLevel(price=tp) for tp in signal.get('take_profits', [])],
                stop_loss=signal.get('stop_loss'),
                status=RoundStatus.PENDING,
                metadata={'signal': signal}
            )

            async with self.lock:
                self.rounds[round_id] = trade_round
                await self._setup_price_monitoring(trade_round)

            return round_id

        except Exception as e:
            logging.error(f"Error handling entry signal: {e}")
            return None

    async def _handle_modify_signal(self, signal: Dict[str, Any], round_id: str) -> bool:
        """处理修改信号"""
        try:
            async with self.lock:
                trade_round = self.rounds.get(round_id)
                if not trade_round:
                    logging.error(f"Round {round_id} not found")
                    return False

                # 更新止损
                if 'stop_loss' in signal:
                    trade_round.stop_loss = signal['stop_loss']
                    for pos in trade_round.positions.values():
                        await self.trade_manager.modify_position(
                            position_id=pos.id,
                            stop_loss=signal['stop_loss'],
                            round_id=round_id
                        )

                # 更新获利目标
                if 'take_profits' in signal:
                    new_tps = [TPLevel(price=tp) for tp in signal['take_profits']]
                    await self._update_take_profits(trade_round, new_tps)

                # 处理分层配置
                if 'layers' in signal:
                    await self._handle_layer_config(trade_round, signal['layers'])

                return True

        except Exception as e:
            logging.error(f"Error handling modify signal: {e}")
            return False

    async def _handle_update_signal(self, signal: Dict[str, Any], round_id: str) -> bool:
        """处理更新信号（补充配置）"""
        try:
            async with self.lock:
                trade_round = self.rounds.get(round_id)
                if not trade_round:
                    logging.error(f"Round {round_id} not found")
                    return False

                # 应用更新
                if 'stop_loss' in signal or 'take_profits' in signal:
                    await self._update_round_config(round_id, signal)

                # 标记信号已处理
                self.signal_tracker.mark_processed(
                    round_id,
                    datetime.now()
                )

                return True

        except Exception as e:
            logging.error(f"Error handling update signal: {e}")
            return False

    async def _update_round_config(self, round_id: str, config: Dict[str, Any]) -> bool:
        """更新round配置"""
        try:
            trade_round = self.rounds.get(round_id)
            if not trade_round:
                return False

            changes = {}

            # 更新止损
            if 'stop_loss' in config:
                changes['stop_loss'] = config['stop_loss']
                trade_round.stop_loss = config['stop_loss']

            # 更新获利目标
            if 'take_profits' in config:
                new_tps = [TPLevel(price=tp) for tp in config['take_profits']]
                changes['take_profits'] = config['take_profits']
                trade_round.tp_levels = new_tps

            # 应用更改到所有相关仓位
            for pos in trade_round.positions.values():
                await self.trade_manager.modify_position(
                    position_id=pos.id,
                    stop_loss=changes.get('stop_loss'),
                    take_profit=changes['take_profits'][0] if changes.get('take_profits') else None,
                    round_id=round_id
                )

            return True

        except Exception as e:
            logging.error(f"Error updating round config: {e}")
            return False


    async def cleanup(self):
        """Cleanup resources"""
        try:
            # Unsubscribe from all symbols
            for symbol in self._price_listeners:
                await self.connection.unsubscribe_from_market_data(symbol)
            
            self._price_listeners.clear()
            self._order_listeners.clear()
            self.rounds.clear()
            
        except Exception as e:
            logging.error(f"Error in RoundManager cleanup: {e}")