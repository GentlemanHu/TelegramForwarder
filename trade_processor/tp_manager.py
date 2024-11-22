
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
            
            # 找到触发的止盈级别
            hit_level = None
            for tp in tp_levels:
                if tp.status == TPStatus.PENDING and self._is_tp_hit(
                    hit_price, tp.price, current_positions[0]['type']
                ):
                    hit_level = tp
                    break
                    
            if not hit_level:
                return actions

            # 更新止盈状态
            hit_level.status = TPStatus.TRIGGERED
            hit_level.hit_count += 1
            hit_level.hit_time = datetime.now()

            # 处理剩余仓位
            remaining_positions = []
            positions_to_close = []
            
            # 按照风险收益比排序仓位
            sorted_positions = sorted(
                current_positions,
                key=lambda p: self._calculate_risk_reward(p),
                reverse=True
            )

            # 确定要平仓的仓位数量
            positions_per_tp = max(1, len(sorted_positions) // len(tp_levels))
            positions_to_close = sorted_positions[:positions_per_tp]
            remaining_positions = sorted_positions[positions_per_tp:]

            # 生成平仓动作
            for position in positions_to_close:
                actions.append({
                    'action': 'close_position',
                    'position_id': position['id'],
                    'reason': 'tp_hit',
                    'tp_level': hit_level.price
                })

            # 处理剩余仓位
            if remaining_positions:
                # 移动止损到保本点
                breakeven_actions = await self._handle_breakeven(
                    round_id,
                    remaining_positions,
                    hit_level
                )
                actions.extend(breakeven_actions)

                # 更新剩余仓位的止盈
                tp_update_actions = await self._update_remaining_tps(
                    round_id,
                    remaining_positions,
                    hit_level
                )
                actions.extend(tp_update_actions)

            return actions

        except Exception as e:
            logging.error(f"Error handling TP hit: {e}")
            return []

    async def _handle_breakeven(
        self,
        round_id: str,
        positions: List[Dict],
        hit_tp: TPLevel
    ) -> List[Dict]:
        """将剩余仓位移动到保本点"""
        try:
            actions = []
            for position in positions:
                entry_price = float(position['openPrice'])
                
                # 添加一些缓冲区
                buffer = abs(entry_price - hit_tp.price) * 0.1
                breakeven_price = entry_price + (buffer if position['type'] == 'buy' else -buffer)
                
                actions.append({
                    'action': 'modify_position',
                    'position_id': position['id'],
                    'stop_loss': breakeven_price,
                    'reason': 'breakeven_after_tp'
                })
                
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

            # 为每个仓位设置下一个止盈
            for position in positions:
                next_tp = remaining_tps[0].price
                actions.append({
                    'action': 'modify_position',
                    'position_id': position['id'],
                    'take_profit': next_tp,
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
            reward = abs(take_profit - entry_price)
            return reward / risk
            
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