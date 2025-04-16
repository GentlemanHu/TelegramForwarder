# message_handler.py
from telethon import TelegramClient, events
import os
import re
import logging
import traceback
from typing import Optional, BinaryIO, Dict, List, Any, Tuple
from tempfile import NamedTemporaryFile
import asyncio
from datetime import datetime, timedelta, time
from locales import get_text

class MyMessageHandler:
    def __init__(self, db, client: TelegramClient, bot):
        self.db = db
        self.client = client
        self.bot = bot
        # 用于跟踪临时文件
        self.temp_files = {}
        # 启动清理任务
        self.cleanup_task = None

    async def start_cleanup_task(self):
        """启动定期清理任务"""
        if self.cleanup_task is None:
            self.cleanup_task = asyncio.create_task(self.cleanup_old_files())

    async def cleanup_old_files(self):
        """定期清理过期的临时文件"""
        while True:
            try:
                current_time = datetime.now()
                files_to_remove = []

                # 检查所有临时文件
                for file_path, timestamp in list(self.temp_files.items()):
                    if current_time - timestamp > timedelta(hours=1):  # 1小时后清理
                        if os.path.exists(file_path):
                            try:
                                os.remove(file_path)
                                logging.info(get_text('en', 'file_cleanup_success', file_path=file_path))
                            except Exception as e:
                                logging.error(get_text('en', 'file_cleanup_error', file_path=file_path, error=str(e)))
                        files_to_remove.append(file_path)

                # 从跟踪列表中移除已清理的文件
                for file_path in files_to_remove:
                    self.temp_files.pop(file_path, None)

            except Exception as e:
                logging.error(get_text('en', 'cleanup_task_error', error=str(e)))

            # 每小时运行一次
            await asyncio.sleep(3600)

    async def handle_channel_message(self, event):
        """处理频道消息"""
        try:
            message = event.message
            if not message:
                return

            chat = await event.get_chat()
            channel_info = self.db.get_channel_info(chat.id)

            if not channel_info or not channel_info.get('is_active'):
                return

            # 获取所有转发频道
            forward_channels = self.db.get_all_forward_channels(chat.id)
            if not forward_channels:
                return

            # 获取消息内容用于过滤
            content = ""
            if getattr(message, 'text', None):
                content = message.text
            elif getattr(message, 'caption', None):
                content = message.caption

            # 获取当前时间
            current_time = datetime.now()
            current_time_str = current_time.strftime('%H:%M')
            current_weekday = current_time.weekday() + 1  # 周一为1，周日为7

            for channel in forward_channels:
                try:
                    monitor_id = chat.id
                    forward_id = channel.get('channel_id')

                    # 检查时间段过滤
                    if not self.check_time_filter(monitor_id, forward_id, current_time_str, current_weekday):
                        logging.info(f"消息被时间段过滤器拦截: 监控频道={monitor_id}, 转发频道={forward_id}")
                        continue

                    # 检查内容过滤
                    if content and not self.check_content_filter(monitor_id, forward_id, content):
                        logging.info(f"消息被内容过滤器拦截: 监控频道={monitor_id}, 转发频道={forward_id}")
                        continue

                    # 通过所有过滤器，转发消息
                    await self.handle_forward_message(message, chat, channel)
                except Exception as e:
                    logging.error(get_text('en', 'forward_channel_error',
                                         channel_id=channel.get('channel_id'),
                                         error=str(e)))
                    continue
        except Exception as e:
            logging.error(get_text('en', 'message_handler_error', error=str(e)))
            logging.error(get_text('en', 'error_details', details=traceback.format_exc()))

    def check_time_filter(self, monitor_id: int, forward_id: int, current_time: str, current_weekday: int) -> bool:
        """检查时间段过滤器"""
        try:
            # 获取时间段过滤器
            time_filters = self.db.get_time_filters(monitor_id, forward_id)

            # 如果没有过滤器，允许所有时间
            if not time_filters:
                return True

            # 检查每个时间段过滤器
            for filter_rule in time_filters:
                # 检查当前星期是否在过滤器的星期范围内
                days_of_week = filter_rule.get('days_of_week', '').split(',')
                if days_of_week and str(current_weekday) not in days_of_week:
                    continue

                # 检查当前时间是否在过滤器的时间范围内
                start_time = filter_rule.get('start_time')
                end_time = filter_rule.get('end_time')

                if start_time and end_time:
                    # 如果当前时间在范围内
                    in_time_range = start_time <= current_time <= end_time

                    # 根据模式决定是否允许
                    mode = filter_rule.get('mode', 'ALLOW')
                    if mode == 'ALLOW' and in_time_range:
                        return True
                    elif mode == 'BLOCK' and in_time_range:
                        return False

            # 如果没有匹配的规则，默认允许
            return True

        except Exception as e:
            logging.error(f"检查时间段过滤器时出错: {e}")
            # 出错时默认允许
            return True

    def check_content_filter(self, monitor_id: int, forward_id: int, content: str) -> bool:
        """检查内容过滤器"""
        try:
            # 获取过滤规则
            filter_rules = self.db.get_filter_rules(monitor_id, forward_id)

            # 如果没有规则，允许所有内容
            if not filter_rules:
                return True

            # 分类规则
            whitelist_rules = []
            blacklist_rules = []

            for rule in filter_rules:
                if rule.get('rule_type') == 'WHITELIST':
                    whitelist_rules.append(rule)
                elif rule.get('rule_type') == 'BLACKLIST':
                    blacklist_rules.append(rule)

            # 如果有白名单规则，必须匹配至少一条才允许
            if whitelist_rules:
                whitelist_match = False
                for rule in whitelist_rules:
                    if self.match_rule(rule, content):
                        whitelist_match = True
                        break

                if not whitelist_match:
                    return False

            # 如果有黑名单规则，匹配任一条则拒绝
            for rule in blacklist_rules:
                if self.match_rule(rule, content):
                    return False

            # 通过所有过滤
            return True

        except Exception as e:
            logging.error(f"检查内容过滤器时出错: {e}")
            # 出错时默认允许
            return True

    def match_rule(self, rule: dict, content: str) -> bool:
        """检查内容是否匹配规则"""
        try:
            pattern = rule.get('pattern', '')
            if not pattern:
                return False

            filter_mode = rule.get('filter_mode', 'KEYWORD')

            if filter_mode == 'KEYWORD':
                # 关键词模式，简单字符串包含
                return pattern.lower() in content.lower()
            elif filter_mode == 'REGEX':
                # 正则表达式模式
                return bool(re.search(pattern, content, re.IGNORECASE))

            return False

        except Exception as e:
            logging.error(f"匹配规则时出错: {e}")
            return False

    async def handle_media_send(self, message, channel_id, from_chat, media_type: str, reply_to_message_id: int = None):
        """处理媒体发送并确保清理"""
        tmp = None
        file_path = None
        chunk_size = 20 * 1024 * 1024  # 20MB 分块

        try:
            # 获取文件大小
            file_size = getattr(message.media, 'file_size', 0) or getattr(message.media, 'size', 0)
            logging.info(f"开始处理文件，大小: {file_size / (1024*1024):.2f}MB")

            # 创建临时文件
            tmp = NamedTemporaryFile(delete=False, prefix='tg_', suffix=f'.{media_type}')
            file_path = tmp.name

            # 使用分块下载
            downloaded_size = 0
            async for chunk in self.client.iter_download(message.media, chunk_size=chunk_size):
                if chunk:
                    tmp.write(chunk)
                    downloaded_size += len(chunk)
                    if downloaded_size % (50 * 1024 * 1024) == 0:
                        progress = (downloaded_size / file_size) * 100 if file_size else 0
                        logging.info(f"下载进度: {progress:.1f}% ({downloaded_size/(1024*1024):.1f}MB/{file_size/(1024*1024):.1f}MB)")

                    if downloaded_size % (100 * 1024 * 1024) == 0:
                        tmp.flush()
                        os.fsync(tmp.fileno())

            tmp.close()
            logging.info("文件下载完成，准备发送")

            if not os.path.exists(file_path):
                raise Exception(get_text('en', 'downloaded_file_not_found', file_path=file_path))

            # 记录临时文件
            self.temp_files[file_path] = datetime.now()

            # 只有在没有回复消息时才添加说明文字
            caption = None
            if not reply_to_message_id:
                # 构建用户名部分
                username = f"(@{from_chat.username})" if getattr(from_chat, 'username', None) else ""

                # 使用简化的模板作为媒体文件的标题
                caption = f"📨 转发自 {getattr(from_chat, 'title', 'Unknown Channel')} {username}"

            # 发送文件
            with open(file_path, 'rb') as media_file:
                try:
                    file_data = media_file.read()
                    send_kwargs = {
                        'chat_id': channel_id,
                        'caption': caption,
                        'read_timeout': 1800,
                        'write_timeout': 1800
                    }

                    if reply_to_message_id:
                        send_kwargs['reply_to_message_id'] = reply_to_message_id

                    if media_type == 'photo':
                        send_kwargs['photo'] = file_data
                        await self.bot.send_photo(**send_kwargs)
                    elif media_type == 'video':
                        # 获取原始视频的参数
                        video = message.media.video
                        send_kwargs.update({
                            'video': file_data,
                            'supports_streaming': True
                        })

                        # 安全地获取视频参数
                        if hasattr(video, 'width') and video.width:
                            send_kwargs['width'] = video.width
                        if hasattr(video, 'height') and video.height:
                            send_kwargs['height'] = video.height
                        if hasattr(video, 'duration') and video.duration:
                            send_kwargs['duration'] = video.duration

                        # 如果有缩略图
                        if hasattr(video, 'thumb') and video.thumb:
                            try:
                                send_kwargs['thumb'] = await self.client.download_media(video.thumb)
                            except Exception as e:
                                logging.warning(f"无法下载视频缩略图: {str(e)}")

                        await self.bot.send_video(**send_kwargs)
                    elif media_type == 'document':
                        # 获取文件名
                        if hasattr(message.media.document, 'attributes'):
                            for attr in message.media.document.attributes:
                                if hasattr(attr, 'file_name'):
                                    send_kwargs['filename'] = attr.file_name
                                    break
                        send_kwargs['document'] = file_data
                        await self.bot.send_document(**send_kwargs)

                    logging.info(f"文件发送成功: {media_type}" +
                           (f" (回复到消息: {reply_to_message_id})" if reply_to_message_id else ""))
                finally:
                    del file_data  # 释放内存
                    # 清理缩略图
                    if 'thumb' in send_kwargs and os.path.exists(send_kwargs['thumb']):
                        os.remove(send_kwargs['thumb'])

            # 发送成功后立即删除文件
            await self.cleanup_file(file_path)

        except Exception as e:
            logging.error(f"处理媒体文件时出错: {str(e)}")
            if file_path:
                await self.cleanup_file(file_path)
            raise
        finally:
            # 确保临时文件被关闭和删除
            if tmp and not tmp.closed:
                tmp.close()
            if file_path and os.path.exists(file_path):
                try:
                    os.remove(file_path)
                except Exception as e:
                    logging.error(f"删除临时文件失败: {str(e)}")

    async def handle_forward_message(self, message, from_chat, to_channel):
        """处理消息转发"""
        if not message or not from_chat or not to_channel:
            logging.error(get_text('en', 'missing_parameters'))
            return

        try:
            channel_id = to_channel.get('channel_id')
            channel_id = int("-100"+str(channel_id))
            if not channel_id:
                logging.error(get_text('en', 'invalid_channel_id'))
                return

            forwarded_msg = None

            # 尝试直接转发
            try:
                forwarded_msg = await self.bot.forward_message(
                    chat_id=channel_id,
                    from_chat_id=from_chat.id,
                    message_id=message.id
                )
                logging.info(get_text('en', 'forward_success', channel_id=channel_id))
                return
            except Exception as e:
                logging.warning(get_text('en', 'direct_forward_failed', error=str(e)))

            # 如果直接转发失败，处理文本消息
            if getattr(message, 'text', None) or getattr(message, 'caption', None):
                content = message.text or message.caption
                # 获取频道类型
                chat_type_key = 'chat_type_channel'  # 默认类型
                if hasattr(from_chat, 'type'):
                    if from_chat.type == 'channel':
                        if getattr(from_chat, 'username', None):
                            chat_type_key = 'chat_type_public_channel'
                        else:
                            chat_type_key = 'chat_type_private_channel'
                    elif from_chat.type == 'group':
                        chat_type_key = 'chat_type_group'
                    elif from_chat.type == 'supergroup':
                        chat_type_key = 'chat_type_supergroup'
                    elif from_chat.type == 'gigagroup':
                        chat_type_key = 'chat_type_gigagroup'

                # 获取用户语言
                lang = self.db.get_user_language(to_channel.get('channel_id', 0)) or 'en'

                # 获取频道类型显示文本
                chat_type = get_text(lang, chat_type_key)

                # 获取当前时间
                current_time = datetime.now().strftime('%Y-%m-%d %H:%M:%S')

                # 构建用户名部分
                username = f"(@{from_chat.username})" if getattr(from_chat, 'username', None) else ""

                # 检查是否是回复消息
                reply_text = ""
                if hasattr(message, 'reply_to_msg_id') and message.reply_to_msg_id:
                    try:
                        # 尝试获取原始回复消息
                        reply_msg = await self.client.get_messages(from_chat.id, ids=message.reply_to_msg_id)
                        if reply_msg and (reply_msg.text or reply_msg.caption):
                            reply_content = reply_msg.text or reply_msg.caption
                            # 截取回复消息的前50个字符
                            short_reply = reply_content[:50] + "..." if len(reply_content) > 50 else reply_content
                            reply_text = get_text(lang, 'reply_to_message', text=short_reply) + "\n"
                    except Exception as e:
                        logging.warning(f"获取回复消息失败: {e}")

                # 使用新的消息模板
                forwarded_text = get_text(lang, 'forwarded_message_template',
                                         title=getattr(from_chat, 'title', 'Unknown Channel'),
                                         username=username,
                                         chat_type=chat_type,
                                         time=current_time,
                                         content=reply_text + content)

                # 检查是否有自定义表情
                has_custom_emoji = await self.handle_custom_emoji(message, channel_id)

                # 发送文本消息，支持Markdown格式
                try:
                    forwarded_msg = await self.bot.send_message(
                        chat_id=channel_id,
                        text=forwarded_text,
                        parse_mode='Markdown',
                        disable_web_page_preview=True
                    )
                except Exception as e:
                    # 如果Markdown解析失败，尝试使用纯文本
                    logging.warning(f"使用Markdown发送消息失败: {e}")
                    forwarded_msg = await self.bot.send_message(
                        chat_id=channel_id,
                        text=forwarded_text,
                        parse_mode=None,
                        disable_web_page_preview=True
                    )
                logging.info(get_text('en', 'text_send_success', channel_id=channel_id))

            # 处理媒体消息
            if getattr(message, 'media', None) and forwarded_msg:
                # 在消息中添加“正在加载媒体”的提示
                loading_text = forwarded_text + "\n\n⚙️ *正在加载媒体文件...*"
                try:
                    # 更新消息以显示加载状态
                    await self.bot.edit_message_text(
                        chat_id=channel_id,
                        message_id=forwarded_msg.message_id,
                        text=loading_text,
                        parse_mode='Markdown',
                        disable_web_page_preview=True
                    )
                except Exception as e:
                    logging.warning(f"更新消息状态失败: {e}")

                # 确定媒体类型
                media_types = []
                is_sticker = False

                # 检查是否是贴图
                if hasattr(message.media, 'document') and hasattr(message.media.document, 'attributes'):
                    for attr in message.media.document.attributes:
                        if hasattr(attr, 'CONSTRUCTOR_ID') and attr.CONSTRUCTOR_ID == 0x6319d612:  # DocumentAttributeSticker
                            is_sticker = True
                            break
                        # 检查属性名称
                        elif hasattr(attr, '__class__') and 'DocumentAttributeSticker' in str(attr.__class__):
                            is_sticker = True
                            break

                if is_sticker:
                    media_types.append('sticker')
                elif hasattr(message.media, 'photo'):
                    media_types.append('photo')
                elif hasattr(message.media, 'video'):
                    media_types.append('video')
                elif hasattr(message.media, 'document'):
                    media_types.append('document')

                # 如果有媒体，尝试下载并编辑原消息
                if media_types:
                    try:
                        # 下载媒体文件
                        if media_types[0] == 'sticker':
                            # 对于贴图，使用特殊处理
                            await self.handle_sticker_send(
                                message=message,
                                channel_id=channel_id,
                                from_chat=from_chat,
                                reply_to_message_id=forwarded_msg.message_id if forwarded_msg else None
                            )
                            # 删除原消息，因为贴图已经发送
                            try:
                                await self.bot.delete_message(
                                    chat_id=channel_id,
                                    message_id=forwarded_msg.message_id
                                )
                            except Exception as e:
                                logging.warning(f"删除原消息失败: {e}")
                            # 跳过后续处理
                            return
                        else:
                            media_info = await self.download_media_file(message, media_types[0])

                        if media_info and media_info.get('file_path'):
                            # 尝试编辑原消息以包含媒体
                            await self.edit_message_with_media(
                                channel_id=channel_id,
                                message_id=forwarded_msg.message_id,
                                text=forwarded_text,
                                media_path=media_info.get('file_path'),
                                media_type=media_types[0],
                                media_info=media_info
                            )
                        else:
                            # 如果媒体下载失败，恢复原消息
                            await self.bot.edit_message_text(
                                chat_id=channel_id,
                                message_id=forwarded_msg.message_id,
                                text=forwarded_text + "\n\n⚠️ *媒体文件加载失败*",
                                parse_mode='Markdown',
                                disable_web_page_preview=True
                            )
                    except Exception as e:
                        logging.error(f"处理媒体文件时出错: {str(e)}")
                        # 如果编辑失败，尝试发送单独的媒体消息
                        try:
                            for media_type in media_types:
                                await self.handle_media_send(
                                    message=message,
                                    channel_id=channel_id,
                                    from_chat=from_chat,
                                    media_type=media_type,
                                    reply_to_message_id=forwarded_msg.message_id
                                )
                        except Exception as e2:
                            logging.error(f"备用方法发送媒体失败: {str(e2)}")

        except Exception as e:
            logging.error(get_text('en', 'forward_message_error', error=str(e)))
            logging.error(get_text('en', 'error_details', details=traceback.format_exc()))
            raise

    async def cleanup_file(self, file_path: str):
        """清理单个文件"""
        try:
            if file_path and os.path.exists(file_path):
                os.remove(file_path)
                self.temp_files.pop(file_path, None)
                logging.info(get_text('en', 'file_cleanup_success', file_path=file_path))
        except Exception as e:
            logging.error(get_text('en', 'file_cleanup_error',
                                 file_path=file_path,
                                 error=str(e)))

    async def download_progress_callback(self, current, total):
        """下载进度回调"""
        if total:
            percentage = current * 100 / total
            if percentage % 20 == 0:  # 每20%记录一次
                logging.info(get_text('en', 'download_progress', percentage=percentage))

    async def handle_edited_message(self, event):
        """处理消息编辑事件"""
        try:
            # 获取编辑后的消息
            message = event.message
            if not message:
                return

            # 获取频道信息
            chat = await event.get_chat()
            channel_info = self.db.get_channel_info(chat.id)

            if not channel_info or not channel_info.get('is_active'):
                return

            # 获取所有转发频道
            forward_channels = self.db.get_all_forward_channels(chat.id)
            if not forward_channels:
                return

            # 获取消息内容
            content = message.text or message.caption or ""
            if not content:
                return

            # 获取用户语言
            lang = self.db.get_user_language(chat.id) or 'en'

            # 构建编辑通知消息
            edit_notice = get_text(lang, 'edited_message')
            edit_text = f"{edit_notice}\n\n{content}"

            # 向所有转发频道发送编辑通知
            for channel in forward_channels:
                try:
                    channel_id = int("-100" + str(channel.get('channel_id')))

                    # 以回复形式发送编辑通知
                    # 注意：这里我们不尝试编辑原消息，而是发送新消息作为通知
                    await self.bot.send_message(
                        chat_id=channel_id,
                        text=edit_text,
                        parse_mode='Markdown',
                        disable_web_page_preview=True
                    )

                except Exception as e:
                    logging.error(f"发送编辑通知到频道 {channel.get('channel_id')} 失败: {str(e)}")
                    continue

        except Exception as e:
            logging.error(f"处理消息编辑事件时出错: {str(e)}")
            logging.error(f"错误详情: {traceback.format_exc()}")

    async def handle_deleted_message(self, event):
        """处理消息删除事件"""
        try:
            # 注意：删除的消息事件只包含消息ID，不包含内容
            # 我们需要从事件中获取频道ID和消息ID

            # 获取频道ID
            chat_id = event.chat_id
            if not chat_id:
                return

            # 获取频道信息
            channel_info = self.db.get_channel_info(chat_id)
            if not channel_info or not channel_info.get('is_active'):
                return

            # 获取所有转发频道
            forward_channels = self.db.get_all_forward_channels(chat_id)
            if not forward_channels:
                return

            # 获取用户语言
            lang = self.db.get_user_language(chat_id) or 'en'

            # 构建删除通知消息
            delete_notice = get_text(lang, 'deleted_message')

            # 向所有转发频道发送删除通知
            for channel in forward_channels:
                try:
                    channel_id = int("-100" + str(channel.get('channel_id')))

                    # 发送删除通知
                    await self.bot.send_message(
                        chat_id=channel_id,
                        text=delete_notice,
                        parse_mode='Markdown'
                    )

                except Exception as e:
                    logging.error(f"发送删除通知到频道 {channel.get('channel_id')} 失败: {str(e)}")
                    continue

        except Exception as e:
            logging.error(f"处理消息删除事件时出错: {str(e)}")
            logging.error(f"错误详情: {traceback.format_exc()}")

    async def download_media_file(self, message, media_type: str) -> dict:
        """下载媒体文件并返回相关信息"""
        tmp = None
        file_path = None
        chunk_size = 20 * 1024 * 1024  # 20MB 分块

        try:
            # 获取文件大小
            file_size = getattr(message.media, 'file_size', 0) or getattr(message.media, 'size', 0)
            logging.info(f"开始下载媒体文件，大小: {file_size / (1024*1024):.2f}MB")

            # 创建临时文件
            tmp = NamedTemporaryFile(delete=False, prefix='tg_', suffix=f'.{media_type}')
            file_path = tmp.name

            # 使用分块下载
            downloaded_size = 0
            async for chunk in self.client.iter_download(message.media, chunk_size=chunk_size):
                if chunk:
                    tmp.write(chunk)
                    downloaded_size += len(chunk)
                    if downloaded_size % (50 * 1024 * 1024) == 0:
                        progress = (downloaded_size / file_size) * 100 if file_size else 0
                        logging.info(f"下载进度: {progress:.1f}% ({downloaded_size/(1024*1024):.1f}MB/{file_size/(1024*1024):.1f}MB)")

                    if downloaded_size % (100 * 1024 * 1024) == 0:
                        tmp.flush()
                        os.fsync(tmp.fileno())

            tmp.close()
            logging.info("媒体文件下载完成")

            if not os.path.exists(file_path):
                raise Exception(get_text('en', 'downloaded_file_not_found', file_path=file_path))

            # 记录临时文件
            self.temp_files[file_path] = datetime.now()

            # 收集媒体信息
            media_info = {
                'file_path': file_path,
                'file_size': file_size,
                'media_type': media_type
            }

            # 收集特定媒体类型的额外信息
            if media_type == 'video' and hasattr(message.media, 'video'):
                video = message.media.video
                if hasattr(video, 'width'):
                    media_info['width'] = video.width
                if hasattr(video, 'height'):
                    media_info['height'] = video.height
                if hasattr(video, 'duration'):
                    media_info['duration'] = video.duration

                # 如果有缩略图
                if hasattr(video, 'thumb') and video.thumb:
                    try:
                        thumb_path = await self.client.download_media(video.thumb)
                        media_info['thumb_path'] = thumb_path
                    except Exception as e:
                        logging.warning(f"无法下载视频缩略图: {str(e)}")

            # 如果是文档，获取文件名
            elif media_type == 'document' and hasattr(message.media, 'document'):
                if hasattr(message.media.document, 'attributes'):
                    for attr in message.media.document.attributes:
                        if hasattr(attr, 'file_name'):
                            media_info['filename'] = attr.file_name
                            break

            return media_info

        except Exception as e:
            logging.error(f"下载媒体文件时出错: {str(e)}")
            if file_path and file_path in self.temp_files:
                await self.cleanup_file(file_path)
            return None

    async def handle_sticker_send(self, message, channel_id, from_chat, reply_to_message_id=None):
        """处理贴图发送"""
        try:
            logging.info(f"开始处理贴图发送")

            # 下载贴图文件
            sticker_path = await self.client.download_media(message.media)
            logging.info(f"贴图下载完成: {sticker_path}")

            # 构建用户名部分
            username = f"(@{from_chat.username})" if getattr(from_chat, 'username', None) else ""

            # 使用简化的模板作为贴图标题
            caption = f"📨 转发自 {getattr(from_chat, 'title', 'Unknown Channel')} {username}"

            # 发送贴图
            with open(sticker_path, 'rb') as sticker_file:
                await self.bot.send_sticker(
                    chat_id=channel_id,
                    sticker=sticker_file.read(),
                    reply_to_message_id=reply_to_message_id
                )

                # 如果有标题且没有回复消息，发送标题
                if caption and not reply_to_message_id:
                    await self.bot.send_message(
                        chat_id=channel_id,
                        text=caption,
                        disable_web_page_preview=True
                    )

            # 清理临时文件
            if sticker_path and os.path.exists(sticker_path):
                os.remove(sticker_path)
                logging.info(f"贴图文件已清理: {sticker_path}")

            logging.info(f"贴图发送成功")

        except Exception as e:
            logging.error(f"发送贴图时出错: {str(e)}")
            logging.error(f"错误详情: {traceback.format_exc()}")

            # 如果失败，发送错误消息
            try:
                await self.bot.send_message(
                    chat_id=channel_id,
                    text=f"⚠️ 贴图发送失败: {str(e)}",
                    reply_to_message_id=reply_to_message_id
                )
            except Exception as e2:
                logging.error(f"发送错误消息失败: {str(e2)}")

            # 清理临时文件
            if 'sticker_path' in locals() and sticker_path and os.path.exists(sticker_path):
                try:
                    os.remove(sticker_path)
                except Exception as e3:
                    logging.error(f"清理贴图文件失败: {str(e3)}")

    async def handle_custom_emoji(self, message, channel_id):
        """处理自定义表情"""
        try:
            # 检查消息中的自定义表情实体
            if hasattr(message, 'entities'):
                has_custom_emoji = False
                for entity in message.entities:
                    if hasattr(entity, 'CONSTRUCTOR_ID') and entity.CONSTRUCTOR_ID == 0x81ccf4d:  # MessageEntityCustomEmoji
                        has_custom_emoji = True
                        break
                    elif hasattr(entity, '__class__') and 'MessageEntityCustomEmoji' in str(entity.__class__):
                        has_custom_emoji = True
                        break

                if has_custom_emoji:
                    logging.info(f"检测到自定义表情，添加提示消息")
                    await self.bot.send_message(
                        chat_id=channel_id,
                        text="ℹ️ 原消息包含自定义表情，可能无法完全显示。"
                    )
                    return True
            return False
        except Exception as e:
            logging.error(f"处理自定义表情时出错: {str(e)}")
            return False

    async def edit_message_with_media(self, channel_id, message_id, text, media_path, media_type, media_info):
        """编辑消息以包含媒体文件"""
        try:
            # 注意：Telegram API 不支持直接编辑消息添加媒体
            # 我们需要删除原消息并发送新消息

            # 先删除原消息
            await self.bot.delete_message(
                chat_id=channel_id,
                message_id=message_id
            )

            # 根据媒体类型发送新消息
            with open(media_path, 'rb') as media_file:
                file_data = media_file.read()
                send_kwargs = {
                    'chat_id': channel_id,
                    'caption': text,
                    'parse_mode': 'Markdown',
                    'read_timeout': 1800,
                    'write_timeout': 1800
                }

                if media_type == 'photo':
                    send_kwargs['photo'] = file_data
                    await self.bot.send_photo(**send_kwargs)
                elif media_type == 'video':
                    send_kwargs['video'] = file_data
                    send_kwargs['supports_streaming'] = True

                    # 添加视频参数
                    if 'width' in media_info:
                        send_kwargs['width'] = media_info['width']
                    if 'height' in media_info:
                        send_kwargs['height'] = media_info['height']
                    if 'duration' in media_info:
                        send_kwargs['duration'] = media_info['duration']
                    if 'thumb_path' in media_info and os.path.exists(media_info['thumb_path']):
                        with open(media_info['thumb_path'], 'rb') as thumb_file:
                            send_kwargs['thumb'] = thumb_file.read()

                    await self.bot.send_video(**send_kwargs)

                    # 清理缩略图
                    if 'thumb_path' in media_info and os.path.exists(media_info['thumb_path']):
                        os.remove(media_info['thumb_path'])

                elif media_type == 'document':
                    send_kwargs['document'] = file_data
                    if 'filename' in media_info:
                        send_kwargs['filename'] = media_info['filename']
                    await self.bot.send_document(**send_kwargs)

            # 清理媒体文件
            await self.cleanup_file(media_path)
            logging.info(f"成功编辑消息并添加{media_type}")

        except Exception as e:
            logging.error(f"编辑消息添加媒体失败: {str(e)}")
            # 如果失败，尝试恢复原消息
            try:
                await self.bot.send_message(
                    chat_id=channel_id,
                    text=text + "\n\n⚠️ *媒体文件加载失败*",
                    parse_mode='Markdown',
                    disable_web_page_preview=True
                )
            except Exception as e2:
                logging.error(f"恢复消息失败: {str(e2)}")

            # 清理媒体文件
            await self.cleanup_file(media_path)
            raise