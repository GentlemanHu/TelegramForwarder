from dataclasses import dataclass, field
from datetime import datetime
from typing import Dict, List, Optional, Any
from enum import Enum

class PositionStatus(Enum):
    PENDING = "pending"
    ACTIVE = "active"
    PARTIALLY_CLOSED = "partially_closed"
    CLOSED = "closed"
    CANCELLED = "cancelled"

@dataclass
class Position:
    id: str
    symbol: str
    direction: str  # 'buy' or 'sell'
    volume: float
    entry_type: str  # 'market' or 'limit'
    status: PositionStatus = PositionStatus.PENDING
    order_id: Optional[str] = None  # 关联的订单ID
    
    # Prices
    entry_price: Optional[float] = None
    stop_loss: Optional[float] = None
    take_profits: List[float] = field(default_factory=list)
    close_price: Optional[float] = None
    
    # Trade management
    layer_index: Optional[int] = None
    round_id: Optional[str] = None
    realized_profit: float = 0.0
    unrealized_profit: float = 0.0
    
    # Timestamps
    created_at: datetime = field(default_factory=datetime.now)
    opened_at: Optional[datetime] = None
    closed_at: Optional[datetime] = None
    
    # Additional data
    metadata: Dict[str, Any] = field(default_factory=dict)
    
    def update(self, data: Dict[str, Any]):
        """Update position with new data"""
        for key, value in data.items():
            if hasattr(self, key):
                setattr(self, key, value)
                
        # Update status if needed
        if self.close_price and self.status != PositionStatus.CLOSED:
            self.status = PositionStatus.CLOSED
            self.closed_at = datetime.now()
            
    def is_in_profit(self) -> bool:
        """Check if position is in profit"""
        return self.unrealized_profit > 0 if self.unrealized_profit is not None else False
    
    def get_risk_reward_ratio(self) -> Optional[float]:
        """Calculate risk/reward ratio"""
        if not all([self.entry_price, self.stop_loss]) or not self.take_profits:
            return None
            
        risk = abs(self.entry_price - self.stop_loss)
        if risk == 0:
            return None
            
        # Use first take profit for R:R calculation
        reward = abs(self.entry_price - self.take_profits[0])
        return reward / risk
        
    def to_dict(self) -> Dict[str, Any]:
        """Convert position to dictionary"""
        return {
            'id': self.id,
            'symbol': self.symbol,
            'direction': self.direction,
            'volume': self.volume,
            'entry_type': self.entry_type,
            'status': self.status.value,
            'entry_price': self.entry_price,
            'stop_loss': self.stop_loss,
            'take_profits': self.take_profits,
            'close_price': self.close_price,
            'layer_index': self.layer_index,
            'round_id': self.round_id,
            'realized_profit': self.realized_profit,
            'unrealized_profit': self.unrealized_profit,
            'order_id': self.order_id,
            'created_at': self.created_at.isoformat(),
            'opened_at': self.opened_at.isoformat() if self.opened_at else None,
            'closed_at': self.closed_at.isoformat() if self.closed_at else None,
            'metadata': self.metadata
        }
    
    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> 'Position':
        """Create position from dictionary"""
        # Convert string timestamps to datetime
        if 'created_at' in data:
            data['created_at'] = datetime.fromisoformat(data['created_at'])
        if 'opened_at' in data and data['opened_at']:
            data['opened_at'] = datetime.fromisoformat(data['opened_at'])
        if 'closed_at' in data and data['closed_at']:
            data['closed_at'] = datetime.fromisoformat(data['closed_at'])
            
        # Convert status string to enum
        if 'status' in data:
            data['status'] = PositionStatus(data['status'])
            
        return cls(**data)
        
    def should_move_to_breakeven(self, current_price: float) -> bool:
        """Check if position should be moved to breakeven"""
        if not self.entry_price or not self.take_profits:
            return False
            
        # Calculate distance to first TP
        distance_to_tp = abs(self.take_profits[0] - self.entry_price)
        current_distance = abs(current_price - self.entry_price)
        
        # Move to breakeven if price has moved 70% towards first TP
        return current_distance >= (distance_to_tp * 0.7)