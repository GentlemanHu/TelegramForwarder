

from typing import Dict, List, Optional, Any
from metaapi_cloud_sdk import MetaApi
import logging
import asyncio
from datetime import datetime
import uuid



class TradeManager:
    def __init__(self, config: 'TradeConfig'):
        self.config = config
        self.api = MetaApi(config.meta_api_token)
        self.account = None
        self.connection = None
        self._initialized = False
        self.sync_complete = asyncio.Event()
        
    async def initialize(self):
        """初始化MetaAPI连接"""
        if self._initialized:
            return True
            
        try:
            # 设置日志级别
            logging.getLogger('socketio.client').setLevel(logging.WARNING)
            logging.getLogger('engineio.client').setLevel(logging.WARNING)
            
            self.account = await self.api.metatrader_account_api.get_account(
                self.config.account_id
            )
            
            if self.account.state not in ['DEPLOYING', 'DEPLOYED']:
                logging.info("Deploying account...")
                await self.account.deploy()
                
            logging.info("Waiting for account connection...")
            await self.account.wait_connected()
            
            # 创建RPC连接
            self.connection = self.account.get_rpc_connection()
            await self.connection.connect()
            
            # 等待同步
            try:
                logging.info("Waiting for synchronization...")
                await asyncio.wait_for(
                    self.connection.wait_synchronized(),
                    timeout=30
                )
                self.sync_complete.set()
                logging.info("Account synchronized successfully")
            except asyncio.TimeoutError:
                logging.warning("Synchronization timeout, but continuing...")
            
            # 获取账户信息以验证连接
            account_info = await self.connection.get_account_information()
            logging.info(f"Connected to account. Balance: {account_info.get('balance')}")
            
            self._initialized = True
            return True
            
        except Exception as e:
            logging.error(f"Error initializing trade manager: {e}")
            if hasattr(e, '__dict__'):
                logging.error(f"Error details: {e.__dict__}")
            return False

    async def wait_synchronized(self, timeout: float = 30.0) -> bool:
        """等待账户同步完成"""
        try:
            await asyncio.wait_for(self.sync_complete.wait(), timeout=timeout)
            return True
        except asyncio.TimeoutError:
            logging.warning("Wait for synchronization timeout")
            return False



    async def place_order(
            self, 
            symbol: str,
            direction: str,
            volume: float,
            entry_type: str = 'market',
            entry_price: Optional[float] = None,
            stop_loss: Optional[float] = None,
            take_profits: Optional[List[float]] = None
        ) -> Dict[str, Any]:
            """统一的下单接口"""
            if not self._initialized:
                await self.initialize()
                
            try:
                # 生成唯一的clientId
                client_id = f"T_{symbol}_{uuid.uuid4().hex[:8]}"
                
                # 基础订单选项
                options = {
                    # 'comment': 'Auto Trade',
                    'clientId': client_id
                }
                
                # 获取价格精度
                symbol_spec = await self.connection.get_symbol_specification(symbol)
                digits = symbol_spec['digits']
                
                # 处理价格精度
                if entry_price is not None:
                    entry_price = round(entry_price, digits)
                if stop_loss is not None:
                    stop_loss = round(stop_loss, digits)
                if take_profits:
                    take_profits = [round(tp, digits) for tp in take_profits]

                # 获取当前市场价格
                price_info = await self.connection.get_symbol_price(symbol)
                
                # 根据订单类型和方向执行下单
                if direction == 'buy':
                    if entry_type == 'market':
                        result = await self.connection.create_market_buy_order(
                            symbol=symbol,
                            volume=volume,
                            stop_loss=stop_loss,
                            take_profit=take_profits[0] if take_profits else None,
                            options=options
                        )
                    else:  # limit
                        result = await self.connection.create_limit_buy_order(
                            symbol=symbol,
                            volume=volume,
                            open_price=entry_price,
                            stop_loss=stop_loss,
                            take_profit=take_profits[0] if take_profits else None,
                            options=options
                        )
                else:  # sell
                    if entry_type == 'market':
                        result = await self.connection.create_market_sell_order(
                            symbol=symbol,
                            volume=volume,
                            stop_loss=stop_loss,
                            take_profit=take_profits[0] if take_profits else None,
                            options=options
                        )
                    else:  # limit
                        result = await self.connection.create_limit_sell_order(
                            symbol=symbol,
                            volume=volume,
                            open_price=entry_price,
                            stop_loss=stop_loss,
                            take_profit=take_profits[0] if take_profits else None,
                            options=options
                        )

                logging.info(f"Order placed successfully: {result}")
                return result
                
            except Exception as e:
                logging.error(f"Error placing order: {e}")
                                # 如果错误对象有额外的属性，打印它们
                if hasattr(e, 'details'):
                    print("\n错误详细信息:")
                    print(f"Details: {e.details}")
                
                # 如果错误对象有错误码，打印它
                if hasattr(e, 'error_code'):
                    print(f"Error code: {e.error_code}")
                raise

    async def get_current_price(self, symbol: str) -> Dict[str, float]:
        """获取当前市场价格"""
        if not self._initialized:
            await self.initialize()
            
        try:
            price_info = await self.connection.get_symbol_price(symbol)
            return {
                'bid': price_info['bid'],
                'ask': price_info['ask'],
                'spread': price_info['ask'] - price_info['bid']
            }
        except Exception as e:
            logging.error(f"Error getting current price: {e}")
            raise



    async def cleanup(self):
        """清理资源"""
        try:
            if self.connection:
                await self.connection.close()
            self._initialized = False
            self.sync_complete.clear()
            logging.info("Trade manager cleaned up successfully")
        except Exception as e:
            logging.error(f"Error cleaning up trade manager: {e}")

    # ... 其他方法保持不变 ...
    
    def _handle_synchronized(self, synchronization_status):
        """处理同步事件"""
        if synchronization_status.synchronized:
            logging.info("Account synchronized")
            self.sync_complete.set()
        else:
            logging.warning("Account synchronization lost")
            self.sync_complete.clear()
 

          
    async def get_account_info(self) -> Dict[str, Any]:
        """获取账户信息"""
        if not self._initialized:
            await self.initialize()
            
        return await self.connection.get_account_information()
                   
    async def modify_position(self, position_id: str, 
                            stop_loss: Optional[float] = None,
                            take_profit: Optional[float] = None) -> Dict[str, Any]:
        """修改持仓"""
        if not self._initialized:
            await self.initialize()
            
        try:
            result = await self.connection.modify_position(
                position_id=position_id,
                stop_loss=stop_loss,
                take_profit=take_profit
            )
            
            logging.info(f"Position {position_id} modified successfully")
            return result
            
        except Exception as e:
            logging.error(f"Error modifying position {position_id}: {e}")
            raise
            
    async def close_position(self, position_id: str) -> Dict[str, Any]:
        """关闭持仓"""
        if not self._initialized:
            await self.initialize()
            
        try:
            result = await self.connection.close_position(position_id=position_id)
            logging.info(f"Position {position_id} closed successfully")
            return result
            
        except Exception as e:
            logging.error(f"Error closing position {position_id}: {e}")
            raise
            
    async def calculate_margin(self, symbol: str, volume: float, 
                             price: Optional[float] = None) -> float:
        """计算所需保证金"""
        if not self._initialized:
            await self.initialize()
            
        try:
            if price is None:
                # 获取当前价格
                price_info = await self.connection.get_symbol_price(symbol)
                price = price_info['ask']
                
            result = await self.connection.calculate_margin({
                'symbol': symbol,
                'type': 'ORDER_TYPE_BUY',
                'volume': volume,
                'openPrice': price
            })
            
            return result['margin']
            
        except Exception as e:
            logging.error(f"Error calculating margin: {e}")
            raise
