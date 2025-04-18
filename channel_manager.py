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
                            filters.ALL & ~filters.COMMAND,  # 捕获所有非命令消息
                            self.handle_forwarded_message
                        ),
                        MessageHandler(filters.Regex('^(cancel|Cancel|取消)$'), self.cancel_add_channel),
                    ],
                    WAITING_FOR_MANUAL_INPUT: [
                        MessageHandler(
                            filters.TEXT & ~filters.COMMAND,
                            self.handle_manual_input
                        ),
                        MessageHandler(filters.Regex('^(cancel|Cancel|取消)$'), self.cancel_add_channel),
                    ]

                },
                fallbacks=[
                    CommandHandler('cancel', self.cancel_add_channel),
                    CallbackQueryHandler(self.cancel_add_channel, pattern='^cancel$')
                ],
                name="add_channel",
                persistent=False
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
            CallbackQueryHandler(self.show_filter_rules_list, pattern='^list_filter_rules$'),
            CallbackQueryHandler(self.show_time_filters_list, pattern='^list_time_filters$'),

            # 返回处理
            CallbackQueryHandler(self.handle_back, pattern='^back_to_'),

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

            if message.text and message.text.lower() in ['cancel', '取消']:
                await message.reply_text(
                    get_text(lang, 'operation_cancelled'),
                    reply_markup=ReplyKeyboardRemove()
                )
                context.user_data.clear()
                return ConversationHandler.END

            await message.reply_text(
                get_text(lang, 'processing'),
                reply_markup=ReplyKeyboardRemove()
            )

            chat_id = None
            chat_title = None
            chat_username = None

            # 处理用户分享
            if message.users_shared:
                users = message.users_shared.users
                if users:
                    user = users[0]
                    chat_id = user.id
                    chat_title = user.first_name or "Unknown User"
                    chat_username = user.username

            # 处理聊天分享
            elif message.chat_shared:
                raw_chat_id = message.chat_shared.chat_id
                # 将ID统一格式化
                chat_id = self.normalize_channel_id(raw_chat_id)
                try:
                    entity = await self.client.get_entity(int(f"-100{chat_id}"))
                    chat_title = getattr(entity, 'title', None) or getattr(entity, 'first_name', 'Unknown')
                    chat_username = getattr(entity, 'username', None)
                except Exception as e:
                    logging.error(f"Error getting entity info: {e}")
                    raise

            # 处理转发的频道/群组消息
            elif message.forward_from_chat:
                chat = message.forward_from_chat
                chat_id = self.normalize_channel_id(chat.id)
                chat_title = chat.title
                chat_username = chat.username

            # 处理转发的用户消息
            elif message.forward_from:
                user = message.forward_from
                chat_id = user.id
                chat_title = user.first_name or "Unknown User"
                chat_username = user.username

            if not chat_id:
                await message.reply_text(
                    get_text(lang, 'invalid_forward'),
                    reply_markup=ReplyKeyboardRemove()
                )
                return WAITING_FOR_FORWARD

            # 添加到数据库
            channel_type = context.user_data.get('channel_type', 'MONITOR')
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
            else:
                await message.reply_text(
                    get_text(lang, 'channel_add_failed'),
                    reply_markup=ReplyKeyboardRemove()
                )

            context.user_data.clear()
            return ConversationHandler.END

        except Exception as e:
            logging.error(f"Error in handle_forwarded_message: {e}")
            await message.reply_text(
                get_text(lang, 'process_error'),
                reply_markup=ReplyKeyboardRemove()
            )
            return ConversationHandler.END

    async def handle_manual_input(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """处理手动输入的频道ID"""
        try:
            message = update.message
            input_text = message.text.strip()
            user_id = update.effective_user.id
            lang = self.db.get_user_language(user_id)

            try:
                # 统一处理ID格式
                channel_id = self.normalize_channel_id(input_text)

                # 使用标准格式获取频道信息
                full_id = int(f"-100{channel_id}")
                chat = await self.client.get_entity(full_id)

                channel_type = context.user_data.get('channel_type')
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
                                type=channel_type_display)
                    )
                else:
                    await message.reply_text(get_text(lang, 'channel_add_failed'))

                context.user_data.clear()
                return ConversationHandler.END

            except ValueError:
                await message.reply_text(get_text(lang, 'invalid_id_format'))
                return WAITING_FOR_MANUAL_INPUT

            except Exception as e:
                logging.error(f"Error getting channel info: {e}")
                await message.reply_text(get_text(lang, 'channel_info_error'))
                return WAITING_FOR_MANUAL_INPUT

        except Exception as e:
            logging.error(f"Error in handle_manual_input: {e}")
            await message.reply_text(get_text(lang, 'process_error'))
            return WAITING_FOR_MANUAL_INPUT

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

        # 清理状态
        context.user_data.clear()
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

        keyboard = []
        for pair in pairs:
            keyboard.append([InlineKeyboardButton(
                f"{pair['monitor_name']} → {pair['forward_name']}",
                callback_data=f"filter_pair_{pair['pair_id']}"
            )])

        keyboard.append([InlineKeyboardButton(get_text(lang, 'back'), callback_data="filter_rules")])

        await query.message.edit_text(
            get_text(lang, 'select_pair_for_filter'),
            reply_markup=InlineKeyboardMarkup(keyboard)
        )

    async def show_pair_selection_for_time(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """显示频道配对选择界面，用于时间设置"""
        query = update.callback_query
        await query.answer()

        user_id = update.effective_user.id
        lang = self.db.get_user_language(user_id)

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

        keyboard = []
        for pair in pairs:
            keyboard.append([InlineKeyboardButton(
                f"{pair['monitor_name']} → {pair['forward_name']}",
                callback_data=f"time_pair_{pair['pair_id']}"
            )])

        keyboard.append([InlineKeyboardButton(get_text(lang, 'back'), callback_data="time_settings")])

        await query.message.edit_text(
            get_text(lang, 'select_pair_for_time'),
            reply_markup=InlineKeyboardMarkup(keyboard)
        )

    async def show_filter_rules_list(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """显示过滤规则列表"""
        query = update.callback_query
        await query.answer()

        user_id = update.effective_user.id
        lang = self.db.get_user_language(user_id)

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

        text = get_text(lang, 'filter_rules_menu') + "\n\n"

        # 获取每个配对的过滤规则
        for pair in pairs:
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

        keyboard = [[InlineKeyboardButton(get_text(lang, 'back'), callback_data="filter_rules")]]

        await query.message.edit_text(
            text,
            reply_markup=InlineKeyboardMarkup(keyboard),
            parse_mode='Markdown'
        )

    async def show_time_filters_list(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """显示时间过滤器列表"""
        query = update.callback_query
        await query.answer()

        user_id = update.effective_user.id
        lang = self.db.get_user_language(user_id)

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

        text = get_text(lang, 'time_settings_menu') + "\n\n"

        # 获取每个配对的时间过滤器
        for pair in pairs:
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

        keyboard = [[InlineKeyboardButton(get_text(lang, 'back'), callback_data="time_settings")]]

        await query.message.edit_text(
            text,
            reply_markup=InlineKeyboardMarkup(keyboard),
            parse_mode='Markdown'
        )