# locales.py
import logging


TRANSLATIONS = {
    'en': {
        'file_cleanup_success': "Cleaned up file: {file_path}",
'file_cleanup_error': "Error cleaning up file {file_path}: {error}",
'cleanup_task_error': "Error in cleanup task: {error}",
'forward_channel_error': "Error forwarding to channel {channel_id}: {error}",
'message_handler_error': "Error in handle_channel_message: {error}",
'error_details': "Full error details: {details}",
'media_download_failed': "Failed to download media",
'forwarded_from': "Forwarded from: {channel}",
'downloaded_file_not_found': "Downloaded file not found: {file_path}",
'media_send_success': "Successfully sent {media_type} to channel {channel_id}",
'media_send_error': "Error sending {media_type}: {error}",
'missing_parameters': "Missing required parameters for message forwarding",
'invalid_channel_id': "Invalid channel ID",
'forward_success': "Successfully forwarded message to channel {channel_id}",
'direct_forward_failed': "Direct forward failed, trying alternative method: {error}",
'text_send_success': "Successfully sent text message to channel {channel_id}",
'forwarded_message_template': "Forwarded from: {title}\n{username}\n{separator}\n\n{content}",
'private_channel': "Private Channel",
'download_progress': "Download progress: {percentage:.1f}%",
'forward_message_error': "Error in handle_forward_message: {error}",
        'welcome': "👋 Welcome to Channel Forward Bot!\n\nUse /channels to manage channels and forwarding pairs",
        'unauthorized': "Unauthorized access",
        'channel_management': "📺 Channel Management\n\n• Add monitor/forward channels\n• Delete existing channels\n• View channel list\n• Manage channel pairs",
        'add_channel': "Add Channel",
        'delete_channel': "Delete Channel",
        'channel_list': "Channel List",
        'pair_management': "Pair Management",
        'select_channel_type': "Select channel type to add:\n\n• Monitor Channel: For monitoring messages\n• Forward Channel: For forwarding messages",
        'monitor_channel': "Monitor Channel",
        'forward_channel': "Forward Channel",
        'cancel': "Cancel",
        'select_add_method': "Please select how to add {channel_type} channel:\n\n• Forward Message: Forward any message from target channel\n• Enter ID: Directly enter channel ID",
        'forward_message': "Forward Message",
        'enter_id': "Enter ID",
        'forward_instruction': "Please forward a message from the target channel.\n\nTip: You can click on a message and select 'Forward'.\n\nUse /cancel to cancel.",
        'manual_input_instruction': "Please enter the channel ID.\n\nTip: Channel ID starts with -100 and can be obtained from channel message links.\nExample: -1001234567890\n\nUse /cancel to cancel.",
        'invalid_forward': "❌ Please forward a message from the target channel.",
        'channel_add_success': "✅ Channel added successfully!\n\nName: {name}\nID: {id}\nType: {type}",
        'channel_add_failed': "❌ Failed to add channel",
        'invalid_id_format': "❌ Invalid channel ID format.\n\nPlease try again or use /cancel to cancel",
        'channel_info_error': "❌ Cannot get channel information. Please ensure:\n1. ID format is correct\n2. Bot has joined the channel\n3. You have access to the channel\n\nPlease try again or use /cancel to cancel",
        'process_error': "❌ Error processing input.\nPlease try again or use /cancel to cancel",
        'operation_cancelled': "❌ Operation cancelled",
        'no_channels': "No channels available.",
        'delete_confirm': "Are you sure you want to delete this channel?\n\nChannel Name: {name}\nChannel ID: {id}\nType: {type}",
        'confirm_delete': "✅ Confirm Delete",
        'channel_deleted': "✅ Channel deleted",
        'delete_failed': "❌ Delete failed",
        'delete_error': "❌ Error occurred while deleting channel",
        'channel_list_title': "📋 Channel List\n\n",
        'monitor_channels': "🔍 Monitor Channels:\n",
        'forward_channels': "\n📢 Forward Channels:\n",
        'no_channels_config': "No channels configured",
        'channel_info': "{idx}. {name}\n   ID: {id}\n   Username: @{username}\n\n",
        'back': "Back",
        'retry': "Retry",
        'previous_page': "⬅️ Previous",
        'next_page': "➡️ Next",
        'page_info': "Page {current}/{total}",
        'language_changed': "✅ Language changed to English",
        'select_language': "Please select your language:",
        'current_language': "Current language: {lang}",
        'help_message': """
📚 *Channel Forward Bot Help*

*Basic Commands:*
/start - Start the bot
/channels - Open channel management menu
/language - Change bot language
/help - Show this help message

*Channel Management:*
• *Add Channel:* Add monitor or forward channels
• *Delete Channel:* Remove existing channels
• *Channel List:* View all configured channels
• *Pair Management:* Manage channel forwarding pairs

*Channel Types:*
• *Monitor Channel:* Source channel to monitor messages from
• *Forward Channel:* Destination channel to forward messages to

*Adding Channels:*
1. Use /channels command
2. Click "Add Channel"
3. Choose channel type
4. Add channel by either:
   - Forwarding a message from the channel
   - Entering the channel ID manually

*Managing Pairs:*
1. Go to pair management
2. Select a monitor channel
3. Add or remove forward channels
4. Messages will be automatically forwarded based on pairs

*Notes:*
• Bot must be added as admin to both monitor and forward channels
• Channel IDs start with -100
• Each monitor channel can be paired with multiple forward channels

*For more help or to report issues, contact the bot administrator.*
""",
        'positions_title': "📊 Current Positions Summary",
        'no_positions': "No open positions",
        'total_positions': "Total Positions: {count}",
        'total_volume': "Total Volume: {volume:.2f} lots",
        'total_pl': "Total P/L: {profit:.2f}",
        'position_details': "Position Details:",
        'position_info': "{emoji} {symbol}: {volume} lots @ {price:.5f}\n   P/L: {profit:.2f} ({type})",
        'breakeven_success': "✅ Modified {count} profitable positions to breakeven",
        'closeall_confirm': "⚠️ Are you sure you want to close ALL positions?",
        'closeall_cancelled': "Operation cancelled",
        'closeall_success': "✅ Successfully closed {count} positions",
        'trade_manager_error': "❌ Trade manager not available",
        'delete_channel_title': 'Select channel to delete:',
        'manage_pair_title': 'Pair Management for {channel}',
        'no_pairs': 'No forwarding pairs configured',
        'current_pairs': 'Current Forward Channels:',
        'available_channels': 'Available Forward Channels:',
        'add_pair_button': '➕ Add {name}',
        'remove_pair_button': '❌ Remove {name}',
        'manage_pairs_button': 'Manage pairs for {name}',
        'error_occurred': 'An error occurred. Please try again.',
        'pair_management_title': "Channel Pair Management",
        'back_to_pairs': "Back to Pairs",
        'back_to_menu': "Back to Menu",
        'remove_channel_title': "Select channel to delete",
        'select_channel': "Select a channel",
        'forward_select_method': "Please select how to add the channel:",
        'confirm_remove_pair': "Are you sure you want to remove the forwarding pair?\n\nMonitor Channel: {monitor}\nForward Channel: {forward}",
'pair_removed_success': "✅ Forward pair removed successfully",
'back_to_pairs_management': "Back to Pair Management",
'confirm_remove': "✅ Confirm Remove",
'pair_added_success': "✅ Successfully added forward pair!\n\nMonitor Channel: {monitor}\nForward Channel: {forward}",
'pair_add_failed': "❌ Failed to add forward pair",
'error_adding_pair': "❌ Error occurred while adding pair",
'processing': "Processing your request...",
'invalid_forward': "❌ Please forward a message from the target channel or use the channel selector.",
'channel_not_found': "❌ Channel not found. Please try again.",
'forwarded_message_template': "Forwarded from: {title}\n{source_info}\n{separator}\n\n{content}",
'chat_type_private_channel': "Private Channel",
'chat_type_public_channel': "Public Channel",
'chat_type_private_channel_with_link': "Private Channel (Invite Link Available)",
'chat_type_group': "Group",
'chat_type_supergroup': "Supergroup",
'chat_type_gigagroup': "Broadcast Group",
'chat_type_channel': "Channel",
    },
    'zh': {
        'forwarded_message_template': "转发自：{title}\n{source_info}\n{separator}\n\n{content}",
'chat_type_private_channel': "私有频道",
'chat_type_public_channel': "公开频道",
'chat_type_private_channel_with_link': "私有频道（有邀请链接）",
'chat_type_group': "群组",
'chat_type_supergroup': "超级群组",
'chat_type_gigagroup': "广播群组",
'chat_type_channel': "频道",
        'file_cleanup_success': "已清理文件：{file_path}",
'file_cleanup_error': "清理文件 {file_path} 时出错：{error}",
'cleanup_task_error': "清理任务出错：{error}",
'forward_channel_error': "转发到频道 {channel_id} 时出错：{error}",
'message_handler_error': "处理频道消息时出错：{error}",
'error_details': "完整错误信息：{details}",
'media_download_failed': "下载媒体文件失败",
'forwarded_from': "转发自：{channel}",
'downloaded_file_not_found': "找不到下载的文件：{file_path}",
'media_send_success': "成功发送{media_type}到频道 {channel_id}",
'media_send_error': "发送{media_type}时出错：{error}",
'missing_parameters': "消息转发缺少必要参数",
'invalid_channel_id': "无效的频道ID",
'forward_success': "成功转发消息到频道 {channel_id}",
'direct_forward_failed': "直接转发失败，尝试替代方法：{error}",
'text_send_success': "成功发送文本消息到频道 {channel_id}",
'forwarded_message_template': "转发自：{title}\n{username}\n{separator}\n\n{content}",
'private_channel': "私有频道",
'download_progress': "下载进度：{percentage:.1f}%",
'forward_message_error': "处理消息转发时出错：{error}",
        'welcome': "👋 欢迎使用频道转发机器人!\n\n使用 /channels 管理频道和转发配对",
        'unauthorized': "未经授权的访问",
        'channel_management': "📺 频道管理\n\n• 添加监控或转发频道\n• 删除现有频道\n• 查看频道列表\n• 管理频道配对",
        'add_channel': "添加频道",
        'delete_channel': "删除频道",
        'channel_list': "频道列表",
        'pair_management': "配对管理",
        'select_channel_type': "选择要添加的频道类型:\n\n• 监控频道: 用于监控消息\n• 转发频道: 用于转发消息",
        'monitor_channel': "监控频道",
        'forward_channel': "转发频道", 
        'cancel': "取消",
        'select_add_method': "请选择添加{channel_type}的方式:\n\n• 转发消息: 从目标频道转发任意消息\n• 输入ID: 直接输入频道ID",
        'forward_message': "转发消息",
        'enter_id': "输入ID",
        'forward_instruction': "请从目标频道转发一条消息。\n\n提示: 你可以点击消息，然后选择'Forward'来转发。\n\n输入 /cancel 取消操作。",
        'manual_input_instruction': "请输入频道ID。\n\n提示: 频道ID是-100开头的数字，可以通过复制频道消息链接获取。\n例如: -1001234567890\n\n输入 /cancel 取消操作。",
        'invalid_forward': "❌ 请转发一条来自目标频道的消息。",
        'channel_add_success': "✅ 频道添加成功!\n\n名称: {name}\nID: {id}\n类型: {type}",
        'channel_add_failed': "❌ 添加频道失败",
        'invalid_id_format': "❌ 无效的频道ID格式。\n\n请重新输入或使用 /cancel 取消",
        'channel_info_error': "❌ 无法获取频道信息。请确保:\n1. ID格式正确\n2. Bot已加入该频道\n3. 您有权限访问该频道\n\n请重新输入或使用 /cancel 取消",
        'process_error': "❌ 处理输入时发生错误。\n请重新输入或使用 /cancel 取消",
        'operation_cancelled': "❌ 操作已取消",
        'no_channels': "当前没有任何频道。",
        'delete_confirm': "确定要删除此频道吗?\n\n频道名称: {name}\n频道ID: {id}\n类型: {type}",
        'confirm_delete': "✅ 确认删除",
        'channel_deleted': "✅ 频道已删除",
        'delete_failed': "❌ 删除失败",
        'delete_error': "❌ 删除频道时发生错误",
        'channel_list_title': "📋 频道列表\n\n",
        'monitor_channels': "🔍 监控频道:\n",
        'forward_channels': "\n📢 转发频道:\n",
        'no_channels_config': "暂无频道配置",
        'channel_info': "{idx}. {name}\n   ID: {id}\n   用户名: @{username}\n\n",
        'back': "返回",
        'retry': "重试",
        'previous_page': "⬅️ 上一页",
        'next_page': "➡️ 下一页",
        'page_info': "第 {current}/{total} 页",
        'language_changed': "✅ 语言已更改为中文",
        'select_language': "请选择语言:",
        'current_language': "当前语言: {lang}",
        'pair_added_success': "✅ 成功添加转发配对！\n\n监控频道: {monitor}\n转发频道: {forward}",
'pair_add_failed': "❌ 添加转发配对失败",
'error_adding_pair': "❌ 添加配对时发生错误",
'processing': "正在处理您的请求...",
'invalid_forward': "❌ 请从目标频道转发消息或使用频道选择器。",
'channel_not_found': "❌ 未找到频道。请重试。",
        'positions_title': "📊 当前持仓汇总",
        'no_positions': "没有开仓",
        'total_positions': "总持仓数: {count}",
        'total_volume': "总手数: {volume:.2f} 手",
        'total_pl': "总盈亏: {profit:.2f}",
        'position_details': "持仓详情:",
        'position_info': "{emoji} {symbol}: {volume} 手 @ {price:.5f}\n   盈亏: {profit:.2f} ({type})",
        'breakeven_success': "✅ 已将 {count} 个盈利仓位的止损移至入场价",
        'closeall_confirm': "⚠️ 确定要关闭所有持仓吗？",
        'closeall_cancelled': "操作已取消",
        'closeall_success': "✅ 成功关闭 {count} 个持仓",
        'trade_manager_error': "❌ 交易管理器不可用",
        'help_message': """
📚 *频道转发机器人帮助*

*基本命令：*
/start - 启动机器人
/channels - 打开频道管理菜单
/language - 更改机器人语言
/positions - 查看所有持仓
/breakeven - 将盈利仓位止损移至入场价
/closeall - 关闭所有持仓
/help - 显示此帮助信息

*频道管理：*
• *添加频道：* 添加监控或转发频道
• *删除频道：* 移除现有频道
• *频道列表：* 查看所有配置的频道
• *配对管理：* 管理频道转发配对

*频道类型：*
• *监控频道：* 用于监控消息的源频道
• *转发频道：* 用于接收转发消息的目标频道

*交易命令：*
• */positions:* 查看所有持仓汇总
• */breakeven:* 将盈利仓位止损移至入场价
• */closeall:* 关闭所有持仓（需确认）

*添加频道：*
1. 使用 /channels 命令
2. 点击"添加频道"
3. 选择频道类型
4. 通过以下方式添加频道：
   - 从目标频道转发一条消息
   - 手动输入频道ID

*管理配对：*
1. 进入配对管理
2. 选择一个监控频道
3. 添加或移除转发频道
4. 消息会根据配对自动转发

*注意事项：*
• 机器人必须被添加为监控和转发频道的管理员
• 频道ID以-100开头
• 每个监控频道可以配对多个转发频道

*如需更多帮助或报告问题，请联系机器人管理员。*
""",
        'delete_channel_title': '选择要删除的频道：',
        'manage_pair_title': '{channel} 的配对管理',
        'no_pairs': '暂无转发配对',
        'current_pairs': '当前转发频道：',
        'available_channels': '可添加的转发频道：',
        'add_pair_button': '➕ 添加 {name}',
        'remove_pair_button': '❌ 移除 {name}',
        'manage_pairs_button': '管理 {name} 的配对',
        'error_occurred': '发生错误，请重试。',
        'pair_management_title': "频道配对管理",
        'back_to_pairs': "返回配对列表",
        'back_to_menu': "返回主菜单",
        'remove_channel_title': "选择要删除的频道",
        'select_channel': "选择一个频道",
        'forward_select_method': "请选择添加频道的方式："
    },
    'confirm_remove_pair': "确定要删除此转发配对吗？\n\n监控频道: {monitor}\n转发频道: {forward}",
'pair_removed_success': "✅ 转发配对已成功删除",
'back_to_pairs_management': "返回配对管理",
'confirm_remove': "✅ 确认删除"
}


def get_text(lang: str, key: str, **kwargs) -> str:
    """获取指定语言的文本
    
    Args:
        lang: 语言代码 ('en' 或 'zh')
        key: 文本键名
        **kwargs: 格式化参数
    """
    if lang not in TRANSLATIONS:
        lang = 'en'  # 默认使用英语
    
    text = TRANSLATIONS[lang].get(key, TRANSLATIONS['en'].get(key, key))
    try:
        if kwargs:
            text = text.format(**kwargs)
    except KeyError as e:
        logging.error(f"Missing format key in translation: {e}")
        return text
    except Exception as e:
        logging.error(f"Error formatting text: {e}")
        return text
    
    return text