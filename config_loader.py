import json
import os
import logging

def load_config(config_file="integration_config.json"):
    """加载配置文件"""
    config = {
        "websocket": {
            "server_url": os.environ.get("VIPBOT_WEBSOCKET_URL", "ws://localhost:8765"),
            "reconnect_interval": 5
        },
        "logging": {
            "level": "INFO",
            "file": "integration.log"
        }
    }
    
    try:
        if os.path.exists(config_file):
            with open(config_file, "r") as f:
                file_config = json.load(f)
                
            # 更新配置
            for section, values in file_config.items():
                if section in config:
                    config[section].update(values)
                else:
                    config[section] = values
                    
            logging.info(f"已加载配置文件: {config_file}")
    except Exception as e:
        logging.error(f"加载配置文件失败: {e}")
    
    return config
