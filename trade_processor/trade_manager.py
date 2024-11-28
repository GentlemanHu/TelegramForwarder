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
        self.trade_manager._connected_instances = set()

    async def on_candle_data_received(self, instance_index: str, candle_data: Dict):
        """Called when candle data is received"""
        await self.trade_manager._handle_candle_update(candle_data)

    async def on_pending_order_updated(self, instance_index: str, order: Dict):
        """Called when pending order is updated"""
        await self.trade_manager._handle_order_update(order)

    async def on_connected(self, instance_index: str, replicas: int):
        """Called when connection established"""
        self.trade_manager._connected_instances.add(instance_index)
        logging.info(f"Instance {instance_index} connected")

    async def on_disconnected(self, instance_index: str):
        """Called when connection dropped"""
        if instance_index in self.trade_manager._connected_instances:
            self.trade_manager._connected_instances.remove(instance_index)
        logging.info(f"Instance {instance_index} disconnected")

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
                logging.debug(f"Price update for {symbol}: Bid={price.get('bid', 'N/A')}, Ask={price.get('ask', 'N/A')}")
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
                
            logging.info(f"Account Update - Balance: {account_information['balance']:.2f}, "
                        f"Equity: {account_information['equity']:.2f}, "
                        f"Profit: {account_information['profit']:.2f}, "
                        f"Free Margin: {account_information['freeMargin']:.2f}")
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
    def __init__(self, config: 'TradeConfig', message_handler=None):
        self.config = config
        self.api = MetaApi(config.meta_api_token)
        self.account = None
        self.connection = None
        self._initialized = False
        self.sync_complete = asyncio.Event()
        self._price_listeners: Dict[str, List] = {}
        self._position_listeners = []
        self._order_listeners = []
        self.sync_listener = None
        self._subscribed_symbols = set()
        self.active_streams = {}  # 新增：跟踪活跃的流订阅
        self._candle_data = {}  # 存储每个symbol的最新K线数据
        self._candle_listeners: Dict[str, List] = {}  # K线数据监听器
        self.message_handler = message_handler  # Add message handler for notifications


    async def _handle_position_update(self, position: Dict):
        """Handle position updates with profit validation"""
        try:
            if not isinstance(position, dict):
                return
                
            if position.get('profit') is None:
                position['profit'] = 0.0
                
            logging.info(f"Position Update - ID: {position.get('id')}, "
                        f"Symbol: {position.get('symbol')}, "
                        f"Type: {position.get('type')}, "
                        f"Volume: {position.get('volume')}, "
                        f"Profit: {position.get('profit'):.2f}")
            
            # Send notifications for position events
            if self.message_handler:
                notification_data = {
                    'symbol': position.get('symbol'),
                    'type': position.get('type'),
                    'volume': position.get('volume'),
                    'entry_price': position.get('openPrice'),
                    'close_price': position.get('closePrice'),
                    'profit': position.get('profit'),
                    'stop_loss': position.get('stopLoss'),
                    'take_profit': position.get('takeProfit')
                }
                
                # Calculate profit percentage if position is closed
                if position.get('state') == 'CLOSED':
                    notification_data['profit_pct'] = (
                        position.get('profit', 0) / 
                        (float(position.get('openPrice', 1)) * float(position.get('volume', 1)))
                    ) * 100
                    notification_data['duration'] = str(
                        datetime.fromisoformat(position.get('closeTime')) - 
                        datetime.fromisoformat(position.get('openTime'))
                    ) if position.get('closeTime') and position.get('openTime') else 'N/A'
                    
                    notification_msg = self.message_handler.format_trade_notification(
                        'order_closed', 
                        notification_data
                    )
                    await self.message_handler.send_trade_notification(notification_msg)
                
                # Handle SL/TP modifications
                elif position.get('stopLossModified'):
                    notification_data.update({
                        'old_sl': position.get('oldStopLoss', 0),
                        'new_sl': position.get('stopLoss', 0)
                    })
                    notification_msg = self.message_handler.format_trade_notification(
                        'sl_modified',
                        notification_data
                    )
                    await self.message_handler.send_trade_notification(notification_msg)
                    
                elif position.get('takeProfitModified'):
                    notification_data.update({
                        'old_tp': position.get('oldTakeProfit', 0),
                        'new_tp': position.get('takeProfit', 0)
                    })
                    notification_msg = self.message_handler.format_trade_notification(
                        'tp_modified',
                        notification_data
                    )
                    await self.message_handler.send_trade_notification(notification_msg)
                        
            for listener in self._position_listeners:
                try:
                    await listener(position)
                except Exception as e:
                    logging.error(f"Error in position listener: {e}")
                    
        except Exception as e:
            logging.error(f"Error handling position update: {e}")
            if self.message_handler:
                notification_data = {
                    'error_type': 'Position Update Error',
                    'error_message': str(e),
                    'error_time': datetime.now().strftime('%Y-%m-%d %H:%M:%S')
                }
                notification_msg = self.message_handler.format_trade_notification(
                    'system_error',
                    notification_data
                )
                await self.message_handler.send_trade_notification(notification_msg)


    async def _handle_position_removed(self, position: Dict):
        """Handle position removal"""
        try:
            position_id = position.get('id')
            if position_id:
                logging.info(f"Position {position_id} removed")
        except Exception as e:
            logging.error(f"Error handling position removal: {e}")

    async def _handle_order_update(self, order: Dict):
        """处理订单更新事件"""
        try:
            order_id = order.get('id')
            if not order_id:
                return
                
            logging.info(
                f"Order update - ID: {order_id}, "
                f"Symbol: {order.get('symbol')}, "
                f"Type: {order.get('type')}, "
                f"State: {order.get('state')}"
            )
            
            # Handle order notifications
            if self.message_handler:
                notification_data = {
                    'symbol': order.get('symbol'),
                    'type': order.get('type'),
                    'volume': order.get('volume'),
                    'entry_price': order.get('openPrice'),
                    'stop_loss': order.get('stopLoss'),
                    'take_profit': order.get('takeProfit'),
                    'error': order.get('error')
                }
                
                # Determine event type based on order state
                event_type = None
                if order.get('state') == 'FILLED':
                    event_type = 'order_opened'
                elif order.get('state') == 'REJECTED':
                    event_type = 'order_failed'
                elif order.get('state') == 'MODIFIED':
                    event_type = 'order_modified'
                    changes = []
                    if order.get('stopLossModified'):
                        changes.append(f"Stop Loss: {order.get('stopLoss'):.5f}")
                    if order.get('takeProfitModified'):
                        changes.append(f"Take Profit: {order.get('takeProfit'):.5f}")
                    notification_data['changes'] = "\n".join(changes)
                
                if event_type:
                    notification_msg = self.message_handler.format_trade_notification(
                        event_type,
                        notification_data
                    )
                    await self.message_handler.send_trade_notification(notification_msg)
            
            # 通知订单监听器
            for listener in self._order_listeners:
                try:
                    await listener(order)
                except Exception as e:
                    logging.error(f"Error in order listener: {e}")
                    
        except Exception as e:
            logging.error(f"Error handling order update: {e}")
            if self.message_handler:
                notification_data = {
                    'error_type': 'Order Update Error',
                    'error_message': str(e),
                    'error_time': datetime.now().strftime('%Y-%m-%d %H:%M:%S')
                }
                notification_msg = self.message_handler.format_trade_notification(
                    'system_error',
                    notification_data
                )
                await self.message_handler.send_trade_notification(notification_msg)

    async def get_current_price(self, symbol: str) -> Optional[Dict]:
        """获取当前价格"""
        if not self._initialized:
            await self.initialize()
            
        try:
            if symbol not in self._subscribed_symbols:
                await self.subscribe_to_market_data(symbol)
                
            terminal_state = self.connection.terminal_state
            if not terminal_state:
                logging.error(f"No terminal state available for {symbol}")
                return None
                
            price_info = terminal_state.price(symbol)
            if not price_info or price_info.get('ask') is None or price_info.get('bid') is None:
                logging.error(f"Invalid price data for {symbol}")
                return None
                
            spread = price_info['ask'] - price_info['bid']
            return {
                'symbol': symbol,
                'bid': price_info['bid'],
                'ask': price_info['ask'],
                'spread': spread,
                'time': datetime.now().isoformat()
            }
            
        except Exception as e:
            logging.error(f"Error getting price for {symbol}: {e}")
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
            # Get original position data for notification
            original_position = await self.get_position(position_id)
            
            options = {}
            if trailing_stop:
                options['trailingStopLoss'] = trailing_stop
                
            result = await self.connection.modify_position(
                position_id=position_id,
                stop_loss=stop_loss,
                take_profit=take_profit,
                options=options
            )

            # Send notifications for SL/TP updates if message handler exists
            if self.message_handler and result:
                current_price = self.connection.terminal_state.price(result.get('symbol'))
                current_price = current_price.get('ask' if result.get('type') == 'buy' else 'bid', 0) if current_price else 0
                
                if stop_loss and original_position:
                    sl_data = {
                        'symbol': result.get('symbol'),
                        'new_sl': stop_loss,
                        'old_sl': original_position.get('stopLoss'),
                        'current_price': current_price,
                        'floating_pl': result.get('profit', 0)
                    }
                    sl_msg = self.message_handler.format_trade_notification('sl_updated', sl_data)
                    await self.message_handler.send_trade_notification(sl_msg)
                    
                if take_profit and original_position:
                    tp_data = {
                        'symbol': result.get('symbol'),
                        'new_tp': take_profit,
                        'old_tp': original_position.get('takeProfit'),
                        'current_price': current_price,
                        'floating_pl': result.get('profit', 0)
                    }
                    tp_msg = self.message_handler.format_trade_notification('tp_updated', tp_data)
                    await self.message_handler.send_trade_notification(tp_msg)
                    
            return result
        except Exception as e:
            logging.error(f"Error modifying position: {e}")
            if self.message_handler:
                error_data = {
                    'error_type': 'Position Modification Error',
                    'error_message': str(e),
                    'symbol': original_position.get('symbol') if original_position else 'Unknown',
                    'details': f"Failed to modify position {position_id}"
                }
                error_msg = self.message_handler.format_trade_notification('error', error_data)
                await self.message_handler.send_trade_notification(error_msg)
            return None

    async def subscribe_to_market_data(self, symbol: str) -> bool:
        """订阅市场数据"""
        if not self._initialized:
            await self.initialize()
        
        try:
            if symbol in self._subscribed_symbols:
                return True
            
            # 使用正确的订阅方法
            await self.connection.subscribe_to_market_data(
                symbol,
                [{'type': 'quotes'}, {'type': 'candles', 'timeframe': '1m'}]
            )
            self._subscribed_symbols.add(symbol)
            logging.info(f"Successfully subscribed to {symbol}")
            return True
            
        except Exception as e:
            logging.error(f"Failed to subscribe to {symbol}: {e}")
            return False

    async def unsubscribe_from_market_data(self, symbol: str) -> bool:
        """取消订阅市场数据"""
        if not self._initialized:
            await self.initialize()
        
        if symbol not in self._subscribed_symbols:
            return True
        
        try:
            # 使用正确的取消订阅方法
            await self.connection.unsubscribe_from_market_data(
                symbol,
                [{'type': 'quotes'}, {'type': 'candles', 'timeframe': '1m'}]
            )
            self._subscribed_symbols.remove(symbol)
            logging.info(f"Successfully unsubscribed from {symbol}")
            return True
        except Exception as e:
            logging.error(f"Failed to unsubscribe from {symbol}: {e}")
            return False


            
    async def get_candles(self, symbol: str, timeframe: str = '1m', limit: int = 100) -> Optional[List[Dict]]:
        """Get candle data for a symbol"""
        if not self._initialized:
            await self.initialize()
            
        try:
            if symbol not in self._subscribed_symbols:
                logging.info(f"Subscribing to market data for {symbol}")
                await self.subscribe_to_market_data(symbol)
                # Wait a bit for initial data
                await asyncio.sleep(1)

            # Initialize candle storage if not exists
            if symbol not in self._candle_data:
                self._candle_data[symbol] = []

            # If we have accumulated candles, return them
            if self._candle_data[symbol]:
                logging.debug(f"Using {len(self._candle_data[symbol])} accumulated candles for {symbol}")
                return self._candle_data[symbol]
            
            # If no data, try to create a candle from current price
            try:
                price = await self.get_current_price(symbol)
                if price:
                    current_time = datetime.now().timestamp()
                    candle = {
                        'time': current_time,
                        'open': price['ask'],
                        'high': price['ask'],
                        'low': price['bid'],
                        'close': price['ask'],
                        'volume': 0,
                        'timeframe': timeframe
                    }
                    self._candle_data[symbol] = [candle]
                    logging.debug(f"Created single candle from current price for {symbol}")
                    return [candle]
            except Exception as e:
                logging.error(f"Failed to get current price for {symbol}: {str(e)}")
            
            return None
                
        except Exception as e:
            logging.error(f"Failed to get candles for {symbol}: {str(e)}")
            return None

    async def get_account_info(self) -> Dict:
        """Get account information including balance, equity, and margin"""
        try:
            if not self._initialized:
                await self.initialize()
            
            if not self.connection:
                logging.error("No connection available")
                return None
                
            # 使用connection对象获取账户信息
            account_info = await self.connection.get_account_information()
            return account_info
            
        except Exception as e:
            logging.error(f"Error getting account info: {e}")
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
            price_info = await self.get_current_price(symbol)
            if not price_info:
                return None
                
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
            if stop_loss is not None or take_profit is not None:
                await self.modify_position(
                    position_id=position_id,
                    stop_loss=stop_loss,
                    take_profit=take_profit
                )
            
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

    async def get_account_information(self) -> Optional[Dict[str, Any]]:
        """获取账户信息"""
        if not self._initialized:
            await self.initialize()
            
        try:
            terminal_state = self.connection.terminal_state
            return terminal_state.account_information
        except Exception as e:
            logging.error(f"Error getting account information: {e}")
            return None

    async def _handle_positions_replaced(self, positions: List[Dict[str, Any]]):
        """处理positions替换事件"""
        try:
            for position in positions:
                if position.get('profit') is None:
                    position['profit'] = 0.0
                for listener in self._position_listeners:
                    await listener(position)
        except Exception as e:
            logging.error(f"Error handling positions replaced: {e}")

    async def _handle_orders_replaced(self, orders: List[Dict[str, Any]]):
        """处理orders替换事件"""
        try:
            for order in orders:
                for listener in self._order_listeners:
                    await listener(order)
        except Exception as e:
            logging.error(f"Error handling orders replaced: {e}")

    async def _handle_order_completed(self, order: Dict[str, Any]):
        """处理order完成事件"""
        try:
            for listener in self._order_listeners:
                await listener(order)
        except Exception as e:
            logging.error(f"Error handling order completed: {e}")

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

    def generate_order_id(self, symbol: str, round_id: Optional[str] = None) -> Dict[str, str]:
        """
        生成订单ID和注释
        确保clientId + comment总长度不超过26个字符
        """
        try:
            timestamp = int(datetime.now().timestamp())
            short_timestamp = str(timestamp)[-4:]  # 只使用最后4位
            
            symbol_code = ''.join(c for c in symbol if c.isalpha())[:3].upper()
            
            client_id = f"T_{symbol_code}_{short_timestamp}"  # 例如: "TXAU1234"
            
            comment = None
            if round_id:
                round_num = ''.join(filter(str.isdigit, round_id))[-4:]  # 只使用最后4位
                comment = f"R{round_num}"  # 例如: "R1234"
            
            return {
                'clientId': client_id,
                'comment': comment
            }
        except Exception as e:
            logging.error(f"Error generating order ID: {e}")
            return {
                'clientId': f"T{int(time.time())%10000}",
                'comment': None
            }

    async def place_order(
        self,
        symbol: str,
        direction: str,
        volume: float,
        entry_type: str = 'market',
        entry_price: Optional[float] = None,
        stop_loss: Optional[float] = None,
        take_profits: Optional[List[float]] = None,
        trailing_stop: Optional[Dict] = None,
        round_id: Optional[str] = None
    ) -> Optional[Dict[str, Any]]:
        """下单方法"""
        if not self._initialized:
            await self.initialize()
            
        try:
            logging.info(f"Placing {entry_type} {direction} order for {symbol} - "
                        f"Volume: {volume}, Entry: {entry_price or 'Market'}, "
                        f"SL: {stop_loss}, TP: {take_profits}")
            
            id_info = self.generate_order_id(symbol, round_id)
            
            options = {'clientId': id_info['clientId']}
            if id_info['comment']:
                options['comment'] = id_info['comment']

            if trailing_stop:
                options['trailingStopLoss'] = trailing_stop

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
                else:
                    result = await self.connection.create_limit_buy_order(
                        symbol=symbol,
                        volume=volume,
                        open_price=entry_price,
                        stop_loss=stop_loss,
                        take_profit=take_profits[0] if take_profits else None,
                        options=options
                    )
            else:
                if entry_type == 'market':
                    result = await self.connection.create_market_sell_order(
                        symbol=symbol,
                        volume=volume,
                        stop_loss=stop_loss,
                        take_profit=take_profits[0] if take_profits else None,
                        options=options
                    )
                else:
                    result = await self.connection.create_limit_sell_order(
                        symbol=symbol,
                        volume=volume,
                        open_price=entry_price,
                        stop_loss=stop_loss,
                        take_profit=take_profits[0] if take_profits else None,
                        options=options
                    )

            if result:
                result.update({
                    'roundId': round_id,
                    'clientId': id_info['clientId'],
                    'orderType': entry_type,
                    'direction': direction
                })
                await self._wait_order_completion(result['orderId'])
                logging.info(f"Order placed successfully: {result}")
            
            return result
            
        except Exception as e:
            logging.error(f"Failed to place order: {str(e)}")
            raise

    async def calculate_smart_layers(
        self,
        symbol: str,
        direction: str,
        entry_range: tuple,  # (entry_start, entry_end)
        target_prices: List[float],
        stop_loss: float,
        options: Dict = None
    ):
        """智能计算交易分层"""
        try:
            logging.info(
                f"开始计算智能分层:\n"
                f"Symbol: {symbol}\n"
                f"Direction: {direction}\n"
                f"Entry Range: {entry_range}\n"
                f"Target Prices: {target_prices}\n"
                f"Stop Loss: {stop_loss}\n"
                f"Options: {options}"
            )
            
            # 1. 获取市场数据
            atr = await self._calculate_atr(symbol)
            volume_profile = await self._get_volume_profile(symbol)
            support_resistance = await self._get_support_resistance(symbol)
            
            logging.info(
                f"市场数据分析:\n"
                f"ATR: {atr}\n"
                f"Support/Resistance Levels: {support_resistance}\n"
                f"Volume Profile Summary: {sum(volume_profile.values()) if volume_profile else 0}"
            )
            
            # 2. 计算层级数量和间距
            if options and 'count' in options:
                # 如果指定了层数，使用指定的层数
                suggested_layers = options['count']
            else:
                # 否则使用ATR计算建议层数
                volatility = atr * 1.5  # 使用1.5倍ATR作为基准间距
                total_range = abs(entry_range[1] - entry_range[0])
                suggested_layers = max(2, min(5, int(total_range / volatility)))
            
            logging.info(
                f"层级计算:\n"
                f"Total Range: {abs(entry_range[1] - entry_range[0])}\n"
                f"Suggested Layers: {suggested_layers}\n"
                f"Distribution: {options.get('distribution', 'smart')}"
            )
            
            # 3. 根据成交量分布调整仓位大小
            if options and options.get('distribution') == 'equal':
                # 如果指定了均匀分布，使用均匀分布
                layer_volumes = [1.0 / suggested_layers] * suggested_layers
            else:
                # 否则使用智能分配
                layer_volumes = self._calculate_layer_volumes(
                    volume_profile, 
                    entry_range, 
                    suggested_layers
                )
            
            # 4. 优化入场价格
            entry_prices = self._optimize_entry_prices(
                entry_range,
                support_resistance,
                suggested_layers,
                direction
            )
            
            result = {
                'layers': suggested_layers,
                'entry_prices': entry_prices,
                'volumes': layer_volumes,
                'take_profits': target_prices,
                'stop_loss': stop_loss
            }
            
            logging.info(
                f"分层计算结果:\n"
                f"Number of Layers: {suggested_layers}\n"
                f"Entry Prices: {entry_prices}\n"
                f"Layer Volumes: {layer_volumes}\n"
                f"Take Profits: {target_prices}\n"
                f"Stop Loss: {stop_loss}"
            )
            
            return result
            
        except Exception as e:
            logging.error(f"Error calculating smart layers: {e}")
            return None

    async def _wait_order_completion(self, order_id: str, timeout: float = 30) -> bool:
        """等待订单完成"""
        try:
            start_time = datetime.now()
            while (datetime.now() - start_time).total_seconds() < timeout:
                order = await self.get_order(order_id)
                if not order or order.get('state') in ['COMPLETED', 'CANCELED', 'REJECTED']:
                    return True
                await asyncio.sleep(0.1)
            return False
        except Exception as e:
            logging.error(f"Error waiting for order completion: {e}")
            return False

    async def initialize(self):
        """Initialize MetaAPI streaming connection"""
        if self._initialized:
            return True
            
        try:
            logging.getLogger('socketio.client').setLevel(logging.WARNING)
            logging.getLogger('engineio.client').setLevel(logging.WARNING)
            
            self.account = await self.api.metatrader_account_api.get_account(
                self.config.account_id
            )
            
            if not self.account:
                raise Exception("Could not get account")

            if self.account.state not in ['DEPLOYING', 'DEPLOYED']:
                logging.info("Deploying account...")
                await self.account.deploy()
                
            logging.info("Waiting for account connection...")
            await self.account.wait_connected()
            
            self.connection = self.account.get_streaming_connection()
            if not self.connection:
                raise Exception("Could not create streaming connection")
            
            self.sync_listener = TradeSynchronizationListener(self)
            self.connection.add_synchronization_listener(self.sync_listener)
            
            await self.connection.connect()
            
            try:
                logging.info("Waiting for synchronization...")
                await asyncio.wait_for(
                    self.connection.wait_synchronized(),
                    timeout=300
                )
                self.sync_complete.set()
                logging.info("Account synchronized successfully")
                
                self.health_monitor = self.connection.health_monitor
                
            except asyncio.TimeoutError:
                logging.warning("Synchronization timeout")
                
            self._initialized = True
            return True
            
        except Exception as e:
            logging.error(f"Error initializing trade manager: {e}")
            return False

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

    async def start_hft_mode(self) -> bool:
        """启动HFT模式"""
        try:
            from .strategies.hft_scalping import HFTScalpingStrategy
            
            # 确保已初始化
            if not self._initialized:
                await self.initialize()
                await self.wait_synchronized()
            
            # 创建HFT策略实例
            self._hft_strategy = HFTScalpingStrategy(self)
            
            # 获取配置的交易对
            symbols = self.config.hft.symbols
            if not symbols:
                logging.error("No symbols configured for HFT mode")
                return False
                
            # 订阅市场数据
            for symbol in symbols:
                await self.subscribe_to_market_data(symbol)
                
            # 启动策略
            await self._hft_strategy.start(symbols)
            logging.info(f"HFT mode started with symbols: {symbols}")
            return True
            
        except Exception as e:
            logging.error(f"Error starting HFT mode: {e}")
            return False
            
    async def stop_hft_mode(self) -> bool:
        """停止HFT模式"""
        try:
            if hasattr(self, '_hft_strategy'):
                await self._hft_strategy.stop()
                
                # 取消订阅市场数据
                for symbol in self.config.hft.symbols:
                    await self.unsubscribe_from_market_data(symbol)
                    
                delattr(self, '_hft_strategy')
                logging.info("HFT mode stopped")
                return True
            return False
            
        except Exception as e:
            logging.error(f"Error stopping HFT mode: {e}")
            return False

    def add_candle_listener(self, symbol: str, callback):
        """添加K线数据监听器"""
        if symbol not in self._candle_listeners:
            self._candle_listeners[symbol] = []
        self._candle_listeners[symbol].append(callback)

    def remove_candle_listener(self, symbol: str, callback):
        """移除K线数据监听器"""
        if symbol in self._candle_listeners:
            try:
                self._candle_listeners[symbol].remove(callback)
            except ValueError:
                pass

    async def _handle_candle_update(self, candle_data: Dict[str, Any]):
        """处理K线数据更新"""
        try:
            symbol = candle_data.get('symbol')
            if not symbol:
                logging.warning("Received candle update without symbol")
                return

            # Initialize candle storage if not exists
            if symbol not in self._candle_data:
                self._candle_data[symbol] = []

            # Add new candle to storage
            self._candle_data[symbol].append(candle_data)
            
            # Keep only the last 100 candles
            if len(self._candle_data[symbol]) > 100:
                self._candle_data[symbol] = self._candle_data[symbol][-100:]

            logging.debug(f"Updated candle data for {symbol}, total candles: {len(self._candle_data[symbol])}")
            
            # Notify listeners
            if symbol in self._candle_listeners:
                for listener in self._candle_listeners[symbol]:
                    try:
                        await listener(candle_data)
                    except Exception as e:
                        logging.error(f"Error in candle listener: {e}")
                        
        except Exception as e:
            logging.error(f"Error handling candle update: {e}")

    async def _notify_trade_execution(self, order_result, order_type="market"):
        """发送交易执行通知"""
        try:
            if not self.message_handler:
                return
                
            symbol = order_result.get('symbol', 'Unknown')
            direction = order_result.get('direction', 'Unknown')
            volume = order_result.get('volume', 0)
            price = order_result.get('price', 'Market')
            order_id = order_result.get('orderId', 'Unknown')
            
            emoji = "🟢" if direction == "buy" else "🔴"
            direction = direction.upper()
            
            message = (
                f"{emoji} New {order_type.upper()} Order Executed\n\n"
                f"Symbol: <code>{symbol}</code>\n"
                f"Direction: <code>{direction}</code>\n"
                f"Volume: <code>{volume}</code>\n"
                f"Price: <code>{price}</code>\n"
                f"Order ID: <code>{order_id}</code>"
            )
            
            await self.message_handler.send_trade_notification(message)
            
        except Exception as e:
            logging.error(f"Failed to send trade execution notification: {e}")

    async def _notify_position_update(self, position):
        """发送持仓更新通知"""
        try:
            if not self.message_handler:
                return
                
            symbol = position.get('symbol', 'Unknown')
            type_ = position.get('type', 'Unknown')
            volume = position.get('volume', 0)
            profit = position.get('profit', 0)
            
            emoji = "📊"
            if profit > 0:
                emoji = "📈"
            elif profit < 0:
                emoji = "📉"
                
            message = (
                f"{emoji} Position Update\n\n"
                f"Symbol: <code>{symbol}</code>\n"
                f"Type: <code>{type_}</code>\n"
                f"Volume: <code>{volume}</code>\n"
                f"Current Profit: <code>{profit:.2f}</code>"
            )
            
            await self.message_handler.send_trade_notification(message)
            
        except Exception as e:
            logging.error(f"Failed to send position update notification: {e}")

    async def place_market_order(self, symbol, direction, volume, sl=None, tp=None):
        """下市价单"""
        try:
            # 原有的下单逻辑
            order_result = await super().place_market_order(symbol, direction, volume, sl, tp)
            
            # 发送交易通知
            await self._notify_trade_execution(order_result)
            
            return order_result
            
        except Exception as e:
            logging.error(f"Error placing market order: {e}")
            raise

    async def on_position_update(self, position):
        """持仓更新回调"""
        try:
            # 原有的持仓更新逻辑
            await super().on_position_update(position)
            
            # 发送持仓更新通知
            await self._notify_position_update(position)
            
        except Exception as e:
            logging.error(f"Error handling position update: {e}")