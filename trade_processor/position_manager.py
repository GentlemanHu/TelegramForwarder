from typing import Dict, List, Optional, Any
import logging
import asyncio
from datetime import datetime
from .position import Position, PositionStatus 
from .round_manager import RoundManager
from .layer_manager import SmartLayerManager, LayerDistributionType
from .trade_manager import TradeManager


class PositionManager:

    def __init__(self, trade_manager: TradeManager):
        self.trade_manager = trade_manager
        self.layer_manager = SmartLayerManager(trade_manager)
        self.round_manager = RoundManager(
            trade_manager.connection, 
            trade_manager
        )
        self._initialized = False

    async def initialize(self):
        """Initialize position manager"""
        try:
            if self._initialized:
                return True
                
            # Initialize trade manager if not already initialized
            if not self.trade_manager._initialized:
                await self.trade_manager.initialize()

            await self.round_manager.initialize()
            self._initialized = True
            return True
            
        except Exception as e:
            logging.error(f"Error initializing position manager: {e}")
            return False

    async def create_layered_positions(self, signal: Dict[str, Any]) -> Optional[str]:
        """Create layered positions with smart distribution"""
        try:
            # Get account info
            terminal_state = self.trade_manager.connection.terminal_state
            account_info = terminal_state.account_information
            account_size = float(account_info['balance'])
            
            # Subscribe to market data
            await self.trade_manager.subscribe_to_market_data(signal['symbol'])
            
            # Calculate layer distribution
            price_range = None
            if signal['entry_type'] == 'limit' and signal['entry_range']:
                price_range = (
                    signal['entry_range']['min'],
                    signal['entry_range']['max']
                )
                
            base_price = signal['entry_price'] or (
                terminal_state.price(signal['symbol'])['ask' 
                if signal['action'] == 'buy' else 'bid']
            )
            
            distribution = await self.layer_manager.calculate_layer_distribution(
                symbol=signal['symbol'],
                direction=signal['action'],
                base_price=base_price,
                price_range=price_range,
                num_layers=signal['layers'].get('count', 3),
                account_size=account_size,
                distribution_type=LayerDistributionType.DYNAMIC
            )
            
            # Create positions
            positions = []
            for i, (entry_price, volume, tps) in enumerate(zip(
                distribution.entry_prices,
                distribution.volumes,
                distribution.take_profits
            )):
                # Create trailing stop if specified
                trailing_stop = None
                if signal.get('trailing_stop'):
                    trailing_stop = {
                        'distance': {
                            'distance': 200,
                            'units': 'RELATIVE_POINTS'
                        }
                    }
                
                order_result = await self.trade_manager.place_order(
                    symbol=signal['symbol'],
                    direction=signal['action'],
                    volume=volume,
                    entry_type=signal['entry_type'],
                    entry_price=entry_price,
                    stop_loss=distribution.stop_loss,
                    take_profits=tps,
                    trailing_stop=trailing_stop
                )
                
                if order_result:
                    position = Position(
                        id=order_result['orderId'],
                        symbol=signal['symbol'],
                        direction=signal['action'],
                        volume=volume,
                        entry_type=signal['entry_type'],
                        entry_price=entry_price,
                        stop_loss=distribution.stop_loss,
                        take_profits=tps,
                        layer_index=i,
                        metadata={
                            'creation_time': datetime.now().isoformat(),
                            'layer_info': {
                                'total_layers': len(distribution.entry_prices),
                                'layer_index': i
                            }
                        }
                    )
                    positions.append(position)
            
            if positions:
                # Create trade round
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
        """Create single position"""
        try:
            # Get account info
            account_info = await self.trade_manager.get_account_info()
            account_size = account_info['balance']
            
            # Calculate optimal entry price and volume
            volatility = await self.layer_manager._calculate_volatility(signal['symbol'])
            momentum = await self.layer_manager._calculate_momentum(signal['symbol'])
            
            # Calculate take profits based on volatility and momentum
            take_profits = []
            if signal.get('take_profits'):
                take_profits = signal['take_profits']
            else:
                base_price = signal['entry_price'] or (
                    await self.trade_manager.get_current_price(signal['symbol'])
                )['ask' if signal['action'] == 'buy' else 'bid']
                
                tp_distances = [
                    volatility * 2 * (1 + momentum),
                    volatility * 3 * (1 + momentum),
                    volatility * 4 * (1 + momentum)
                ]
                
                for dist in tp_distances:
                    tp = base_price * (1 + dist if signal['action'] == 'buy' else 1 - dist)
                    take_profits.append(round(tp, 5))

            # Place order
            order_result = await self.trade_manager.place_order(
                symbol=signal['symbol'],
                direction=signal['action'],
                volume=signal.get('volume', 0.01),
                entry_type=signal['entry_type'],
                entry_price=signal.get('entry_price'),
                stop_loss=signal.get('stop_loss'),
                take_profits=take_profits
            )

            if order_result:
                position = Position(
                    id=order_result['orderId'],
                    symbol=signal['symbol'],
                    direction=signal['action'],
                    volume=signal.get('volume', 0.01),
                    entry_type=signal['entry_type'],
                    entry_price=signal.get('entry_price'),
                    stop_loss=signal.get('stop_loss'),
                    take_profits=take_profits,
                    layer_index=0,
                    metadata={
                        'creation_time': datetime.now().isoformat(),
                        'single_position': True
                    }
                )
                
                # Create trade round
                round_id = await self.round_manager.create_round(signal, [position])
                return round_id
                
            return None
            
        except Exception as e:
            logging.error(f"Error creating single position: {e}")
            return None

