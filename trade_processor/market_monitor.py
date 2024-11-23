import logging
from typing import Dict, List, Optional, Any
from datetime import datetime
import asyncio
import numpy as np
from dataclasses import dataclass

@dataclass
class MonitorConfig:
    """监控配置"""
    min_volume: float = 0.01  # 最小交易量
    max_layers: int = 5      # 最大分层数
    min_layers: int = 2      # 最小分层数
    atr_multiplier: float = 1.5  # ATR倍数
    volume_scale: List[float] = None  # 量能分配比例
    price_check_interval: float = 1.0  # 价格检查间隔
    
    def __post_init__(self):
        if self.volume_scale is None:
            # 默认的量能分配比例，靠近目标价格的仓位更大
            self.volume_scale = [0.4, 0.3, 0.2, 0.1]

class MarketMonitor:
    def __init__(self, trade_manager):
        self.trade_manager = trade_manager
        self.active_monitors = {}
        self.config = MonitorConfig()
        self._last_price_check = {}  # 记录每个symbol最后一次价格检查时间
        self._price_check_lock = {}  # 价格检查锁
        
    async def start_monitoring(
        self,
        symbol: str,
        direction: str,
        entry_range: tuple,
        target_prices: List[float],
        stop_loss: float,
        round_id: str,
        total_volume: float,
        options: Dict = None
    ):
        """开始市场监控"""
        try:
            # 1. 设置监控参数
            monitor = {
                'symbol': symbol,
                'direction': direction,
                'entry_range': entry_range,
                'targets': target_prices,
                'stop_loss': stop_loss,
                'round_id': round_id,
                'total_volume': total_volume,
                'status': 'active',
                'filled_layers': set(),  # 记录已成交的层级
                'start_time': datetime.now(),
                'options': options or {},
                'last_check_time': datetime.now(),
            }
            
            # 2. 计算智能分层
            layers = await self.trade_manager.calculate_smart_layers(
                symbol=symbol,
                direction=direction,
                entry_range=entry_range,
                target_prices=target_prices,
                stop_loss=stop_loss,
                options=options
            )
            
            if not layers:
                logging.error(f"Failed to calculate layers for {round_id}")
                return False
                
            monitor['layers'] = layers
            self.active_monitors[round_id] = monitor
            
            # 3. 初始化价格检查锁
            if symbol not in self._price_check_lock:
                self._price_check_lock[symbol] = asyncio.Lock()
            
            # 4. 添加价格监听器
            price_handler = self._create_price_handler(monitor)
            await self.trade_manager.add_price_listener(symbol, price_handler)
            
            logging.info(
                f"Started monitoring {symbol} for round {round_id}\n"
                f"Direction: {direction}\n"
                f"Entry Range: {entry_range}\n"
                f"Layers: {len(layers['volumes'])}"
            )
            return True
            
        except Exception as e:
            logging.error(f"Error starting market monitor: {e}")
            return False

    def _create_price_handler(self, monitor: Dict):
        """创建价格处理器"""
        async def handle_price(price_data: Dict):
            try:
                if monitor['status'] != 'active':
                    return
                    
                symbol = monitor['symbol']
                
                # 检查是否需要节流
                now = datetime.now()
                last_check = self._last_price_check.get(symbol)
                if last_check and (now - last_check).total_seconds() < self.config.price_check_interval:
                    return
                    
                # 使用锁防止并发检查
                async with self._price_check_lock[symbol]:
                    self._last_price_check[symbol] = now
                    
                    current_price = float(
                        price_data['ask'] if monitor['direction'] == 'buy'
                        else price_data['bid']
                    )
                    
                    # 定期打印监控状态
                    if (now - monitor.get('last_check_time', now)).seconds >= 60:
                        monitor['last_check_time'] = now
                        logging.info(
                            f"Market Monitor Status:\n"
                            f"Round: {monitor['round_id']}\n"
                            f"Symbol: {symbol}\n"
                            f"Direction: {monitor['direction']}\n"
                            f"Current Price: {current_price}\n"
                            f"Entry Range: {monitor['entry_range']}\n"
                            f"Filled Layers: {len(monitor['filled_layers'])}/{len(monitor['layers']['volumes'])}\n"
                            f"Active Time: {(now - monitor.get('start_time', now)).seconds}s"
                        )
                    
                    # 检查是否满足入场条件
                    layers = monitor['layers']
                    for i, entry_price in enumerate(layers['entry_prices']):
                        if i in monitor['filled_layers']:
                            continue
                            
                        if self._should_enter_position(
                            current_price, 
                            entry_price,
                            monitor['direction']
                        ):
                            logging.info(
                                f"Entry condition met for layer {i}:\n"
                                f"Target Price: {entry_price}\n"
                                f"Current Price: {current_price}\n"
                                f"Price Difference: {abs(current_price - entry_price)}"
                            )
                            
                            # 执行下单
                            success = await self._execute_layer_entry(
                                monitor,
                                entry_price,
                                layers['volumes'][i],
                                i
                            )
                            if success:
                                monitor['filled_layers'].add(i)
                                logging.info(
                                    f"Layer {i} filled. "
                                    f"Remaining layers: {len(layers['volumes']) - len(monitor['filled_layers'])}"
                                )
                            
            except Exception as e:
                logging.error(f"Error handling price update in monitor: {e}")
                
        return handle_price            

    def _should_enter_position(
        self, 
        current_price: float, 
        entry_price: float,
        direction: str
    ) -> bool:
        """判断是否应该入场"""
        if direction == 'buy':
            return current_price <= entry_price
        else:
            return current_price >= entry_price
            
    async def _execute_layer_entry(
        self,
        monitor: Dict,
        entry_price: float,
        volume: float,
        layer_index: int
    ) -> bool:
        """执行层级入场"""
        try:
            price_data = await self.trade_manager.get_current_price(monitor['symbol'])
            if not price_data:
                logging.error(f"Failed to get current price for {monitor['symbol']}")
                return False
                
            # 根据交易方向选择正确的价格
            current_price = price_data['ask'] if monitor['direction'] == 'buy' else price_data['bid']
            
            # 判断是否应该使用市价单
            price_diff = abs(current_price - entry_price)
            slippage = monitor['options'].get('slippage', self.trade_manager.config.default_slippage)
            use_market = price_diff <= slippage
            
            logging.info(
                f"Executing layer {layer_index} entry:\n"
                f"Direction: {monitor['direction']}\n"
                f"Entry Price: {entry_price}\n"
                f"Current Price: {current_price}\n"
                f"Volume: {volume}\n"
                f"Using Market Order: {use_market}"
            )
            
            result = await self.trade_manager.place_order(
                symbol=monitor['symbol'],
                direction=monitor['direction'],
                volume=volume,
                entry_type='market' if use_market else 'limit',
                entry_price=entry_price if not use_market else None,
                stop_loss=monitor['stop_loss'],
                take_profits=monitor['targets'],
                round_id=monitor['round_id'],
                options={
                    'slippage': slippage,
                    'comment': f"Layer {layer_index+1}/{len(monitor['layers']['volumes'])}"
                }
            )
            
            if result:
                logging.info(
                    f"Successfully executed layer {layer_index}:\n"
                    f"Order ID: {result.get('orderId')}\n"
                    f"Execution Time: {result.get('tradeExecutionTime')}\n"
                    f"Type: {result.get('orderType')}"
                )
                return True
                
            logging.error(f"Failed to execute layer {layer_index}")
            return False
            
        except Exception as e:
            logging.error(f"Error executing layer entry: {e}")
            return False
            
    def stop_monitoring(self, round_id: str):
        """停止监控"""
        if round_id in self.active_monitors:
            monitor = self.active_monitors[round_id]
            monitor['status'] = 'stopped'
            # 移除价格监听器
            self.trade_manager.remove_price_listener(
                monitor['symbol'],
                self._create_price_handler(monitor)
            )
            self.active_monitors.pop(round_id)