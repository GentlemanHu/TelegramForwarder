from dataclasses import dataclass, field
from typing import Dict, List, Optional, Any
import os
import json
import logging
import math

@dataclass
class LayerConfig:
    account_min: float      # 最小账户金额
    account_max: float      # 最大账户金额
    lot_size: float        # 基础仓位大小
    num_layers: int        # 默认分层数量
    risk_percent: float    # 风险百分比

@dataclass
class MonitoringConfig:
    """市场监控配置"""
    min_volume: float = 0.01
    max_layers: int = 5
    min_layers: int = 2
    atr_multiplier: float = 1.5
    volume_scale: List[float] = field(default_factory=lambda: [0.4, 0.3, 0.2, 0.1])
    price_check_interval: int = 1;  # 秒
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

# TODO: 暂时未使用，后续可能用于AI分析
# @dataclass
# class GPTConfig:
#     """GPT配置"""
#     model: str = "gpt-4"  # 使用的模型
#     max_tokens: int = 500
#     temperature: float = 0.7
#     use_streaming: bool = True
#     prompt_template: str = """
#     分析以下市场数据并提供交易建议：
#     Symbol: {symbol}
#     Current Price: {price}
#     Market Context: {context}
#     Technical Indicators: {indicators}
    
#     请提供：
#     1. 市场分析
#     2. 建议的入场区间
#     3. 目标价格
#     4. 止损位置
#     5. 风险评估
#     """
    
@dataclass
class TradeConfig:
    """统一交易配置"""
    meta_api_token: str = field(default_factory=lambda: os.getenv('META_API_TOKEN'))
    account_id: str = field(default_factory=lambda: os.getenv('ACCOUNT_ID'))
    openai_api_key: str = field(default_factory=lambda: os.getenv('OPENAI_API_KEY'))
    openai_base_url: Optional[str] = None
    
    # 子配置
    monitoring: MonitoringConfig = field(default_factory=MonitoringConfig)
    smart_trading: SmartTradingConfig = field(default_factory=SmartTradingConfig)
    # gpt: GPTConfig = field(default_factory=GPTConfig)  # 暂时注释掉未使用的配置
    
    # 交易限制
    min_lot_size: float = 0.01  # 最小下单量
    max_lot_size: float = 100.0  # 最大下单量
    max_slippage: float = 10  # 最大滑点(点)
    default_slippage: float = 3  # 默认滑点(点)
    
    # 全局交易设置
    default_risk_percent: float = 1.0  # 默认风险百分比
    max_positions_per_symbol: int = 5  # 每个币种最大持仓数
    default_execution_mode: str = 'smart'  # 默认执行模式 standard|smart;
    
    # 分层设置
    layer_settings: Dict = field(default_factory=lambda: {
        'default_count': 3,
        'min_distance': 50,  # 最小层级间距(点)
        'max_distance': 500,  # 最大层级间距(点)
        'volume_scale': [0.4, 0.3, 0.2, 0.1]  # 默认的量能分配比例
    })
    
    # 风控设置
    risk_settings: Dict = field(default_factory=lambda: {
        'max_daily_trades': 20,  # 每日最大交易次数
        'max_daily_drawdown': 5.0,  # 每日最大回撤(%)
        'max_position_size': 10.0,  # 单个仓位最大资金比例(%)
        'max_total_risk': 20.0  # 总风险敞口(%)
    })
    
    # 分层配置
    layer_configs: List[LayerConfig] = None
    
    @classmethod
    def load_from_file(cls, filepath: str) -> 'TradeConfig':
        """从文件加载配置"""
        try:
            with open(filepath, 'r') as f:
                config_dict = json.load(f)
            return cls(**config_dict)
        except Exception as e:
            print(f"Error loading config: {e}")
            return cls()  # 返回默认配置
            
    def save_to_file(self, filepath: str):
        """保存配置到文件"""
        try:
            config_dict = {
                'meta_api_token': self.meta_api_token,
                'account_id': self.account_id,
                'openai_api_key': self.openai_api_key,
                'openai_base_url': self.openai_base_url,
                'monitoring': self.monitoring.__dict__,
                'smart_trading': self.smart_trading.__dict__,
                # 'gpt': self.gpt.__dict__,  # 暂时注释掉未使用的配置
                'min_lot_size': self.min_lot_size,
                'max_lot_size': self.max_lot_size,
                'max_slippage': self.max_slippage,
                'default_slippage': self.default_slippage,
                'default_risk_percent': self.default_risk_percent,
                'max_positions_per_symbol': self.max_positions_per_symbol,
                'default_execution_mode': self.default_execution_mode,
                'layer_settings': self.layer_settings,
                'risk_settings': self.risk_settings,
                'layer_configs': [config.__dict__ for config in self.layer_configs]
            }
            with open(filepath, 'w') as f:
                json.dump(config_dict, f, indent=4)
        except Exception as e:
            print(f"Error saving config: {e}")
            
    def __post_init__(self):
        if self.layer_configs is None:
            self.layer_configs = [
                LayerConfig(
                    account_min=50,
                    account_max=500,
                    lot_size=0.01,
                    num_layers=3,
                    risk_percent=1.0
                ),
                LayerConfig(
                    account_min=500,
                    account_max=2000,
                    lot_size=0.03,
                    num_layers=5,
                    risk_percent=1.5
                ),
                LayerConfig(
                    account_min=2000,
                    account_max=5000,
                    lot_size=0.05,
                    num_layers=5,
                    risk_percent=2.0
                ),
                LayerConfig(
                    account_min=5000,
                    account_max=float('inf'),
                    lot_size=0.1,
                    num_layers=7,
                    risk_percent=2.0
                )
            ]

    def get_layer_config(self, account_size: float) -> LayerConfig:
        """根据账户规模获取对应的分层配置"""
        for config in self.layer_configs:
            if config.account_min <= account_size <= config.account_max:
                return config
        return self.layer_configs[-1]

    def calculate_base_position(self, account_size: float, risk_points: float, risk_percent: Optional[float] = None) -> float:
        """计算基础仓位大小"""
        config = self.get_layer_config(account_size)
        
        # 使用配置的风险百分比或默认值
        risk_percent = risk_percent or config.risk_percent
        risk_percent = min(risk_percent, 5.0)
        
        # 计算风险金额
        risk_amount = (account_size * risk_percent) / 100
        
        # 根据风险点数和合约大小计算仓位
        position_size = (risk_amount / risk_points)
        position_size = max(position_size, 0.01)
        position_size = min(position_size, config.lot_size * 2)  # 限制最大仓位
        
        # 四舍五入到合适的精度
        precision = int(-math.log10(0.01))
        return round(position_size, precision)

    def calculate_layer_sizes(self, 
                            account_size: float, 
                            risk_points: float,
                            num_layers: int,
                            distribution: str = 'equal',
                            total_risk_percent: Optional[float] = None) -> List[float]:
        """
        计算分层仓位大小
        
        Args:
            account_size: 账户规模
            risk_points: 风险点数
            num_layers: 层数
            distribution: 分配方式 ('equal', 'pyramid', 'reverse_pyramid')
            total_risk_percent: 总风险百分比
            
        Returns:
            每层的仓位大小列表
        """
        try:
            logging.info(f"Calculating layer sizes - Account: {account_size}, Risk Points: {risk_points}, "
                        f"Layers: {num_layers}, Distribution: {distribution}")
            
            config = self.get_layer_config(account_size)
            
            # 计算每层的风险百分比
            layer_risk_percent = (total_risk_percent or config.risk_percent) / num_layers
            
            # 计算基础仓位
            base_size = self.calculate_base_position(
                account_size=account_size,
                risk_points=risk_points,
                risk_percent=layer_risk_percent
            )
            
            logging.info(f"Base position size calculated: {base_size}")
            
            if distribution == 'equal':
                sizes = [base_size] * num_layers
            
            elif distribution == 'pyramid':
                # 金字塔式分配，后面的仓位逐渐增加
                factor = 2 / (num_layers * (num_layers + 1))  # 确保总和为1
                sizes = []
                for i in range(num_layers):
                    size = base_size * (i + 1) * factor * num_layers
                    # 确保不小于最小仓位
                    size = max(size, 0.01)
                    sizes.append(size)
            
            elif distribution == 'reverse_pyramid':
                # 反金字塔式分配，前面的仓位较大
                factor = 2 / (num_layers * (num_layers + 1))
                sizes = []
                for i in range(num_layers):
                    size = base_size * (num_layers - i) * factor * num_layers
                    # 确保不小于最小仓位
                    size = max(size, 0.01)
                    sizes.append(size)
            
            else:
                sizes = [base_size] * num_layers
            
            # 规范化所有仓位大小
            precision = int(-math.log10(0.01))
            sizes = [round(size, precision) for size in sizes]
            
            logging.info(f"Calculated layer sizes: {sizes}")
            return sizes
            
        except Exception as e:
            logging.error(f"Error in calculate_layer_sizes: {e}")
            raise

    def calculate_position_size(self, account_size: float, risk_amount: float) -> float:
        """计算仓位大小"""
        layer_config = self.get_layer_config(account_size)
        base_lot = layer_config.lot_size
        
        # 根据风险金额调整lot size
        risk_adjusted_lot = (risk_amount / account_size) * base_lot
        
        # 确保不小于最小lot size
        return max(risk_adjusted_lot, 0.01)