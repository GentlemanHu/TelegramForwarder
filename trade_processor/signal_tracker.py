
# signal_tracker.py

from dataclasses import dataclass
from datetime import datetime, timedelta
from typing import Dict, List, Optional, Any
from enum import Enum
import logging

class SignalType(Enum):
    ENTRY = "entry"
    MODIFY = "modify"
    EXIT = "exit"
    UPDATE = "update"

@dataclass
class SignalConfig:
    # 信号配置时间窗口（分钟）
    UPDATE_WINDOW: int = 5
    # 最大跟踪信号数
    MAX_TRACKED_SIGNALS: int = 100
    # 信号清理时间（小时）
    CLEANUP_AFTER: int = 24

@dataclass
class SignalUpdate:
    timestamp: datetime
    content: Dict[str, Any]
    type: SignalType
    processed: bool = False

class SignalTracker:
    def __init__(self, config: SignalConfig = None):
        self.config = config or SignalConfig()
        # round_id -> List[SignalUpdate]
        self.signal_history: Dict[str, List[SignalUpdate]] = {}
        # symbol -> Dict[timestamp, round_id]
        self.active_rounds: Dict[str, Dict[datetime, str]] = {}
        # 清理任务
        self.cleanup_task = None

    def add_signal(self, symbol: str, signal_data: Dict[str, Any], round_id: Optional[str] = None) -> str:
        """添加新信号并返回round_id"""
        try:
            current_time = datetime.now()
            signal_type = SignalType(signal_data.get('type', 'entry'))

            # 检查是否是现有round的更新
            if signal_type != SignalType.ENTRY and round_id:
                if round_id in self.signal_history:
                    self._add_signal_update(round_id, signal_data, signal_type)
                    return round_id

            # 检查是否是相近时间的信号更新
            if not round_id and signal_type == SignalType.ENTRY:
                round_id = self._find_recent_round(symbol, current_time)

            # 如果没找到现有round，创建新的
            if not round_id:
                round_id = f"R_{symbol}_{int(current_time.timestamp())}"

            # 添加到跟踪系统
            if round_id not in self.signal_history:
                self.signal_history[round_id] = []
                if symbol not in self.active_rounds:
                    self.active_rounds[symbol] = {}
                self.active_rounds[symbol][current_time] = round_id

            self._add_signal_update(round_id, signal_data, signal_type)
            return round_id

        except Exception as e:
            logging.error(f"Error adding signal: {e}")
            return round_id or f"R_{symbol}_{int(datetime.now().timestamp())}"

    def _add_signal_update(self, round_id: str, signal_data: Dict[str, Any], signal_type: SignalType):
        """添加信号更新"""
        update = SignalUpdate(
            timestamp=datetime.now(),
            content=signal_data,
            type=signal_type
        )
        self.signal_history[round_id].append(update)
        self._cleanup_old_signals()

    def _find_recent_round(self, symbol: str, current_time: datetime) -> Optional[str]:
        """查找最近的相关round"""
        if symbol not in self.active_rounds:
            return None

        window_start = current_time - timedelta(minutes=self.config.UPDATE_WINDOW)
        for timestamp, round_id in self.active_rounds[symbol].items():
            if window_start <= timestamp <= current_time:
                return round_id
        return None

    def get_signal_updates(self, round_id: str, since: Optional[datetime] = None) -> List[SignalUpdate]:
        """获取指定round的更新"""
        if round_id not in self.signal_history:
            return []

        updates = self.signal_history[round_id]
        if since:
            updates = [u for u in updates if u.timestamp >= since]
        return updates

    def mark_processed(self, round_id: str, update_time: datetime):
        """标记信号已处理"""
        if round_id in self.signal_history:
            for update in self.signal_history[round_id]:
                if update.timestamp == update_time:
                    update.processed = True

    def get_unprocessed_updates(self, round_id: str) -> List[SignalUpdate]:
        """获取未处理的更新"""
        if round_id not in self.signal_history:
            return []
        return [u for u in self.signal_history[round_id] if not u.processed]

    def _cleanup_old_signals(self):
        """清理旧信号"""
        current_time = datetime.now()
        cleanup_threshold = current_time - timedelta(hours=self.config.CLEANUP_AFTER)

        # 清理信号历史
        for round_id, updates in list(self.signal_history.items()):
            latest_update = max(updates, key=lambda u: u.timestamp)
            if latest_update.timestamp < cleanup_threshold:
                del self.signal_history[round_id]

        # 清理活跃rounds
        for symbol, rounds in self.active_rounds.items():
            self.active_rounds[symbol] = {
                ts: rid for ts, rid in rounds.items()
                if ts > cleanup_threshold
            }

    def get_round_status(self, round_id: str) -> Dict[str, Any]:
        """获取round状态信息"""
        if round_id not in self.signal_history:
            return {'status': 'not_found'}

        updates = self.signal_history[round_id]
        latest_update = max(updates, key=lambda u: u.timestamp)

        return {
            'status': 'active',
            'last_update': latest_update.timestamp,
            'update_count': len(updates),
            'updates': [
                {
                    'time': u.timestamp,
                    'type': u.type.value,
                    'processed': u.processed
                }
                for u in updates
            ]
        }
