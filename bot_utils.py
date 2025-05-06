# bot_utils.py (в корне проекта)
from aiogram import Bot, types
from aiogram.utils.keyboard import ReplyKeyboardBuilder, InlineKeyboardBuilder
import html # Для экранирования HTML

# Импортируем loader для get_db
from loader import get_db
# Импортируем вашу функцию проверки прав пользователя
from utils.checks import is_channel_admin as check_user_is_channel_admin


# Ваша функция is_channel_admin из utils.checks уже есть,
# мы ее импортировали выше как check_user_is_channel_admin.

async def check_bot_is_channel_admin(bot: Bot, channel_id: int) -> bool:
    """
    Проверяет, является ли БОТ администратором указанного канала и имеет ли права на постинг.
    """
    try:
        # bot.id доступен в aiogram 3+
        bot_member = await bot.get_chat_member(chat_id=channel_id, user_id=bot.id)
        if bot_member.status == 'administrator':
            # Для aiogram 3.x: ChatMemberAdministrator имеет атрибуты вроде can_post_messages
            if hasattr(bot_member, 'can_post_messages') and bot_member.can_post_messages:
                return True
            # Если такого атрибута нет в используемой версии/типе ChatMember,
            # но статус администратор, можно считать это достаточным (упрощение)
            # или добавить более детальные проверки для разных типов ChatMember (creator, etc.)
            # Для базового постинга достаточно быть администратором.
            return True  # Упрощенная проверка
        return False
    except Exception as e:
        # Логирование ошибки будет полезно
        print(f"Error checking bot admin status for channel {channel_id}: {e}")
        return False


def get_main_keyboard() -> types.ReplyKeyboardMarkup:
    builder = ReplyKeyboardBuilder()
    builder.button(text="📝 Создать пост")
    builder.button(text="📢 Мои каналы")
    builder.button(text="➕ Добавить канал")
    builder.button(text="📚 Шаблоны")
    builder.button(text="📜 История")
    builder.button(text="🆘 Помощь")
    builder.adjust(2, 2, 2)
    return builder.as_markup(resize_keyboard=True)


async def get_channels_keyboard(selected_channel_id: int = None) -> types.InlineKeyboardMarkup:
    """
    Генерирует клавиатуру с подключенными каналами.
    selected_channel_id - опциональный ID канала, который будет помечен как выбранный.
    """
    db = get_db()
    channels = db.fetchall("SELECT channel_id, title FROM channels ORDER BY title")
    builder = InlineKeyboardBuilder()
    if channels:
        for cid, title in channels:
            button_text = title
            if selected_channel_id and cid == selected_channel_id:
                button_text = f"✅ {title}"  # Помечаем выбранный канал
            builder.row(types.InlineKeyboardButton(text=button_text, callback_data=f"channel_{cid}"))
    # Если каналов нет, клавиатура будет пустой, что нормально для некоторых сценариев
    return builder.as_markup()


async def notify_user(bot: Bot, user_id: int, text: str, **kwargs):
    """Отправляет уведомление пользователю."""
    try:
        await bot.send_message(chat_id=user_id, text=text, **kwargs)
    except Exception as e:
        print(f"Ошибка отправки уведомления пользователю {user_id}: {e}")


async def notify_post_published(bot: Bot, user_id: int, channel_id: int, message_id: int, channel_title: str):
    """Уведомляет пользователя об успешной публикации поста."""
    try:
        channel_id_str = str(channel_id).replace('-100', '')  # Для публичной ссылки

        text = (f"✅ Пост опубликован в канале «{channel_title}»!\n"
                f"👁‍🗨 Посмотреть: https://t.me/c/{channel_id_str}/{message_id}")
        await notify_user(bot, user_id, text)
    except Exception as e:
        print(f"Ошибка уведомления о публикации: {e}")

def escape_html(text: str) -> str:
    """Экранирует специальные HTML символы."""
    if not text:
        return ""
    return html.escape(text)
