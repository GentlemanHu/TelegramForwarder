from typing import Dict, List, Optional, Any
from dataclasses import dataclass
from datetime import datetime
import logging
import asyncio
import uuid

from trade_processor.trade_manager import TradeManager

@dataclass
class Position:
    id: str
    symbol: str
    entry_price: Optional[float]
    stop_loss: Optional[float]
    take_profits: List[float]
    volume: float
    direction: str  # 'buy' or 'sell'
    entry_type: str  # 'market' or 'limit'
    layer_index: Optional[int]
    round_id: str
    status: str = 'pending'  # pending, active, partially_closed, closed
    realized_profit: float = 0.0
    close_price: Optional[float] = None
    close_time: Optional[datetime] = None
    metadata: Dict[str, Any] = None



from typing import Dict, List, Optional, Any, Tuple
from dataclasses import dataclass
from datetime import datetime
import logging
import asyncio
import uuid

class PositionManager:
    
    
    def __init__(self, trade_manager: 'TradeManager'):
        self.trade_manager:TradeManager = trade_manager
        self.active_positions: Dict[str, List[Position]] = {}
        self.closed_positions: Dict[str, List[Position]] = {}
        self.position_updates: Dict[str, asyncio.Queue] = {}



    
    async def create_layered_positions(self, signal: Dict[str, Any]) -> Optional[str]:
        """创建分层持仓"""
        try:
            # 获取账户信息和配置
            account_info = await self.trade_manager.get_account_info()
            account_size = account_info['balance']
            layer_config = self.trade_manager.config.get_layer_config(account_size)
            
            # 详细日志记录初始配置
            logging.info(f"Creating layered positions with signal: {signal}")
            logging.info(f"Account size: {account_size}, Layer config: {layer_config}")
            
            # 生成round_id
            round_id = str(uuid.uuid4())
            self.active_positions[round_id] = []

            # 确定层数和分布
            # 如果signal中指定了layers.enabled=false，仍然使用分层时，将其设为1层
            num_layers = 1
            if signal['layers']['enabled']:
                num_layers = signal['layers'].get('count', layer_config.num_layers)
            logging.info(f"Using {num_layers} layers for position creation")

            # 计算价格范围和风险点数
            entry_min = entry_max = entry_price = None
            price_step = 0
            
            if signal['entry_type'] == 'limit' and signal['entry_range']:
                entry_min = signal['entry_range']['min']
                entry_max = signal['entry_range']['max']
                if num_layers > 1:
                    price_step = (entry_max - entry_min) / (num_layers - 1)
                logging.info(f"Price range: {entry_min}-{entry_max}, Step: {price_step}")
            else:
                current_price = await self.trade_manager.get_current_price(signal['symbol'])
                entry_price = current_price['ask'] if signal['action'] == 'buy' else current_price['bid']
                entry_min = entry_max = entry_price
                logging.info(f"Using market price: {entry_price}")

            # 计算风险点数
            risk_points = None
            if signal.get('stop_loss'):
                risk_points = abs(entry_min - signal['stop_loss'])
            else:
                risk_points = entry_min * 0.01  # 默认1%风险
            logging.info(f"Risk points: {risk_points}")

            # 计算每层的仓位大小
            try:
                layer_sizes = self.trade_manager.config.calculate_layer_sizes(
                    account_size=account_size,
                    risk_points=risk_points,
                    num_layers=num_layers,
                    distribution=signal['layers'].get('distribution', 'equal')
                )
                logging.info(f"Calculated layer sizes: {layer_sizes}")
            except Exception as e:
                logging.error(f"Error calculating layer sizes: {e}")
                raise

            # 创建每一层的持仓
            for i in range(num_layers):
                try:
                    # 计算当前层的入场价
                    if price_step != 0:
                        entry_price = entry_min + (i * price_step)
                    
                    # 构建订单参数
                    order_params = {
                        'symbol': signal['symbol'],
                        'direction': signal['action'],
                        'volume': layer_sizes[i],
                        'entry_type': signal['entry_type'],
                        'entry_price': entry_price,
                        'stop_loss': signal.get('stop_loss'),
                        'take_profits': signal.get('take_profits', [])
                    }
                    
                    logging.info(f"Placing order for layer {i+1}/{num_layers} with params: {order_params}")
                    
                    # 下单
                    order_result = await self.trade_manager.place_order(**order_params)
                    if not order_result:
                        logging.error(f"No order result returned for layer {i+1}")
                        continue
                    
                    logging.info(f"Order placed successfully for layer {i+1}: {order_result}")

                    # 创建持仓对象
                    position = Position(
                        id=order_result['orderId'],
                        symbol=signal['symbol'],
                        entry_price=entry_price,
                        stop_loss=signal.get('stop_loss'),
                        take_profits=signal.get('take_profits', []),
                        volume=layer_sizes[i],
                        direction=signal['action'],
                        entry_type=signal['entry_type'],
                        layer_index=i,
                        round_id=round_id,
                        metadata={
                            'creation_time': datetime.now().isoformat(),
                            'signal': signal,
                            'layer_info': {
                                'total_layers': num_layers,
                                'current_layer': i + 1,
                                'distribution': signal['layers'].get('distribution', 'equal')
                            }
                        }
                    )
                    
                    self.active_positions[round_id].append(position)
                    
                except Exception as e:
                    logging.error(f"Error creating position for layer {i+1}: {e}")
                    if hasattr(e, '__dict__'):
                        logging.error(f"Error details: {e.__dict__}")

            # 检查是否成功创建了任何持仓
            if not self.active_positions[round_id]:
                logging.error("No positions were created successfully")
                return None

            num_created = len(self.active_positions[round_id])
            logging.info(f"Successfully created {num_created}/{num_layers} positions")
            return round_id

        except Exception as e:
            logging.error(f"Error in create_layered_positions: {e}")
            if hasattr(e, '__dict__'):
                logging.error(f"Error details: {e.__dict__}")
            return None

    def _log_position_details(self, position: Position):
        """记录持仓详情"""
        logging.info(f"""
Position Details:
- ID: {position.id}
- Symbol: {position.symbol}
- Direction: {position.direction}
- Volume: {position.volume}
- Entry Type: {position.entry_type}
- Entry Price: {position.entry_price}
- Stop Loss: {position.stop_loss}
- Take Profits: {position.take_profits}
- Layer Index: {position.layer_index}
- Status: {position.status}
""")

    async def create_single_position(self, signal: Dict[str, Any]) -> Optional[str]:
        """创建单个持仓"""
        try:
            # 生成round_id
            round_id = str(uuid.uuid4())
            self.active_positions[round_id] = []
            
            logging.info(f"Creating single position with signal: {signal}")

            # 获取账户信息
            account_info = await self.trade_manager.get_account_info()
            account_size = account_info['balance']
            logging.info(f"Account size: {account_size}")

            # 计算仓位大小
            try:
                volume = 0.01
                # volume = self.trade_manager.config.calculate_position_size(
                #     account_size=account_size,
                #     risk_points=signal.get('risk_points', account_size * 0.01)
                # )
                # logging.info(f"Calculated position size: {volume}")
            except Exception as e:
                logging.error(f"Error calculating position size: {e}")
                raise

            # 构建订单参数
            order_params = {
                'symbol': signal['symbol'],
                'direction': signal['action'],
                'volume': volume,
                'entry_type': signal['entry_type'],
                'entry_price': signal.get('entry_price'),
                'stop_loss': signal.get('stop_loss'),
                'take_profits': signal.get('take_profits', [])
            }
            
            logging.info(f"Placing order with params: {order_params}")

            try:
                order_result = await self.trade_manager.place_order(**order_params)
                logging.info(f"Order result: {order_result}")
            except Exception as e:
                logging.error(f"Error placing order: {e}")
                if hasattr(e, '__dict__'):
                    logging.error(f"Error details: {e.__dict__}")
                raise

            # 创建持仓对象
            position = Position(
                id=order_result['orderId'],
                symbol=signal['symbol'],
                entry_price=signal.get('entry_price'),
                stop_loss=signal.get('stop_loss'),
                take_profits=signal.get('take_profits', []),
                volume=volume,
                direction=signal['action'],
                entry_type=signal['entry_type'],
                layer_index=0,
                round_id=round_id,
                metadata={
                    'creation_time': datetime.now().isoformat(),
                    'signal': signal
                }
            )
            
            self._log_position_details(position)
            self.active_positions[round_id].append(position)
            
            return round_id

        except Exception as e:
            logging.error(f"Error in create_single_position: {e}")
            if hasattr(e, '__dict__'):
                logging.error(f"Error details: {e.__dict__}")
            return None


    async def modify_positions(self, round_id: str, modifications: Dict[str, Any]) -> bool:
        """修改持仓"""
        if round_id not in self.active_positions:
            return False

        success = True
        for position in self.active_positions[round_id]:
            if position.status != 'active':
                continue

            try:
                if 'stop_loss' in modifications:
                    await self.trade_manager.modify_position(
                        position_id=position.id,
                        stop_loss=modifications['stop_loss']
                    )
                    position.stop_loss = modifications['stop_loss']

                if modifications.get('breakeven', False):
                    await self.trade_manager.modify_position(
                        position_id=position.id,
                        stop_loss=position.entry_price or position.metadata['entry_price']
                    )
                    position.stop_loss = position.entry_price

                if 'take_profits' in modifications:
                    await self.trade_manager.modify_position(
                        position_id=position.id,
                        take_profit=modifications['take_profits'][0] if modifications['take_profits'] else None
                    )
                    position.take_profits = modifications['take_profits']

            except Exception as e:
                logging.error(f"Error modifying position {position.id}: {e}")
                success = False

        return success

    async def close_positions(self, round_id: str, close_type: str = 'all') -> bool:
        """关闭持仓"""
        if round_id not in self.active_positions:
            return False

        positions = self.active_positions[round_id]
        success = True
        
        if close_type == 'partial':
            # 按盈利排序，关闭表现最差的一半
            positions.sort(key=lambda x: x.realized_profit)
            positions_to_close = positions[:len(positions)//2]
        else:
            positions_to_close = positions

        for position in positions_to_close:
            if position.status != 'active':
                continue

            try:
                result = await self.trade_manager.close_position(position.id)
                position.status = 'closed'
                position.close_price = result['price']
                position.close_time = datetime.now()
                position.realized_profit = result['profit']

            except Exception as e:
                logging.error(f"Error closing position {position.id}: {e}")
                success = False

        # 更新持仓列表
        self.closed_positions[round_id] = [p for p in positions if p.status == 'closed']
        self.active_positions[round_id] = [p for p in positions if p.status == 'active']

        return success

    def _calculate_custom_volumes(self, base_volume: float, num_layers: int) -> List[float]:
        """计算自定义的分层仓位大小"""
        # 这里可以实现不同的仓位分配策略
        # 例如: 金字塔策略、反向金字塔策略等
        # 默认实现均匀分配
        return [base_volume] * num_layers

    def get_active_rounds(self) -> List[str]:
        """获取活跃的交易轮次"""
        return [
            round_id for round_id, positions in self.active_positions.items() 
            if any(p.status == 'active' for p in positions)
        ]

    def get_position_status(self, round_id: str) -> Dict[str, Any]:
        """获取交易轮次的状态信息"""
        if round_id not in self.active_positions:
            return {'status': 'not_found'}

        active_count = len([p for p in self.active_positions[round_id] if p.status == 'active'])
        closed_count = len([p for p in self.active_positions[round_id] if p.status == 'closed'])
        
        total_profit = sum(p.realized_profit for p in self.active_positions[round_id])
        
        return {
            'status': 'active' if active_count > 0 else 'closed',
            'active_positions': active_count,
            'closed_positions': closed_count,
            'total_positions': len(self.active_positions[round_id]),
            'total_profit': total_profit
        }