from dataclasses import dataclass
import logging
import math
from typing import Dict, List, Optional




@dataclass
class LayerConfig:
    account_min: float      # 最小账户金额
    account_max: float      # 最大账户金额
    lot_size: float        # 基础仓位大小
    num_layers: int        # 默认分层数量
    risk_percent: float    # 风险百分比

@dataclass
class TradeConfig:
    # API配置
    meta_api_token: str
    account_id: str
    openai_api_key: str
    openai_base_url: Optional[str] = None
    
    # 交易配置
    default_risk_percent: float = 2.0  # 默认风险百分比
    max_risk_percent: float = 5.0      # 最大风险百分比
    max_layers: int = 7                # 最大分层数
    min_lot_size: float = 0.01         # 最小仓位
    
    # 分层配置
    layer_configs: List[LayerConfig] = None
    
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
        risk_percent = min(risk_percent, self.max_risk_percent)
        
        # 计算风险金额
        risk_amount = (account_size * risk_percent) / 100
        
        # 根据风险点数和合约大小计算仓位
        position_size = (risk_amount / risk_points)
        position_size = max(position_size, self.min_lot_size)
        position_size = min(position_size, config.lot_size * 2)  # 限制最大仓位
        
        # 四舍五入到合适的精度
        precision = int(-math.log10(self.min_lot_size))
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
                    size = max(size, self.min_lot_size)
                    sizes.append(size)
            
            elif distribution == 'reverse_pyramid':
                # 反金字塔式分配，前面的仓位较大
                factor = 2 / (num_layers * (num_layers + 1))
                sizes = []
                for i in range(num_layers):
                    size = base_size * (num_layers - i) * factor * num_layers
                    # 确保不小于最小仓位
                    size = max(size, self.min_lot_size)
                    sizes.append(size)
            
            else:
                sizes = [base_size] * num_layers
            
            # 规范化所有仓位大小
            precision = int(-math.log10(self.min_lot_size))
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
        return max(risk_adjusted_lot, self.min_lot_size)