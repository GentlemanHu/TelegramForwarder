from metaapi_cloud_sdk import MetaApi,SynchronizationListener
from typing import Dict, List, Optional, Any
import logging
import asyncio
from datetime import datetime
import uuid
from .trade_config import TradeConfig



class TradeSynchronizationListener(SynchronizationListener):
    def __init__(self, trade_manager: 'TradeManager'):
        self.trade_manager = trade_manager

    async def on_connected(self, instance_index: str, replicas: int):
        """Called when connection established"""
        logging.info(f"Connected to MetaApi, instance: {instance_index}, replicas: {replicas}")

    async def on_disconnected(self, instance_index: str):
        """Called when connection dropped"""
        logging.info(f"Disconnected from MetaApi, instance: {instance_index}")

    async def on_symbol_specifications_updated(
        self, 
        instance_index: str,
        specifications: List[Dict],
        removed_symbols: List[str]
    ):
        """Called when specifications updated"""
        pass

    async def on_symbol_prices_updated(
        self,
        instance_index: str,
        prices: List[Dict],
        equity: Optional[float] = None,
        margin: Optional[float] = None,
        free_margin: Optional[float] = None,
        margin_level: Optional[float] = None,
        account_currency_exchange_rate: Optional[float] = None
    ):
        """Called when symbol prices updated"""
        try:
            for price in prices:
                symbol = price.get('symbol')
                if symbol in self.trade_manager._price_listeners:
                    for listener in self.trade_manager._price_listeners[symbol]:
                        await listener(price)
        except Exception as e:
            logging.error(f"Error handling price update: {e}")

    async def on_account_information_updated(
        self,
        instance_index: str,
        account_information: Dict
    ):
        """Called when account information updated"""
        try:
            # Handle None values in account information
            if account_information.get('profit') is None:
                account_information['profit'] = 0.0
            if account_information.get('balance') is None:
                account_information['balance'] = 0.0
            if account_information.get('equity') is None:
                account_information['equity'] = 0.0
            if account_information.get('margin') is None:
                account_information['margin'] = 0.0
            if account_information.get('freeMargin') is None:
                account_information['freeMargin'] = 0.0
            if account_information.get('marginLevel') is None:
                account_information['marginLevel'] = 0.0
        except Exception as e:
            logging.error(f"Error handling account information update: {e}")

    async def on_positions_replaced(self, instance_index: str, positions: List[Dict]):
        """Called when positions replaced"""
        try:
            for position in positions:
                if position.get('profit') is None:
                    position['profit'] = 0.0
            await self.trade_manager._handle_positions_replaced(positions)
        except Exception as e:
            logging.error(f"Error handling positions replaced: {e}")

    async def on_position_updated(self, instance_index: str, position: Dict):
        """Called when position updated"""
        try:
            if position.get('profit') is None:
                position['profit'] = 0.0
            await self.trade_manager._handle_position_update(position)
        except Exception as e:
            logging.error(f"Error handling position update: {e}")

    async def on_position_removed(self, instance_index: str, position_id: str):
        """Called when position removed"""
        try:
            await self.trade_manager._handle_position_removed({"id": position_id})
        except Exception as e:
            logging.error(f"Error handling position removal: {e}")

    async def on_pending_orders_replaced(self, instance_index: str, orders: List[Dict]):
        """Called when pending orders replaced"""
        try:
            await self.trade_manager._handle_orders_replaced(orders)
        except Exception as e:
            logging.error(f"Error handling orders replaced: {e}")

    async def on_pending_order_updated(self, instance_index: str, order: Dict):
        """Called when pending order updated"""
        try:
            await self.trade_manager._handle_order_update(order)
        except Exception as e:
            logging.error(f"Error handling order update: {e}")

    async def on_pending_order_completed(self, instance_index: str, order_id: str):
        """Called when pending order completed"""
        try:
            await self.trade_manager._handle_order_completed({"id": order_id})
        except Exception as e:
            logging.error(f"Error handling order completion: {e}")

    async def on_history_orders_synchronized(self, instance_index: str, synchronization_id: str):
        """Called when historical orders synchronized"""
        pass

    async def on_deals_synchronized(self, instance_index: str, synchronization_id: str):
        """Called when deals synchronized"""
        pass

    async def on_synchronization_started(
        self,
        instance_index: str,
        specifications_hash: Optional[str] = None,
        positions_hash: Optional[str] = None,
        orders_hash: Optional[str] = None,
        synchronization_id: Optional[str] = None
    ):
        """Called when synchronization started"""
        pass

    async def on_positions_synchronized(self, instance_index: str, synchronization_id: str):
        """Called when positions synchronized"""
        pass

    async def on_pending_orders_synchronized(self, instance_index: str, synchronization_id: str):
        """Called when pending orders synchronized"""
        pass

    async def on_broker_connection_status_changed(self, instance_index: str, connected: bool):
        """Called when broker connection status changed"""
        pass

    async def on_health_status(self, instance_index: str, status: Dict):
        """Called when health status received"""
        pass

    async def on_health_status_updated(self, instance_index: str, status: str):
        """Called when health status updated"""
        pass

class TradeManager:
    def __init__(self, config: 'TradeConfig'):
        self.config = config
        self.api = MetaApi(config.meta_api_token)
        self.account = None
        self.connection = None
        self._initialized = False
        self.sync_complete = asyncio.Event()
        self._price_listeners: Dict[str, List] = {}  # symbol -> listeners
        self._position_listeners = []
        self._order_listeners = []
        self.sync_listener = None
        
    async def _handle_position_update(self, position: Dict):
        """Handle position updates with profit validation"""
        try:
            # Ensure position has required fields
            if not isinstance(position, dict):
                return
                
            # Handle None profit
            if position.get('profit') is None:
                position['profit'] = 0.0
                
            # Notify listeners
            for listener in self._position_listeners:
                try:
                    await listener(position)
                except Exception as e:
                    logging.error(f"Error in position listener: {e}")
                    
        except Exception as e:
            logging.error(f"Error handling position update: {e}")

    async def _handle_position_removed(self, position: Dict):
        """Handle position removal"""
        try:
            position_id = position.get('id')
            if position_id:
                logging.info(f"Position {position_id} removed")
        except Exception as e:
            logging.error(f"Error handling position removal: {e}")

    async def initialize(self):
        """Initialize MetaAPI streaming connection"""
        if self._initialized:
            return True
            
        try:
            # Set logging levels
            logging.getLogger('socketio.client').setLevel(logging.WARNING)
            logging.getLogger('engineio.client').setLevel(logging.WARNING)
            
            # Get account
            self.account = await self.api.metatrader_account_api.get_account(
                self.config.account_id
            )
            
            if self.account.state not in ['DEPLOYING', 'DEPLOYED']:
                logging.info("Deploying account...")
                await self.account.deploy()
                
            logging.info("Waiting for account connection...")
            await self.account.wait_connected()
            
            # Create streaming connection
            self.connection = self.account.get_streaming_connection()
            
            # Add synchronization listener
            self.sync_listener = TradeSynchronizationListener(self)
            self.connection.add_synchronization_listener(self.sync_listener)
            
            # Connect
            await self.connection.connect()
            
            # Wait for synchronization
            try:
                logging.info("Waiting for synchronization...")
                await asyncio.wait_for(
                    self.connection.wait_synchronized(),
                    timeout=300
                )
                self.sync_complete.set()
                logging.info("Account synchronized successfully")
                
                # Initialize health monitor
                self.health_monitor = self.connection.health_monitor
                
            except asyncio.TimeoutError:
                logging.warning("Synchronization timeout")
                
            self._initialized = True
            return True
            
        except Exception as e:
            logging.error(f"Error initializing trade manager: {e}")
            if hasattr(e, '__dict__'):
                logging.error(f"Error details: {e.__dict__}")
            return False

    def add_price_listener(self, symbol: str, callback):
        """Add price listener for specific symbol"""
        if symbol not in self._price_listeners:
            self._price_listeners[symbol] = []
        self._price_listeners[symbol].append(callback)
        
    def remove_price_listener(self, symbol: str, callback):
        """Remove price listener"""
        if symbol in self._price_listeners:
            self._price_listeners[symbol].remove(callback)
            if not self._price_listeners[symbol]:
                self._price_listeners.pop(symbol)
    async def subscribe_to_market_data(self, symbol: str):
        """Subscribe to market data for a symbol"""
        try:
            if not self._initialized:
                await self.initialize()
                
            # 检查是否已经订阅
            terminal_state = self.connection.terminal_state
            if terminal_state and terminal_state.price(symbol):
                logging.info(f"Already subscribed to {symbol}")
                return
                
            await self.connection.subscribe_to_market_data(
                symbol=symbol,
                subscriptions=['quotes', 'specifications']
            )
            logging.info(f"Subscribed to market data for {symbol}")
            
        except Exception as e:
            logging.error(f"Error subscribing to market data for {symbol}: {e}")
            raise

    async def place_order(
        self,
        symbol: str,
        direction: str,
        volume: float,
        entry_type: str = 'market',
        entry_price: Optional[float] = None,
        stop_loss: Optional[float] = None,
        take_profits: Optional[List[float]] = None,
        trailing_stop: Optional[Dict] = None
    ) -> Optional[Dict[str, Any]]:
        """Place trading order with enhanced features"""
        if not self._initialized:
            await self.initialize()
            
        try:
            # Generate client ID
            client_id = f"T_{symbol}_{datetime.now().timestamp()}"
            
            # Build order options
            options = {
                'comment': 'Auto Trade',
                'clientId': client_id
            }
            
            # Add trailing stop if specified
            if trailing_stop:
                options['trailingStopLoss'] = trailing_stop

            # Place order based on type and direction
            result = None
            
            if direction == 'buy':
                if entry_type == 'market':
                    result = await self.connection.create_market_buy_order(
                        symbol=symbol,
                        volume=volume,
                        stop_loss=stop_loss,
                        take_profit=take_profits[0] if take_profits else None,
                        options=options
                    )
                else:  # limit
                    result = await self.connection.create_limit_buy_order(
                        symbol=symbol,
                        volume=volume,
                        open_price=entry_price,
                        stop_loss=stop_loss,
                        take_profit=take_profits[0] if take_profits else None,
                        options=options
                    )
            else:  # sell
                if entry_type == 'market':
                    result = await self.connection.create_market_sell_order(
                        symbol=symbol,
                        volume=volume,
                        stop_loss=stop_loss,
                        take_profit=take_profits[0] if take_profits else None,
                        options=options
                    )
                else:  # limit
                    result = await self.connection.create_limit_sell_order(
                        symbol=symbol,
                        volume=volume,
                        open_price=entry_price,
                        stop_loss=stop_loss,
                        take_profit=take_profits[0] if take_profits else None,
                        options=options
                    )

            logging.info(f"Order placed: {result}")
            return result
            
        except Exception as e:
            logging.error(f"Error placing order: {e}")
            if hasattr(e, '__dict__'):
                logging.error(f"Error details: {e.__dict__}")
            return None

    async def get_positions(self) -> List[Dict[str, Any]]:
        """Get all positions"""
        if not self._initialized:
            await self.initialize()
        
        try:
            terminal_state = self.connection.terminal_state
            return terminal_state.positions
        except Exception as e:
            logging.error(f"Error getting positions: {e}")
            return []

    async def get_orders(self) -> List[Dict[str, Any]]:
        """Get all pending orders"""
        if not self._initialized:
            await self.initialize()
        
        try:
            terminal_state = self.connection.terminal_state
            return terminal_state.orders
        except Exception as e:
            logging.error(f"Error getting orders: {e}")
            return []

    async def modify_position(
        self,
        position_id: str,
        stop_loss: Optional[float] = None,
        take_profit: Optional[float] = None,
        trailing_stop: Optional[Dict] = None
    ) -> Optional[Dict[str, Any]]:
        """Modify position parameters"""
        if not self._initialized:
            await self.initialize()
            
        try:
            options = {}
            if trailing_stop:
                options['trailingStopLoss'] = trailing_stop
                
            result = await self.connection.modify_position(
                position_id=position_id,
                stop_loss=stop_loss,
                take_profit=take_profit,
                options=options
            )
            return result
        except Exception as e:
            logging.error(f"Error modifying position: {e}")
            return None

    async def close_position(
        self,
        position_id: str,
        volume: Optional[float] = None
    ) -> Optional[Dict[str, Any]]:
        """Close position fully or partially"""
        if not self._initialized:
            await self.initialize()
            
        try:
            if volume:
                result = await self.connection.close_position_partially(
                    position_id=position_id,
                    volume=volume
                )
            else:
                result = await self.connection.close_position(
                    position_id=position_id
                )
            return result
        except Exception as e:
            logging.error(f"Error closing position: {e}")
            return None

    async def _subscribe_to_updates(self):
        """Subscribe to market updates and order/position changes"""
        try:
            # Add listeners for order and position updates
            self.connection.add_order_listener(self._handle_order_update)
            self.connection.add_position_listener(self._handle_position_update)
            
            # Subscribe to market data for actively traded symbols
            terminal_state = self.connection.terminal_state
            positions = terminal_state.positions
            
            for position in positions:
                symbol = position['symbol']
                if symbol not in self._price_listeners:
                    await self.subscribe_to_market_data(symbol)
                    
        except Exception as e:
            logging.error(f"Error subscribing to updates: {e}")

 
    def add_order_listener(self, callback):
        """Add order update listener"""
        self._order_listeners.append(callback)
        
    def add_position_listener(self, callback):
        """Add position update listener"""
        self._position_listeners.append(callback)

    async def _handle_order_update(self, order_data: Dict[str, Any]):
        """Handle order updates"""
        try:
            for listener in self._order_listeners:
                await listener(order_data)
        except Exception as e:
            logging.error(f"Error handling order update: {e}")

    async def _handle_price_update(self, price_data: Dict[str, Any]):
        """Handle price updates"""
        try:
            symbol = price_data['symbol']
            for listener in self._price_listeners.values():
                await listener(symbol, price_data)
        except Exception as e:
            logging.error(f"Error handling price update: {e}")


    async def cancel_order(self, order_id: str) -> bool:
        """Cancel pending order"""
        if not self._initialized:
            await self.initialize()
            
        try:
            await self.connection.cancel_order(order_id)
            return True
        except Exception as e:
            logging.error(f"Error canceling order: {e}")
            return False


    async def cleanup(self):
        """Cleanup resources"""
        try:
            if self.connection:
                # Remove synchronization listener
                if self.sync_listener:
                    self.connection.remove_synchronization_listener(self.sync_listener)
                
                # Unsubscribe from market data
                terminal_state = self.connection.terminal_state
                if terminal_state:
                    for symbol in list(self._price_listeners.keys()):
                        await self.connection.unsubscribe_from_market_data(symbol)
                
                # Close connection
                await self.connection.close()
                
            # Clear listeners
            self._price_listeners.clear()
            self._position_listeners.clear()
            self._order_listeners.clear()
            
            self._initialized = False
            self.sync_complete.clear()
            
        except Exception as e:
            logging.error(f"Error in cleanup: {e}")


    async def get_account_info(self) -> Optional[Dict[str, Any]]:
        """Get account information"""
        if not self._initialized:
            await self.initialize()
            
        try:
            info = await self.connection.get_account_information()
            return info
        except Exception as e:
            logging.error(f"Error getting account info: {e}")
            return None

    async def get_current_price(self, symbol: str) -> Optional[Dict[str, Any]]:
        """Get current market price with enhanced data"""
        if not self._initialized:
            await self.initialize()
            
        try:
            price_info = await self.connection.get_symbol_price(symbol)
            spread = price_info['ask'] - price_info['bid']
            
            return {
                'symbol': symbol,
                'bid': price_info['bid'],
                'ask': price_info['ask'],
                'spread': spread,
                'time': datetime.now().isoformat(),
                'profit_calculation_mode': price_info['profitCalculationMode'],
                'tick_value': price_info['tickValue']
            }
        except Exception as e:
            logging.error(f"Error getting current price: {e}")
            return None

    async def get_pending_orders(self, symbol: Optional[str] = None) -> List[Dict[str, Any]]:
        """Get pending orders with optional symbol filter"""
        if not self._initialized:
            await self.initialize()
            
        try:
            terminal_state = self.connection.terminal_state
            orders = terminal_state.orders
            
            if symbol:
                orders = [o for o in orders if o['symbol'] == symbol]
                
            return orders
        except Exception as e:
            logging.error(f"Error getting pending orders: {e}")
            return []

    async def calculate_margin(
        self,
        symbol: str,
        volume: float,
        direction: str = 'buy'
    ) -> Optional[float]:
        """Calculate required margin for a trade"""
        if not self._initialized:
            await self.initialize()
            
        try:
            # Get current price
            price_info = await self.get_current_price(symbol)
            if not price_info:
                return None
                
            # Calculate margin
            margin = await self.connection.calculate_margin({
                'symbol': symbol,
                'type': 'ORDER_TYPE_BUY' if direction == 'buy' else 'ORDER_TYPE_SELL',
                'volume': volume,
                'openPrice': price_info['ask'] if direction == 'buy' else price_info['bid']
            })
            
            return margin['margin']
        except Exception as e:
            logging.error(f"Error calculating margin: {e}")
            return None

    def _create_market_order_params(
        self,
        symbol: str,
        volume: float,
        direction: str,
        stop_loss: Optional[float] = None,
        take_profit: Optional[float] = None,
        options: Optional[Dict[str, Any]] = None
    ) -> Dict[str, Any]:
        """Create standardized market order parameters"""
        params = {
            'symbol': symbol,
            'volume': volume,
            'type': 'ORDER_TYPE_BUY' if direction == 'buy' else 'ORDER_TYPE_SELL'
        }
        
        if stop_loss is not None:
            params['stopLoss'] = stop_loss
        if take_profit is not None:
            params['takeProfit'] = take_profit
        if options:
            params.update(options)
            
        return params

    def _create_limit_order_params(
        self,
        symbol: str,
        volume: float,
        direction: str,
        entry_price: float,
        stop_loss: Optional[float] = None,
        take_profit: Optional[float] = None,
        options: Optional[Dict[str, Any]] = None
    ) -> Dict[str, Any]:
        """Create standardized limit order parameters"""
        params = {
            'symbol': symbol,
            'volume': volume,
            'type': 'ORDER_TYPE_BUY_LIMIT' if direction == 'buy' else 'ORDER_TYPE_SELL_LIMIT',
            'openPrice': entry_price
        }
        
        if stop_loss is not None:
            params['stopLoss'] = stop_loss
        if take_profit is not None:
            params['takeProfit'] = take_profit
        if options:
            params.update(options)
            
        return params

    async def modify_position_partial(
        self,
        position_id: str,
        volume: float,
        stop_loss: Optional[float] = None,
        take_profit: Optional[float] = None
    ) -> Optional[Dict[str, Any]]:
        """Modify position with partial close/modify support"""
        if not self._initialized:
            await self.initialize()
            
        try:
            # First modify stop loss and take profit if needed
            if stop_loss is not None or take_profit is not None:
                await self.modify_position(
                    position_id=position_id,
                    stop_loss=stop_loss,
                    take_profit=take_profit
                )
            
            # Then perform partial close if needed
            position = await self.get_position(position_id)
            if position and position['volume'] > volume:
                close_volume = position['volume'] - volume
                await self.close_position(position_id, close_volume)
                
            return await self.get_position(position_id)
            
        except Exception as e:
            logging.error(f"Error in modify_position_partial: {e}")
            return None

    async def get_position(self, position_id: str) -> Optional[Dict[str, Any]]:
        """Get position by ID"""
        if not self._initialized:
            await self.initialize()
            
        try:
            terminal_state = self.connection.terminal_state
            positions = terminal_state.positions
            
            for position in positions:
                if position['id'] == position_id:
                    return position
                    
            return None
        except Exception as e:
            logging.error(f"Error getting position: {e}")
            return None

    async def get_order(self, order_id: str) -> Optional[Dict[str, Any]]:
        """Get order by ID"""
        if not self._initialized:
            await self.initialize()
            
        try:
            terminal_state = self.connection.terminal_state
            orders = terminal_state.orders
            
            for order in orders:
                if order['id'] == order_id:
                    return order
                    
            return None
        except Exception as e:
            logging.error(f"Error getting order: {e}")
            return None
            
    async def wait_synchronized(self, timeout: float = 300) -> bool:
        """Wait for synchronization with timeout"""
        try:
            await asyncio.wait_for(
                self.sync_complete.wait(),
                timeout=timeout
            )
            return True
        except asyncio.TimeoutError:
            logging.warning("Synchronization timeout")
            return False