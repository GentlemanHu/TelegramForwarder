# commands.py
from typing import Dict, List, Tuple

class BotCommands:
    """Bot commands configuration"""
    
    @staticmethod
    def get_commands() -> Dict[str, Dict[str, List[Tuple[str, str]]]]:
        """
        Get bot commands for all supported languages
        Returns dict: {
            'en': {
                'commands': [(command, description)],
                'scope': 'default'
            },
            'zh': {
                'commands': [(command, description)],
                'scope': 'default'
            }
        }
        """
        return {
            'en': {
                'commands': [
                    ('start', 'Start the bot'),
                    ('channels', 'Manage channels and forwarding'),
                    ('language', 'Change language settings'),
                    ('positions', 'View all open positions'),
                    ('breakeven', 'Set stop loss to entry price for profitable positions'),
                    ('closeall', 'Close all open positions'),
                    ('help', 'Show help message'),
                ],
                'scope': 'default'
            },
            'zh': {
                'commands': [
                    ('start', '启动机器人'),
                    ('channels', '管理频道和转发'),
                    ('language', '更改语言设置'),
                    ('positions', '查看所有持仓'),
                    ('breakeven', '将盈利仓位止损移至入场价'),
                    ('closeall', '关闭所有持仓'),
                    ('help', '显示帮助信息'),
                ],
                'scope': 'default'
            }
        }

    @staticmethod
    async def setup_commands(application):
        """Setup bot commands for each language"""
        commands = BotCommands.get_commands()
        
        for lang_code, config in commands.items():
            try:
                await application.bot.set_my_commands(
                    [
                        (command, description)
                        for command, description in config['commands']
                    ],
                    language_code=lang_code
                )
                print(f"Successfully set up commands for language: {lang_code}")
            except Exception as e:
                print(f"Failed to set up commands for language {lang_code}: {e}")