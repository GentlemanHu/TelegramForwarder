"""
Trade Processor Package - Simple signal processing system for trading operations
"""
from typing import Dict, List, Optional, Any

from .trade_config import TradeConfig
from .ai_analyzer import AIAnalyzer
from .position_manager import PositionManager
from .trade_manager import TradeManager
from .signal_processor import SignalProcessor

__version__ = '1.0.0'

__all__ = [
    'TradeConfig',
    'AIAnalyzer',
    'PositionManager',
    'TradeManager',
    'SignalProcessor'
]