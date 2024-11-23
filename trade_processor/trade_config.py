from dataclasses import dataclass, field
from typing import Dict, List, Optional, Any
import os
import json
import logging
import math
import sys
import os.path
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from config import Config

@dataclass
class BaseTradeConfig:
    """基础交易配置"""
    min_lot_size: float = 0.01  # 最小下单量
    max_lot_size: float = 100.0  # 最大下单量
    max_slippage: float = 10  # 最大滑点(点)
    default_slippage: float = 3  # 默认滑点(点)
    default_risk_percent: float = 1.0  # 默认风险百分比
    max_positions_per_symbol: int = 5  # 每个币种最大持仓数

@dataclass
class MonitoringConfig:
    """市场监控配置"""
    min_volume: float = 0.01
    max_layers: int = 5
    min_layers: int = 2
    atr_multiplier: float = 1.5
    volume_scale: List[float] = field(default_factory=lambda: [0.4, 0.3, 0.2, 0.1])
    price_check_interval: int = 1  # 秒
    entry_timeout: int = 3600  # 1小时

@dataclass
class SmartTradingConfig:
    """智能交易配置"""
    use_market_profile: bool = True  # 是否使用市场轮廓
    use_support_resistance: bool = True  # 是否使用支撑阻力
    use_momentum: bool = True  # 是否使用动量
    momentum_period: int = 14  # 动量周期
    volume_profile_periods: int = 24  # 成交量轮廓计算周期
    sr_lookback_periods: int = 100  # 支撑阻力回溯周期

@dataclass
class HFTConfig:
    """HFT策略配置"""
    enabled: bool = False
    symbols: List[str] = field(default_factory=lambda: ['BTCUSDm'])  # 要监控的交易对
    
    # 交易参数
    volume_per_trade: float = 0.01  # 每次交易量
    max_positions: int = 5  # 最大同时持仓数
    max_daily_trades: int = 100  # 每日最大交易次数
    
    # 技术指标参数
    rsi_period: int = 14
    rsi_overbought: int = 70
    rsi_oversold: int = 30
    bb_period: int = 20
    bb_std: int = 2
    
    # 风控参数
    min_profit_ticks: int = 3  # 最小获利点数
    max_loss_ticks: int = 6  # 最大损失点数
    max_position_time: int = 300  # 最大持仓时间(秒)
    risk_reward_ratio: float = 1.5  # 风险收益比
    
    # 性能参数
    check_interval: float = 0.1  # 检查间隔(秒)
    price_precision: int = 5  # 价格精度
    
    # 监控参数
    enable_performance_monitoring: bool = True  # 是否启用性能监控
    max_latency: float = 0.5  # 最大延迟(秒)
    monitor_interval: int = 60  # 监控统计间隔(秒)
    
    # Scalping策略参数
    hft_scalping: Dict[str, Any] = field(default_factory=lambda: {
        'enabled': True,  # 是否启用scalping策略
        'min_spread': 2,  # 最小价差(点)
        'max_spread': 20,  # 最大价差(点)
        'min_volume': 0.01,  # 最小交易量
        'profit_ticks': 5,  # 目标获利点数
        'stop_loss_ticks': 3,  # 止损点数
        'trailing_stop': True,  # 是否启用追踪止损
        'trailing_distance': 2,  # 追踪止损距离(点)
        'max_open_time': 60,  # 最大开仓时间(秒)
        'use_martingale': False,  # 是否使用马丁策略
        'martingale_multiplier': 2.0,  # 马丁倍数
        'max_martingale_orders': 3,  # 最大马丁订单数
        'time_filters': {  # 交易时间过滤
            'enabled': True,
            'trading_hours': {
                'start': '00:00',
                'end': '23:59'
            },
            'exclude_weekends': True
        }
    })

@dataclass
class TradeConfig(BaseTradeConfig):
    """统一交易配置"""
    # 从基础配置获取API密钥
    _base_config: Config = field(default_factory=Config, repr=False)
    
    # API配置
    meta_api_token: str = field(default_factory=lambda: os.getenv('META_API_TOKEN'))
    account_id: str = field(default_factory=lambda: os.getenv('ACCOUNT_ID'))
    openai_api_key: str = field(default_factory=lambda: os.getenv('OPENAI_API_KEY'))
    openai_base_url: str = field(default_factory=lambda: os.getenv('OPENAI_BASE_URL', 'https://api.openai.com/v1'))
    
    # 子配置
    monitoring: MonitoringConfig = field(default_factory=MonitoringConfig)
    smart_trading: SmartTradingConfig = field(default_factory=SmartTradingConfig)
    hft: HFTConfig = field(default_factory=HFTConfig)
    
    # 风控设置
    risk_settings: Dict = field(default_factory=lambda: {
        'max_daily_trades': 20,  # 每日最大交易次数
        'max_daily_drawdown': 5.0,  # 每日最大回撤(%)
        'max_position_size': 10.0,  # 单个仓位最大资金比例(%)
        'max_total_risk': 20.0  # 总风险敞口(%)
    })

    def __post_init__(self):
        """初始化后处理"""
        # 设置API密钥
        if not self.meta_api_token:
            self.meta_api_token = self._base_config.meta_api_token
        if not self.account_id:
            self.account_id = self._base_config.account_id
            
        # 启用HFT配置
        self.hft.enabled = True
        self.hft.symbols = ['BTCUSDm']  # 设置要交易的币种
        
        # 验证配置
        self._validate_config()
        
    def _validate_config(self):
        """验证配置有效性"""
        if not self.meta_api_token:
            raise ValueError("MetaAPI token not found")
        if not self.account_id:
            raise ValueError("Account ID not found")
        if self.hft.enabled and not self.hft.symbols:
            raise ValueError("HFT enabled but no symbols specified")
            
    def to_dict(self) -> Dict[str, Any]:
        """转换为字典格式"""
        return {
            'meta_api_token': self.meta_api_token,
            'account_id': self.account_id,
            'monitoring': self.monitoring.__dict__,
            'smart_trading': self.smart_trading.__dict__,
            'hft': {
                **self.hft.__dict__,
                'hft_scalping': self.hft.hft_scalping
            },
            'risk_settings': self.risk_settings
        }
        
    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> 'TradeConfig':
        """从字典创建配置"""
        config = cls()
        
        # 更新API配置
        config.meta_api_token = data.get('meta_api_token', config.meta_api_token)
        config.account_id = data.get('account_id', config.account_id)
        
        # 更新子配置
        if 'monitoring' in data:
            config.monitoring = MonitoringConfig(**data['monitoring'])
        if 'smart_trading' in data:
            config.smart_trading = SmartTradingConfig(**data['smart_trading'])
        if 'hft' in data:
            hft_data = data['hft']
            if 'hft_scalping' in hft_data:
                hft_data['hft_scalping'] = {**config.hft.hft_scalping, **hft_data['hft_scalping']}
            config.hft = HFTConfig(**hft_data)
            
        # 更新风控设置
        if 'risk_settings' in data:
            config.risk_settings.update(data['risk_settings'])
            
        return config

    def save_to_file(self, filepath: str):
        """保存配置到文件"""
        with open(filepath, 'w') as f:
            json.dump(self.to_dict(), f, indent=4)

    @classmethod
    def load_from_file(cls, filepath: str) -> 'TradeConfig':
        """从文件加载配置"""
        with open(filepath, 'r') as f:
            data = json.load(f)
        return cls.from_dict(data)