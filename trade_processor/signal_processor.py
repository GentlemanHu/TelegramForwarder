from typing import Optional, Dict, Any, List
import logging
import asyncio
from datetime import datetime
import uuid
from .trade_config import TradeConfig
from .ai_analyzer import AIAnalyzer
from .position_manager import PositionManager
from .position import Position
from .round_manager import RoundStatus
from .tp_manager import *

class SignalProcessor:
    def __init__(self, config: 'TradeConfig', 
                 ai_analyzer: 'AIAnalyzer',
                 position_manager: 'PositionManager'):
        self.config = config
        self.ai_analyzer = ai_analyzer
        self.position_manager = position_manager
                # 将锁分开，用于不同目的
        self.signal_lock = asyncio.Lock()  # 用于信号追踪
        self.round_lock = asyncio.Lock()   # 用于round更新
        self.active_rounds: Dict[str, Dict[str, Any]] = {}

    async def handle_channel_message(self, event):
        """处理频道消息入口方法"""
        try:
            message = event.message
            if not message or not message.text:
                return

            # 处理消息
            await self.process_message(message.text)
            
        except Exception as e:
            logging.error(f"Error handling channel message: {e}")
            if hasattr(e, '__dict__'):
                logging.error(f"Error details: {e.__dict__}")


    async def _find_matching_round(self, signal: Dict[str, Any]) -> Optional[str]:
        """找到匹配的交易轮次"""
        try:
            symbol = signal['symbol']
            current_time = datetime.now()
            
            # 获取所有rounds的当前状态
            rounds_info = []
            for round_id, round_data in self.position_manager.round_manager.rounds.items():
                try:
                    time_diff = (current_time - round_data.created_at).total_seconds()
                    rounds_info.append({
                        'round_id': round_id,
                        'symbol': round_data.symbol,
                        'direction': round_data.direction,
                        'status': round_data.status,
                        'time_diff': time_diff,
                        'created_at': round_data.created_at.isoformat()
                    })
                except Exception as e:
                    logging.error(f"Error processing round {round_id}: {e}")

            logging.debug(f"Available rounds: {rounds_info}")
            
            # 查找最近的相同symbol的活跃round
            for round_id, round_data in self.position_manager.round_manager.rounds.items():
                try:
                    time_diff = (current_time - round_data.created_at).total_seconds()
                    
                    if (round_data.symbol == symbol and 
                        round_data.direction == signal['action'] and
                        str(round_data.status) not in ['CLOSED', 'CANCELLED'] and
                        time_diff < 300):  # 5分钟内
                        
                        logging.info(f"Found matching round {round_id} created {time_diff}s ago")
                        return round_id
                        
                except Exception as e:
                    logging.error(f"Error checking round {round_id}: {e}")
                    continue
                    
            logging.info("No matching round found, will create new one")
            return None
            
        except Exception as e:
            logging.error(f"Error finding matching round: {e}")
            return None



    async def process_message(self, message: str):
        """处理频道消息"""
        try:
            # 使用AI分析信号
            signal = await self.ai_analyzer.analyze_signal(message)
            if not signal:
                logging.info("No valid trading signal detected in message")
                return

            logging.info(f"Detected signal type: {signal.get('type')}")
            logging.info(f"Signal details: {signal}")

            # 使用signal_lock只保护信号追踪部分
            async with self.signal_lock:
                round_id = await self._find_matching_round(signal)
                logging.debug(f"Found matching round: {round_id}")

            if round_id:
                # 处理更新，不需要全局锁
                success = await self._handle_modify_signal(signal, round_id)
                if success:
                    logging.info(f"Updated existing round: {round_id}")
                else:
                    logging.error(f"Failed to update round: {round_id}")
            else:
                # 创建新的round，不需要全局锁
                if signal['type'] == 'entry':
                    if signal['layers'].get('enabled'):
                        new_round_id = await self.position_manager.create_layered_positions(signal)
                    else:
                        new_round_id = await self.position_manager.create_single_position(signal)
                    
                    if new_round_id:
                        logging.info(f"Created new trading round: {new_round_id}")
                    else:
                        logging.error("Failed to create positions")

        except Exception as e:
            logging.error(f"Error processing message: {e}")
            logging.error(f"Original message: {message}")
            if hasattr(e, '__dict__'):
                logging.error(f"Error details: {e.__dict__}")

    async def _handle_modify_signal(self, signal: Dict[str, Any], round_id: str) -> bool:
        """处理修改信号"""
        try:
            logging.info(f"Starting to handle modify signal for round {round_id}")
            
            # 验证和获取必要的状态
            if not self.position_manager.trade_manager._initialized:
                await self.position_manager.trade_manager.initialize()
                
            terminal_state = self.position_manager.trade_manager.connection.terminal_state
            if not terminal_state:
                logging.error("Terminal state not available")
                return False
            
            # 获取round信息，使用round特定的锁
            async with self.round_lock:
                trade_round = self.position_manager.round_manager.rounds.get(round_id)
                if not trade_round:
                    logging.error(f"Round {round_id} not found")
                    return False

            logging.info(f"Found trade round with {len(trade_round.positions)} positions")

            # 收集活跃仓位
            active_positions = []
            for pos_id, pos in trade_round.positions.items():
                try:
                    position = next(
                        (p for p in terminal_state.positions if p['id'] == pos_id), 
                        None
                    )
                    if position and position.get('state') != 'CLOSED':
                        active_positions.append(pos)
                        logging.info(f"Found active position: {pos_id}")
                except Exception as e:
                    logging.error(f"Error checking position {pos_id}: {e}")

            # 更新仓位，每个仓位独立处理
            update_tasks = []
            for pos in active_positions:
                if signal.get('stop_loss'):
                    update_tasks.append(
                        self.position_manager.trade_manager.connection.modify_position(
                            position_id=pos.id,
                            stop_loss=signal['stop_loss']
                        )
                    )
                    
                if signal.get('take_profits'):
                    update_tasks.append(
                        self.position_manager.trade_manager.connection.modify_position(
                            position_id=pos.id,
                            take_profit=signal['take_profits'][0]
                        )
                    )

            # 并行执行所有更新
            if update_tasks:
                await asyncio.gather(*update_tasks, return_exceptions=True)

            # 更新round配置
            async with self.round_lock:
                trade_round.stop_loss = signal.get('stop_loss')
                trade_round.tp_levels = [TPLevel(price=tp) for tp in signal.get('take_profits', [])]
                
                # 如果需要创建新layers
                if (signal.get('entry_range') and 
                    signal.get('entry_type') == 'limit' and 
                    len(active_positions) > 0):
                    layer_config = signal.get('layers', {})
                    if not layer_config.get('enabled'):
                        layer_config['enabled'] = True
                        layer_config['count'] = len(signal['take_profits'])
                        layer_config['distribution'] = 'equal'
                    
                    await self.position_manager.round_manager._create_additional_layers(
                        trade_round, 
                        {
                            'entry_range': signal['entry_range'],
                            'layers': layer_config,
                            'stop_loss': signal['stop_loss'],
                            'take_profits': signal['take_profits']
                        }
                    )

            logging.info(f"Successfully updated round {round_id}")
            return True

        except Exception as e:
            logging.error(f"Error handling modify signal: {e}")
            if hasattr(e, '__dict__'):
                logging.error(f"Error details: {e.__dict__}")
            return False


    async def _handle_entry_signal(self, signal: Dict[str, Any]):
        """处理入场信号"""
        try:
            round_id = signal['round_id']
            terminal_state = self.position_manager.trade_manager.connection.terminal_state
            
            # 检查是否是同一个symbol的已有信号的更新
            existing_round = None
            symbol = signal['symbol']
            
            for active_round in self.active_rounds.values():
                if (active_round['signal']['symbol'] == symbol and
                    active_round['status'] == 'active' and
                    (datetime.now() - active_round['timestamp']).total_seconds() < 300):
                    existing_round = active_round
                    round_id = existing_round['round_id']
                    break

            if existing_round:
                # 更新现有round的配置
                config_updates = {
                    'stop_loss': signal.get('stop_loss'),
                    'take_profits': signal.get('take_profits', [])
                }
                
                # 如果有trailing stop设置
                if signal.get('trailing_stop'):
                    config_updates['trailing_stop'] = signal['trailing_stop']
                    
                await self.position_manager.update_positions_config(
                    round_id, 
                    config_updates
                )
                logging.info(f"Updated existing round: {round_id}")
            else:
                # 创建新的交易round
                if signal['layers']['enabled']:
                    round_id = await self.position_manager.create_layered_positions(signal)
                else:
                    round_id = await self.position_manager.create_single_position(signal)

                if round_id:
                    self.active_rounds[round_id] = {
                        'round_id': round_id,
                        'signal': signal,
                        'status': 'active',
                        'timestamp': datetime.now()
                    }
                    logging.info(f"Created new trading round: {round_id}")
                else:
                    logging.error("Failed to create positions")

        except Exception as e:
            logging.error(f"Error handling entry signal: {e}")
            if hasattr(e, '__dict__'):
                logging.error(f"Error details: {e.__dict__}")


    async def _handle_exit_signal(self, signal: Dict[str, Any]):
        """处理出场信号"""
        try:
            symbol = signal['symbol']
            close_type = signal.get('close_type', 'all')
            terminal_state = self.position_manager.trade_manager.connection.terminal_state
            
            # 查找相关的交易rounds
            for round_id, round_data in list(self.active_rounds.items()):
                if round_data['signal']['symbol'] != symbol:
                    continue
                    
                if round_data['status'] != 'active':
                    continue

                trade_round = self.position_manager.round_manager.rounds.get(round_id)
                if not trade_round:
                    continue

                # 处理部分平仓
                if close_type == 'partial':
                    active_positions = [
                        pos for pos_id in trade_round.positions
                        if (pos := next(
                            (p for p in terminal_state.positions if p['id'] == pos_id),
                            None
                        ))
                    ]
                    
                    # 按盈利排序，关闭表现最差的一半
                    active_positions.sort(key=lambda x: x.get('profit', 0))
                    positions_to_close = active_positions[:len(active_positions)//2]
                    
                    for position in positions_to_close:
                        success = await self.position_manager.trade_manager.close_position(
                            position_id=position['id']
                        )
                        if not success:
                            logging.error(f"Failed to close position {position['id']}")
                else:
                    # 关闭所有持仓
                    success = await self.position_manager.close_positions(round_id)
                    
                    if success:
                        logging.info(f"Closed all positions for round: {round_id}")
                        self.active_rounds[round_id]['status'] = 'closed'
                        self.active_rounds[round_id]['close_signal'] = {
                            'signal': signal,
                            'timestamp': datetime.now()
                        }
                    else:
                        logging.error(f"Failed to close positions for round: {round_id}")

        except Exception as e:
            logging.error(f"Error handling exit signal: {e}")
            if hasattr(e, '__dict__'):
                logging.error(f"Error details: {e.__dict__}")

    async def _cleanup_old_rounds(self):
        """清理旧的交易rounds"""
        try:
            current_time = datetime.now()
            to_remove = []
            
            for round_id, round_data in self.active_rounds.items():
                if round_data['status'] == 'closed':
                    # 关闭1小时后清理
                    if (current_time - round_data['close_signal']['timestamp']).total_seconds() > 3600:
                        to_remove.append(round_id)
                else:
                    # 检查是否有已经关闭但未更新状态的round
                    trade_round = self.position_manager.round_manager.rounds.get(round_id)
                    if trade_round and trade_round.status == RoundStatus.CLOSED:
                        round_data['status'] = 'closed'
                        round_data['close_time'] = current_time
                    # 活跃超过24小时的也清理
                    elif (current_time - round_data['timestamp']).total_seconds() > 86400:
                        to_remove.append(round_id)
            
            # 执行清理
            for round_id in to_remove:
                self.active_rounds.pop(round_id)
                logging.info(f"Cleaned up round: {round_id}")
                
        except Exception as e:
            logging.error(f"Error cleaning up old rounds: {e}")

    async def _get_round_statistics(self, round_id: str) -> Dict[str, Any]:
        """获取交易轮次的统计信息"""
        try:
            stats = await self.position_manager.get_round_status(round_id)
            if not stats:
                return None
                
            terminal_state = self.position_manager.trade_manager.connection.terminal_state
            trade_round = self.position_manager.round_manager.rounds.get(round_id)
            
            if trade_round:
                # 添加更多统计信息
                positions = [
                    pos for pos_id in trade_round.positions
                    if (pos := next(
                        (p for p in terminal_state.positions if p['id'] == pos_id),
                        None
                    ))
                ]
                
                stats.update({
                    'total_volume': sum(p.get('volume', 0) for p in positions),
                    'floating_profit': sum(
                        p.get('profit', 0) 
                        for p in positions 
                        if p.get('state') != 'CLOSED'
                    ),
                    'realized_profit': sum(
                        p.get('profit', 0) 
                        for p in positions 
                        if p.get('state') == 'CLOSED'
                    ),
                    'max_profit': max((p.get('profit', 0) for p in positions), default=0),
                    'min_profit': min((p.get('profit', 0) for p in positions), default=0)
                })
                
            return stats
            
        except Exception as e:
            logging.error(f"Error getting round statistics: {e}")
            return None


    def _cleanup_old_rounds(self):
        """清理旧的交易rounds"""
        try:
            current_time = datetime.now()
            to_remove = []
            
            for round_id, round_data in self.active_rounds.items():
                if round_data['status'] == 'closed':
                    # 关闭1小时后清理
                    if (current_time - round_data['close_signal']['timestamp']).total_seconds() > 3600:
                        to_remove.append(round_id)
                else:
                    # 活跃超过24小时的也清理
                    if (current_time - round_data['timestamp']).total_seconds() > 86400:
                        to_remove.append(round_id)
            
            for round_id in to_remove:
                self.active_rounds.pop(round_id)
                
        except Exception as e:
            logging.error(f"Error cleaning up old rounds: {e}")