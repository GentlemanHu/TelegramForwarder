from ..base_strategy import BaseStrategy

class MultiLayerHFTStrategy(BaseStrategy):
    def __init__(self, trade_manager):
        super().__init__(trade_manager)
