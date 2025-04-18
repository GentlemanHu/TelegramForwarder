# commands.py
from typing import Dict, List, Tuple
from locales import TRANSLATIONS

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
        commands_dict = {}

        # 命令列表 - 所有语言通用
        command_keys = [
            ('start', 'welcome_command'),
            ('channels', 'channels_command'),
            ('language', 'language_command'),
            ('help', 'help_command')
        ]

        # 为每种语言生成命令描述
        for lang_code in TRANSLATIONS.keys():
            commands = []
            for cmd, key in command_keys:
                # 尝试从翻译中获取命令描述，如果没有则使用英文
                description = TRANSLATIONS.get(lang_code, {}).get(key,
                                TRANSLATIONS.get('en', {}).get(key, cmd))
                commands.append((cmd, description))

            commands_dict[lang_code] = {
                'commands': commands,
                'scope': 'default'
            }

        return commands_dict

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