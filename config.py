from dataclasses import dataclass
import os
from dotenv import load_dotenv
from typing import Optional

load_dotenv()

@dataclass
class Config:
    """基础配置和Telegram配置"""
    # Telegram配置
    TELEGRAM_TOKEN: str = os.getenv("TELEGRAM_TOKEN")
    API_ID: str = os.getenv("API_ID")
    API_HASH: str = os.getenv("API_HASH") 
    PHONE_NUMBER: str = os.getenv("PHONE_NUMBER")
    SESSION_NAME: str = os.getenv("SESSION_NAME", "forwarder_session")
    OWNER_ID: int = int(os.getenv("OWNER_ID", "0"))
    DATABASE_NAME: str = os.getenv("DATABASE_NAME", "forward_bot.db")
    DEFAULT_LANGUAGE: str = os.getenv("DEFAULT_LANGUAGE", "en")
    
    # API密钥 (这些将被trade_config使用)
    META_API_TOKEN: str = os.getenv("META_API_TOKEN")
    ACCOUNT_ID: str = os.getenv("ACCOUNT_ID")
    OPENAI_API_KEY: str = os.getenv("OPENAI_API_KEY")
    OPENAI_BASE_URL: Optional[str] = os.getenv("OPENAI_BASE_URL")

    def __post_init__(self):
        """验证必要的配置是否存在"""
        required_fields = [
            "TELEGRAM_TOKEN",
            "API_ID", 
            "API_HASH",
            "PHONE_NUMBER",
            "OWNER_ID",
            "META_API_TOKEN",
            "ACCOUNT_ID"
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
        except ValueError as e:
            raise ValueError(f"Invalid configuration value: {str(e)}")