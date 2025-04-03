from aiogram import Router, F, types
from aiogram.fsm.context import FSMContext
from aiogram import Bot

router = Router()

async def notify_success(bot: Bot, user_id: int, channel_id: int, message_id: int, text: str):
    try:
        channel_info = await bot.get_chat(chat_id=channel_id)
        # В notifications.py (функция notify_success)
        channel_id_str = str(channel_id).replace('-100', '')  # Добавить эту строку
        await bot.send_message(
            chat_id=user_id,
            text=f"✅ Пост опубликован в канале {channel_info.title}!\n"
                 f"👁‍🗨 Посмотреть: https://t.me/c/{channel_id_str}/{message_id}"
        )
    except Exception as e:
        print(f"Ошибка уведомления: {e}")