# channel_manager.py
from telegram import (
    KeyboardButton,
    ReplyKeyboardMarkup,
    ReplyKeyboardRemove,
    Update,
    InlineKeyboardButton,
    InlineKeyboardMarkup,
    CallbackQuery
)
from telegram.ext import (
    ContextTypes,
    ConversationHandler,
    CallbackQueryHandler,
    MessageHandler,
    CommandHandler,
    filters
)
import logging
import datetime
import traceback
from custom_keyboard import CustomKeyboard
from typing import Optional, Dict, Any
from telethon import TelegramClient
from locales import get_text, TRANSLATIONS
from telegram.error import BadRequest

# 定义会话状态
CHOOSING_CHANNEL_TYPE = 0
CHOOSING_ADD_METHOD = 1
WAITING_FOR_FORWARD = 2
WAITING_FOR_MANUAL_INPUT = 3

class ChannelManager:
    def __init__(self, db, config, client: TelegramClient):
        self.db = db
        self.config = config
        self.client = client


    async def show_language_settings(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """显示语言设置"""
        user_id = update.effective_user.id
        current_lang = self.db.get_user_language(user_id)

        # 语言显示名称映射
        language_display_names = {
            'en': 'English',
            'zh': '中文',
            'ru': 'Русский',
            'uk': 'Українська'
        }

        # 动态生成语言按钮
        language_buttons = []
        row = []

        # 每行最多放置2个语言按钮
        for i, lang_code in enumerate(TRANSLATIONS.keys()):
            display_name = language_display_names.get(lang_code, lang_code)
            row.append(InlineKeyboardButton(display_name, callback_data=f"lang_{lang_code}"))

            # 每2个按钮换一行
            if len(row) == 2 or i == len(TRANSLATIONS.keys()) - 1:
                language_buttons.append(row)
                row = []

        # 添加返回按钮
        language_buttons.append([InlineKeyboardButton(get_text(current_lang, 'back'), callback_data="channel_management")])

        # 获取当前语言的显示名称
        current_lang_display = language_display_names.get(current_lang, current_lang)

        text = (
            f"{get_text(current_lang, 'select_language')}\n"
            f"{get_text(current_lang, 'current_language', language_name=current_lang_display)}"
        )

        if isinstance(update, Update) and update.callback_query:
            await update.callback_query.message.edit_text(
                text,
                reply_markup=InlineKeyboardMarkup(language_buttons)
            )
        else:
            await update.message.reply_text(
                text,
                reply_markup=InlineKeyboardMarkup(language_buttons)
            )

    async def handle_language_change(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """处理语言更改"""
        query = update.callback_query
        await query.answer()

        user_id = update.effective_user.id
        new_lang = query.data.split('_')[1]

        success = self.db.set_user_language(user_id, new_lang)
        if success:
            await query.message.edit_text(
                get_text(new_lang, 'language_changed'),
                reply_markup=InlineKeyboardMarkup([[
                    InlineKeyboardButton(
                        get_text(new_lang, 'back'),
                        callback_data="channel_management"
                    )
                ]])
            )

    def get_handlers(self):
        """获取所有处理器"""
        handlers = [
            # 语言设置处理器
            CommandHandler("language", self.show_language_settings),
            CallbackQueryHandler(self.handle_language_change, pattern='^lang_'),

            # 添加频道的 ConversationHandler
            ConversationHandler(
                entry_points=[
                    CallbackQueryHandler(self.start_add_channel, pattern='^add_channel$')
                ],
                states={
                    CHOOSING_CHANNEL_TYPE: [
                        CallbackQueryHandler(self.handle_channel_type_choice, pattern='^type_')
                    ],
                    CHOOSING_ADD_METHOD: [
                        CallbackQueryHandler(self.handle_add_method, pattern='^method_')
                    ],
                    WAITING_FOR_FORWARD: [
                        MessageHandler(
                            filters.ALL & ~filters.COMMAND & ~filters.Regex('^(cancel|Cancel|取消)$'),  # 捕获所有非命令非取消消息
                            self.handle_forwarded_message
                        ),
                        MessageHandler(filters.Regex('^(cancel|Cancel|取消)$'), self.cancel_add_channel),
                        CommandHandler('cancel', self.cancel_add_channel),
                    ],
                    WAITING_FOR_MANUAL_INPUT: [
                        MessageHandler(
                            filters.TEXT & ~filters.COMMAND & ~filters.Regex('^(cancel|Cancel|取消)$'),
                            self.handle_manual_input
                        ),
                        MessageHandler(filters.Regex('^(cancel|Cancel|取消)$'), self.cancel_add_channel),
                        CommandHandler('cancel', self.cancel_add_channel),
                    ]

                },
                fallbacks=[
                    CommandHandler('cancel', self.cancel_add_channel),
                    CallbackQueryHandler(self.cancel_add_channel, pattern='^cancel$')
                ],
                name="add_channel",
                persistent=False,
                allow_reentry=True,
                map_to_parent={
                    ConversationHandler.END: ConversationHandler.END
                }
            ),

            # 删除频道相关
            CallbackQueryHandler(
                self.show_remove_channel_options,
                pattern='^remove_channel(_[0-9]+)?$'
            ),
            CallbackQueryHandler(
                self.handle_remove_channel,
                pattern='^remove_channel_[0-9]+$'
            ),
            CallbackQueryHandler(
                self.handle_remove_confirmation,
                pattern='^confirm_remove_channel_[0-9]+$'
            ),

            # 频道列表
            CallbackQueryHandler(
                self.show_channel_list,
                pattern='^list_channels(_[0-9]+)?$'
            ),

            # 配对管理相关
            CallbackQueryHandler(
                self.view_channel_pairs,
                pattern='^view_pairs(_[0-9]+)?$'
            ),
            CallbackQueryHandler(
                self.handle_manage_specific_pair,
                pattern='^manage_pair_[0-9]+(_[0-9]+)?$'
            ),
            CallbackQueryHandler(
                self.handle_add_specific_pair,
                pattern='^add_pair_[0-9]+_[0-9]+(_add)?$'
            ),
            CallbackQueryHandler(
                self.handle_remove_specific_pair,
                pattern='^remove_pair_[0-9]+_[0-9]+$'
            ),
            CallbackQueryHandler(
self.handle_confirm_remove_pair,
                pattern='^confirm_remove_pair_[0-9]+_[0-9]+$'
            ),

            # 过滤规则管理
            CallbackQueryHandler(self.show_filter_rules_menu, pattern='^filter_rules$'),
            CallbackQueryHandler(self.show_time_settings_menu, pattern='^time_settings$'),
            CallbackQueryHandler(self.show_pair_selection_for_filter, pattern='^add_filter_rule$'),
            CallbackQueryHandler(self.show_pair_selection_for_time, pattern='^add_time_filter$'),
            CallbackQueryHandler(self.show_filter_rules_list, pattern='^list_filter_rules(_[0-9]+)?$'),
            CallbackQueryHandler(self.show_time_filters_list, pattern='^list_time_filters(_[0-9]+)?$'),

            # 过滤规则处理
            CallbackQueryHandler(self.handle_filter_pair_selection, pattern='^filter_pair_'),
            CallbackQueryHandler(self.handle_filter_type_selection, pattern='^filter_type_'),
            CallbackQueryHandler(self.handle_filter_mode_selection, pattern='^filter_mode_'),
            CallbackQueryHandler(self.handle_delete_filter_rule, pattern='^delete_filter_rule_'),

            # 媒体过滤器相关回调
            CallbackQueryHandler(self.show_media_filter_menu, pattern='^media_filter$'),
            CallbackQueryHandler(self.show_pair_selection_for_media, pattern='^add_media_filter(_\d+)?$'),
            CallbackQueryHandler(self.show_media_filter_settings, pattern='^media_filter_pair_'),
            CallbackQueryHandler(self.toggle_media_filter, pattern='^toggle_media_'),

            # 时间过滤处理
            CallbackQueryHandler(self.handle_time_pair_selection, pattern='^time_pair_'),
            CallbackQueryHandler(self.handle_time_mode_selection, pattern='^time_mode_'),
            CallbackQueryHandler(self.handle_delete_time_filter, pattern='^delete_time_filter_'),

            # 添加过滤规则输入的处理器
            MessageHandler(
                filters.TEXT & filters.Regex(r'^[^/]') & ~filters.COMMAND & ~filters.UpdateType.EDITED_MESSAGE,
                self.handle_filter_pattern_input
            ),

            # 添加时间范围输入的处理器
            MessageHandler(
                filters.TEXT & filters.Regex(r'^\d{1,2}:\d{1,2}-\d{1,2}:\d{1,2}$') & ~filters.COMMAND & ~filters.UpdateType.EDITED_MESSAGE,
                self.handle_time_range_input
            ),

            # 添加星期输入的处理器
            MessageHandler(
                filters.TEXT & filters.Regex(r'^[1-7]([,-][1-7])*$') & ~filters.COMMAND & ~filters.UpdateType.EDITED_MESSAGE,
                self.handle_days_input
            ),

            # 返回处理
            # CallbackQueryHandler(self.handle_back, pattern='^back_to_'),

            # 通用管理菜单
            CallbackQueryHandler(self.show_channel_management, pattern='^channel_management$'),
        ]
        return handlers

    async def start_add_channel(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """开始添加频道流程"""
        query = update.callback_query
        await query.answer()

        user_id = update.effective_user.id
        lang = self.db.get_user_language(user_id)

        keyboard = [
            [
                InlineKeyboardButton(
                    get_text(lang, 'monitor_channel'),
                    callback_data="type_monitor"
                ),
                InlineKeyboardButton(
                    get_text(lang, 'forward_channel'),
                    callback_data="type_forward"
                )
            ],
            [InlineKeyboardButton(get_text(lang, 'cancel'), callback_data="cancel")]
        ]

        await query.message.edit_text(
            get_text(lang, 'select_channel_type'),
            reply_markup=InlineKeyboardMarkup(keyboard)
        )

        return CHOOSING_CHANNEL_TYPE

    async def handle_channel_type_choice(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """处理频道类型选择"""
        query = update.callback_query
        await query.answer()

        user_id = update.effective_user.id
        lang = self.db.get_user_language(user_id)

        channel_type = query.data.split('_')[1].upper()
        context.user_data['channel_type'] = channel_type

        keyboard = [
            [
                InlineKeyboardButton(
                    get_text(lang, 'forward_message'),
                    callback_data="method_forward"
                ),
                InlineKeyboardButton(
                    get_text(lang, 'enter_id'),
                    callback_data="method_manual"
                )
            ],
            [InlineKeyboardButton(get_text(lang, 'cancel'), callback_data="cancel")]
        ]

        channel_type_display = get_text(lang, 'monitor_channel' if channel_type == 'MONITOR' else 'forward_channel')
        await query.message.edit_text(
            get_text(lang, 'select_add_method', channel_type=channel_type_display),
            reply_markup=InlineKeyboardMarkup(keyboard)
        )

        return CHOOSING_ADD_METHOD


    async def handle_add_method(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """处理添加方法选择"""
        query = update.callback_query
        await query.answer()

        user_id = update.effective_user.id
        lang = self.db.get_user_language(user_id)

        try:
            if query.data == "method_forward":
                reply_markup = CustomKeyboard.get_share_keyboard(lang)

                context.user_data['awaiting_share'] = True
                context.user_data['channel_type'] = 'MONITOR' if 'monitor' in query.message.text.lower() else 'FORWARD'

                # 发送新消息并保存其ID
                new_message = await query.message.reply_text(
                    get_text(lang, 'forward_instruction'),
                    reply_markup=reply_markup
                )
                context.user_data['keyboard_message_id'] = new_message.message_id

                # 删除原消息
                await query.message.delete()

                return WAITING_FOR_FORWARD

            elif query.data == "method_manual":
                await query.message.edit_text(
                    get_text(lang, 'manual_input_instruction'),
                    reply_markup=InlineKeyboardMarkup([[
                        InlineKeyboardButton(get_text(lang, 'cancel'), callback_data="cancel")
                    ]])
                )
                return WAITING_FOR_MANUAL_INPUT

        except Exception as e:
            logging.error(f"Error in handle_add_method: {e}")
            await query.message.reply_text(
                get_text(lang, 'error_occurred'),
                reply_markup=InlineKeyboardMarkup([[
                    InlineKeyboardButton(get_text(lang, 'back'), callback_data="channel_management")
                ]])
            )
            return ConversationHandler.END



    def normalize_channel_id(self, channel_id: int) -> int:
        """统一频道ID格式，确保存储时不带-100前缀"""
        str_id = str(channel_id)
        if str_id.startswith('-100'):
            return int(str_id[4:])
        elif str_id.startswith('-'):
            return int(str_id[1:])
        return int(str_id)

    async def handle_forwarded_message(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """处理所有类型的消息"""
        try:
            message = update.message
            user_id = update.effective_user.id
            lang = self.db.get_user_language(user_id)

            # 记录消息类型和属性，用于调试
            logging.info(f"收到消息类型: {type(message).__name__}")
            logging.info(f"消息属性: {dir(message)}")

            if message.text and message.text.lower() in ['cancel', '取消']:
                await message.reply_text(
                    get_text(lang, 'operation_cancelled'),
                    reply_markup=ReplyKeyboardRemove()
                )
                context.user_data.clear()
                # 返回到频道管理菜单
                await self.show_channel_management(update, context)
                return ConversationHandler.END

            await message.reply_text(
                get_text(lang, 'processing'),
                reply_markup=ReplyKeyboardRemove()
            )

            chat_id = None
            chat_title = None
            chat_username = None

            # 处理用户分享
            if hasattr(message, 'users_shared') and message.users_shared:
                users = message.users_shared.users
                if users:
                    user = users[0]
                    chat_id = user.id
                    chat_title = user.first_name or "Unknown User"
                    chat_username = user.username
                    logging.info(f"处理用户分享: ID={chat_id}, 名称={chat_title}")

            # 处理聊天分享
            elif hasattr(message, 'chat_shared') and message.chat_shared:
                raw_chat_id = message.chat_shared.chat_id
                # 将ID统一格式化
                chat_id = self.normalize_channel_id(raw_chat_id)
                logging.info(f"处理聊天分享: 原始ID={raw_chat_id}, 标准化ID={chat_id}")
                try:
                    entity = await self.client.get_entity(int(f"-100{chat_id}"))
                    chat_title = getattr(entity, 'title', None) or getattr(entity, 'first_name', 'Unknown')
                    chat_username = getattr(entity, 'username', None)
                    logging.info(f"获取到实体信息: 标题={chat_title}, 用户名={chat_username}")
                except Exception as e:
                    logging.error(f"获取实体信息时出错: {e}")
                    raise

            # 处理转发消息（新版API使用forward_origin）
            elif hasattr(message, 'forward_origin') and message.forward_origin:
                logging.info(f"检测到forward_origin: {type(message.forward_origin).__name__}")
                logging.info(f"forward_origin属性: {dir(message.forward_origin)}")

                # 尝试获取频道信息
                try:
                    # 如果是频道转发
                    if hasattr(message.forward_origin, 'chat') and message.forward_origin.chat:
                        chat = message.forward_origin.chat
                        chat_id = self.normalize_channel_id(chat.id)
                        chat_title = chat.title
                        chat_username = chat.username
                        logging.info(f"处理新版转发的频道/群组消息: ID={chat_id}, 标题={chat_title}")
                    # 如果是用户转发
                    elif hasattr(message.forward_origin, 'sender_user') and message.forward_origin.sender_user:
                        user = message.forward_origin.sender_user
                        chat_id = user.id
                        chat_title = user.first_name or "Unknown User"
                        chat_username = user.username
                        logging.info(f"处理新版转发的用户消息: ID={chat_id}, 名称={chat_title}")
                    # 如果是频道转发，但使用不同的属性名
                    elif hasattr(message.forward_origin, 'sender_chat') and message.forward_origin.sender_chat:
                        chat = message.forward_origin.sender_chat
                        chat_id = self.normalize_channel_id(chat.id)
                        chat_title = chat.title
                        chat_username = chat.username
                        logging.info(f"处理新版sender_chat转发的频道/群组消息: ID={chat_id}, 标题={chat_title}")
                except Exception as e:
                    logging.error(f"处理forward_origin时出错: {e}")
                    logging.error(f"错误详情: {traceback.format_exc()}")

            # 兼容旧版API - 处理转发的频道/群组消息
            elif hasattr(message, 'forward_from_chat') and message.forward_from_chat:
                chat = message.forward_from_chat
                chat_id = self.normalize_channel_id(chat.id)
                chat_title = chat.title
                chat_username = chat.username
                logging.info(f"处理旧版转发的频道/群组消息: ID={chat_id}, 标题={chat_title}")

            # 兼容旧版API - 处理转发的用户消息
            elif hasattr(message, 'forward_from') and message.forward_from:
                user = message.forward_from
                chat_id = user.id
                chat_title = user.first_name or "Unknown User"
                chat_username = user.username
                logging.info(f"处理旧版转发的用户消息: ID={chat_id}, 名称={chat_title}")

            # 处理普通消息（可能是用户直接输入的ID或其他内容）
            elif message.text and message.text.strip():
                try:
                    # 尝试将文本解析为频道ID
                    input_text = message.text.strip()
                    logging.info(f"尝试将文本解析为频道ID: {input_text}")

                    # 统一处理ID格式
                    channel_id = self.normalize_channel_id(input_text)
                    logging.info(f"标准化后的ID: {channel_id}")

                    # 使用标准格式获取频道信息
                    full_id = int(f"-100{channel_id}")
                    entity = await self.client.get_entity(full_id)

                    chat_id = channel_id
                    chat_title = getattr(entity, 'title', None) or getattr(entity, 'first_name', 'Unknown')
                    chat_username = getattr(entity, 'username', None)
                    logging.info(f"成功解析为频道: ID={chat_id}, 标题={chat_title}")
                except Exception as e:
                    logging.error(f"解析文本为频道ID时出错: {e}")
                    # 不抛出异常，继续检查其他可能性

            if not chat_id:
                logging.warning("未能获取到有效的聊天ID")
                await message.reply_text(
                    get_text(lang, 'invalid_forward'),
                    reply_markup=ReplyKeyboardRemove()
                )
                return WAITING_FOR_FORWARD

            # 添加到数据库
            channel_type = context.user_data.get('channel_type', 'MONITOR')
            logging.info(f"准备添加频道: ID={chat_id}, 名称={chat_title}, 类型={channel_type}")
            success = self.db.add_channel(
                channel_id=chat_id,  # 使用标准化的ID
                channel_name=chat_title or "Unknown",
                channel_username=chat_username,
                channel_type=channel_type
            )

            if success:
                channel_type_display = get_text(
                    lang,
                    'monitor_channel' if channel_type == 'MONITOR' else 'forward_channel'
                )
                await message.reply_text(
                    get_text(lang, 'channel_add_success',
                            name=chat_title or "Unknown",
                            id=chat_id,
                            type=channel_type_display),
                    reply_markup=ReplyKeyboardRemove()
                )
                logging.info(f"成功添加频道: {chat_title} (ID: {chat_id})")
            else:
                await message.reply_text(
                    get_text(lang, 'channel_add_failed'),
                    reply_markup=ReplyKeyboardRemove()
                )
                logging.warning(f"添加频道失败: {chat_title} (ID: {chat_id})")

            context.user_data.clear()
            # 返回到频道管理菜单
            await self.show_channel_management(update, context)
            return ConversationHandler.END

        except Exception as e:
            logging.error(f"处理转发消息时出错: {e}")
            logging.error(f"错误详情: {traceback.format_exc()}")
            try:
                await message.reply_text(
                    get_text(lang, 'process_error'),
                    reply_markup=ReplyKeyboardRemove()
                )
                # 返回到频道管理菜单
                await self.show_channel_management(update, context)
            except Exception as reply_error:
                logging.error(f"发送错误消息时出错: {reply_error}")
            return ConversationHandler.END

    async def handle_manual_input(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """处理手动输入的频道ID"""
        try:
            message = update.message
            input_text = message.text.strip()
            user_id = update.effective_user.id
            lang = self.db.get_user_language(user_id)

            # 记录输入内容用于调试
            logging.info(f"手动输入内容: '{input_text}'")

            try:
                # 统一处理ID格式
                channel_id = self.normalize_channel_id(input_text)
                logging.info(f"标准化后的ID: {channel_id}")

                # 使用标准格式获取频道信息
                full_id = int(f"-100{channel_id}")
                logging.info(f"尝试获取频道信息: {full_id}")
                chat = await self.client.get_entity(full_id)
                logging.info(f"获取到频道信息: {getattr(chat, 'title', None) or getattr(chat, 'first_name', 'Unknown')}")

                channel_type = context.user_data.get('channel_type')
                logging.info(f"准备添加频道: ID={channel_id}, 类型={channel_type}")
                success = self.db.add_channel(
                    channel_id=channel_id,  # 使用标准化的ID
                    channel_name=getattr(chat, 'title', None) or getattr(chat, 'first_name', 'Unknown'),
                    channel_username=getattr(chat, 'username', None),
                    channel_type=channel_type
                )

                if success:
                    channel_type_display = get_text(lang, 'monitor_channel' if channel_type == 'MONITOR' else 'forward_channel')
                    await message.reply_text(
                        get_text(lang, 'channel_add_success',
                                name=getattr(chat, 'title', None) or getattr(chat, 'first_name', 'Unknown'),
                                id=channel_id,
                                type=channel_type_display),
                        reply_markup=ReplyKeyboardRemove()
                    )
                    logging.info(f"成功添加频道: {getattr(chat, 'title', None) or getattr(chat, 'first_name', 'Unknown')} (ID: {channel_id})")
                else:
                    await message.reply_text(
                        get_text(lang, 'channel_add_failed'),
                        reply_markup=ReplyKeyboardRemove()
                    )
                    logging.warning(f"添加频道失败: ID={channel_id}")

                context.user_data.clear()
                # 返回到频道管理菜单
                await self.show_channel_management(update, context)
                return ConversationHandler.END

            except ValueError as e:
                logging.error(f"无效的ID格式: {e}")
                await message.reply_text(
                    get_text(lang, 'invalid_id_format'),
                    reply_markup=ReplyKeyboardRemove()
                )
                return WAITING_FOR_MANUAL_INPUT

            except Exception as e:
                logging.error(f"获取频道信息时出错: {e}")
                logging.error(f"错误详情: {traceback.format_exc()}")
                await message.reply_text(
                    get_text(lang, 'channel_info_error'),
                    reply_markup=ReplyKeyboardRemove()
                )
                return WAITING_FOR_MANUAL_INPUT

        except Exception as e:
            logging.error(f"处理手动输入时出错: {e}")
            logging.error(f"错误详情: {traceback.format_exc()}")
            try:
                await message.reply_text(
                    get_text(lang, 'process_error'),
                    reply_markup=ReplyKeyboardRemove()
                )
                # 返回到频道管理菜单
                await self.show_channel_management(update, context)
            except Exception as reply_error:
                logging.error(f"发送错误消息时出错: {reply_error}")
            return ConversationHandler.END

    def get_display_channel_id(self, channel_id: int) -> str:
        """获取用于显示的频道ID格式"""
        return f"-100{channel_id}" if str(channel_id).isdigit() else str(channel_id)




    async def handle_remove_channel(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """处理删除频道请求"""
        query = update.callback_query
        await query.answer()

        user_id = update.effective_user.id
        lang = self.db.get_user_language(user_id)

        try:
            # 添加详细日志
            logging.info(f"处理删除频道请求: {query.data}")

            channel_id = int(query.data.split('_')[-1])
            logging.info(f"获取频道信息: {channel_id}")

            channel_info = self.db.get_channel_info(channel_id)

            if not channel_info:
                logging.error(f"未找到频道: {channel_id}")
                await query.message.reply_text(
                    get_text(lang, 'channel_not_found'),
                    reply_markup=InlineKeyboardMarkup([[
                        InlineKeyboardButton(get_text(lang, 'back'), callback_data="remove_channel")
                    ]])
                )
                # 删除原消息
                await query.message.delete()
                return

            keyboard = [
                [
                    InlineKeyboardButton(
                        get_text(lang, 'confirm_delete'),
                        callback_data=f"confirm_remove_channel_{channel_id}"
                    )
                ],
                [
                    InlineKeyboardButton(
                        get_text(lang, 'back'),
                        callback_data="remove_channel"
                    )
                ]
            ]

            channel_type_display = get_text(
                lang,
                'monitor_channel' if channel_info['channel_type'] == 'MONITOR' else 'forward_channel'
            )

            logging.info(f"准备发送删除确认消息: {channel_info['channel_name']} (ID: {channel_id})")

            # 发送新消息而不是编辑原消息
            await query.message.reply_text(
                get_text(lang, 'delete_confirm',
                        name=channel_info['channel_name'],
                        id=channel_info['channel_id'],
                        type=channel_type_display),
                reply_markup=InlineKeyboardMarkup(keyboard)
            )

            # 删除原消息
            await query.message.delete()

        except Exception as e:
            logging.error(f"Error in handle_remove_channel: {e}")
            # 发送新消息而不是编辑原消息
            await query.message.reply_text(
                get_text(lang, 'error_occurred'),
                reply_markup=InlineKeyboardMarkup([[
                    InlineKeyboardButton(get_text(lang, 'back'), callback_data="channel_management")
                ]])
            )
            # 尝试删除原消息
            try:
                await query.message.delete()
            except Exception as delete_error:
                logging.error(f"删除原消息失败: {delete_error}")




    async def cancel_add_channel(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """取消添加频道"""
        user_id = update.effective_user.id
        lang = self.db.get_user_language(user_id)

        try:
            # 记录调试信息
            logging.info(f"执行取消添加频道操作: {update.effective_user.id}")
            logging.info(f"当前用户数据: {context.user_data}")

            # 移除自定义键盘
            if context.user_data.get('awaiting_share'):
                if update.callback_query:
                    await update.callback_query.message.reply_text(
                        get_text(lang, 'operation_cancelled'),
                        reply_markup=CustomKeyboard.remove_keyboard()
                    )
                else:
                    await update.message.reply_text(
                        get_text(lang, 'operation_cancelled'),
                        reply_markup=CustomKeyboard.remove_keyboard()
                    )
            else:
                if update.callback_query:
                    await update.callback_query.message.edit_text(get_text(lang, 'operation_cancelled'))
                else:
                    await update.message.reply_text(get_text(lang, 'operation_cancelled'))

            # 强制清理所有状态
            context.user_data.clear()

            # 记录清理后的状态
            logging.info(f"清理后的用户数据: {context.user_data}")

            # 返回到频道管理菜单
            try:
                await self.show_channel_management(update, context)
                logging.info("成功返回到频道管理菜单")
            except Exception as menu_error:
                logging.error(f"显示频道管理菜单时出错: {menu_error}")
                logging.error(f"错误详情: {traceback.format_exc()}")
                # 尝试发送简单消息
                try:
                    if update.message:
                        await update.message.reply_text(
                            get_text(lang, 'back_to_menu'),
                            reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton(
                                get_text(lang, 'back_to_menu'), callback_data="channel_management"
                            )]])
                        )
                    elif update.callback_query:
                        await update.callback_query.message.reply_text(
                            get_text(lang, 'back_to_menu'),
                            reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton(
                                get_text(lang, 'back_to_menu'), callback_data="channel_management"
                            )]])
                        )
                except Exception as reply_error:
                    logging.error(f"发送简单消息时出错: {reply_error}")

            return ConversationHandler.END

        except Exception as e:
            logging.error(f"取消添加频道时出错: {e}")
            logging.error(f"错误详情: {traceback.format_exc()}")
            try:
                # 强制清理所有状态
                context.user_data.clear()

                if update.message:
                    await update.message.reply_text(
                        get_text(lang, 'error_occurred'),
                        reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton(
                            get_text(lang, 'back_to_menu'), callback_data="channel_management"
                        )]])
                    )
                elif update.callback_query:
                    await update.callback_query.message.reply_text(
                        get_text(lang, 'error_occurred'),
                        reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton(
                            get_text(lang, 'back_to_menu'), callback_data="channel_management"
                        )]])
                    )
            except Exception as reply_error:
                logging.error(f"发送错误消息时出错: {reply_error}")

            return ConversationHandler.END

    async def show_remove_channel_options(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """显示可删除的频道列表"""
        query = update.callback_query
        await query.answer()

        user_id = update.effective_user.id
        lang = self.db.get_user_language(user_id)

        try:
            # 添加详细日志
            logging.info(f"显示删除频道选项: {query.data}")

            # 获取页码
            page = 1
            if query.data and '_' in query.data:
                try:
                    # 确保我们只获取最后一个数字作为页码
                    parts = query.data.split('_')
                    if len(parts) > 1 and parts[-1].isdigit():
                        page = int(parts[-1])
                        logging.info(f"当前页码: {page}")
                except ValueError:
                    page = 1

            per_page = 7
            monitor_result = self.db.get_channels_by_type('MONITOR', page, per_page)
            forward_result = self.db.get_channels_by_type('FORWARD', page, per_page)

            monitor_channels = monitor_result['channels']
            forward_channels = forward_result['channels']
            total_pages = max(monitor_result['total_pages'], forward_result['total_pages'])

            # 确保至少有1页
            total_pages = max(1, total_pages)
            # 确保页码在有效范围内
            page = max(1, min(page, total_pages))
            logging.info(f"页面信息: 当前页={page}, 总页数={total_pages}")
            logging.info(f"监控频道数量: {len(monitor_channels)}, 转发频道数量: {len(forward_channels)}")

            if not monitor_channels and not forward_channels:
                logging.info("没有可用的频道")
                # 发送新消息而不是编辑原消息
                await query.message.reply_text(
                    get_text(lang, 'no_channels'),
                    reply_markup=InlineKeyboardMarkup([[
                        InlineKeyboardButton(get_text(lang, 'back'), callback_data="channel_management")
                    ]])
                )
                # 删除原消息
                await query.message.delete()
                return

            keyboard = []

            if monitor_channels:
                keyboard.append([InlineKeyboardButton(
                    f"-- {get_text(lang, 'monitor_channel')} --",
                    callback_data="dummy"
                )])
                for channel in monitor_channels:
                    keyboard.append([InlineKeyboardButton(
                        f"🔍 {channel['channel_name']}",
                        callback_data=f"remove_channel_{channel['channel_id']}"
                    )])

            if forward_channels:
                keyboard.append([InlineKeyboardButton(
                    f"-- {get_text(lang, 'forward_channel')} --",
                    callback_data="dummy"
                )])
                for channel in forward_channels:
                    keyboard.append([InlineKeyboardButton(
                        f"📢 {channel['channel_name']}",
                        callback_data=f"remove_channel_{channel['channel_id']}"
                    )])

            # 导航按钮
            navigation = []
            if page > 1:
                navigation.append(InlineKeyboardButton(
                    get_text(lang, 'previous_page'),
                    callback_data=f"remove_channel_{page-1}"
                ))
            if page < total_pages:
                navigation.append(InlineKeyboardButton(
                    get_text(lang, 'next_page'),
                    callback_data=f"remove_channel_{page+1}"
                ))
            if navigation:
                keyboard.append(navigation)

            keyboard.append([InlineKeyboardButton(
                get_text(lang, 'back'),
                callback_data="channel_management"
            )])

            text = (
                f"{get_text(lang, 'remove_channel_title')}\n\n"
                f"{get_text(lang, 'page_info').format(current=page, total=total_pages)}"
            )

            logging.info("准备发送频道列表")
            # 发送新消息而不是编辑原消息
            await query.message.reply_text(
                text,
                reply_markup=InlineKeyboardMarkup(keyboard)
            )
            # 删除原消息
            await query.message.delete()

        except Exception as e:
            logging.error(f"Error in show_remove_channel_options: {e}")
            # 发送新消息而不是编辑原消息
            await query.message.reply_text(
                get_text(lang, 'error_occurred'),
                reply_markup=InlineKeyboardMarkup([[
                    InlineKeyboardButton(get_text(lang, 'back'), callback_data="channel_management")
                ]])
            )
            # 尝试删除原消息
            try:
                await query.message.delete()
            except Exception as delete_error:
                logging.error(f"删除原消息失败: {delete_error}")




    async def handle_remove_confirmation(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """处理删除确认"""
        query = update.callback_query
        await query.answer()

        user_id = update.effective_user.id
        lang = self.db.get_user_language(user_id)

        try:
            # 添加详细日志
            logging.info(f"处理删除确认回调: {query.data}")

            # 解析频道ID
            parts = query.data.split('_')
            if len(parts) >= 3:
                channel_id = int(parts[-1])
                logging.info(f"准备删除频道ID: {channel_id}")

                # 获取频道信息用于日志记录
                channel_info = self.db.get_channel_info(channel_id)
                if channel_info:
                    logging.info(f"删除频道: {channel_info['channel_name']} (ID: {channel_id})")

                # 执行删除操作
                success = self.db.remove_channel(channel_id)
                logging.info(f"删除操作结果: {success}")

                if success:
                    # 发送新消息而不是编辑原消息
                    await query.message.reply_text(
                        get_text(lang, 'channel_deleted'),
                        reply_markup=InlineKeyboardMarkup([[
                            InlineKeyboardButton(get_text(lang, 'back'), callback_data="channel_management")
                        ]])
                    )
                    # 删除原消息
                    await query.message.delete()
                else:
                    # 发送新消息而不是编辑原消息
                    await query.message.reply_text(
                        get_text(lang, 'delete_failed'),
                        reply_markup=InlineKeyboardMarkup([[
                            InlineKeyboardButton(get_text(lang, 'retry'), callback_data="remove_channel")
                        ]])
                    )
                    # 删除原消息
                    await query.message.delete()
            else:
                logging.error(f"无效的回调数据格式: {query.data}")
                await query.message.reply_text(
                    get_text(lang, 'error_occurred'),
                    reply_markup=InlineKeyboardMarkup([[
                        InlineKeyboardButton(get_text(lang, 'back'), callback_data="channel_management")
                    ]])
                )
        except Exception as e:
            logging.error(f"Error in handle_remove_confirmation: {e}")
            # 发送新消息而不是编辑原消息
            await query.message.reply_text(
                get_text(lang, 'delete_error'),
                reply_markup=InlineKeyboardMarkup([[
                    InlineKeyboardButton(get_text(lang, 'back'), callback_data="channel_management")
                ]])
            )
            # 尝试删除原消息
            try:
                await query.message.delete()
            except Exception as delete_error:
                logging.error(f"删除原消息失败: {delete_error}")


    async def show_channel_management(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """显示频道管理菜单"""
        user_id = update.effective_user.id
        lang = self.db.get_user_language(user_id)

        keyboard = [
            [
                InlineKeyboardButton(get_text(lang, 'add_channel'), callback_data="add_channel"),
                InlineKeyboardButton(get_text(lang, 'delete_channel'), callback_data="remove_channel")
            ],
            [
                InlineKeyboardButton(get_text(lang, 'channel_list'), callback_data="list_channels"),
                InlineKeyboardButton(get_text(lang, 'pair_management'), callback_data="view_pairs")
            ],
            [
                InlineKeyboardButton(get_text(lang, 'filter_rules'), callback_data="filter_rules"),
                InlineKeyboardButton(get_text(lang, 'time_settings'), callback_data="time_settings")
            ]
        ]

        menu_text = get_text(lang, 'channel_management')

        try:
            if isinstance(update, Update):
                if update.callback_query:
                    await update.callback_query.message.edit_text(
                        menu_text,
                        reply_markup=InlineKeyboardMarkup(keyboard)
                    )
                elif update.message:
                    await update.message.reply_text(
                        menu_text,
                        reply_markup=InlineKeyboardMarkup(keyboard)
                    )
        except Exception as e:
            logging.error(f"Error in show_channel_management: {e}")
            # 发生错误时尝试发送错误消息
            try:
                if update.callback_query:
                    await update.callback_query.message.edit_text(
                        get_text(lang, 'error_occurred'),
                        reply_markup=InlineKeyboardMarkup([[
                            InlineKeyboardButton(get_text(lang, 'retry'), callback_data="channel_management")
                        ]])
                    )
                elif update.message:
                    await update.message.reply_text(
                        get_text(lang, 'error_occurred'),
                        reply_markup=InlineKeyboardMarkup([[
                            InlineKeyboardButton(get_text(lang, 'retry'), callback_data="channel_management")
                        ]])
                    )
            except Exception as e2:
                logging.error(f"Error sending error message: {e2}")


    async def handle_back(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """处理返回操作"""
        query = update.callback_query
        await query.answer()

        user_id = update.effective_user.id
        lang = self.db.get_user_language(user_id)

        destination = query.data.split('_')[2]

        if destination == "main":
            # 返回主菜单
            await self.show_channel_management(update, context)
        elif destination == "channels":
            # 返回频道列表
            await self.show_channel_list(update, context)
        elif destination == "pairs":
            # 返回配对列表
            await self.view_channel_pairs(update, context)
        else:
            # 默认返回主菜单
            await self.show_channel_management(update, context)

    # 其他配对相关方法的实现...
    async def view_channel_pairs(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """显示频道配对列表"""
        query = update.callback_query
        await query.answer()

        user_id = update.effective_user.id
        lang = self.db.get_user_language(user_id)

        # 获取页码
        page = 1
        if query.data and '_' in query.data:
            try:
                page = int(query.data.split('_')[-1])
            except ValueError:
                page = 1

        per_page = 7
        monitor_result = self.db.get_channels_by_type('MONITOR', page, per_page)

        if not monitor_result['channels']:
            await query.message.edit_text(
                get_text(lang, 'no_monitor_channels'),
                reply_markup=InlineKeyboardMarkup([[
                    InlineKeyboardButton(get_text(lang, 'back'), callback_data="channel_management")
                ]])
            )
            return

        text = get_text(lang, 'pair_management_title') + "\n\n"
        keyboard = []

        for channel in monitor_result['channels']:
            forward_pairs = self.db.get_forward_channels(channel['channel_id'], 1, 3)
            text += f"\n🔍 {channel['channel_name']}\n"

            if forward_pairs['channels']:
                text += get_text(lang, 'current_pairs') + "\n"
                for fwd in forward_pairs['channels']:
                    text += f"└─ 📢 {fwd['channel_name']}\n"
                if forward_pairs['total'] > 3:
                    text += get_text(lang, 'more_pairs', count=forward_pairs['total']) + "\n"
            else:
                text += get_text(lang, 'no_pairs') + "\n"

            keyboard.append([InlineKeyboardButton(
                get_text(lang, 'manage_pairs_button').format(name=channel['channel_name']),
                callback_data=f"manage_pair_{channel['channel_id']}_1"
            )])

        # 添加导航按钮
        navigation = []
        if page > 1:
            navigation.append(InlineKeyboardButton(
                get_text(lang, 'previous_page'),
                callback_data=f"view_pairs_{page-1}"
            ))
        if page < monitor_result['total_pages']:
            navigation.append(InlineKeyboardButton(
                get_text(lang, 'next_page'),
                callback_data=f"view_pairs_{page+1}"
            ))
        if navigation:
            keyboard.append(navigation)

        keyboard.append([InlineKeyboardButton(
            get_text(lang, 'back'),
            callback_data="channel_management"
        )])

        text += f"\n{get_text(lang, 'page_info').format(current=page, total=monitor_result['total_pages'])}"

        # 检查消息长度并截断如果需要
        if len(text) > 4096:
            text = text[:4000] + "\n\n" + get_text(lang, 'message_truncated')

        await query.message.edit_text(
            text,
            reply_markup=InlineKeyboardMarkup(keyboard)
        )

    async def show_channel_list(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
            """显示频道列表"""
            query = update.callback_query
            await query.answer()

            user_id = update.effective_user.id
            lang = self.db.get_user_language(user_id)

            # 获取页码
            page = 1
            if query.data and '_' in query.data:
                try:
                    page = int(query.data.split('_')[-1])
                except ValueError:
                    page = 1

            per_page = 7  # 每页显示7个频道

            # 获取分页数据
            monitor_result = self.db.get_channels_by_type('MONITOR', page, per_page)
            forward_result = self.db.get_channels_by_type('FORWARD', page, per_page)

            monitor_channels = monitor_result['channels']
            forward_channels = forward_result['channels']
            total_pages = max(monitor_result['total_pages'], forward_result['total_pages'])

            text = get_text(lang, 'channel_list_title')

            if monitor_channels:
                text += get_text(lang, 'monitor_channels')
                for idx, channel in enumerate(monitor_channels, 1):
                    text += get_text(lang, 'channel_info').format(
                        idx=idx,
                        name=channel['channel_name'],
                        id=channel['channel_id'],
                        username=channel['channel_username'] or 'N/A'
                    )

            if forward_channels:
                text += get_text(lang, 'forward_channels')
                for idx, channel in enumerate(forward_channels, 1):
                    text += get_text(lang, 'channel_info').format(
                        idx=idx,
                        name=channel['channel_name'],
                        id=channel['channel_id'],
                        username=channel['channel_username'] or 'N/A'
                    )

            if not monitor_channels and not forward_channels:
                text += get_text(lang, 'no_channels_config')

            # 构建分页按钮
            keyboard = []
            navigation = []

            if page > 1:
                navigation.append(InlineKeyboardButton(
                    get_text(lang, 'previous_page'),
                    callback_data=f"list_channels_{page-1}"
                ))
            if page < total_pages:
                navigation.append(InlineKeyboardButton(
                    get_text(lang, 'next_page'),
                    callback_data=f"list_channels_{page+1}"
                ))

            if navigation:
                keyboard.append(navigation)

            keyboard.append([InlineKeyboardButton(
                get_text(lang, 'back'),
                callback_data="channel_management"
            )])

            # 添加当前页码信息
            text += f"\n{get_text(lang, 'page_info').format(current=page, total=total_pages)}"

            try:
                await query.message.edit_text(
                    text,
                    reply_markup=InlineKeyboardMarkup(keyboard)
                )
            except Exception as e:
                logging.error(f"Error in show_channel_list: {e}")
                # 如果消息太长，尝试发送简化版本
                await query.message.edit_text(
                    get_text(lang, 'list_too_long'),
                    reply_markup=InlineKeyboardMarkup(keyboard)
                )

    async def handle_manage_specific_pair(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """处理特定频道的配对管理"""
        query = update.callback_query
        await query.answer()

        user_id = update.effective_user.id
        lang = self.db.get_user_language(user_id)

        try:
            parts = query.data.split('_')
            monitor_id = int(parts[2])
            logging.info(f"get monitor_id -- {monitor_id}")
            page = int(parts[3]) if len(parts) > 3 else 1

            monitor_info = self.db.get_channel_info(monitor_id)
            if not monitor_info:
                await query.message.edit_text(
                    get_text(lang, 'channel_not_found'),
                    reply_markup=InlineKeyboardMarkup([[
                        InlineKeyboardButton(get_text(lang, 'back'), callback_data="channel_management")
                    ]])
                )
                return

            text = get_text(lang, 'manage_pair_title', channel=monitor_info['channel_name']) + "\n\n"
            keyboard = []

            # 获取当前配对
            current_pairs = self.db.get_forward_channels(monitor_id, page)
            if current_pairs['channels']:
                text += get_text(lang, 'current_pairs') + "\n"
                for channel in current_pairs['channels']:
                    text += f"📢 {channel['channel_name']}\n"
                    keyboard.append([InlineKeyboardButton(
                        get_text(lang, 'remove_pair_button', name=channel['channel_name']),
                        callback_data=f"remove_pair_{monitor_id}_{channel['channel_id']}"
                    )])
            else:
                text += get_text(lang, 'no_pairs') + "\n"

            # 获取可用的转发频道
            available_channels = self.db.get_unpaired_forward_channels(monitor_id, page)
            if available_channels['channels']:
                text += "\n" + get_text(lang, 'available_channels') + "\n"
                for channel in available_channels['channels']:
                    keyboard.append([InlineKeyboardButton(
                        get_text(lang, 'add_pair_button', name=channel['channel_name']),
                        callback_data=f"add_pair_{monitor_id}_{channel['channel_id']}_add"
                    )])

            # 导航按钮
            navigation = []
            total_pages = max(current_pairs['total_pages'], available_channels['total_pages'])
            if page > 1:
                navigation.append(InlineKeyboardButton(
                    get_text(lang, 'previous_page'),
                    callback_data=f"manage_pair_{monitor_id}_{page-1}"
                ))
            if page < total_pages:
                navigation.append(InlineKeyboardButton(
                    get_text(lang, 'next_page'),
                    callback_data=f"manage_pair_{monitor_id}_{page+1}"
                ))
            if navigation:
                keyboard.append(navigation)

            # 返回按钮
            keyboard.append([
                InlineKeyboardButton(get_text(lang, 'back_to_pairs'), callback_data="view_pairs"),
                InlineKeyboardButton(get_text(lang, 'back_to_menu'), callback_data="channel_management")
            ])

            # 添加页码信息
            if total_pages > 1:
                text += f"\n{get_text(lang, 'page_info').format(current=page, total=total_pages)}"

            try:
                await query.message.edit_text(
                    text,
                    reply_markup=InlineKeyboardMarkup(keyboard)
                )
            except BadRequest as e:
                if not str(e).startswith("Message is not modified"):
                    raise

        except Exception as e:
            logging.error(f"Error in handle_manage_specific_pair: {e}")
            await query.message.edit_text(
                get_text(lang, 'error_occurred'),
                reply_markup=InlineKeyboardMarkup([[
                    InlineKeyboardButton(get_text(lang, 'back'), callback_data="channel_management")
                ]])
            )


    async def handle_add_specific_pair(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """处理添加特定配对"""
        query = update.callback_query
        await query.answer()

        user_id = update.effective_user.id
        lang = self.db.get_user_language(user_id)

        try:
            parts = query.data.split('_')
            if len(parts) >= 4:
                monitor_id = int(parts[2])
                forward_id = int(parts[3])
            else:
                raise ValueError("Invalid callback data format")

            # 获取频道信息用于显示
            monitor_info = self.db.get_channel_info(monitor_id)
            forward_info = self.db.get_channel_info(forward_id)

            if not monitor_info or not forward_info:
                await query.message.edit_text(
                    get_text(lang, 'channel_not_found'),
                    reply_markup=InlineKeyboardMarkup([[
                        InlineKeyboardButton(get_text(lang, 'back'), callback_data="view_pairs")
                    ]])
                )
                return

            success = self.db.add_channel_pair(monitor_id, forward_id)

            if success:
                await query.message.edit_text(
                    get_text(lang, 'pair_added_success').format(
                        monitor=monitor_info['channel_name'],
                        forward=forward_info['channel_name']
                    ),
                    reply_markup=InlineKeyboardMarkup([[
                        InlineKeyboardButton(
                            get_text(lang, 'back_to_pairs_management'),
                            callback_data=f"manage_pair_{monitor_id}_1"
                        )
                    ]])
                )
            else:
                await query.message.edit_text(
                    get_text(lang, 'pair_add_failed'),
                    reply_markup=InlineKeyboardMarkup([[
                        InlineKeyboardButton(
                            get_text(lang, 'retry'),
                            callback_data=f"manage_pair_{monitor_id}_1"
                        )
                    ]])
                )
        except Exception as e:
            logging.error(f"Error in handle_add_specific_pair: {e}")
            await query.message.edit_text(
                get_text(lang, 'error_adding_pair'),
                reply_markup=InlineKeyboardMarkup([[
                    InlineKeyboardButton(get_text(lang, 'back'), callback_data="view_pairs")
                ]])
            )

    async def handle_remove_specific_pair(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """处理移除配对"""
        query = update.callback_query
        await query.answer()

        user_id = update.effective_user.id
        lang = self.db.get_user_language(user_id)

        try:
            parts = query.data.split('_')
            monitor_id = int(parts[2])
            forward_id = int(parts[3])

            # 获取频道信息用于显示
            monitor_info = self.db.get_channel_info(monitor_id)
            forward_info = self.db.get_channel_info(forward_id)

            if not monitor_info or not forward_info:
                await query.message.edit_text(
                    get_text(lang, 'channel_not_found'),
                    reply_markup=InlineKeyboardMarkup([[
                        InlineKeyboardButton(get_text(lang, 'back'), callback_data=f"manage_pair_{monitor_id}_1")
                    ]])
                )
                return

            # 显示确认消息
            keyboard = [
                [
                    InlineKeyboardButton(
                        get_text(lang, 'confirm_remove'),
                        callback_data=f"confirm_remove_pair_{monitor_id}_{forward_id}"
                    ),
                    InlineKeyboardButton(
                        get_text(lang, 'cancel'),
                        callback_data=f"manage_pair_{monitor_id}_1"
                    )
                ]
            ]

            await query.message.edit_text(
                get_text(lang, 'confirm_remove_pair').format(
                    monitor=monitor_info['channel_name'],
                    forward=forward_info['channel_name']
                ),
                reply_markup=InlineKeyboardMarkup(keyboard)
            )

        except Exception as e:
            logging.error(f"Error in handle_remove_specific_pair: {e}")
            await query.message.edit_text(
                get_text(lang, 'error_removing_pair'),
                reply_markup=InlineKeyboardMarkup([[
                    InlineKeyboardButton(get_text(lang, 'back'), callback_data="view_pairs")
                ]])
            )

    async def handle_confirm_remove_pair(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """处理确认移除配对"""
        query = update.callback_query
        await query.answer()

        user_id = update.effective_user.id
        lang = self.db.get_user_language(user_id)

        try:
            parts = query.data.split('_')
            monitor_id = int(parts[3])
            forward_id = int(parts[4])

            success = self.db.remove_channel_pair(monitor_id, forward_id)

            if success:
                await query.message.edit_text(
                    get_text(lang, 'pair_removed_success'),
                    reply_markup=InlineKeyboardMarkup([[
                        InlineKeyboardButton(
                            get_text(lang, 'back_to_pairs_management'),
                            callback_data=f"manage_pair_{monitor_id}_1"
                        )
                    ]])
                )
            else:
                await query.message.edit_text(
                    get_text(lang, 'pair_remove_failed'),
                    reply_markup=InlineKeyboardMarkup([[
                        InlineKeyboardButton(
                            get_text(lang, 'retry'),
                            callback_data=f"manage_pair_{monitor_id}_1"
                        )
                    ]])
                )

        except Exception as e:
            logging.error(f"Error in handle_confirm_remove_pair: {e}")
            await query.message.edit_text(
                get_text(lang, 'error_removing_pair'),
                reply_markup=InlineKeyboardMarkup([[
                    InlineKeyboardButton(get_text(lang, 'back'), callback_data="view_pairs")
                ]])
            )

    async def show_filter_rules_menu(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """显示过滤规则管理菜单"""
        query = update.callback_query
        await query.answer()

        user_id = update.effective_user.id
        lang = self.db.get_user_language(user_id)

        keyboard = [
            [InlineKeyboardButton(get_text(lang, 'add_filter_rule'), callback_data="add_filter_rule")],
            [InlineKeyboardButton(get_text(lang, 'list_filter_rules'), callback_data="list_filter_rules")],
            [InlineKeyboardButton(get_text(lang, 'media_filter'), callback_data="media_filter")],
            [InlineKeyboardButton(get_text(lang, 'back'), callback_data="channel_management")]
        ]

        await query.message.edit_text(
            get_text(lang, 'filter_rules_menu'),
            reply_markup=InlineKeyboardMarkup(keyboard)
        )

    async def show_time_settings_menu(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """显示时间设置管理菜单"""
        query = update.callback_query
        await query.answer()

        user_id = update.effective_user.id
        lang = self.db.get_user_language(user_id)

        keyboard = [
            [InlineKeyboardButton(get_text(lang, 'add_time_filter'), callback_data="add_time_filter")],
            [InlineKeyboardButton(get_text(lang, 'list_time_filters'), callback_data="list_time_filters")],
            [InlineKeyboardButton(get_text(lang, 'back'), callback_data="channel_management")]
        ]

        await query.message.edit_text(
            get_text(lang, 'time_settings_menu'),
            reply_markup=InlineKeyboardMarkup(keyboard)
        )

    async def show_pair_selection_for_filter(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """显示频道配对选择界面，用于过滤规则"""
        query = update.callback_query
        await query.answer()

        user_id = update.effective_user.id
        lang = self.db.get_user_language(user_id)

        # 获取页码
        page = 1
        if query.data and '_' in query.data:
            try:
                parts = query.data.split('_')
                if len(parts) > 1 and parts[-1].isdigit():
                    page = int(parts[-1])
            except ValueError:
                page = 1

        # 获取所有频道配对
        pairs = self.db.get_all_channel_pairs()

        if not pairs:
            await query.message.edit_text(
                get_text(lang, 'no_pairs'),
                reply_markup=InlineKeyboardMarkup([[
                    InlineKeyboardButton(get_text(lang, 'back'), callback_data="filter_rules")
                ]])
            )
            return

        # 每页显示的配对数
        per_page = 5
        total_pages = (len(pairs) + per_page - 1) // per_page
        page = max(1, min(page, total_pages))

        # 获取当前页的配对
        start_idx = (page - 1) * per_page
        end_idx = min(start_idx + per_page, len(pairs))
        current_pairs = pairs[start_idx:end_idx]

        keyboard = []
        for pair in current_pairs:
            keyboard.append([InlineKeyboardButton(
                f"{pair['monitor_name']} → {pair['forward_name']}",
                callback_data=f"filter_pair_{pair['pair_id']}"
            )])

        # 构建分页按钮
        navigation = []
        if page > 1:
            navigation.append(InlineKeyboardButton(
                get_text(lang, 'previous_page'),
                callback_data=f"add_filter_rule_{page-1}"
            ))
        if page < total_pages:
            navigation.append(InlineKeyboardButton(
                get_text(lang, 'next_page'),
                callback_data=f"add_filter_rule_{page+1}"
            ))

        if navigation:
            keyboard.append(navigation)

        keyboard.append([InlineKeyboardButton(get_text(lang, 'back'), callback_data="filter_rules")])

        # 添加当前页码信息
        page_info = f"\n{get_text(lang, 'page_info').format(current=page, total=total_pages)}"

        await query.message.edit_text(
            get_text(lang, 'select_pair_for_filter') + page_info,
            reply_markup=InlineKeyboardMarkup(keyboard)
        )

    async def show_pair_selection_for_time(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """显示频道配对选择界面，用于时间设置"""
        query = update.callback_query
        await query.answer()

        user_id = update.effective_user.id
        lang = self.db.get_user_language(user_id)

        # 获取页码
        page = 1
        if query.data and '_' in query.data:
            try:
                parts = query.data.split('_')
                if len(parts) > 1 and parts[-1].isdigit():
                    page = int(parts[-1])
            except ValueError:
                page = 1

        # 获取所有频道配对
        pairs = self.db.get_all_channel_pairs()

        if not pairs:
            await query.message.edit_text(
                get_text(lang, 'no_pairs'),
                reply_markup=InlineKeyboardMarkup([[
                    InlineKeyboardButton(get_text(lang, 'back'), callback_data="time_settings")
                ]])
            )
            return

        # 每页显示的配对数
        per_page = 5
        total_pages = (len(pairs) + per_page - 1) // per_page
        page = max(1, min(page, total_pages))

        # 获取当前页的配对
        start_idx = (page - 1) * per_page
        end_idx = min(start_idx + per_page, len(pairs))
        current_pairs = pairs[start_idx:end_idx]

        keyboard = []
        for pair in current_pairs:
            keyboard.append([InlineKeyboardButton(
                f"{pair['monitor_name']} → {pair['forward_name']}",
                callback_data=f"time_pair_{pair['pair_id']}"
            )])

        # 构建分页按钮
        navigation = []
        if page > 1:
            navigation.append(InlineKeyboardButton(
                get_text(lang, 'previous_page'),
                callback_data=f"add_time_filter_{page-1}"
            ))
        if page < total_pages:
            navigation.append(InlineKeyboardButton(
                get_text(lang, 'next_page'),
                callback_data=f"add_time_filter_{page+1}"
            ))

        if navigation:
            keyboard.append(navigation)

        keyboard.append([InlineKeyboardButton(get_text(lang, 'back'), callback_data="time_settings")])

        # 添加当前页码信息
        page_info = f"\n{get_text(lang, 'page_info').format(current=page, total=total_pages)}"

        await query.message.edit_text(
            get_text(lang, 'select_pair_for_time') + page_info,
            reply_markup=InlineKeyboardMarkup(keyboard)
        )

    async def show_filter_rules_list(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """显示过滤规则列表"""
        query = update.callback_query
        await query.answer()

        user_id = update.effective_user.id
        lang = self.db.get_user_language(user_id)

        # 获取页码
        page = 1
        if query.data and '_' in query.data:
            try:
                page = int(query.data.split('_')[-1])
            except ValueError:
                page = 1

        # 获取所有频道配对
        pairs = self.db.get_all_channel_pairs()

        if not pairs:
            await query.message.edit_text(
                get_text(lang, 'no_pairs'),
                reply_markup=InlineKeyboardMarkup([[
                    InlineKeyboardButton(get_text(lang, 'back'), callback_data="filter_rules")
                ]])
            )
            return

        # 每页显示的配对数
        per_page = 3
        total_pages = (len(pairs) + per_page - 1) // per_page
        page = max(1, min(page, total_pages))

        # 获取当前页的配对
        start_idx = (page - 1) * per_page
        end_idx = min(start_idx + per_page, len(pairs))
        current_pairs = pairs[start_idx:end_idx]

        text = get_text(lang, 'filter_rules_menu') + "\n\n"

        # 初始化键盘
        keyboard = []

        # 获取每个配对的过滤规则
        for pair in current_pairs:
            pair_id = pair['pair_id']
            rules = self.db.get_filter_rules(pair_id)

            text += f"\n**{pair['monitor_name']} → {pair['forward_name']}**\n"

            if not rules:
                text += get_text(lang, 'no_filter_rules') + "\n"
            else:
                for rule in rules:
                    rule_type = get_text(lang, rule['rule_type'].lower())
                    filter_mode = get_text(lang, rule['filter_mode'].lower())
                    text += f"- {rule_type} ({filter_mode}): {rule['pattern']}\n"
                    # 添加删除按钮
                    keyboard.append([InlineKeyboardButton(
                        f"删除: {rule['pattern'][:15]}{'...' if len(rule['pattern']) > 15 else ''}",
                        callback_data=f"delete_filter_rule_{rule['rule_id']}"
                    )])

        # 构建分页按钮
        navigation = []

        if page > 1:
            navigation.append(InlineKeyboardButton(
                get_text(lang, 'previous_page'),
                callback_data=f"list_filter_rules_{page-1}"
            ))
        if page < total_pages:
            navigation.append(InlineKeyboardButton(
                get_text(lang, 'next_page'),
                callback_data=f"list_filter_rules_{page+1}"
            ))

        if navigation:
            keyboard.append(navigation)

        keyboard.append([InlineKeyboardButton(get_text(lang, 'back'), callback_data="filter_rules")])

        # 添加当前页码信息
        text += f"\n{get_text(lang, 'page_info').format(current=page, total=total_pages)}"

        try:
            await query.message.edit_text(
                text,
                reply_markup=InlineKeyboardMarkup(keyboard),
                parse_mode='Markdown'
            )
        except Exception as e:
            logging.error(f"Error in show_filter_rules_list: {e}")
            # 如果消息太长，尝试发送简化版本
            await query.message.edit_text(
                get_text(lang, 'list_too_long'),
                reply_markup=InlineKeyboardMarkup(keyboard)
            )

    async def show_time_filters_list(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """显示时间过滤器列表"""
        query = update.callback_query
        await query.answer()

        user_id = update.effective_user.id
        lang = self.db.get_user_language(user_id)

        # 获取页码
        page = 1
        if query.data and '_' in query.data:
            try:
                page = int(query.data.split('_')[-1])
            except ValueError:
                page = 1

        # 获取所有频道配对
        pairs = self.db.get_all_channel_pairs()

        if not pairs:
            await query.message.edit_text(
                get_text(lang, 'no_pairs'),
                reply_markup=InlineKeyboardMarkup([[
                    InlineKeyboardButton(get_text(lang, 'back'), callback_data="time_settings")
                ]])
            )
            return

        # 每页显示的配对数
        per_page = 3
        total_pages = (len(pairs) + per_page - 1) // per_page
        page = max(1, min(page, total_pages))

        # 获取当前页的配对
        start_idx = (page - 1) * per_page
        end_idx = min(start_idx + per_page, len(pairs))
        current_pairs = pairs[start_idx:end_idx]

        text = get_text(lang, 'time_settings_menu') + "\n\n"

        # 初始化键盘
        keyboard = []

        # 获取每个配对的时间过滤器
        for pair in current_pairs:
            pair_id = pair['pair_id']
            filters = self.db.get_time_filters(pair_id)

            text += f"\n**{pair['monitor_name']} → {pair['forward_name']}**\n"

            if not filters:
                text += get_text(lang, 'no_time_filters') + "\n"
            else:
                for filter in filters:
                    mode = get_text(lang, filter['mode'].lower())
                    days = filter['days_of_week']
                    text += f"- {mode}: {filter['start_time']}-{filter['end_time']} ({days})\n"
                    # 添加删除按钮
                    keyboard.append([InlineKeyboardButton(
                        f"删除: {filter['start_time']}-{filter['end_time']}",
                        callback_data=f"delete_time_filter_{filter['filter_id']}"
                    )])

        # 构建分页按钮
        navigation = []

        if page > 1:
            navigation.append(InlineKeyboardButton(
                get_text(lang, 'previous_page'),
                callback_data=f"list_time_filters_{page-1}"
            ))
        if page < total_pages:
            navigation.append(InlineKeyboardButton(
                get_text(lang, 'next_page'),
                callback_data=f"list_time_filters_{page+1}"
            ))

        if navigation:
            keyboard.append(navigation)

        keyboard.append([InlineKeyboardButton(get_text(lang, 'back'), callback_data="time_settings")])

        # 添加当前页码信息
        text += f"\n{get_text(lang, 'page_info').format(current=page, total=total_pages)}"

        try:
            await query.message.edit_text(
                text,
                reply_markup=InlineKeyboardMarkup(keyboard),
                parse_mode='Markdown'
            )
        except Exception as e:
            logging.error(f"Error in show_time_filters_list: {e}")
            # 如果消息太长，尝试发送简化版本
            await query.message.edit_text(
                get_text(lang, 'list_too_long'),
                reply_markup=InlineKeyboardMarkup(keyboard)
            )

    async def handle_filter_pair_selection(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """处理过滤规则的频道配对选择"""
        query = update.callback_query
        await query.answer()

        user_id = update.effective_user.id
        lang = self.db.get_user_language(user_id)

        # 获取配对ID
        pair_id = query.data.split('_')[-1]
        context.user_data['filter_pair_id'] = pair_id

        # 解析配对ID获取频道信息
        try:
            monitor_id, forward_id = pair_id.split(':')
            monitor_info = self.db.get_channel_info(int(monitor_id))
            forward_info = self.db.get_channel_info(int(forward_id))

            if not monitor_info or not forward_info:
                await query.message.edit_text(
                    get_text(lang, 'channel_not_found'),
                    reply_markup=InlineKeyboardMarkup([[
                        InlineKeyboardButton(get_text(lang, 'back'), callback_data="filter_rules")
                    ]])
                )
                return

            # 显示过滤类型选择
            keyboard = [
                [
                    InlineKeyboardButton(
                        get_text(lang, 'whitelist'),
                        callback_data=f"filter_type_WHITELIST_{pair_id}"
                    ),
                    InlineKeyboardButton(
                        get_text(lang, 'blacklist'),
                        callback_data=f"filter_type_BLACKLIST_{pair_id}"
                    )
                ],
                [InlineKeyboardButton(get_text(lang, 'back'), callback_data="add_filter_rule")]
            ]

            await query.message.edit_text(
                get_text(lang, 'select_filter_type'),
                reply_markup=InlineKeyboardMarkup(keyboard)
            )

        except Exception as e:
            logging.error(f"Error in handle_filter_pair_selection: {e}")
            await query.message.edit_text(
                get_text(lang, 'error_occurred'),
                reply_markup=InlineKeyboardMarkup([[
                    InlineKeyboardButton(get_text(lang, 'back'), callback_data="filter_rules")
                ]])
            )

    async def handle_filter_type_selection(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """处理过滤类型选择"""
        query = update.callback_query
        await query.answer()

        user_id = update.effective_user.id
        lang = self.db.get_user_language(user_id)

        # 解析数据
        parts = query.data.split('_')
        filter_type = parts[2]
        pair_id = parts[3]

        # 保存到用户数据
        context.user_data['filter_type'] = filter_type
        context.user_data['filter_pair_id'] = pair_id

        # 显示过滤模式选择
        keyboard = [
            [
                InlineKeyboardButton(
                    get_text(lang, 'keyword'),
                    callback_data=f"filter_mode_KEYWORD_{pair_id}"
                ),
                InlineKeyboardButton(
                    get_text(lang, 'regex'),
                    callback_data=f"filter_mode_REGEX_{pair_id}"
                )
            ],
            [InlineKeyboardButton(get_text(lang, 'back'), callback_data=f"filter_pair_{pair_id}")]
        ]

        await query.message.edit_text(
            get_text(lang, 'select_filter_mode'),
            reply_markup=InlineKeyboardMarkup(keyboard)
        )

    async def handle_filter_mode_selection(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """处理过滤模式选择"""
        query = update.callback_query
        await query.answer()

        user_id = update.effective_user.id
        lang = self.db.get_user_language(user_id)

        # 解析数据
        parts = query.data.split('_')
        filter_mode = parts[2]
        pair_id = parts[3]

        # 保存到用户数据
        context.user_data['filter_mode'] = filter_mode

        # 创建一个唯一的模式标识符
        pattern_id = f"{user_id}_{int(datetime.datetime.now().timestamp())}"
        context.user_data['pattern_id'] = pattern_id

        # 显示输入模式的提示
        keyboard = [
            [InlineKeyboardButton(get_text(lang, 'back'), callback_data=f"filter_type_{context.user_data['filter_type']}_{pair_id}")]
        ]

        # 注册一个消息处理器来捕获用户的下一条消息
        # 这里我们使用回调数据来标记模式输入状态
        await query.message.edit_text(
            get_text(lang, 'enter_filter_pattern'),
            reply_markup=InlineKeyboardMarkup(keyboard)
        )

        # 将状态设置为等待模式输入
        # 设置状态标记，表示正在等待过滤规则输入
        context.user_data['waiting_for_filter_pattern'] = True

    async def handle_filter_pattern_input(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """处理过滤模式输入"""
        # 这个函数处理用户发送的文本消息，而不是回调查询
        user_id = update.effective_user.id
        lang = self.db.get_user_language(user_id)

        # 检查是否正在等待过滤规则输入
        if not context.user_data.get('waiting_for_filter_pattern'):
            return

        # 获取用户输入的模式
        pattern = update.message.text.strip()

        # 获取保存的数据
        pair_id = context.user_data.get('filter_pair_id')
        filter_type = context.user_data.get('filter_type')
        filter_mode = context.user_data.get('filter_mode')

        if not pair_id or not filter_type or not filter_mode:
            await update.message.reply_text(
                get_text(lang, 'error_occurred'),
                reply_markup=InlineKeyboardMarkup([[
                    InlineKeyboardButton(get_text(lang, 'back'), callback_data="filter_rules")
                ]])
            )
            return ConversationHandler.END

        try:
            # 解析配对ID
            monitor_id, forward_id = pair_id.split(':')

            # 添加过滤规则
            success = self.db.add_filter_rule(
                monitor_id=int(monitor_id),
                forward_id=int(forward_id),
                rule_type=filter_type,
                filter_mode=filter_mode,
                pattern=pattern
            )

            if success:
                # 清除状态标记
                context.user_data.pop('waiting_for_filter_pattern', None)

                await update.message.reply_text(
                    get_text(lang, 'filter_rule_added'),
                    reply_markup=InlineKeyboardMarkup([[
                        InlineKeyboardButton(get_text(lang, 'back'), callback_data="filter_rules")
                    ]])
                )
                return ConversationHandler.END
            else:
                await update.message.reply_text(
                    get_text(lang, 'error_occurred'),
                    reply_markup=InlineKeyboardMarkup([[
                        InlineKeyboardButton(get_text(lang, 'back'), callback_data="filter_rules")
                    ]])
                )
                return ConversationHandler.END

        except Exception as e:
            logging.error(f"Error in handle_filter_pattern_input: {e}")
            await update.message.reply_text(
                get_text(lang, 'error_occurred'),
                reply_markup=InlineKeyboardMarkup([[
                    InlineKeyboardButton(get_text(lang, 'back'), callback_data="filter_rules")
                ]])
            )
            return ConversationHandler.END

    async def handle_delete_filter_rule(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """处理删除过滤规则"""
        query = update.callback_query
        await query.answer()

        user_id = update.effective_user.id
        lang = self.db.get_user_language(user_id)

        # 获取规则ID
        rule_id = int(query.data.split('_')[-1])

        try:
            # 删除规则
            success = self.db.remove_filter_rule(rule_id)

            if success:
                await query.message.edit_text(
                    get_text(lang, 'filter_rule_deleted'),
                    reply_markup=InlineKeyboardMarkup([[
                        InlineKeyboardButton(get_text(lang, 'back'), callback_data="list_filter_rules")
                    ]])
                )
            else:
                await query.message.edit_text(
                    get_text(lang, 'error_occurred'),
                    reply_markup=InlineKeyboardMarkup([[
                        InlineKeyboardButton(get_text(lang, 'back'), callback_data="list_filter_rules")
                    ]])
                )

        except Exception as e:
            logging.error(f"Error in handle_delete_filter_rule: {e}")
            await query.message.edit_text(
                get_text(lang, 'error_occurred'),
                reply_markup=InlineKeyboardMarkup([[
                    InlineKeyboardButton(get_text(lang, 'back'), callback_data="list_filter_rules")
                ]])
            )

    async def handle_time_pair_selection(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """处理时间过滤的频道配对选择"""
        query = update.callback_query
        await query.answer()

        user_id = update.effective_user.id
        lang = self.db.get_user_language(user_id)

        # 获取配对ID
        pair_id = query.data.split('_')[-1]
        context.user_data['time_pair_id'] = pair_id

        # 解析配对ID获取频道信息
        try:
            monitor_id, forward_id = pair_id.split(':')
            monitor_info = self.db.get_channel_info(int(monitor_id))
            forward_info = self.db.get_channel_info(int(forward_id))

            if not monitor_info or not forward_info:
                await query.message.edit_text(
                    get_text(lang, 'channel_not_found'),
                    reply_markup=InlineKeyboardMarkup([[
                        InlineKeyboardButton(get_text(lang, 'back'), callback_data="time_settings")
                    ]])
                )
                return

            # 显示时间模式选择
            keyboard = [
                [
                    InlineKeyboardButton(
                        get_text(lang, 'allow_mode'),
                        callback_data=f"time_mode_ALLOW_{pair_id}"
                    ),
                    InlineKeyboardButton(
                        get_text(lang, 'block_mode'),
                        callback_data=f"time_mode_BLOCK_{pair_id}"
                    )
                ],
                [InlineKeyboardButton(get_text(lang, 'back'), callback_data="add_time_filter")]
            ]

            await query.message.edit_text(
                get_text(lang, 'select_time_mode'),
                reply_markup=InlineKeyboardMarkup(keyboard)
            )

        except Exception as e:
            logging.error(f"Error in handle_time_pair_selection: {e}")
            await query.message.edit_text(
                get_text(lang, 'error_occurred'),
                reply_markup=InlineKeyboardMarkup([[
                    InlineKeyboardButton(get_text(lang, 'back'), callback_data="time_settings")
                ]])
            )

    async def handle_time_mode_selection(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """处理时间模式选择"""
        query = update.callback_query
        await query.answer()

        user_id = update.effective_user.id
        lang = self.db.get_user_language(user_id)

        # 解析数据
        parts = query.data.split('_')
        time_mode = parts[2]
        pair_id = parts[3]

        # 保存到用户数据
        context.user_data['time_mode'] = time_mode
        context.user_data['time_pair_id'] = pair_id

        # 显示时间范围输入提示
        keyboard = [
            [InlineKeyboardButton(get_text(lang, 'back'), callback_data=f"time_pair_{pair_id}")]
        ]

        await query.message.edit_text(
            get_text(lang, 'enter_time_range'),
            reply_markup=InlineKeyboardMarkup(keyboard)
        )

        # 设置状态标记，表示正在等待时间范围输入
        context.user_data['waiting_for_time_range'] = True

    async def handle_time_range_input(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """处理时间范围输入"""
        # 这个函数处理用户发送的文本消息，而不是回调查询
        user_id = update.effective_user.id
        lang = self.db.get_user_language(user_id)

        # 检查是否正在等待时间范围输入
        if not context.user_data.get('waiting_for_time_range'):
            return

        # 获取用户输入的时间范围
        time_range = update.message.text.strip()

        # 验证时间范围格式
        if not self._validate_time_range(time_range):
            # 清除状态标记
            context.user_data.pop('waiting_for_time_range', None)

            await update.message.reply_text(
                get_text(lang, 'invalid_time_format'),
                reply_markup=InlineKeyboardMarkup([[
                    InlineKeyboardButton(get_text(lang, 'back'), callback_data=f"time_mode_{context.user_data.get('time_mode')}_{context.user_data.get('time_pair_id')}")
                ]])
            )
            return ConversationHandler.END

        # 解析时间范围
        start_time, end_time = time_range.split('-')
        context.user_data['start_time'] = start_time.strip()
        context.user_data['end_time'] = end_time.strip()

        # 提示输入星期
        keyboard = [
            [InlineKeyboardButton(get_text(lang, 'back'), callback_data=f"time_mode_{context.user_data.get('time_mode')}_{context.user_data.get('time_pair_id')}")]
        ]

        await update.message.reply_text(
            get_text(lang, 'enter_days_of_week'),
            reply_markup=InlineKeyboardMarkup(keyboard)
        )

        # 设置状态标记，表示正在等待星期输入
        context.user_data['waiting_for_days'] = True

    async def handle_days_input(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """处理星期输入"""
        # 这个函数处理用户发送的文本消息，而不是回调查询
        user_id = update.effective_user.id
        lang = self.db.get_user_language(user_id)

        # 检查是否正在等待星期输入
        if not context.user_data.get('waiting_for_days'):
            return

        # 获取用户输入的星期
        days = update.message.text.strip()

        # 验证星期格式
        if not self._validate_days(days):
            # 清除状态标记
            context.user_data.pop('waiting_for_days', None)

            await update.message.reply_text(
                get_text(lang, 'invalid_days_format'),
                reply_markup=InlineKeyboardMarkup([[
                    InlineKeyboardButton(get_text(lang, 'back'), callback_data=f"time_range_{context.user_data.get('time_pair_id')}")
                ]])
            )
            return ConversationHandler.END

        # 获取保存的数据
        pair_id = context.user_data.get('time_pair_id')
        time_mode = context.user_data.get('time_mode')
        start_time = context.user_data.get('start_time')
        end_time = context.user_data.get('end_time')

        if not pair_id or not time_mode or not start_time or not end_time:
            await update.message.reply_text(
                get_text(lang, 'error_occurred'),
                reply_markup=InlineKeyboardMarkup([[
                    InlineKeyboardButton(get_text(lang, 'back'), callback_data="time_settings")
                ]])
            )
            return ConversationHandler.END

        try:
            # 解析配对ID
            monitor_id, forward_id = pair_id.split(':')

            # 添加时间过滤器
            success = self.db.add_time_filter(
                monitor_id=int(monitor_id),
                forward_id=int(forward_id),
                mode=time_mode,
                start_time=start_time,
                end_time=end_time,
                days_of_week=days
            )

            if success:
                # 清除状态标记
                context.user_data.pop('waiting_for_days', None)
                context.user_data.pop('waiting_for_time_range', None)

                await update.message.reply_text(
                    get_text(lang, 'time_filter_added'),
                    reply_markup=InlineKeyboardMarkup([[
                        InlineKeyboardButton(get_text(lang, 'back'), callback_data="time_settings")
                    ]])
                )
                return ConversationHandler.END
            else:
                await update.message.reply_text(
                    get_text(lang, 'error_occurred'),
                    reply_markup=InlineKeyboardMarkup([[
                        InlineKeyboardButton(get_text(lang, 'back'), callback_data="time_settings")
                    ]])
                )
                return ConversationHandler.END

        except Exception as e:
            logging.error(f"Error in handle_days_input: {e}")
            await update.message.reply_text(
                get_text(lang, 'error_occurred'),
                reply_markup=InlineKeyboardMarkup([[
                    InlineKeyboardButton(get_text(lang, 'back'), callback_data="time_settings")
                ]])
            )
            return ConversationHandler.END

    async def handle_delete_time_filter(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """处理删除时间过滤器"""
        query = update.callback_query
        await query.answer()

        user_id = update.effective_user.id
        lang = self.db.get_user_language(user_id)

        # 获取过滤器ID
        filter_id = int(query.data.split('_')[-1])

        try:
            # 删除过滤器
            success = self.db.remove_time_filter(filter_id)

            if success:
                await query.message.edit_text(
                    get_text(lang, 'time_filter_deleted'),
                    reply_markup=InlineKeyboardMarkup([[
                        InlineKeyboardButton(get_text(lang, 'back'), callback_data="list_time_filters")
                    ]])
                )
            else:
                await query.message.edit_text(
                    get_text(lang, 'error_occurred'),
                    reply_markup=InlineKeyboardMarkup([[
                        InlineKeyboardButton(get_text(lang, 'back'), callback_data="list_time_filters")
                    ]])
                )

        except Exception as e:
            logging.error(f"Error in handle_delete_time_filter: {e}")
            await query.message.edit_text(
                get_text(lang, 'error_occurred'),
                reply_markup=InlineKeyboardMarkup([[
                    InlineKeyboardButton(get_text(lang, 'back'), callback_data="list_time_filters")
                ]])
            )

    def _validate_time_range(self, time_range):
        """验证时间范围格式"""
        try:
            if '-' not in time_range:
                return False

            start_time, end_time = time_range.split('-')
            start_time = start_time.strip()
            end_time = end_time.strip()

            # 验证时间格式
            datetime.datetime.strptime(start_time, '%H:%M')
            datetime.datetime.strptime(end_time, '%H:%M')

            return True
        except Exception:
            return False

    def _validate_days(self, days):
        """验证星期格式"""
        valid_days = ['1', '2', '3', '4', '5', '6', '7']

        # 允许的格式：1,2,3,4,5,6,7 或 1-5 或 1,3-5,7
        try:
            # 先按逗号分割
            parts = days.split(',')

            for part in parts:
                part = part.strip()

                if '-' in part:
                    # 如果是范围，如 1-5
                    start, end = part.split('-')
                    start = start.strip()
                    end = end.strip()

                    if start not in valid_days or end not in valid_days:
                        return False

                    if int(start) > int(end):
                        return False
                else:
                    # 如果是单个数字，如 1
                    if part not in valid_days:
                        return False

            return True
        except Exception:
            return False

    # 媒体过滤器相关方法
    async def show_media_filter_menu(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """显示媒体过滤器菜单"""
        query = update.callback_query
        await query.answer()

        user_id = update.effective_user.id
        lang = self.db.get_user_language(user_id)

        keyboard = [
            [InlineKeyboardButton(get_text(lang, 'add_media_filter'), callback_data="add_media_filter")],
            [InlineKeyboardButton(get_text(lang, 'back'), callback_data="filter_rules")]
        ]

        await query.message.edit_text(
            get_text(lang, 'media_filter_menu'),
            reply_markup=InlineKeyboardMarkup(keyboard)
        )

    async def show_pair_selection_for_media(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """显示频道配对选择界面，用于媒体过滤器"""
        query = update.callback_query
        await query.answer()

        user_id = update.effective_user.id
        lang = self.db.get_user_language(user_id)

        # 获取页码
        page = 1
        if query.data and '_' in query.data:
            try:
                parts = query.data.split('_')
                if len(parts) > 1 and parts[-1].isdigit():
                    page = int(parts[-1])
            except ValueError:
                page = 1

        # 获取所有频道配对
        pairs = self.db.get_all_channel_pairs()

        if not pairs:
            await query.message.edit_text(
                get_text(lang, 'no_pairs'),
                reply_markup=InlineKeyboardMarkup([[
                    InlineKeyboardButton(get_text(lang, 'back'), callback_data="media_filter")
                ]])
            )
            return

        # 每页显示的配对数
        per_page = 5
        total_pages = (len(pairs) + per_page - 1) // per_page
        page = max(1, min(page, total_pages))

        # 获取当前页的配对
        start_idx = (page - 1) * per_page
        end_idx = min(start_idx + per_page, len(pairs))
        current_pairs = pairs[start_idx:end_idx]

        keyboard = []
        for pair in current_pairs:
            keyboard.append([InlineKeyboardButton(
                f"{pair['monitor_name']} → {pair['forward_name']}",
                callback_data=f"media_filter_pair_{pair['pair_id']}"
            )])

        # 构建分页按钮
        navigation = []
        if page > 1:
            navigation.append(InlineKeyboardButton(
                get_text(lang, 'previous_page'),
                callback_data=f"add_media_filter_{page-1}"
            ))
        if page < total_pages:
            navigation.append(InlineKeyboardButton(
                get_text(lang, 'next_page'),
                callback_data=f"add_media_filter_{page+1}"
            ))

        if navigation:
            keyboard.append(navigation)

        keyboard.append([InlineKeyboardButton(get_text(lang, 'back'), callback_data="media_filter")])

        # 添加当前页码信息
        page_info = f"\n{get_text(lang, 'page_info').format(current=page, total=total_pages)}"

        await query.message.edit_text(
            get_text(lang, 'select_pair_for_media') + page_info,
            reply_markup=InlineKeyboardMarkup(keyboard)
        )

    async def show_media_filter_settings(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """显示媒体过滤器设置界面"""
        query = update.callback_query
        await query.answer()

        user_id = update.effective_user.id
        lang = self.db.get_user_language(user_id)

        # 获取配对ID
        pair_id = query.data.split('_')[-1]
        monitor_id, forward_id = map(int, pair_id.split(':'))

        # 获取频道信息
        monitor_info = self.db.get_channel_info(monitor_id)
        forward_info = self.db.get_channel_info(forward_id)

        if not monitor_info or not forward_info:
            await query.message.edit_text(
                get_text(lang, 'pair_not_found'),
                reply_markup=InlineKeyboardMarkup([[
                    InlineKeyboardButton(get_text(lang, 'back'), callback_data="add_media_filter")
                ]])
            )
            return

        # 获取当前媒体过滤器设置
        media_filters = self.db.get_media_filters(pair_id)

        # 将过滤器转换为字典，便于查找
        filter_dict = {}
        for filter_rule in media_filters:
            filter_dict[filter_rule['media_type']] = filter_rule['action']

        # 定义所有支持的媒体类型
        media_types = [
            {'id': 'photo', 'name': get_text(lang, 'media_photo')},
            {'id': 'video', 'name': get_text(lang, 'media_video')},
            {'id': 'audio', 'name': get_text(lang, 'media_audio')},
            {'id': 'document', 'name': get_text(lang, 'media_document')},
            {'id': 'animation', 'name': get_text(lang, 'media_animation')},
            {'id': 'sticker', 'name': get_text(lang, 'media_sticker')},
            {'id': 'text', 'name': get_text(lang, 'media_text')}
        ]

        # 构建开关按钮
        keyboard = []
        for media_type in media_types:
            type_id = media_type['id']
            type_name = media_type['name']

            # 获取当前状态
            current_action = filter_dict.get(type_id, 'ALLOW')

            # 根据当前状态设置按钮文本和图标
            if current_action == 'ALLOW':
                status_text = f"✅ {type_name}"
                toggle_action = 'BLOCK'
            else:  # BLOCK
                status_text = f"❌ {type_name}"
                toggle_action = 'ALLOW'

            keyboard.append([InlineKeyboardButton(
                status_text,
                callback_data=f"toggle_media_{type_id}_{pair_id}_{toggle_action}"
            )])

        keyboard.append([InlineKeyboardButton(get_text(lang, 'back'), callback_data="add_media_filter")])

        # 显示配对信息和当前设置
        await query.message.edit_text(
            get_text(lang, 'media_filter_settings',
                    monitor_name=monitor_info['channel_name'],
                    forward_name=forward_info['channel_name']),
            reply_markup=InlineKeyboardMarkup(keyboard)
        )

    async def toggle_media_filter(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """切换媒体过滤器状态"""
        query = update.callback_query
        await query.answer()

        user_id = update.effective_user.id
        lang = self.db.get_user_language(user_id)

        try:
            # 解析回调数据
            parts = query.data.split('_')
            media_type = parts[2]
            pair_id = parts[3]
            action = parts[4]  # ALLOW 或 BLOCK

            # 更新数据库
            success = self.db.add_media_filter(pair_id, media_type, action)

            if success:
                # 重新显示设置页面
                await self.show_media_filter_settings(update, context)
            else:
                await query.message.edit_text(
                    get_text(lang, 'media_filter_update_failed'),
                    reply_markup=InlineKeyboardMarkup([[
                        InlineKeyboardButton(get_text(lang, 'back'), callback_data=f"media_filter_pair_{pair_id}")
                    ]])
                )

        except Exception as e:
            logging.error(f"Error in toggle_media_filter: {e}")
            await query.message.edit_text(
                get_text(lang, 'error_occurred'),
                reply_markup=InlineKeyboardMarkup([[
                    InlineKeyboardButton(get_text(lang, 'back'), callback_data="media_filter")
                ]])
            )