# utils/checks.py
from aiogram import Bot

async def is_channel_admin(bot: Bot, user_id: int, channel_id: int) -> bool:
    """
    Проверяет, является ли ПОЛЬЗОВАТЕЛЬ администратором указанного канала.
    """
    try:
        member = await bot.get_chat_member(chat_id=channel_id, user_id=user_id)
        return member.status in ['creator', 'administrator']
    except Exception:
        return False