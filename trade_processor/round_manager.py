# round_manager.py

import asyncio
import logging
from dataclasses import dataclass
from datetime import datetime
from typing import Dict, List, Optional, Any, Set
from enum import Enum
from .position import Position, PositionStatus
from .signal_tracker import SignalTracker
from .tp_manager import DynamicTPManager, TPStatus, TPLevel

class RoundStatus(Enum):
    PENDING = "pending"
    ACTIVE = "active"
    PARTIALLY_CLOSED = "partially_closed"
    CLOSED = "closed"

@dataclass
class TradeRound:
    id: str
    symbol: str
    direction: str  # 'buy' or 'sell'
    created_at: datetime
    positions: Dict[str, Position]  # position_id -> Position
    tp_levels: List[TPLevel]
    stop_loss: Optional[float] = None
    status: RoundStatus = RoundStatus.PENDING
    metadata: Dict[str, Any] = None
    
    @property
    def active_positions(self) -> Dict[str, Position]:
        return {id: pos for id, pos in self.positions.items() 
                if pos.status == PositionStatus.ACTIVE}
    
    @property
    def closed_positions(self) -> Dict[str, Position]:
        return {id: pos for id, pos in self.positions.items() 
                if pos.status == PositionStatus.CLOSED}

class RoundManager:
    def __init__(self, connection, trade_manager: 'TradeManager'):
        self.connection = connection
        self.trade_manager = trade_manager
        self.rounds: Dict[str, TradeRound] = {}
        self.lock = asyncio.Lock()
        self.signal_tracker = SignalTracker()
        self.tp_manager = DynamicTPManager(self)
        
        self._price_listeners: Dict[str, Set] = {}
        self._position_listeners: Set = set()
        self._order_listeners: Set = set()
        self._subscribed_symbols: Set[str] = set()
        self._initialized = False

    # Required SynchronizationListener methods
    async def on_connected(self, instance_index: str, replicas: int):
        """Called when connection established"""
        logging.info(f"Connected to MetaApi, instance: {instance_index}, replicas: {replicas}")

    async def on_disconnected(self, instance_index: str):
        """Called when connection dropped"""
        logging.info(f"Disconnected from MetaApi, instance: {instance_index}")

    async def on_account_information_updated(
        self,
        instance_index: str,
        account_information: Dict
    ):
        """Called when account information updated"""
        try:
            # Handle None values in account information
            if account_information.get('balance') is None:
                account_information['balance'] = 0.0
            if account_information.get('equity') is None:
                account_information['equity'] = 0.0
            if account_information.get('margin') is None:
                account_information['margin'] = 0.0
            if account_information.get('freeMargin') is None:
                account_information['freeMargin'] = 0.0
            
            logging.debug(f"Account information updated: {account_information}")
        except Exception as e:
            logging.error(f"Error handling account information update: {e}")

    async def on_positions_updated(
        self,
        instance_index: str,
        updated_positions: List[Dict],
        removed_position_ids: List[str]
    ):
        """Called when positions updated"""
        try:
            # Process updated positions
            for position in updated_positions:
                await self._handle_position_update(position)
            
            # Process removed positions
            for position_id in removed_position_ids:
                await self._handle_position_removed({"id": position_id})
                
        except Exception as e:
            logging.error(f"Error handling positions update: {e}")

    async def on_position_updated(self, instance_index: str, position: Dict):
        """Called when position updated"""
        try:
            await self._handle_position_update(position)
        except Exception as e:
            logging.error(f"Error handling position update: {e}")

    async def on_position_removed(self, instance_index: str, position_id: str):
        """Called when position removed"""
        try:
            await self._handle_position_removed({"id": position_id})
        except Exception as e:
            logging.error(f"Error handling position removal: {e}")

    async def on_pending_orders_updated(
        self,
        instance_index: str,
        updated_orders: List[Dict],
        removed_order_ids: List[str]
    ):
        """Called when pending orders updated"""
        try:
            for order in updated_orders:
                await self._handle_order_update(order)
                
            for order_id in removed_order_ids:
                await self._handle_order_removed({"id": order_id})
                
        except Exception as e:
            logging.error(f"Error handling orders update: {e}")

    async def on_pending_order_updated(self, instance_index: str, order: Dict):
        """Called when pending order updated"""
        try:
            await self._handle_order_update(order)
        except Exception as e:
            logging.error(f"Error handling order update: {e}")

    async def on_pending_order_completed(self, instance_index: str, order_id: str):
        """Called when pending order completed"""
        try:
            await self._handle_order_completed({"id": order_id})
        except Exception as e:
            logging.error(f"Error handling order completion: {e}")

    async def on_symbol_specifications_updated(
        self, 
        instance_index: str,
        specifications: List[Dict],
        removed_symbols: List[str]
    ):
        """Called when symbol specifications updated"""
        pass

    async def on_symbol_price_updated(
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
                if symbol in self._price_listeners:
                    for listener in self._price_listeners[symbol]:
                        await listener(price)
        except Exception as e:
            logging.error(f"Error handling price update: {e}")





    async def on_symbol_prices_updated(
        self,
        instance_index: str,
        prices: List[Dict[str, Any]],
        equity: Optional[float] = None,
        margin: Optional[float] = None,
        free_margin: Optional[float] = None,
        margin_level: Optional[float] = None,
        account_currency_exchange_rate: Optional[float] = None
    ):
        """Called when symbol prices updated"""
        try:
            for price_data in prices:
                if not isinstance(price_data, dict):
                    continue
                    
                symbol = price_data.get('symbol')
                if not symbol:
                    continue

                if symbol in self._price_listeners:
                    sanitized_price = {
                        'symbol': symbol,
                        'bid': price_data.get('bid', 0),
                        'ask': price_data.get('ask', 0),
                        'time': price_data.get('time'),
                        'brokerTime': price_data.get('brokerTime'),
                        'equity': equity,
                        'margin': margin,
                        'freeMargin': free_margin,
                        'marginLevel': margin_level
                    }
                    
                    for listener in self._price_listeners[symbol]:
                        try:
                            await listener(sanitized_price)
                        except Exception as listener_error:
                            logging.error(f"Error in price listener for {symbol}: {listener_error}")
                            
        except Exception as e:
            logging.error(f"Error handling price updates: {e}")

    async def on_books_updated(
        self,
        instance_index: str,
        books: List[Dict],
        equity: Optional[float] = None,
        margin: Optional[float] = None,
        free_margin: Optional[float] = None,
        margin_level: Optional[float] = None,
        account_currency_exchange_rate: Optional[float] = None
    ):
        """Called when order books updated"""
        pass

    async def _setup_price_monitoring(self, symbol: str):
        """设置价格监控"""
        try:
            if symbol in self._subscribed_symbols:
                return

            # 创建价格监听器
            async def price_listener(price_data: Dict[str, Any]):
                await self._handle_price_update(symbol, price_data)

            # 订阅市场数据
            if self.connection:
                await self.connection.subscribe_to_market_data(
                    symbol,
                    ['quotes']  # 简化订阅，只要quotes
                )
                
                if symbol not in self._price_listeners:
                    self._price_listeners[symbol] = set()
                self._price_listeners[symbol].add(price_listener)
                self._subscribed_symbols.add(symbol)
                logging.info(f"Price monitoring setup for {symbol}")

        except Exception as e:
            logging.error(f"Error setting up price monitoring for {symbol}: {e}")

    async def _handle_price_update(self, symbol: str, price_data: Dict[str, Any]):
        """处理价格更新"""
        try:
            # 查找相关的交易rounds
            relevant_rounds = [
                round_id for round_id, trade_round in self.rounds.items()
                if trade_round.symbol == symbol and 
                trade_round.status != RoundStatus.CLOSED
            ]

            for round_id in relevant_rounds:
                async with self.lock:
                    trade_round = self.rounds.get(round_id)
                    if not trade_round:
                        continue

                    # 获取当前价格
                    current_price = (
                        price_data.get('ask')
                        if trade_round.direction == 'buy'
                        else price_data.get('bid')
                    )
                    
                    if current_price is None:
                        continue

                    # 处理止盈触发
                    actions = await self.tp_manager.handle_tp_hit(
                        round_id,
                        current_price,
                        list(trade_round.positions.values())
                    )

                    # 执行止盈动作
                    for action in actions:
                        if action['action'] == 'close_position':
                            await self.trade_manager.close_position(
                                action['position_id']
                            )
                        elif action['action'] == 'modify_position':
                            await self.trade_manager.modify_position(
                                position_id=action['position_id'],
                                stop_loss=action.get('stop_loss'),
                                take_profit=action.get('take_profit')
                            )

                    # 更新round状态
                    await self._update_round_status(trade_round)

        except Exception as e:
            logging.error(f"Error handling price update for {symbol}: {e}")



    async def on_history_orders_synchronized(
        self, 
        instance_index: str, 
        synchronization_id: str
    ):
        """Called when historical orders synchronized"""
        pass

    async def on_deals_synchronized(
        self, 
        instance_index: str, 
        synchronization_id: str
    ):
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

    async def on_positions_synchronized(
        self, 
        instance_index: str, 
        synchronization_id: str
    ):
        """Called when positions synchronized"""
        pass

    async def on_pending_orders_synchronized(
        self, 
        instance_index: str, 
        synchronization_id: str
    ):
        """Called when pending orders synchronized"""
        pass

    async def on_broker_connection_status_changed(
        self, 
        instance_index: str, 
        connected: bool
    ):
        """Called when broker connection status changed"""
        logging.info(f"Broker connection status changed: {connected}")

    async def on_health_status(self, instance_index: str, status: Dict):
        """Called when health status received"""
        logging.info(f"Health status received: {status}")

    async def on_health_status_updated(self, instance_index: str, status: str):
        """Called when health status updated"""
        logging.info(f"Health status updated: {status}")

    async def initialize(self):
        """初始化RoundManager"""
        if self._initialized:
            return True
            
        try:
            # 确保trade manager已完全初始化
            if not self.trade_manager._initialized:
                success = await self.trade_manager.initialize()
                if not success:
                    raise Exception("Failed to initialize trade manager")

            # 等待trade manager同步完成
            if not self.trade_manager.sync_complete.is_set():
                success = await self.trade_manager.wait_synchronized()
                if not success:
                    raise Exception("Trade manager synchronization failed")

            # 验证connection
            if not self.trade_manager.connection:
                raise Exception("Trade manager connection not available")
            self.connection = self.trade_manager.connection

            # 验证terminal state
            terminal_state = self.connection.terminal_state
            if not terminal_state:
                raise Exception("Terminal state not available")

            # 初始化监听器
            await self._setup_listeners()

            self._initialized = True
            logging.info("RoundManager initialized successfully")
            return True

        except Exception as e:
            logging.error(f"Error initializing RoundManager: {e}")
            return False


    async def _setup_listeners(self):
        """设置事件监听器"""
        try:
            if not self.connection:
                return
            
            # 使用正确的监听器添加方法
            self.connection.add_synchronization_listener(self)
            
            # 设置价格监听
            for symbol in self._subscribed_symbols:
                await self._setup_price_monitoring(symbol)

        except Exception as e:
            logging.error(f"Error setting up listeners: {e}")

    async def _update_positions_sl(self, trade_round: TradeRound, new_stop_loss: float):
        """更新所有仓位的止损"""
        try:
            terminal_state = self.connection.terminal_state
            
            # 更新活跃仓位
            for pos_id in trade_round.positions:
                position = next(
                    (p for p in terminal_state.positions if p['id'] == pos_id), 
                    None
                )
                if position and position.get('state') != 'CLOSED':
                    await self.connection.modify_position(
                        position_id=pos_id,
                        stop_loss=new_stop_loss
                    )
                    logging.info(f"Updated stop loss for position {pos_id} to {new_stop_loss}")
                
        except Exception as e:
            logging.error(f"Error updating positions stop loss: {e}")

    async def _update_positions_tp(self, trade_round: TradeRound, new_take_profits: List[float]):
        """更新所有仓位的止盈"""
        try:
            if not new_take_profits:
                return
                
            terminal_state = self.connection.terminal_state
            positions = list(trade_round.positions.values())
            
            # 根据仓位层级分配止盈
            for pos in positions:
                position = next(
                    (p for p in terminal_state.positions if p['id'] == pos.id), 
                    None
                )
                if not position or position.get('state') == 'CLOSED':
                    continue
                
                # 分配止盈（前面的层级使用更高的止盈目标）
                tp_index = min(pos.layer_index, len(new_take_profits) - 1)
                tp_price = new_take_profits[tp_index]
                
                await self.connection.modify_position(
                    position_id=pos.id,
                    take_profit=tp_price
                )
                logging.info(f"Updated take profit for position {pos.id} to {tp_price}")
                
        except Exception as e:
            logging.error(f"Error updating positions take profit: {e}")



    async def on_candles_updated(
        self,
        instance_index: str,
        symbol: str,
        timeframe: str,
        candles: List[Dict],
        equity: Optional[float] = None,
        margin: Optional[float] = None,
        free_margin: Optional[float] = None,
        margin_level: Optional[float] = None,
        account_currency_exchange_rate: Optional[float] = None
    ):
        """Called when candles updated"""
        try:
            if not isinstance(candles, list):
                candles = [candles]

            # 处理每个K线数据
            for candle in candles:
                try:
                    sanitized_candle = {
                        'symbol': symbol,
                        'timeframe': timeframe,
                        'time': candle.get('time'),
                        'open': candle.get('open'),
                        'high': candle.get('high'),
                        'low': candle.get('low'),
                        'close': candle.get('close'),
                        'volume': candle.get('tickVolume'),
                        'spread': candle.get('spread')
                    }
                    
                    # 通知价格监听器
                    if symbol in self._price_listeners:
                        for listener in self._price_listeners[symbol]:
                            try:
                                await listener(sanitized_candle)
                            except Exception as e:
                                logging.error(f"Error in candle listener for {symbol}: {e}")
                                
                except Exception as e:
                    logging.error(f"Error processing individual candle: {e}")
                    
        except Exception as e:
            logging.error(f"Error handling candles update: {e}")

    async def update_round_config(self, round_id: str, config: Dict[str, Any]) -> bool:
        """更新round配置"""
        async with self.lock:
            try:
                if not self._initialized:
                    success = await self.initialize()
                    if not success:
                        raise Exception("Failed to initialize RoundManager")

                if not self.connection:
                    raise Exception("Connection not available")

                if round_id not in self.rounds:
                    logging.error(f"Round {round_id} not found")
                    return False
                    
                trade_round = self.rounds[round_id]
                updates_succeeded = True

                # 获取现有仓位信息
                terminal_state = self.connection.terminal_state
                if not terminal_state:
                    raise Exception("Terminal state not available")

                # 获取所有活跃仓位
                active_positions = []
                for pos_id, pos in trade_round.positions.items():
                    position = next(
                        (p for p in terminal_state.positions if p['id'] == pos_id), 
                        None
                    )
                    if position and position.get('state') != 'CLOSED':
                        active_positions.append(pos_id)

                try:
                    # 更新止损
                    if 'stop_loss' in config:
                        trade_round.stop_loss = config['stop_loss']
                        for pos_id in active_positions:
                            await self.connection.modify_position(
                                position_id=pos_id,
                                stop_loss=config['stop_loss']
                            )
                            logging.info(f"Updated stop loss for position {pos_id} to {config['stop_loss']}")
                except Exception as e:
                    logging.error(f"Error updating stop loss: {e}")
                    updates_succeeded = False

                try:
                    # 更新止盈
                    if 'take_profits' in config:
                        trade_round.tp_levels = [TPLevel(price=tp) for tp in config['take_profits']]
                        for pos_id in active_positions:
                            await self.connection.modify_position(
                                position_id=pos_id,
                                take_profit=config['take_profits'][0]  # 使用第一个止盈价
                            )
                            logging.info(f"Updated take profit for position {pos_id} to {config['take_profits'][0]}")
                except Exception as e:
                    logging.error(f"Error updating take profits: {e}")
                    updates_succeeded = False

                try:
                    # 处理layers
                    if config.get('layers', {}).get('enabled'):
                        await self._create_additional_layers(trade_round, config)
                except Exception as e:
                    logging.error(f"Error creating additional layers: {e}")
                    updates_succeeded = False

                return updates_succeeded

            except Exception as e:
                logging.error(f"Error in update_round_config: {e}")
                return False

    async def _track_position(self, round_id: str, position: Position):
        """跟踪仓位状态"""
        try:
            if round_id not in self.rounds:
                logging.error(f"Round {round_id} not found")
                return

            trade_round = self.rounds[round_id]
            terminal_state = self.connection.terminal_state
            if not terminal_state:
                return

            pos_data = next(
                (p for p in terminal_state.positions if p['id'] == position.id),
                None
            )

            if pos_data:
                position.status = (
                    PositionStatus.ACTIVE 
                    if pos_data.get('state') != 'CLOSED' 
                    else PositionStatus.CLOSED
                )
                position.unrealized_profit = pos_data.get('profit', 0)
                position.opened_at = (
                    datetime.fromisoformat(pos_data['time']) 
                    if pos_data.get('time') 
                    else None
                )

                # 如果仓位已关闭，更新相关信息
                if position.status == PositionStatus.CLOSED:
                    position.closed_at = datetime.now()
                    position.realized_profit = pos_data.get('profit', 0)
                    logging.info(
                        f"Position {position.id} closed with profit {position.realized_profit}"
                    )

        except Exception as e:
            logging.error(f"Error tracking position: {e}")

    async def _setup_price_monitoring(self, symbol: str):
        """设置价格监控"""
        try:
            if symbol in self._subscribed_symbols:
                return

            # 创建价格监听器
            async def price_listener(price_data: Dict[str, Any]):
                await self._handle_price_update(symbol, price_data)

            # 订阅市场数据
            if self.connection:
                await self.connection.subscribe_to_market_data(
                    symbol,
                    [{'type': 'quotes'}]  # 简化订阅类型
                )
                
                if symbol not in self._price_listeners:
                    self._price_listeners[symbol] = set()
                self._price_listeners[symbol].add(price_listener)
                self._subscribed_symbols.add(symbol)
                logging.info(f"Price monitoring setup for {symbol}")

        except Exception as e:
            logging.error(f"Error setting up price monitoring for {symbol}: {e}")


    async def create_round(
        self, 
        signal: Dict[str, Any], 
        positions: List[Position]
    ) -> Optional[str]:
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
                # 设置价格监控
                await self._setup_price_monitoring(signal['symbol'])
                
                # 设置止盈水平
                if signal.get('take_profits'):
                    await self.tp_manager.update_round_tps(
                        round_id,
                        signal['take_profits'],
                        positions
                    )

            return round_id

        except Exception as e:
            logging.error(f"Error creating round: {e}")
            return None

    async def _update_round_status(self, trade_round: TradeRound):
        """更新轮次状态"""
        try:
            terminal_state = self.connection.terminal_state
            if not terminal_state:
                return

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

    async def _create_additional_layers(self, trade_round: TradeRound, config: Dict[str, Any]):
        """创建额外的交易层级"""
        try:
            if not config.get('entry_range'):
                return
                
            # 获取layer配置
            layers_config = config['layers']
            num_layers = layers_config.get('count', 3)
            distribution = layers_config.get('distribution', 'equal')
            
            # 计算层级价格
            entry_min = config['entry_range']['min']
            entry_max = config['entry_range']['max']
            price_range = abs(entry_max - entry_min)
            
            # 根据分布类型计算prices
            if distribution == 'equal':
                step = price_range / (num_layers + 1)
                prices = [entry_min + step * (i + 1) for i in range(num_layers)]
            else:
                # 可以添加其他分布类型的实现
                prices = [entry_min + price_range * (i + 1) / (num_layers + 1) 
                        for i in range(num_layers)]
            
            # 创建新的orders
            base_volume = self.trade_manager.config.min_lot_size
            for i, price in enumerate(prices):
                # 为每一层设置个性化止盈
                layer_tps = self._get_layer_take_profits(
                    config['take_profits'], 
                    i, 
                    num_layers
                )
                
                order_result = await self.trade_manager.place_order(
                    symbol=trade_round.symbol,
                    direction=trade_round.direction,
                    volume=base_volume,
                    entry_type='limit',
                    entry_price=price,
                    stop_loss=config['stop_loss'],
                    take_profits=layer_tps,
                    round_id=trade_round.id
                )
                
                if order_result:
                    # 创建并添加Position对象
                    position = Position(
                        id=order_result['orderId'],
                        symbol=trade_round.symbol,
                        direction=trade_round.direction,
                        volume=base_volume,
                        entry_type='limit',
                        entry_price=price,
                        stop_loss=config['stop_loss'],
                        take_profits=layer_tps,
                        layer_index=len(trade_round.positions) + 1,
                        round_id=trade_round.id,
                        metadata={'layer': i + 1}
                    )
                    trade_round.positions[position.id] = position
                        
        except Exception as e:
            logging.error(f"Error creating additional layers: {e}")
            raise

    def _get_layer_take_profits(
        self, 
        base_take_profits: List[float], 
        layer_index: int, 
        total_layers: int
    ) -> List[float]:
        """获取特定层级的止盈价格"""
        try:
            if not base_take_profits:
                return []
                
            # 第一层使用所有止盈目标
            if layer_index == 0:
                return base_take_profits
                
            # 最后一层只使用第一个止盈
            if layer_index == total_layers - 1:
                return [base_take_profits[0]]
                
            # 中间层根据位置使用不同数量的止盈
            num_tps = len(base_take_profits)
            layer_position = (total_layers - layer_index) / total_layers
            num_layer_tps = max(1, int(num_tps * layer_position))
            return base_take_profits[:num_layer_tps]
            
        except Exception as e:
            logging.error(f"Error getting layer take profits: {e}")
            return [base_take_profits[0]] if base_take_profits else []



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
            for symbol in list(self._subscribed_symbols):
                if self.connection:
                    await self.connection.unsubscribe_from_market_data(symbol)
                self._subscribed_symbols.remove(symbol)
                self._price_listeners.pop(symbol, None)

            # Clear all collections
            self._position_listeners.clear()
            self._order_listeners.clear()
            self.rounds.clear()
            
        except Exception as e:
            logging.error(f"Error in RoundManager cleanup: {e}")