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

    def _normalize_entry_signal(self, signal: Dict[str, Any]) -> Dict[str, Any]:
        """标准化入场信号"""
        # 确保基本字段存在
        signal['symbol'] = signal.get('symbol', "")+"m"
        signal['entry_type'] = signal.get('entry_type', 'market')
        signal['entry_price'] = signal.get('entry_price')
        signal['entry_range'] = signal.get('entry_range')
        signal['stop_loss'] = signal.get('stop_loss')
        signal['take_profits'] = signal.get('take_profits', [])

        # 更新分层配置
        layers_config = signal.get('layers', {
            'enabled': False,
            'count': None,
            'distribution': None
        })

        if layers_config.get('enabled', False):
            if not layers_config.get('count'):
                layers_config['count'] = 3  # 默认3层
                
            # 确保distribution是有效的枚举值
            valid_distributions = ['EQUAL', 'FIBONACCI', 'MOMENTUM', 'VOLUME']
            current_dist = layers_config.get('distribution', 'EQUAL').upper()
            layers_config['distribution'] = (
                current_dist if current_dist in valid_distributions else 'EQUAL'
            )
            
            # 添加高级分层配置
            if not layers_config.get('advanced'):
                layers_config['advanced'] = {
                    'min_distance': 0.001,  # 最小层间距
                    'max_distance': 0.005,  # 最大层间距
                    'volume_scale': 1.0,    # 量的缩放因子
                    'use_market_profile': False  # 是否使用市场轮廓
                }

        signal['layers'] = layers_config

        # 计算风险点数（如果有止损）
        if all(v is not None for v in [signal['entry_price'], signal['stop_loss']]):
            risk_points = abs(signal['entry_price'] - signal['stop_loss'])
            signal['risk_points'] = risk_points
            
            # 计算风险比例（如果有止盈）
            if signal['take_profits']:
                first_tp = signal['take_profits'][0]
                reward_points = abs(first_tp - signal['entry_price'])
                signal['risk_reward_ratio'] = reward_points / risk_points if risk_points else 0

        return signal

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
                    "distribution": "equal"|"fibonacci"|"momentum"|"volume"|null,
                    "advanced": {
                        "min_distance": number,
                        "max_distance": number,
                        "volume_scale": number,
                        "use_market_profile": boolean
                    }
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
            8. If layers are enabled, you can specify distribution type and advanced settings

            Example message: "Buy BTCUSD between 35000-36000 with 3 layers fibonacci distribution, sl 34000, tp 37000,38000"
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
                "layers": {
                    "enabled": true,
                    "count": 3,
                    "distribution": "fibonacci",
                    "advanced": {
                        "min_distance": 0.001,
                        "max_distance": 0.005,
                        "volume_scale": 1.0,
                        "use_market_profile": false
                    }
                }
            }
            """

            response = await self.client.chat.completions.create(
                model="gpt-3.5-turbo",
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

    def _extract_numbers(self, text: str) -> List[float]:
        """从文本中提取数字"""
        try:
            pattern = r'[-+]?\d*\.?\d+'
            return [float(num) for num in re.findall(pattern, text)]
        except Exception as e:
            logging.error(f"Error extracting numbers: {e}")
            return []