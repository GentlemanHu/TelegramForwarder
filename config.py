from dataclasses import dataclass
import os
from dotenv import load_dotenv
from typing import Optional

load_dotenv()

@dataclass
class Config:
    # Telegram配置
    TELEGRAM_TOKEN: str = os.getenv("TELEGRAM_TOKEN")
    API_ID: str = os.getenv("API_ID")
    API_HASH: str = os.getenv("API_HASH") 
    PHONE_NUMBER: str = os.getenv("PHONE_NUMBER")
    SESSION_NAME: str = os.getenv("SESSION_NAME", "forwarder_session")
    OWNER_ID: int = int(os.getenv("OWNER_ID", "0"))
    DATABASE_NAME: str = os.getenv("DATABASE_NAME", "forward_bot.db")
    DEFAULT_LANGUAGE: str = os.getenv("DEFAULT_LANGUAGE", "en")
    
    # 交易配置
    META_API_TOKEN: str = os.getenv("META_API_TOKEN")
    ACCOUNT_ID: str = os.getenv("ACCOUNT_ID")
    OPENAI_API_KEY: str = os.getenv("OPENAI_API_KEY")
    OPENAI_BASE_URL: Optional[str] = os.getenv("OPENAI_BASE_URL")
    
    # 交易参数
    DEFAULT_RISK_PERCENT: float = float(os.getenv("DEFAULT_RISK_PERCENT", "2.0"))
    MAX_LAYERS: int = int(os.getenv("MAX_LAYERS", "7"))
    MIN_LOT_SIZE: float = float(os.getenv("MIN_LOT_SIZE", "0.01"))

    def __post_init__(self):
        """验证必要的配置是否存在"""
        required_fields = [
            "TELEGRAM_TOKEN",
            "API_ID", 
            "API_HASH",
            "PHONE_NUMBER",
            "OWNER_ID",
            "META_API_TOKEN",
            "ACCOUNT_ID",
            "OPENAI_API_KEY"
        ]
        
        missing_fields = [
            field for field in required_fields 
            if not getattr(self, field)
        ]
        
        if missing_fields:
            raise ValueError(
                f"Missing required configuration: {', '.join(missing_fields)}\n"
                "Please check your .env file."
            )

        # 验证数值类型
        try:
            self.OWNER_ID = int(self.OWNER_ID)
            self.DEFAULT_RISK_PERCENT = float(self.DEFAULT_RISK_PERCENT)
            self.MAX_LAYERS = int(self.MAX_LAYERS)
            self.MIN_LOT_SIZE = float(self.MIN_LOT_SIZE)
        except ValueError as e:
            raise ValueError(f"Invalid configuration value: {str(e)}")