import asyncio
import logging
import numpy as np
from typing import Dict, List, Optional
from datetime import datetime, timedelta
from .base_strategy import BaseStrategy

class HFTScalpingStrategy(BaseStrategy):
    def __init__(self, trade_manager):
        super().__init__(trade_manager)
        self.vwap_data = {}
        self.rsi_data = {}
        self.bb_data = {}
        self.config = {
            'rsi_period': 14,
            'rsi_overbought': 70,
            'rsi_oversold': 30,
            'bb_period': 20,
            'bb_std': 2,
            'min_profit_ticks': 3,
            'max_position_time': 300,  # 5分钟
            'risk_reward_ratio': 1.5
        }



    async def calculate_vwap(self, symbol: str, candles: List[Dict]):
        """计算VWAP"""
        try:
            if not candles:
                logging.warning(f"{symbol} - No candles provided for VWAP calculation")
                return None
                
            # For single candle, use typical price
            if len(candles) == 1:
                candle = candles[0]
                if not all(k in candle for k in ['high', 'low', 'close']):
                    logging.warning(f"{symbol} - Invalid candle data for VWAP")
                    return None
                typical_price = (candle['high'] + candle['low'] + candle['close']) / 3
                logging.debug(f"{symbol} - Using typical price as VWAP for single candle: {typical_price:.2f}")
                return typical_price
                
            # Normal VWAP calculation for multiple candles
            cumulative_pv = 0
            cumulative_volume = 0
            
            for candle in candles:
                if not all(k in candle for k in ['high', 'low', 'close']):
                    continue
                typical_price = (candle['high'] + candle['low'] + candle['close']) / 3
                # Use 1.0 as default volume if not available
                volume = candle.get('volume', 1.0)
                cumulative_pv += typical_price * volume
                cumulative_volume += volume
            
            if cumulative_volume == 0:
                logging.warning(f"{symbol} - No valid volume data for VWAP calculation")
                # Fall back to simple average
                prices = [(c['high'] + c['low'] + c['close'])/3 for c in candles if all(k in c for k in ['high', 'low', 'close'])]
                if prices:
                    vwap = sum(prices) / len(prices)
                    logging.debug(f"{symbol} - Using simple average as VWAP fallback: {vwap:.2f}")
                    return vwap
                return None
                
            vwap = cumulative_pv / cumulative_volume
            logging.debug(f"{symbol} - VWAP calculated from {len(candles)} candles: {vwap:.2f}")
            return vwap
            
        except Exception as e:
            logging.error(f"{symbol} - Error calculating VWAP: {str(e)}")
            return None
        
    async def calculate_rsi(self, prices: List[float], period: int = 14):
        """计算RSI"""
        try:
            if len(prices) < 2:
                logging.warning(f"Too few prices for RSI calculation, minimum 2 needed")
                return None
                
            # For very limited data, calculate simple momentum RSI
            if len(prices) == 2:
                change = prices[1] - prices[0]
                if change > 0:
                    rsi = 100 - (100 / (1 + abs(change/prices[0])))
                elif change < 0:
                    rsi = 100 / (1 + abs(change/prices[0]))
                else:
                    rsi = 50
                logging.debug(f"Simple momentum RSI calculated from 2 prices: {rsi:.2f}")
                return rsi
                
            # Normal RSI calculation for more data
            actual_period = min(period, len(prices) - 1)
            deltas = np.diff(prices)
            gains = np.where(deltas > 0, deltas, 0)
            losses = np.where(deltas < 0, -deltas, 0)
            
            avg_gain = np.mean(gains[:actual_period])
            avg_loss = np.mean(losses[:actual_period])
            
            if avg_loss == 0:
                if avg_gain == 0:
                    rsi = 50  # No movement
                else:
                    rsi = 100  # Only gains
            else:
                rs = avg_gain / avg_loss
                rsi = 100 - (100 / (1 + rs))
            
            logging.debug(f"RSI calculated with period {actual_period} from {len(prices)} prices: {rsi:.2f}")
            return rsi
            
        except Exception as e:
            logging.error(f"Error calculating RSI: {str(e)}")
            return None
        
    async def calculate_bollinger_bands(self, prices: List[float], period: int = 20, std: int = 2):
        """计算布林带"""
        try:
            # Adjust period based on available data
            actual_period = min(period, len(prices))
            if actual_period < 2:
                logging.warning(f"Too few prices for Bollinger Bands calculation, minimum 2 needed")
                return None
                
            prices_array = np.array(prices[-actual_period:])
            if not np.all(np.isfinite(prices_array)):
                logging.warning("Invalid prices detected in Bollinger Bands calculation")
                return None
                
            sma = np.mean(prices_array)
            std_dev = np.std(prices_array)
            
            bb = {
                'middle': sma,
                'upper': sma + (std_dev * std),
                'lower': sma - (std_dev * std)
            }
            
            logging.debug(f"Bollinger Bands calculated with period {actual_period} from {len(prices)} prices: "
                         f"Middle={bb['middle']:.2f}, Upper={bb['upper']:.2f}, Lower={bb['lower']:.2f}")
            return bb
            
        except Exception as e:
            logging.error(f"Error calculating Bollinger Bands: {str(e)}")
            return None        

    async def check_scalping_opportunity(self, symbol: str, current_price: float):
        """检查剥头皮机会"""
        try:
            logging.info(f"Checking scalping opportunity for {symbol} at price {current_price}")
            
            # 获取K线数据
            candles = await self.trade_manager.get_candles(symbol, '1m', 100)
            if not candles:
                logging.warning(f"{symbol} - No candle data available")
                return None
                
            # 计算技术指标
            prices = [c['close'] for c in candles]
            if len(prices) == 1:
                # Use current price and last candle close for minimal analysis
                prices = [prices[0], current_price]
                logging.info(f"{symbol} - Using current price {current_price:.2f} with last close {prices[0]:.2f}")
            
            # 并行计算所有指标
            vwap_task = asyncio.create_task(self.calculate_vwap(symbol, candles))
            rsi_task = asyncio.create_task(self.calculate_rsi(prices))
            bb_task = asyncio.create_task(self.calculate_bollinger_bands(prices))
            
            vwap = await vwap_task
            rsi = await rsi_task
            bb = await bb_task
            
            if not all([vwap, rsi, bb]):
                logging.warning(f"{symbol} - Missing indicators: VWAP={vwap is not None}, RSI={rsi is not None}, BB={bb is not None}")
                return None
                
            logging.info(f"{symbol} - Indicators: VWAP={vwap:.2f}, RSI={rsi:.2f}, BB_lower={bb['lower']:.2f}, BB_upper={bb['upper']:.2f}")
            
            # 策略逻辑
            signal = None
            
            # 超卖区域的做多机会
            if (current_price < bb['lower'] and 
                rsi < self.config['rsi_oversold'] and 
                current_price < vwap):
                logging.info(f"{symbol} - Oversold conditions met: Price < BB_lower ({current_price:.2f} < {bb['lower']:.2f}), "
                           f"RSI < {self.config['rsi_oversold']} ({rsi:.2f}), Price < VWAP ({current_price:.2f} < {vwap:.2f})")
                signal = {
                    'action': 'buy',
                    'entry_price': current_price,
                    'stop_loss': current_price - (self.config['min_profit_ticks'] * 2),
                    'take_profit': current_price + (self.config['min_profit_ticks'] * 3)
                }
                
            # 超买区域的做空机会
            elif (current_price > bb['upper'] and 
                  rsi > self.config['rsi_overbought'] and 
                  current_price > vwap):
                logging.info(f"{symbol} - Overbought conditions met: Price > BB_upper ({current_price:.2f} > {bb['upper']:.2f}), "
                           f"RSI > {self.config['rsi_overbought']} ({rsi:.2f}), Price > VWAP ({current_price:.2f} > {vwap:.2f})")
                signal = {
                    'action': 'sell',
                    'entry_price': current_price,
                    'stop_loss': current_price + (self.config['min_profit_ticks'] * 2),
                    'take_profit': current_price - (self.config['min_profit_ticks'] * 3)
                }
                
            if signal:
                signal.update({
                    'symbol': symbol,
                    'strategy': 'hft_scalping',
                    'timeframe': '1m',
                    'metadata': {
                        'vwap': vwap,
                        'rsi': rsi,
                        'bollinger_bands': bb
                    }
                })
                logging.info(f"Found {signal['action']} opportunity for {symbol}")
                
            return signal
            
        except Exception as e:
            logging.error(f"Error in check_scalping_opportunity: {e}")
            return None
            
    async def monitor_symbol(self, symbol: str):
        """监控单个交易对"""
        failures = 0  # 连续失败计数
        last_error = None  # 上一次错误信息
        last_price = None
        
        try:
            logging.info(f"Started monitoring {symbol}")
            while self.active:
                try:
                    current_price = await self.trade_manager.get_current_price(symbol)
                    if not current_price:
                        logging.warning(f"{symbol} - Failed to get current price")
                        await asyncio.sleep(1)
                        continue
                    
                    if last_price is None or abs(current_price['ask'] - last_price) > 0.01:
                        logging.info(f"{symbol} - Current ask price: {current_price['ask']}")
                        last_price = current_price['ask']
                        
                    signal = await self.check_scalping_opportunity(symbol, current_price['ask'])
                    
                    if signal:
                        logging.info(f"{symbol} - Executing {signal['action']} signal - Entry: {signal['entry_price']}, "
                                   f"SL: {signal['stop_loss']}, TP: {signal['take_profit']}")
                        await self.trade_manager.handle_signal(signal)
                        failures = 0  # 重置失败计数
                        last_error = None  # 清除错误记录
                    
                    # 动态调整检查间隔
                    await asyncio.sleep(max(1, min(failures, 5)))
                        
                except Exception as e:
                    failures += 1
                    error_msg = str(e)
                    
                    # 只在错误消息改变时才记录
                    if error_msg != last_error:
                        logging.error(f"Error in monitoring {symbol}: {error_msg}")
                        last_error = error_msg
                    
                    if failures > 10:  # 连续失败超过10次
                        logging.error(f"Too many failures monitoring {symbol}, stopping...")
                        break
                    
                    await asyncio.sleep(min(failures, 10))  # 最多等待10秒
                
        except Exception as e:
            logging.error(f"Fatal error in monitoring {symbol}: {e}")
        finally:
            if symbol in self._monitoring_tasks:
                del self._monitoring_tasks[symbol]
                logging.info(f"Stopped monitoring {symbol}")

    async def start(self, symbols: List[str]):
        """启动策略"""
        await super().start()
        self._monitoring_tasks = {}  # 重置任务列表
        
        for symbol in symbols:
            if symbol not in self._monitoring_tasks:
                task = asyncio.create_task(self.monitor_symbol(symbol))
                self._monitoring_tasks[symbol] = task
                
        logging.info(f"Started monitoring symbols: {symbols}")  # 只记录一次