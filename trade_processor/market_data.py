
# market_data.py

from dataclasses import dataclass
from typing import Dict, Optional
from datetime import datetime

@dataclass
class MarketData:
    symbol: str
    timestamp: datetime
    bid: float
    ask: float
    momentum: Optional[float] = 0
    volatility: Optional[float] = 0.001
    volume_profile: Optional[Dict[float, float]] = None
    account_size: Optional[float] = None
    risk_percent: Optional[float] = 0.02

    @property
    def mid_price(self) -> float:
        return (self.bid + self.ask) / 2

    @property
    def spread(self) -> float:
        return self.ask - self.bid

    def to_dict(self) -> Dict:
        return {
            'symbol': self.symbol,
            'timestamp': self.timestamp.isoformat(),
            'bid': self.bid,
            'ask': self.ask,
            'momentum': self.momentum,
            'volatility': self.volatility,
            'volume_profile': self.volume_profile,
            'account_size': self.account_size,
            'risk_percent': self.risk_percent
        }

    @classmethod
    def from_dict(cls, data: Dict) -> 'MarketData':
        return cls(
            symbol=data['symbol'],
            timestamp=datetime.fromisoformat(data['timestamp']),
            bid=data['bid'],
            ask=data['ask'],
            momentum=data.get('momentum', 0),
            volatility=data.get('volatility', 0.001),
            volume_profile=data.get('volume_profile'),
            account_size=data.get('account_size'),
            risk_percent=data.get('risk_percent', 0.02)
        )
