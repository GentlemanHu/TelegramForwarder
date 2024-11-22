import numpy as np
from typing import List, Dict, Tuple, Optional
import logging
from dataclasses import dataclass
from enum import Enum
from datetime import datetime
from .trade_manager import TradeManager

class LayerDistributionType(Enum):
    EQUAL = "equal"
    DYNAMIC = "dynamic"
    WEIGHTED = "weighted"
    MARKET_MOMENTUM = "market_momentum"

@dataclass
class LayerDistribution:
    entry_prices: List[float]
    volumes: List[float]
    take_profits: List[List[float]]  # Each layer can have multiple TPs
    stop_loss: float

class SmartLayerManager:
    def __init__(self, trade_manager: 'TradeManager'):
        self.trade_manager = trade_manager
        
    async def calculate_layer_distribution(
        self,
        symbol: str,
        direction: str,
        base_price: float,
        price_range: Optional[Tuple[float, float]],
        num_layers: int,
        account_size: float,
        distribution_type: LayerDistributionType = LayerDistributionType.DYNAMIC
    ) -> LayerDistribution:
        """Calculate smart layer distribution"""
        try:
            # 1. Get market data
            market_data = await self._get_market_data(symbol)
            volatility = await self._calculate_volatility(symbol)
            momentum = await self._calculate_momentum(symbol)
            
            # 2. Determine price distribution
            if distribution_type == LayerDistributionType.EQUAL:
                entry_prices = await self._calculate_equal_distribution(
                    base_price, price_range, num_layers
                )
            elif distribution_type == LayerDistributionType.DYNAMIC:
                entry_prices = await self._calculate_dynamic_distribution(
                    base_price, price_range, num_layers, volatility
                )
            elif distribution_type == LayerDistributionType.MARKET_MOMENTUM:
                entry_prices = await self._calculate_momentum_distribution(
                    base_price, price_range, num_layers, momentum
                )
            else:
                entry_prices = await self._calculate_weighted_distribution(
                    base_price, price_range, num_layers, market_data
                )

            # 3. Calculate volume distribution
            volumes = await self._calculate_volume_distribution(
                num_layers, account_size, volatility
            )
            
            # 4. Calculate take profits for each layer
            take_profits = await self._calculate_layer_take_profits(
                entry_prices, direction, volatility, momentum
            )
            
            # 5. Calculate optimal stop loss
            stop_loss = await self._calculate_optimal_stop_loss(
                entry_prices, direction, volatility
            )
            
            return LayerDistribution(
                entry_prices=entry_prices,
                volumes=volumes,
                take_profits=take_profits,
                stop_loss=stop_loss
            )
            
        except Exception as e:
            logging.error(f"Error calculating layer distribution: {e}")
            raise

    async def _get_market_data(self, symbol: str) -> Dict:
        """Get comprehensive market data"""
        try:
            current_price = await self.trade_manager.get_current_price(symbol)
            
            # Get historical prices for analysis
            candles = await self.trade_manager.connection.get_candles(
                symbol=symbol,
                timeframe='5m',
                limit=100
            )
            
            return {
                'current_price': current_price,
                'historical_data': candles
            }
        except Exception as e:
            logging.error(f"Error getting market data: {e}")
            raise

    async def _calculate_volatility(self, symbol: str) -> float:
        """Calculate market volatility"""
        try:
            candles = await self.trade_manager.connection.get_candles(
                symbol=symbol,
                timeframe='5m',
                limit=20
            )
            
            if not candles:
                return 0.002  # Default volatility
                
            closes = [c['close'] for c in candles]
            returns = np.diff(np.log(closes))
            return float(np.std(returns))
            
        except Exception as e:
            logging.error(f"Error calculating volatility: {e}")
            return 0.002

    async def _calculate_momentum(self, symbol: str) -> float:
        """Calculate market momentum"""
        try:
            candles = await self.trade_manager.connection.get_candles(
                symbol=symbol,
                timeframe='5m',
                limit=20
            )
            
            if not candles:
                return 0
                
            closes = [c['close'] for c in candles]
            momentum = (closes[-1] - closes[0]) / closes[0]
            return float(momentum)
            
        except Exception as e:
            logging.error(f"Error calculating momentum: {e}")
            return 0

    async def _calculate_dynamic_distribution(
        self,
        base_price: float,
        price_range: Optional[Tuple[float, float]],
        num_layers: int,
        volatility: float
    ) -> List[float]:
        """Calculate dynamic price distribution based on volatility"""
        try:
            if price_range:
                min_price, max_price = price_range
            else:
                range_size = base_price * volatility * 5
                min_price = base_price - range_size
                max_price = base_price + range_size
            
            # Use exponential distribution for more layers near base price
            exp_points = np.exp(np.linspace(0, 1, num_layers))
            normalized_points = (exp_points - exp_points.min()) / (exp_points.max() - exp_points.min())
            
            # Calculate prices
            prices = min_price + normalized_points * (max_price - min_price)
            return prices.tolist()
            
        except Exception as e:
            logging.error(f"Error calculating dynamic distribution: {e}")
            raise

    async def _calculate_momentum_distribution(
        self,
        base_price: float,
        price_range: Optional[Tuple[float, float]],
        num_layers: int,
        momentum: float
    ) -> List[float]:
        """Calculate price distribution based on market momentum"""
        try:
            if price_range:
                min_price, max_price = price_range
            else:
                range_size = base_price * 0.01  # 1% range
                min_price = base_price - range_size
                max_price = base_price + range_size
            
            # Adjust distribution based on momentum
            momentum_factor = 1 + momentum
            points = np.linspace(0, 1, num_layers) ** momentum_factor
            
            # Calculate prices
            prices = min_price + points * (max_price - min_price)
            return prices.tolist()
            
        except Exception as e:
            logging.error(f"Error calculating momentum distribution: {e}")
            raise

    async def _calculate_volume_distribution(
        self,
        num_layers: int,
        account_size: float,
        volatility: float
    ) -> List[float]:
        """Calculate volume distribution for layers"""
        try:
            # Base volume calculation
            base_volume = account_size * 0.01 * (1 + volatility)  # Adjust for volatility
            
            # Create pyramid distribution
            volumes = []
            total_parts = sum(range(1, num_layers + 1))
            
            for i in range(num_layers, 0, -1):
                volume = (base_volume * i) / total_parts
                volumes.append(round(volume, 2))
            
            return volumes
            
        except Exception as e:
            logging.error(f"Error calculating volume distribution: {e}")
            raise

    async def _calculate_layer_take_profits(
        self,
        entry_prices: List[float],
        direction: str,
        volatility: float,
        momentum: float
    ) -> List[List[float]]:
        """Calculate take profits for each layer"""
        try:
            take_profits = []
            
            for i, entry_price in enumerate(entry_prices):
                layer_tps = []
                # More aggressive TPs for better positioned layers
                position_factor = (i + 1) / len(entry_prices)
                
                # Calculate TPs based on volatility and momentum
                tp1 = entry_price * (1 + (volatility * 2 * position_factor) * (1 if direction == 'buy' else -1))
                tp2 = entry_price * (1 + (volatility * 3 * position_factor) * (1 if direction == 'buy' else -1))
                tp3 = entry_price * (1 + (volatility * 4 * position_factor) * (1 if direction == 'buy' else -1))
                
                # Adjust TPs based on momentum
                momentum_adjust = 1 + (momentum * position_factor)
                layer_tps = [
                    round(tp1 * momentum_adjust, 5),
                    round(tp2 * momentum_adjust, 5),
                    round(tp3 * momentum_adjust, 5)
                ]
                
                take_profits.append(layer_tps)
            
            return take_profits
            
        except Exception as e:
            logging.error(f"Error calculating layer take profits: {e}")
            raise

    async def _calculate_optimal_stop_loss(
        self,
        entry_prices: List[float],
        direction: str,
        volatility: float
    ) -> float:
        """Calculate optimal stop loss based on volatility"""
        try:
            # Use the worst positioned entry as reference
            reference_price = entry_prices[0] if direction == 'buy' else entry_prices[-1]
            
            # Calculate stop loss distance based on volatility
            sl_distance = reference_price * volatility * 2
            
            # Calculate stop loss price
            stop_loss = reference_price * (1 - sl_distance if direction == 'buy' else 1 + sl_distance)
            
            return round(stop_loss, 5)
            
        except Exception as e:
            logging.error(f"Error calculating optimal stop loss: {e}")
            raise