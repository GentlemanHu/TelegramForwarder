
# layer_manager.py

from enum import Enum
import numpy as np
from dataclasses import dataclass
from typing import List, Dict, Optional, Tuple
import logging
from datetime import datetime, timedelta

class LayerDistributionType(Enum):
    EQUAL = "equal"          # 等距分布
    FIBONACCI = "fibonacci"  # 斐波那契分布
    MOMENTUM = "momentum"    # 动量感知分布
    VOLUME = "volume"        # 成交量分布
    CUSTOM = "custom"        # 自定义分布

@dataclass
class LayerConfig:
    entry_price: float
    stop_loss: float
    base_tp: float
    risk_points: float
    num_layers: int
    distribution_type: LayerDistributionType
    volume_profile: Optional[Dict] = None  # 成交量分布数据
    momentum_data: Optional[Dict] = None   # 动量数据

@dataclass
class Layer:
    index: int                      # 层级索引
    entry_price: float              # 入场价格
    volume: float                   # 交易量
    stop_loss: float               # 止损价格
    take_profits: List[float]      # 止盈价格列表
    risk_reward_ratio: float       # 风险收益比
    breakeven_price: float         # 保本价格
    is_active: bool = True         # 是否活跃
    filled: bool = False           # 是否已成交
    status: str = 'pending'        # 状态

class SmartLayerManager:
    def __init__(self, trade_manager: 'TradeManager'):
        self.trade_manager = trade_manager
        self._layer_cache = {}  # 缓存已计算的分层

    async def calculate_smart_layers(
        self,
        symbol: str,
        direction: str,
        config: LayerConfig,
        market_data: Optional[Dict] = None
    ) -> List[Layer]:
        """计算智能分层"""
        try:
            # 获取市场数据
            if not market_data:
                market_data = await self._get_market_data(symbol)

            # 计算价格分布
            entry_prices = await self._calculate_entry_distribution(
                config, market_data, direction
            )

            # 计算交易量分布
            volumes = await self._calculate_volume_distribution(
                config, market_data, len(entry_prices)
            )

            # 计算止盈级别
            take_profits = await self._calculate_take_profits(
                config, market_data, direction, len(entry_prices)
            )

            # 创建层级
            layers = []
            for i, (price, volume) in enumerate(zip(entry_prices, volumes)):
                # 根据层级计算个性化止盈
                layer_tps = self._get_layer_take_profits(
                    take_profits, i, config.num_layers
                )
                
                # 计算保本价格
                breakeven = self._calculate_breakeven_price(
                    price, config.stop_loss, direction
                )
                
                # 计算风险收益比
                rr_ratio = self._calculate_risk_reward_ratio(
                    price, config.stop_loss, layer_tps[0], direction
                )

                layer = Layer(
                    index=i,
                    entry_price=price,
                    volume=volume,
                    stop_loss=config.stop_loss,
                    take_profits=layer_tps,
                    risk_reward_ratio=rr_ratio,
                    breakeven_price=breakeven
                )
                layers.append(layer)

            return layers

        except Exception as e:
            logging.error(f"Error calculating smart layers: {e}")
            return []

    async def _calculate_entry_distribution(
        self,
        config: LayerConfig,
        market_data: Dict,
        direction: str
    ) -> List[float]:
        """计算入场价格分布"""
        try:
            price_range = abs(config.entry_price - config.stop_loss)
            
            if config.distribution_type == LayerDistributionType.EQUAL:
                return self._calculate_equal_distribution(
                    config.entry_price,
                    price_range,
                    config.num_layers,
                    direction
                )
                
            elif config.distribution_type == LayerDistributionType.FIBONACCI:
                return self._calculate_fibonacci_distribution(
                    config.entry_price,
                    price_range,
                    config.num_layers,
                    direction
                )
                
            elif config.distribution_type == LayerDistributionType.MOMENTUM:
                return await self._calculate_momentum_distribution(
                    config,
                    market_data,
                    direction
                )
                
            elif config.distribution_type == LayerDistributionType.VOLUME:
                return await self._calculate_volume_based_distribution(
                    config,
                    market_data,
                    direction
                )
            
            else:
                return self._calculate_equal_distribution(
                    config.entry_price,
                    price_range,
                    config.num_layers,
                    direction
                )

        except Exception as e:
            logging.error(f"Error calculating entry distribution: {e}")
            return []

    def _calculate_equal_distribution(
        self,
        base_price: float,
        price_range: float,
        num_layers: int,
        direction: str
    ) -> List[float]:
        """计算等距分布"""
        step = price_range / (num_layers + 1)
        prices = []
        
        for i in range(num_layers):
            if direction == 'buy':
                price = base_price - (i + 1) * step
            else:
                price = base_price + (i + 1) * step
            prices.append(round(price, 5))
            
        return prices

    def _calculate_fibonacci_distribution(
        self,
        base_price: float,
        price_range: float,
        num_layers: int,
        direction: str
    ) -> List[float]:
        """计算斐波那契分布"""
        fib_ratios = [0.236, 0.382, 0.500, 0.618, 0.786]
        prices = []
        
        # 确保有足够的斐波那契水平
        while len(fib_ratios) < num_layers:
            fib_ratios.extend(fib_ratios)
        fib_ratios = fib_ratios[:num_layers]
        
        for ratio in fib_ratios:
            if direction == 'buy':
                price = base_price - (price_range * ratio)
            else:
                price = base_price + (price_range * ratio)
            prices.append(round(price, 5))
            
        return sorted(prices, reverse=(direction=='sell'))

    async def _calculate_momentum_distribution(
        self,
        config: LayerConfig,
        market_data: Dict,
        direction: str
    ) -> List[float]:
        """基于动量的智能分布"""
        try:
            momentum = market_data.get('momentum', 0)
            volatility = market_data.get('volatility', 0.001)
            price_range = abs(config.entry_price - config.stop_loss)
            
            # 根据动量调整分布密度
            momentum_factor = 1 + abs(momentum)
            adjusted_range = price_range * momentum_factor
            
            # 使用非线性分布
            ratios = np.power(
                np.linspace(0, 1, config.num_layers),
                1 / momentum_factor
            )
            
            prices = []
            for ratio in ratios:
                if direction == 'buy':
                    price = config.entry_price - (adjusted_range * ratio)
                else:
                    price = config.entry_price + (adjusted_range * ratio)
                prices.append(round(price, 5))
            
            return prices

        except Exception as e:
            logging.error(f"Error calculating momentum distribution: {e}")
            return self._calculate_equal_distribution(
                config.entry_price,
                price_range,
                config.num_layers,
                direction
            )

    async def _calculate_volume_based_distribution(
        self,
        config: LayerConfig,
        market_data: Dict,
        direction: str
    ) -> List[float]:
        """基于成交量的智能分布"""
        try:
            volume_profile = market_data.get('volume_profile', {})
            if not volume_profile:
                return self._calculate_equal_distribution(
                    config.entry_price,
                    abs(config.entry_price - config.stop_loss),
                    config.num_layers,
                    direction
                )

            # 分析成交量分布
            price_levels = sorted(volume_profile.keys())
            volumes = [volume_profile[price] for price in price_levels]
            
            # 归一化成交量
            total_volume = sum(volumes)
            if total_volume == 0:
                return self._calculate_equal_distribution(
                    config.entry_price,
                    abs(config.entry_price - config.stop_loss),
                    config.num_layers,
                    direction
                )
                
            normalized_volumes = [v/total_volume for v in volumes]
            
            # 基于成交量分布计算价格水平
            cumulative_volumes = np.cumsum(normalized_volumes)
            target_levels = np.linspace(0, 1, config.num_layers)
            
            prices = []
            for target in target_levels:
                idx = np.searchsorted(cumulative_volumes, target)
                if idx >= len(price_levels):
                    idx = len(price_levels) - 1
                prices.append(price_levels[idx])
            
            return sorted(prices, reverse=(direction=='sell'))

        except Exception as e:
            logging.error(f"Error calculating volume-based distribution: {e}")
            return self._calculate_equal_distribution(
                config.entry_price,
                abs(config.entry_price - config.stop_loss),
                config.num_layers,
                direction
            )

    async def _calculate_volume_distribution(
        self,
        config: LayerConfig,
        market_data: Dict,
        num_layers: int
    ) -> List[float]:
        """计算交易量分布"""
        try:
            base_volume = config.volume_profile.get('base_volume', 0.01)
            
            # 计算基于风险的量
            account_size = market_data.get('account_size', 0)
            risk_percent = market_data.get('risk_percent', 0.02)
            risk_amount = account_size * risk_percent
            
            # 根据层级调整交易量
            volumes = []
            total_weight = sum(range(1, num_layers + 1))
            
            for i in range(num_layers):
                layer_weight = (i + 1) / total_weight
                volume = base_volume * layer_weight
                volumes.append(round(volume, 2))
            
            return volumes

        except Exception as e:
            logging.error(f"Error calculating volume distribution: {e}")
            return [base_volume] * num_layers

    def _calculate_risk_reward_ratio(
        self,
        entry_price: float,
        stop_loss: float,
        take_profit: float,
        direction: str
    ) -> float:
        """计算风险收益比"""
        try:
            risk = abs(entry_price - stop_loss)
            if risk == 0:
                return 0
                
            reward = abs(take_profit - entry_price)
            return round(reward / risk, 2)
            
        except Exception as e:
            logging.error(f"Error calculating risk reward ratio: {e}")
            return 0

    def _calculate_breakeven_price(
        self,
        entry_price: float,
        stop_loss: float,
        direction: str
    ) -> float:
        """计算保本价格"""
        try:
            # 基本保本价格就是入场价格
            return round(entry_price, 5)
            
        except Exception as e:
            logging.error(f"Error calculating breakeven price: {e}")
            return entry_price

    def _get_layer_take_profits(
        self,
        base_take_profits: List[float],
        layer_index: int,
        total_layers: int
    ) -> List[float]:
        """根据层级获取个性化止盈价格"""
        try:
            # 越靠前的层级设置越多的止盈目标
            num_tps = len(base_take_profits)
            layer_position = (total_layers - layer_index) / total_layers
            
            # 第一层使用所有止盈
            if layer_index == 0:
                return base_take_profits
                
            # 最后一层只使用第一个止盈
            if layer_index == total_layers - 1:
                return [base_take_profits[0]]
                
            # 中间层根据位置使用不同数量的止盈
            num_layer_tps = max(1, int(num_tps * layer_position))
            return base_take_profits[:num_layer_tps]
            
        except Exception as e:
            logging.error(f"Error getting layer take profits: {e}")
            return [base_take_profits[0]] if base_take_profits else []

