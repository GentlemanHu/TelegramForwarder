from openai import AsyncOpenAI
from typing import Dict, Any, Optional, List
import logging
import json
import re
from datetime import datetime

class AIAnalyzer:
    def __init__(self, config: 'TradeConfig'):
        self.config = config
        self.client = AsyncOpenAI(
            api_key=config.openai_api_key,
            base_url=config.openai_base_url
        )

    async def analyze_signal(self, message: str) -> Optional[Dict[str, Any]]:
        """分析交易信号"""
        try:
            system_prompt = """
            You are a trading signal analyzer. Extract key information from trading messages and always return a valid JSON with the following structure:

            For entry signals:
            {
                "type": "entry",
                "action": "buy"|"sell",
                "symbol": string,
                "entry_type": "market"|"limit",
                "entry_price": number|null,
                "entry_range": {"min": number, "max": number}|null,
                "stop_loss": number|null,
                "take_profits": [number]|[],
                "layers": {
                    "enabled": boolean,
                    "count": number|null,
                    "distribution": "equal"|"custom"|null
                }
            }

            Rules:
            1. Always set type, action, and symbol
            2. If no specific entry price is given, set entry_type="market" and entry_price=null
            3. If a price range is given, set entry_type="limit" and fill entry_range
            4. If a single price is given, set entry_type="limit", entry_price to that value, and entry_range to null
            5. Set layers.enabled=true if message mentions multiple entries or layering
            6. Default to layers.enabled=false and layers.count=null if not specified
            7. Notice always convert symbol to Forex, example if send GOLD, it will be XAUUSD 

            Example message: "Buy BTCUSD between 35000-36000, sl 34000, tp 37000,38000"
            Would return:
            {
                "type": "entry",
                "action": "buy",
                "symbol": "BTCUSD",
                "entry_type": "limit",
                "entry_price": null,
                "entry_range": {"min": 35000, "max": 36000},
                "stop_loss": 34000,
                "take_profits": [37000, 38000],
                "layers": {"enabled": true, "count": 3, "distribution": "equal"}
            }
            
            Be aware layers enabled depends upon if has range entry
            """

            response = await self.client.chat.completions.create(
                model="gpt-4",
                messages=[
                    {"role": "system", "content": system_prompt},
                    {"role": "user", "content": message}
                ],
                temperature=0.1
            )

            # 解析响应
            result_content = response.choices[0].message.content.strip()
            result_content = result_content.replace('```json', '').replace('```', '').strip()
            result = json.loads(result_content)

            # 验证必要字段
            if not all(k in result for k in ['type', 'action', 'symbol']):
                raise ValueError("Missing required fields in signal")

            # 标准化处理
            if result['type'] == 'entry':
                result = self._normalize_entry_signal(result)
            
            return result

        except Exception as e:
            logging.error(f"Error analyzing signal: {e}")
            if hasattr(e, '__dict__'):
                logging.error(f"Error details: {e.__dict__}")
            return None

    def _normalize_entry_signal(self, signal: Dict[str, Any]) -> Dict[str, Any]:
        """标准化入场信号"""
        # 确保基本字段存在
        signal['symbol'] = signal.get('symbol')+"m"
        signal['entry_type'] = signal.get('entry_type', 'market')
        signal['entry_price'] = signal.get('entry_price')
        signal['entry_range'] = signal.get('entry_range')
        signal['stop_loss'] = signal.get('stop_loss')
        signal['take_profits'] = signal.get('take_profits', [])
        signal['layers'] = signal.get('layers', {
            'enabled': False,
            'count': None,
            'distribution': None
        })

        # 处理分层配置
        if signal['layers']['enabled']:
            if not signal['layers'].get('count'):
                signal['layers']['count'] = 3  # 默认3层
            if not signal['layers'].get('distribution'):
                signal['layers']['distribution'] = 'equal'

        # 处理价格范围
        if signal['entry_type'] == 'limit':
            if signal['entry_price'] and not signal['entry_range']:
                price = float(signal['entry_price'])
                signal['entry_range'] = {
                    'min': price,
                    'max': price
                }
            elif signal['entry_range']:
                signal['entry_range'] = {
                    'min': float(signal['entry_range']['min']),
                    'max': float(signal['entry_range']['max'])
                }

        # 确保数值类型正确
        if signal['stop_loss']:
            signal['stop_loss'] = float(signal['stop_loss'])
        signal['take_profits'] = [float(tp) for tp in signal['take_profits'] if tp]

        # 添加风险计算
        if signal['stop_loss'] and (signal['entry_price'] or signal['entry_range']):
            entry_price = signal['entry_price']
            if not entry_price and signal['entry_range']:
                entry_price = (signal['entry_range']['min'] + signal['entry_range']['max']) / 2
            if entry_price:
                risk_points = abs(entry_price - signal['stop_loss'])
                signal['risk_points'] = risk_points

        return signal

    def _extract_numbers(self, text: str) -> List[float]:
        """从文本中提取数字"""
        try:
            pattern = r'[-+]?\d*\.?\d+'
            return [float(num) for num in re.findall(pattern, text)]
        except Exception as e:
            logging.error(f"Error extracting numbers: {e}")
            return []