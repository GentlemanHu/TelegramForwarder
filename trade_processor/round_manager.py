import asyncio
import logging
from dataclasses import dataclass
from datetime import datetime
from typing import Dict, List, Optional, Any
from enum import Enum
from .position import Position, PositionStatus


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

    async def create_round(self, signal: Dict[str, Any], positions: List['Position']) -> Optional[str]:
        """Create a new trading round"""
        try:
            round_id = signal.get('round_id')
            
            # Create TPLevels from signal
            tp_levels = [TPLevel(price=price) for price in signal.get('take_profits', [])]
            
            # Create trade round
            trade_round = TradeRound(
                id=round_id,
                symbol=signal['symbol'],
                direction=signal['action'],
                created_at=datetime.now(),
                positions={pos.id: pos for pos in positions},
                tp_levels=tp_levels,
                stop_loss=signal.get('stop_loss'),
                metadata={
                    'signal': signal,
                    'creation_time': datetime.now().isoformat()
                }
            )
            
            async with self.lock:
                self.rounds[round_id] = trade_round
                
            # Set up price monitoring
            await self._setup_price_monitoring(trade_round)
            
            logging.info(f"Created new trade round: {round_id}")
            return round_id
            
        except Exception as e:
            logging.error(f"Error creating trade round: {e}")
            return None
            
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

    async def _handle_price_update(self, round_id: str, price_data: Dict[str, Any]):
        """Handle price updates for a trade round"""
        try:
            async with self.lock:
                trade_round = self.rounds.get(round_id)
                if not trade_round:
                    return
                    
                current_price = price_data['bid' if trade_round.direction == 'sell' else 'ask']
                
                # Check take profit levels
                terminal_state = self.connection.terminal_state
                for tp_level in trade_round.tp_levels:
                    if not tp_level.active:
                        continue
                        
                    tp_hit = (trade_round.direction == 'buy' and current_price >= tp_level.price) or \
                            (trade_round.direction == 'sell' and current_price <= tp_level.price)
                                
                    if tp_hit:
                        await self._handle_tp_hit(trade_round, tp_level, terminal_state)
                        
                # Update round status
                await self._update_round_status(trade_round, terminal_state)
                    
        except Exception as e:
            logging.error(f"Error handling price update: {e}")

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

    async def _update_round_status(self, trade_round: TradeRound, terminal_state):
        """Update round status based on positions"""
        try:
            active_count = 0
            closed_count = 0
            
            for pos_id in trade_round.positions:
                position = next(
                    (p for p in terminal_state.positions if p['id'] == pos_id),
                    None
                )
                if position:
                    if position.get('state') == 'CLOSED':
                        closed_count += 1
                    else:
                        active_count += 1
            
            if active_count == 0 and closed_count > 0:
                trade_round.status = RoundStatus.CLOSED
            elif closed_count > 0:
                trade_round.status = RoundStatus.PARTIALLY_CLOSED
            elif active_count > 0:
                trade_round.status = RoundStatus.ACTIVE
                
        except Exception as e:
            logging.error(f"Error updating round status: {e}")

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