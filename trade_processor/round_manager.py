# round_manager.py

import asyncio
import logging
import uuid
from dataclasses import dataclass
from datetime import datetime
from typing import Dict, List, Optional, Any, Set
from enum import Enum
from .position import Position, PositionStatus
from .signal_tracker import SignalTracker
from .tp_manager import DynamicTPManager, TPStatus, TPLevel
from .market_monitor import MarketMonitor

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
        self.market_monitor = MarketMonitor(trade_manager)
        
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

    async def on_positions_replaced(self, instance_index: str, positions: List[Dict]):
        """Called when positions are replaced"""
        try:
            for position in positions:
                await self._handle_position_update(position)
        except Exception as e:
            logging.error(f"Error handling positions replacement: {e}")

    async def on_pending_orders_replaced(self, instance_index: str, orders: List[Dict]):
        """Called when pending orders are replaced"""
        try:
            for order in orders:
                await self._handle_order_update(order)
        except Exception as e:
            logging.error(f"Error handling orders replacement: {e}")

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
            pass
            # logging.info(f"prices---{prices}")
            #TODO -- update
            # for price in prices:
            #     symbol = price.get('symbol')
            #     if symbol in self._price_listeners:
            #         for listener in self._price_listeners[symbol]:
            #             await listener(price)
        except Exception as e:
            logging.error(f"-----roundmanager___on_symbol_price_updated__Error handling price update: {e}")


    async def on_symbol_specifications_updated(
        self, 
        instance_index: str,
        specifications: List[Dict],
        removed_symbols: List[str]
    ):
        """Called when symbol specifications updated"""
        pass


    async def on_symbol_specification_updated(
        self,
        instance_index: str,
        specification: Dict[str, Any]
    ):
        """Called when symbol specification updated"""
        try:
            symbol = specification.get('symbol')
            if symbol in self._price_listeners:
                for listener in self._price_listeners[symbol]:
                    await listener({
                        'type': 'specification',
                        'symbol': symbol,
                        'specification': specification
                    })
        except Exception as e:
            logging.error(f"Error in symbol specification update: {e}")

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
        """处理价格更新"""
        try:
            for price_data in prices:
                if isinstance(price_data, dict):
                    symbol = price_data.get('symbol')
                    if symbol and symbol in self._price_listeners:
                        sanitized_price = {
                            'symbol': symbol,
                            'bid': float(price_data.get('bid', 0)),
                            'ask': float(price_data.get('ask', 0)),
                            'time': price_data.get('time', datetime.now().isoformat()),
                            'brokerTime': price_data.get('brokerTime', ''),
                            'profitTickValue': float(price_data.get('profitTickValue', 0)),
                            'lossTickValue': float(price_data.get('lossTickValue', 0)),
                            'equity': equity,
                            'margin': margin,
                            'freeMargin': free_margin,
                            'marginLevel': margin_level
                        }
                        
                        for listener in self._price_listeners[symbol]:
                            try:
                                await listener(sanitized_price)
                            except Exception as e:
                                logging.error(f"Error in price listener: {e}")
                                
        except Exception as e:
            logging.error(f"----on_symbol_prices_updated---round_manager---Error handling price updates: {e}")

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
                    ask_price = price_data.get('ask')
                    bid_price = price_data.get('bid')
                    
                    if ask_price is None or bid_price is None:
                        logging.warning(f"Incomplete price data for {symbol}: ask={ask_price}, bid={bid_price}")
                        continue
                        
                    current_price = float(ask_price if trade_round.direction == 'buy' else bid_price)

                    # 获取活跃仓位
                    active_positions = [
                        pos.to_dict() for pos in trade_round.positions.values()
                        if pos.status == PositionStatus.ACTIVE
                    ]

                    # 处理止盈触发
                    tp_actions = await self.tp_manager.handle_tp_hit(
                        round_id,
                        current_price,
                        active_positions
                    )

                    # 处理追踪止损
                    for position in active_positions:
                        tsl_action = await self.tp_manager.update_trailing_stop(
                            position['id'],
                            current_price,
                            position['direction']
                        )
                        if tsl_action:
                            tp_actions.append(tsl_action)

                    # 执行所有动作
                    for action in tp_actions:
                        if action['action'] == 'close_position':
                            await self.connection.close_position(
                                action['position_id']
                            )
                        elif action['action'] == 'modify_position':
                            await self.connection.modify_position(
                                position_id=action['position_id'],
                                stop_loss=action.get('stop_loss'),
                                take_profit=action.get('take_profit')
                            )

                    # 更新round状态
                    await self._update_round_status(trade_round)

        except Exception as e:
            logging.error(f"Error handling price update for {symbol}: {e}")

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
        """处理K线数据更新"""
        try:
            if not isinstance(candles, list):
                candles = [candles]

            for candle in candles:
                if isinstance(candle, dict):
                    sanitized_candle = {
                        'symbol': symbol,
                        'timeframe': timeframe,
                        'time': candle.get('time', datetime.now().isoformat()),
                        'brokerTime': candle.get('brokerTime', ''),
                        'open': float(candle.get('open', 0)),
                        'high': float(candle.get('high', 0)),
                        'low': float(candle.get('low', 0)),
                        'close': float(candle.get('close', 0)),
                        'tickVolume': float(candle.get('tickVolume', 0)),
                        'spread': float(candle.get('spread', 0)),
                        'volume': float(candle.get('volume', 0))
                    }
                    
                    if symbol in self._price_listeners:
                        for listener in self._price_listeners[symbol]:
                            try:
                                await listener(sanitized_candle)
                            except Exception as e:
                                logging.error(f"Error in candle listener: {e}")
        except Exception as e:
            logging.error(f"Error handling candles update: {e}")



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

    async def on_history_order_added(
        self,
        instance_index,
        order
    ):
        """Called when hi add started"""
        pass


    async def on_deal_added(
        self,
        instance_index,
        deal
    ):
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

    async def _handle_position_removed(self, position_data: Dict[str, Any]):
        """处理仓位移除事件"""
        try:
            position_id = position_data.get('id')
            if not position_id:
                return
                
            # 查找并更新相关的交易轮次
            for round_id, trade_round in self.rounds.items():
                if position_id in trade_round.positions:
                    position = trade_round.positions[position_id]
                    position.status = PositionStatus.CLOSED
                    await self._handle_position_closure(round_id, position_id)
                    break
                    
        except Exception as e:
            logging.error(f"Error in _handle_position_removed: {e}")

    async def _handle_order_removed(self, order_data: Dict[str, Any]):
        """处理订单移除事件"""
        try:
            order_id = order_data.get('id')
            if not order_id:
                return
                
            # 处理订单移除逻辑
            await self._handle_order_status_change(order_id, 'removed')
            
        except Exception as e:
            logging.error(f"Error in _handle_order_removed: {e}")

    async def _handle_order_completed(self, order_data: Dict[str, Any]):
        """处理订单完成事件"""
        try:
            order_id = order_data.get('id')
            if not order_id:
                return
                
            # 处理订单完成逻辑
            await self._handle_order_status_change(order_id, 'completed')
            
        except Exception as e:
            logging.error(f"Error in _handle_order_completed: {e}")

    async def _handle_order_status_change(self, order_id: str, status: str):
        """处理订单状态变化"""
        try:
            # 根据订单状态执行相应操作
            if status == 'completed':
                # 检查是否是止盈订单
                for round_id, trade_round in self.rounds.items():
                    for position in trade_round.positions.values():
                        if position.tp_order_id == order_id:
                            await self._handle_tp_hit(trade_round, position)
                            break
            elif status == 'removed':
                # 可能需要重新设置止盈止损
                for round_id, trade_round in self.rounds.items():
                    for position in trade_round.positions.values():
                        if (position.tp_order_id == order_id or 
                            position.sl_order_id == order_id):
                            await self._reset_position_orders(position)
                            break
                
        except Exception as e:
            logging.error(f"Error in _handle_order_status_change: {e}")

    async def _handle_tp_hit(self, trade_round: TradeRound, position: Position):
        """处理止盈触发"""
        try:
            # 获取当前价格
            price_data = await self.connection.get_symbol_price(position.symbol)
            if not price_data:
                return
                
            current_price = float(price_data.get('ask' if position.type == 'buy' else 'bid', 0))

            # 处理止盈触发
            actions = await self.tp_manager.handle_tp_hit(
                trade_round.id,
                current_price,
                [pos.to_dict() for pos in trade_round.positions.values() 
                 if pos.status == PositionStatus.ACTIVE]
            )
            
            # 执行动作
            for action in actions:
                if action['action'] == 'close_position':
                    await self.connection.close_position(action['position_id'])
                elif action['action'] == 'modify_position':
                    await self.connection.modify_position(
                        action['position_id'],
                        stop_loss=action.get('stop_loss'),
                        take_profit=action.get('take_profit')
                    )
                    
        except Exception as e:
            logging.error(f"Error in _handle_tp_hit: {e}")

    async def _reset_position_orders(self, position: Position):
        """重新设置仓位的订单"""
        try:
            # 重新设置止盈止损订单
            await self.connection.modify_position(
                position.id,
                stop_loss=position.stop_loss,
                take_profit=position.take_profit
            )
        except Exception as e:
            logging.error(f"Error in _reset_position_orders: {e}")

    async def _handle_position_closure(self, round_id: str, closed_position_id: str):
        """处理仓位关闭后的操作"""
        try:
            trade_round = self.rounds.get(round_id)
            if not trade_round:
                return
                
            # 获取关闭的仓位信息
            closed_position = trade_round.positions.get(closed_position_id)
            if not closed_position:
                return

            # 获取当前仓位的 TP 水平
            if not closed_position.take_profits:
                return

            hit_tp_price = closed_position.close_price
            hit_tp_level = None

            # 确定是哪个 TP 水平被触发
            for tp_level in trade_round.tp_levels:
                if abs(hit_tp_price - tp_level.price) < 0.0001:  # 考虑浮点数精度
                    hit_tp_level = tp_level
                    break

            if not hit_tp_level:
                return

            # 处理剩余活跃仓位
            await self._handle_remaining_positions(trade_round, hit_tp_level)

        except Exception as e:
            logging.error(f"Error handling position closure: {e}")

    async def _handle_remaining_positions(self, trade_round: TradeRound, hit_tp_level: TPLevel):
        """处理剩余仓位的止盈止损设置"""
        try:
            active_positions = [pos for pos in trade_round.positions.values() 
                              if pos.status == PositionStatus.ACTIVE]

            if not active_positions:
                return

            # 如果是 TP1 被触发
            if hit_tp_level == trade_round.tp_levels[0]:
                # 将所有活跃仓位移动到保本位
                for pos in active_positions:
                    await self.trade_manager.modify_position(
                        position_id=pos.id,
                        stop_loss=pos.entry_price  # 移动到保本位
                    )
                logging.info(f"Moved {len(active_positions)} positions to breakeven after TP1 hit")

            # 更新剩余仓位的止盈水平
            remaining_tps = [tp for tp in trade_round.tp_levels 
                           if tp.price > hit_tp_level.price]

            if remaining_tps:
                # 根据仓位层级分配不同的止盈
                for pos in active_positions:
                    tp_index = min(pos.layer_index, len(remaining_tps) - 1)
                    new_tp = remaining_tps[tp_index].price
                    await self.trade_manager.modify_position(
                        position_id=pos.id,
                        take_profit=new_tp
                    )
                    logging.info(f"Updated TP for position {pos.id} to {new_tp}")

        except Exception as e:
            logging.error(f"Error handling remaining positions: {e}")

    async def _handle_order_update(self, order_data: Dict[str, Any]):
        """处理订单更新"""
        try:
            order_id = order_data.get('id')
            if not order_id:
                return

            # 找到相关的交易轮次
            round_id = None
            for r_id, trade_round in self.rounds.items():
                if any(pos.order_id == order_id for pos in trade_round.positions.values()):
                    round_id = r_id
                    break

            if not round_id:
                return

            # 如果TP1已触发，取消所有limit订单
            trade_round = self.rounds.get(round_id)
            if trade_round and trade_round.tp_levels:
                first_tp = trade_round.tp_levels[0]
                if first_tp.status == TPStatus.TRIGGERED:
                    if order_data.get('type') == 'limit' and order_data.get('state') == 'placed':
                        await self.connection.cancel_order(order_id)
                        logging.info(f"Cancelled limit order {order_id} after TP1 hit")

        except Exception as e:
            logging.error(f"Error handling order update: {e}")

    async def _handle_position_update(self, position_data: Dict[str, Any]):
        """处理仓位更新"""
        try:
            position_id = position_data.get('id')
            if not position_id:
                return

            # 找到相关的交易轮次
            for round_id, trade_round in self.rounds.items():
                if position_id in trade_round.positions:
                    position = trade_round.positions[position_id]
                    
                    # 准备更新数据
                    update_data = {
                        'status': PositionStatus.CLOSED if position_data.get('state') == 'closed' else position.status,
                        'entry_price': float(position_data.get('openPrice', position.entry_price or 0)),
                        'close_price': float(position_data.get('closePrice', 0)) if position_data.get('closePrice') else None,
                        'realized_profit': float(position_data.get('profit', 0)),
                        'volume': float(position_data.get('volume', position.volume))
                    }
                    
                    # 更新仓位状态
                    position.update(update_data)
                    
                    # 如果仓位已关闭，处理相关操作
                    if position.status == PositionStatus.CLOSED:
                        await self._handle_position_closure(round_id, position_id)
                    
                    # 更新round状态
                    await self._update_round_status(trade_round)
                    logging.info(f"Updated position {position_id} in round {round_id}")
                    break

        except Exception as e:
            logging.error(f"Error handling position update: {e}")

    async def handle_signal(self, signal: Dict[str, Any]) -> Optional[str]:
        """处理交易信号"""
        try:
            symbol = signal.get('symbol')
            if not symbol:
                logging.error("Signal missing symbol")
                return None

            # 生成round_id
            round_id = str(uuid.uuid4())

            # 解析信号参数
            entry_type = signal.get('entry_type', 'limit')  # 默认使用限价单
            direction = signal.get('direction', 'buy')
            volume = signal.get('volume', 0.01)
            stop_loss = signal.get('stop_loss')
            take_profits = signal.get('take_profits', [])
            
            # 智能模式参数
            entry_start = signal.get('entry_start')
            entry_end = signal.get('entry_end')
            execution_mode = signal.get('execution_mode', 'standard')  # 默认使用标准模式
            
            # 创建交易轮次
            trade_round = TradeRound(
                id=round_id,
                symbol=symbol,
                direction=direction,
                created_at=datetime.now(),
                positions={},
                tp_levels=[TPLevel(price=tp) for tp in take_profits],
                stop_loss=stop_loss,
                status=RoundStatus.PENDING,
                metadata=signal.get('metadata', {})
            )
            
            self.rounds[round_id] = trade_round
            
            # 根据执行模式处理信号
            if execution_mode == 'smart' and entry_start and entry_end:
                # 使用智能监控模式
                success = await self.market_monitor.start_monitoring(
                    symbol=symbol,
                    direction=direction,
                    entry_range=(entry_start, entry_end),
                    target_prices=take_profits,
                    stop_loss=stop_loss,
                    round_id=round_id,
                    total_volume=volume,
                    options=signal.get('options')
                )
                
                if not success:
                    logging.error(f"Failed to start market monitoring for round {round_id}")
                    self.rounds.pop(round_id)
                    return None
                    
                logging.info(
                    f"Started smart monitoring for {symbol} {direction} "
                    f"between {entry_start}-{entry_end}"
                )
                
            else:
                # 使用标准模式
                await self._handle_entry_signal(signal, round_id)
            
            return round_id
            
        except Exception as e:
            logging.error(f"Error handling signal: {e}")
            if round_id in self.rounds:
                self.rounds.pop(round_id)
            return None

    async def _handle_entry_signal(self, signal: Dict[str, Any], round_id: str) -> Optional[str]:
        """处理入场信号"""
        try:
            # 基本参数验证
            symbol = signal.get('symbol')
            direction = signal.get('direction')
            volume = signal.get('volume', self.trade_manager.config.min_lot_size)
            stop_loss = signal.get('stop_loss')
            take_profits = signal.get('take_profits', [])
            
            if not all([symbol, direction]):
                logging.error("Missing required signal parameters")
                return None
                
            # 验证交易量
            if volume < self.trade_manager.config.min_lot_size:
                volume = self.trade_manager.config.min_lot_size
                logging.warning(f"Volume adjusted to minimum: {volume}")
            elif volume > self.trade_manager.config.max_lot_size:
                logging.error(f"Volume {volume} exceeds maximum {self.trade_manager.config.max_lot_size}")
                return None
            
            # 创建交易轮次
            trade_round = TradeRound(
                id=round_id,
                symbol=symbol,
                direction=direction,
                created_at=datetime.now(),
                positions={},
                tp_levels=[TPLevel(price=tp) for tp in take_profits],
                stop_loss=stop_loss,
                status=RoundStatus.PENDING,
                metadata=signal.get('metadata', {})
            )
            
            # 根据执行类型处理
            entry_type = signal.get('entry_type', 'limit')
            
            if entry_type == 'limit':
                # 标准限价单模式
                entry_price = signal.get('entry_price')
                if not entry_price:
                    logging.error("Limit order requires entry_price")
                    return None
                    
                # 下单
                order_result = await self.trade_manager.place_order(
                    symbol=symbol,
                    direction=direction,
                    volume=volume,
                    entry_type='limit',
                    entry_price=entry_price,
                    stop_loss=stop_loss,
                    take_profits=take_profits,
                    round_id=round_id,
                    options={'slippage': signal.get('slippage', self.trade_manager.config.default_slippage)}
                )
                
                if not order_result:
                    return None
                    
            elif entry_type == 'smart':
                # 智能分层模式
                entry_start = signal.get('entry_start')
                entry_end = signal.get('entry_end')
                
                if not all([entry_start, entry_end]):
                    logging.error("Smart entry requires entry_start and entry_end")
                    return None
                
                # 验证层级间距
                price_range = abs(entry_end - entry_start)
                min_distance = self.trade_manager.config.layer_settings['min_distance']
                max_distance = self.trade_manager.config.layer_settings['max_distance']
                
                if price_range < min_distance:
                    logging.error(f"Price range {price_range} is too small (min: {min_distance})")
                    return None
                elif price_range > max_distance:
                    logging.warning(f"Price range {price_range} exceeds max distance {max_distance}")
                    
                # 启动市场监控
                success = await self.market_monitor.start_monitoring(
                    symbol=symbol,
                    direction=direction,
                    entry_range=(entry_start, entry_end),
                    target_prices=take_profits,
                    stop_loss=stop_loss,
                    round_id=round_id,
                    total_volume=volume,
                    options={
                        **signal.get('options', {}),
                        'slippage': signal.get('slippage', self.trade_manager.config.default_slippage),
                        'volume_scale': signal.get('volume_scale', self.trade_manager.config.layer_settings['volume_scale'])
                    }
                )
                
                if not success:
                    logging.error(f"Failed to start market monitoring for round {round_id}")
                    return None
                
            else:
                # 市价单模式
                order_result = await self.trade_manager.place_order(
                    symbol=symbol,
                    direction=direction,
                    volume=volume,
                    entry_type='market',
                    stop_loss=stop_loss,
                    take_profits=take_profits,
                    round_id=round_id,
                    options={'slippage': signal.get('slippage', self.trade_manager.config.default_slippage)}
                )
                
                if not order_result:
                    return None
            
            # 保存交易轮次
            self.rounds[round_id] = trade_round
            await self._setup_price_monitoring(trade_round)
            
            return round_id
            
        except Exception as e:
            logging.error(f"Error handling entry signal: {e}")
            if round_id in self.rounds:
                self.rounds.pop(round_id)
            return None

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

    async def _handle_entry_signal(self, signal: Dict, round_id: str = None):
        """处理入场信号"""
        try:
            # 生成唯一的round_id
            if not round_id:
                round_id = f"R_{signal['symbol']}_{int(datetime.now().timestamp())}"
                
            logging.info(f"Processing entry signal for round {round_id}")
            logging.info(f"Signal details: {signal}")
            
            # 创建交易轮次
            round = TradeRound(
                id=round_id,
                symbol=signal['symbol'],
                direction=signal['action'],
                created_at=datetime.now(),
                positions={},
                tp_levels=[],
                stop_loss=signal.get('stop_loss'),
                metadata={'signal': signal}
            )
            
            # 处理止盈设置
            if signal.get('take_profits'):
                for price in signal['take_profits']:
                    round.tp_levels.append(TPLevel(price=price, status=TPStatus.PENDING))
            
            # 检查是否需要分层
            if signal.get('layers', {}).get('enabled', False):
                logging.info(
                    f"开始创建分层订单:\n"
                    f"Symbol: {signal['symbol']}\n"
                    f"Direction: {signal['action']}\n"
                    f"Entry Range: {signal['entry_range']}\n"
                    f"Layers Config: {signal['layers']}"
                )
                
                # 计算智能分层
                layers = await self.trade_manager.calculate_smart_layers(
                    symbol=signal['symbol'],
                    direction=signal['action'],
                    entry_range=(signal['entry_range']['min'], signal['entry_range']['max']),
                    target_prices=signal['take_profits'],
                    stop_loss=signal['stop_loss'],
                    options=signal['layers']  # 传入完整的layers配置
                )
                
                if not layers:
                    logging.error(f"Failed to calculate layers for round {round_id}")
                    return None
                    
                logging.info(
                    f"分层计算完成:\n"
                    f"Number of Layers: {layers['layers']}\n"
                    f"Entry Prices: {layers['entry_prices']}\n"
                    f"Layer Volumes: {layers['volumes']}"
                )
                
                # 执行每个层级的订单
                for i, (entry_price, volume) in enumerate(zip(layers['entry_prices'], layers['volumes'])):
                    logging.info(
                        f"Placing order for layer {i+1}/{len(layers['entry_prices'])}:\n"
                        f"Entry Price: {entry_price}\n"
                        f"Volume: {volume}"
                    )
                    
                    result = await self.trade_manager.place_order(
                        symbol=signal['symbol'],
                        direction=signal['action'],
                        volume=volume,
                        entry_type='limit',
                        entry_price=entry_price,
                        stop_loss=signal['stop_loss'],
                        take_profits=signal['take_profits'],
                        round_id=round_id
                    )
                    
                    if result:
                        position = Position(
                            id=result['orderId'],
                            symbol=signal['symbol'],
                            direction=signal['action'],
                            volume=volume,
                            entry_price=entry_price,
                            stop_loss=signal['stop_loss'],
                            take_profit=signal['take_profits'][0] if signal['take_profits'] else None,
                            status=PositionStatus.PENDING,
                            metadata={'layer': i}
                        )
                        round.positions[result['orderId']] = position
                        logging.info(f"Layer {i+1} order placed successfully: {result['orderId']}")
                    else:
                        logging.error(f"Failed to place order for layer {i+1}")
                
            else:
                # 单层订单处理...
                pass
            
        except Exception as e:
            logging.error(f"Error handling entry signal: {e}")