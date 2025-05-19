from aiogram import Bot, types
from aiogram.utils.keyboard import ReplyKeyboardBuilder, InlineKeyboardBuilder
import html

from loader import get_db
from utils.checks import is_channel_admin as check_user_is_channel_admin

async def check_bot_is_channel_admin(bot: Bot, channel_id: int) -> bool:
    try:
        bot_member = await bot.get_chat_member(chat_id=channel_id, user_id=bot.id)
        if bot_member.status == 'administrator':
            if hasattr(bot_member, 'can_post_messages') and bot_member.can_post_messages:
                return True
            return True
        return False
    except Exception as e:
        print(f"Error checking bot admin status for channel {channel_id}: {e}")
        return False


def get_main_keyboard() -> types.ReplyKeyboardMarkup:
    builder = ReplyKeyboardBuilder()
    builder.button(text="📝 Создать пост")
    builder.button(text="📢 Мои каналы")
    builder.button(text="➕ Добавить канал")
    builder.button(text="🗓️ Запланированные") # <--- НОВАЯ КНОПКА
    builder.button(text="📚 Шаблоны")
    builder.button(text="📜 История")
    builder.button(text="🆘 Помощь")
    # Подбираем количество кнопок в ряду. Например, 3 в первом, 2 во втором, 2 в третьем.
    builder.adjust(3, 2, 2)
    return builder.as_markup(resize_keyboard=True)


async def get_channels_keyboard(user_id: int, selected_channel_id: int = None) -> types.InlineKeyboardMarkup:
    db = get_db()
    channels = db.fetchall(
        "SELECT channel_id, title FROM channels WHERE user_id = ? ORDER BY title",
        (user_id,)
    )
    builder = InlineKeyboardBuilder()
    if channels:
        for cid, title in channels:
            button_text = escape_html(title)
            if selected_channel_id and cid == selected_channel_id:
                button_text = f"✅ {button_text}"
            builder.row(types.InlineKeyboardButton(text=button_text, callback_data=f"channel_{cid}"))
    return builder.as_markup()


async def notify_user(bot: Bot, user_id: int, text: str, **kwargs):
    try:
        await bot.send_message(chat_id=user_id, text=text, **kwargs)
    except Exception as e:
        print(f"Ошибка отправки уведомления пользователю {user_id}: {e}")


async def notify_post_published(bot: Bot, user_id: int, channel_id: int, message_id: int, channel_title: str):
    try:
        channel_id_str = str(channel_id).replace('-100', '')
        safe_channel_title = escape_html(channel_title)
        text = (f"✅ Пост опубликован в канале «{safe_channel_title}»!\n"
                f"👁‍🗨 Посмотреть: https://t.me/c/{channel_id_str}/{message_id}")
        await notify_user(bot, user_id, text, disable_web_page_preview=True)
    except Exception as e:
        print(f"Ошибка уведомления о публикации: {e}")

def escape_html(text: str | None) -> str:
    if not text:
        return ""
    return html.escape(str(text))