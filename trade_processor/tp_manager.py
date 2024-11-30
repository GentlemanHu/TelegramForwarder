# tp_manager.py

from dataclasses import dataclass
from datetime import datetime
from typing import List, Dict, Optional
from enum import Enum
import logging

class TPStatus(Enum):
    PENDING = "pending"
    TRIGGERED = "triggered"
    CANCELLED = "cancelled"

@dataclass
class TPLevel:
    price: float
    status: TPStatus = TPStatus.PENDING
    hit_count: int = 0
    hit_time: Optional[datetime] = None

class DynamicTPManager:
    def __init__(self, round_manager: 'RoundManager'):
        self.round_manager = round_manager
        self.tp_cache = {}  # round_id -> List[TPLevel]

    async def handle_tp_hit(
        self,
        round_id: str,
        hit_price: float,
        current_positions: List[Dict]
    ) -> List[Dict]:
        """处理止盈触发"""
        try:
            actions = []
            tp_levels = self.tp_cache.get(round_id, [])
            if not tp_levels:
                return actions

            # 找到触发的止盈级别
            hit_level = None
            for tp in tp_levels:
                if tp.status != TPStatus.TRIGGERED and self._is_tp_hit(hit_price, tp.price, current_positions[0]['type']):
                    hit_level = tp
                    break

            if not hit_level:
                return actions

            # 更新止盈状态
            hit_level.status = TPStatus.TRIGGERED
            hit_level.hit_time = datetime.now()
            hit_level.hit_count += 1

            # 确定要关闭的仓位数量
            total_positions = len(current_positions)
            positions_to_close = []
            
            # 如果是第一个TP
            if hit_level == tp_levels[0]:
                # 关闭30%的仓位
                positions_to_close = current_positions[:max(1, int(total_positions * 0.3))]
                # 取消所有limit订单
                actions.append({
                    'action': 'cancel_pending_orders',
                    'round_id': round_id,
                    'reason': 'tp1_hit'
                })
            elif hit_level == tp_levels[-1]:
                # 最后的TP，关闭所有仓位
                positions_to_close = current_positions
            else:
                # 中间的TP，关闭50%的剩余仓位
                positions_to_close = current_positions[:max(1, int(total_positions * 0.5))]

            # 添加关闭仓位的动作
            for position in positions_to_close:
                actions.append({
                    'action': 'close_position',
                    'position_id': position['id'],
                    'reason': 'tp_hit',
                    'tp_level': hit_level.price
                })

            # 处理剩余仓位
            remaining_positions = [p for p in current_positions if p not in positions_to_close]
            if remaining_positions:
                # 移动止损到保本点
                breakeven_actions = await self._handle_breakeven(round_id, remaining_positions, hit_level)
                actions.extend(breakeven_actions)

                # 更新剩余仓位的止盈
                tp_update_actions = await self._update_remaining_tps(round_id, remaining_positions, hit_level)
                actions.extend(tp_update_actions)

                # 为剩余仓位启用追踪止损
                for position in remaining_positions:
                    entry_price = float(position['openPrice'])
                    price_range = abs(hit_level.price - entry_price)
                    trailing_distance = price_range * 0.1
                    actions.append({
                        'action': 'modify_position',
                        'position_id': position['id'],
                        'trailing_stop': {
                            'distance': trailing_distance,
                            'threshold': hit_price
                        }
                    })

            return actions

        except Exception as e:
            logging.error(f"Error handling TP hit: {e}")
            return []

    async def handle_position_closure(
        self,
        round_id: str,
        current_price: float,
        remaining_positions: List[Dict]
    ) -> List[Dict]:
        """处理仓位关闭后的其他仓位设置"""
        try:
            actions = []
            tp_levels = self.tp_cache.get(round_id, [])
            
            # 找到最近触发的止盈级别
            hit_level = None
            for tp in reversed(tp_levels):
                if tp.status == TPStatus.TRIGGERED:
                    hit_level = tp
                    break
                    
            if not hit_level:
                return actions

            # 处理剩余仓位
            if remaining_positions:
                # 设置保本点
                breakeven_actions = await self._handle_breakeven(
                    round_id,
                    remaining_positions,
                    hit_level
                )
                actions.extend(breakeven_actions)

                # 更新剩余仓位的止盈和启用追踪止损
                tp_update_actions = await self._update_remaining_tps(
                    round_id,
                    remaining_positions,
                    hit_level
                )
                actions.extend(tp_update_actions)

                # 为剩余仓位启用追踪止损
                for position in remaining_positions:
                    # 计算追踪止损的激活价格和距离
                    entry_price = float(position['openPrice'])
                    price_range = abs(hit_level.price - entry_price)
                    
                    # 追踪止损距离设为价格范围的10%
                    trailing_distance = price_range * 0.1
                    
                    # 激活价格设为当前价格
                    self.enable_trailing_stop(
                        position['id'],
                        current_price,
                        trailing_distance
                    )

            return actions
            
        except Exception as e:
            logging.error(f"Error handling position closure: {e}")
            return []

    async def _handle_breakeven(
        self,
        round_id: str,
        positions: List[Dict],
        hit_tp: TPLevel
    ) -> List[Dict]:
        """将盈利的仓位移动到保本点"""
        try:
            actions = []
            modified_count = 0
            for position in positions:
                entry_price = float(position['openPrice'])
                current_price = float(position.get('currentPrice', entry_price))
                
                # 检查是否盈利
                is_long = position['type'] == 'buy'
                is_profitable = (current_price > entry_price) if is_long else (current_price < entry_price)
                
                if not is_profitable:
                    continue
                    
                # 计算保本点 - 为了安全起见，在入场价格基础上留一点点余地
                safety_margin = abs(entry_price) * 0.001  # 0.1%的安全边际
                breakeven_price = entry_price + (safety_margin if is_long else -safety_margin)
                
                # 确保breakeven价格对于多头来说在当前价格之下，对于空头来说在当前价格之上
                if (is_long and breakeven_price >= current_price) or (not is_long and breakeven_price <= current_price):
                    breakeven_price = current_price + (-safety_margin if is_long else safety_margin)
                
                actions.append({
                    'action': 'modify_position',
                    'position_id': position['id'],
                    'stop_loss': breakeven_price,
                    'reason': 'breakeven_after_tp'
                })
                modified_count += 1
                
            logging.info(f"Modified {modified_count} profitable positions to breakeven")
            return actions
            
        except Exception as e:
            logging.error(f"Error handling breakeven: {e}")
            return []

    async def _update_remaining_tps(
        self,
        round_id: str,
        positions: List[Dict],
        hit_tp: TPLevel
    ) -> List[Dict]:
        """更新剩余仓位的止盈水平"""
        try:
            actions = []
            remaining_tps = [tp for tp in self.tp_cache[round_id] 
                           if tp.price > hit_tp.price and tp.status == TPStatus.PENDING]

            if not remaining_tps:
                return actions

            # 智能分配剩余止盈
            for position in positions:
                entry_price = float(position['openPrice'])
                current_profit = abs(hit_tp.price - entry_price)
                
                # 根据当前盈利调整剩余止盈
                adjusted_tps = []
                for tp in remaining_tps:
                    # 如果盈利显著，适当提高止盈目标
                    if current_profit > 0:
                        profit_factor = current_profit / entry_price
                        adjusted_price = tp.price * (1 + profit_factor * 0.1)
                        adjusted_tps.append(adjusted_price)
                    else:
                        adjusted_tps.append(tp.price)

                if adjusted_tps:
                    actions.append({
                        'action': 'modify_position',
                        'position_id': position['id'],
                        'take_profit': adjusted_tps[0],
                        'reason': 'tp_update_after_hit'
                    })

            return actions

        except Exception as e:
            logging.error(f"Error updating remaining TPs: {e}")
            return []

    def _is_tp_hit(self, current_price: float, tp_price: float, direction: str) -> bool:
        """判断是否触发止盈"""
        if direction == 'buy':
            return current_price >= tp_price
        return current_price <= tp_price

    def _calculate_risk_reward(self, position: Dict) -> float:
        """计算仓位的风险收益比"""
        try:
            entry_price = float(position['openPrice'])
            stop_loss = float(position.get('stopLoss', entry_price))
            take_profit = float(position.get('takeProfit', entry_price))
            
            if stop_loss == entry_price:
                return 0
                
            risk = abs(entry_price - stop_loss)
            if risk == 0:
                return 0
                
            reward = abs(take_profit - entry_price)
            
            # 考虑当前价格对风险收益比的影响
            current_price = float(position.get('currentPrice', entry_price))
            unrealized_profit = abs(current_price - entry_price)
            
            # 将未实现利润纳入考虑
            adjusted_reward = reward + unrealized_profit
            
            return adjusted_reward / risk
            
        except Exception as e:
            logging.error(f"Error calculating risk reward: {e}")
            return 0

    async def update_round_tps(
        self,
        round_id: str,
        new_tp_levels: List[float],
        current_positions: List[Dict]
    ) -> List[Dict]:
        """更新一轮交易的止盈水平"""
        try:
            actions = []
            
            # 更新缓存
            self.tp_cache[round_id] = [
                TPLevel(price=price) for price in new_tp_levels
            ]

            # 为不同层级分配不同数量的止盈
            positions_per_tp = max(1, len(current_positions) // len(new_tp_levels))
            
            # 按照风险收益比排序仓位
            sorted_positions = sorted(
                current_positions,
                key=lambda p: self._calculate_risk_reward(p),
                reverse=True
            )

            # 分配止盈
            for i, position in enumerate(sorted_positions):
                tp_index = min(i // positions_per_tp, len(new_tp_levels) - 1)
                actions.append({
                    'action': 'modify_position',
                    'position_id': position['id'],
                    'take_profit': new_tp_levels[tp_index],
                    'reason': 'tp_update'
                })

            return actions

        except Exception as e:
            logging.error(f"Error updating round TPs: {e}")
            return []

    def get_round_tp_status(self, round_id: str) -> Dict:
        """获取一轮交易的止盈状态"""
        try:
            if round_id not in self.tp_cache:
                return {'status': 'not_found'}

            tp_levels = self.tp_cache[round_id]
            return {
                'total_levels': len(tp_levels),
                'triggered_levels': sum(1 for tp in tp_levels if tp.status == TPStatus.TRIGGERED),
                'pending_levels': sum(1 for tp in tp_levels if tp.status == TPStatus.PENDING),
                'levels': [
                    {
                        'price': tp.price,
                        'status': tp.status.value,
                        'hit_count': tp.hit_count,
                        'hit_time': tp.hit_time.isoformat() if tp.hit_time else None
                    }
                    for tp in tp_levels
                ]
            }

        except Exception as e:
            logging.error(f"Error getting TP status: {e}")
            return {'status': 'error'}