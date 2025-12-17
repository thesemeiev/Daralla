"""
Утилиты для бота
"""
from .ui import UIEmojis, UIStyles, UIButtons, UIMessages
from .message_helpers import (
    safe_edit_or_reply,
    safe_edit_or_reply_photo,
    safe_edit_or_reply_universal,
    safe_send_message_with_photo,
    safe_edit_message_with_photo,
    safe_answer_callback_query,
    set_image_paths,
)
from .validators import check_private_chat
from .helpers import calculate_time_remaining, format_vpn_key_message, check_user_has_existing_keys

__all__ = [
    'UIEmojis',
    'UIStyles',
    'UIButtons',
    'UIMessages',
    'safe_edit_or_reply',
    'safe_edit_or_reply_photo',
    'safe_edit_or_reply_universal',
    'safe_send_message_with_photo',
    'safe_edit_message_with_photo',
    'safe_answer_callback_query',
    'set_image_paths',
    'check_private_chat',
    'calculate_time_remaining',
    'format_vpn_key_message',
    'check_user_has_existing_keys',
]

