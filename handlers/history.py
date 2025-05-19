import sqlite3
from datetime import datetime
from aiogram import Router, types, F
from aiogram.filters import Command
from aiogram.utils.keyboard import InlineKeyboardBuilder
import logging

from loader import get_db
from bot_utils import get_main_keyboard, escape_html

router = Router()
logger = logging.getLogger(__name__)  # Используем логгер из logging

POSTS_PER_PAGE = 5  # Количество постов на одной странице истории


@router.message(Command("history"))
@router.message(F.text == "📜 История")
async def show_history_command(message: types.Message):
    await display_history_page(message, page=0)


async def display_history_page(message_or_callback: types.Message | types.CallbackQuery, page: int):
    db = get_db()
    current_user_id = message_or_callback.from_user.id
    offset = page * POSTS_PER_PAGE

    try:
        # Считаем общее количество постов для пагинации ДЛЯ ТЕКУЩЕГО ПОЛЬЗОВАТЕЛЯ
        total_posts_query = db.fetchone(
            "SELECT COUNT(*) FROM posts WHERE user_id = ?",
            (current_user_id,)
        )
        total_posts = total_posts_query[0] if total_posts_query else 0

        # Запрос постов для текущей страницы ДЛЯ ТЕКУЩЕГО ПОЛЬЗОВАТЕЛЯ
        # Используем LEFT JOIN, чтобы получить посты, даже если канал был удален из списка пользователя
        posts_data = db.fetchall(
            f"""SELECT 
                p.id, 
                ch.title,        -- Название канала из таблицы channels (может быть NULL)
                p.content, 
                p.publish_time, 
                p.status,
                p.message_id,    -- ID сообщения в канале
                p.channel_id     -- Telegram ID канала из таблицы posts
            FROM posts p
            LEFT JOIN channels ch ON p.channel_id = ch.channel_id AND p.user_id = ch.user_id 
            WHERE p.user_id = ?
            ORDER BY p.publish_time DESC 
            LIMIT ? OFFSET ?""",
            (current_user_id, POSTS_PER_PAGE, offset)
        )

        if not posts_data and page == 0:
            response_text = "📭 Ваша история публикаций пуста."
            reply_markup = get_main_keyboard()  # Для сообщения, а не для коллбэка
            if isinstance(message_or_callback, types.Message):
                await message_or_callback.answer(response_text, reply_markup=reply_markup)
            elif isinstance(message_or_callback, types.CallbackQuery):
                # Если это коллбэк и первая страница пуста, редактируем сообщение
                await message_or_callback.message.edit_text(response_text, reply_markup=None)  # Убираем инлайн кнопки
                await message_or_callback.answer()
            return

        if not posts_data and page > 0:
            response_text = "📭 Больше нет записей в вашей истории."
            builder = InlineKeyboardBuilder()
            if page > 0:  # Кнопка назад всегда должна быть, если page > 0
                builder.button(text="⬅️ Назад", callback_data=f"history_page_{page - 1}")
            builder.button(text="🏠 В меню", callback_data="history_to_main_menu")  # Общая кнопка в меню
            reply_markup = builder.as_markup()

            if isinstance(message_or_callback, types.CallbackQuery):
                await message_or_callback.message.edit_text(response_text, reply_markup=reply_markup)
                await message_or_callback.answer()
            # Для message такой ситуации (page > 0 и нет постов) быть не должно, т.к. history_page вызывается только из коллбэка
            return

        response_parts = [f"📜 <b>Ваша история публикаций (Страница {page + 1}):</b>\n"]
        for post_id, ch_title_from_db, content, pub_time_iso, status, msg_id, ch_id_tg_from_post in posts_data:

            safe_content_preview = escape_html(
                content[:70] + "..." if content and len(content) > 70 else (content or "[Без текста]")
            )

            publish_time_dt = datetime.fromisoformat(pub_time_iso)
            publish_time_str = escape_html(publish_time_dt.strftime('%d.%m.%Y %H:%M'))

            status_emoji = {
                "published": "✅", "scheduled": "⏳", "failed": "❌", "cancelled": "🚫"
            }.get(status, "❓")
            safe_status_capitalized = escape_html(status.capitalize())

            # Обработка названия канала
            safe_ch_title_display: str
            if ch_title_from_db:
                safe_ch_title_display = escape_html(ch_title_from_db)
            else:
                # Если канал был удален пользователем из его списка `channels` (или никогда не был корректно добавлен под этим user_id)
                escaped_ch_id_tg = escape_html(str(ch_id_tg_from_post))
                safe_ch_title_display = f"<i>Канал (ID: <code>{escaped_ch_id_tg}</code>)</i>"

            post_link_html = ""
            if status == "published" and msg_id and ch_id_tg_from_post:
                channel_id_str_for_link = str(ch_id_tg_from_post).replace('-100', '')
                link_url = f"https://t.me/c/{channel_id_str_for_link}/{msg_id}"
                post_link_html = f' (<a href="{link_url}">Посмотреть</a>)'

            response_parts.append(
                f"🆔 <b>Пост:</b> {post_id}\n"
                f"📢 <b>Канал:</b> {safe_ch_title_display}\n"
                f"⏰ <b>Время:</b> {publish_time_str}\n"
                f"📝 <b>Текст:</b> {safe_content_preview}\n"
                f"🔸 <b>Статус:</b> {status_emoji} {safe_status_capitalized}{post_link_html}\n"
            )

        response_text = "\n".join(response_parts)
        builder = InlineKeyboardBuilder()
        row_buttons = []
        if page > 0:
            row_buttons.append(types.InlineKeyboardButton(text="⬅️ Пред.", callback_data=f"history_page_{page - 1}"))

        total_pages = (total_posts + POSTS_PER_PAGE - 1) // POSTS_PER_PAGE
        if page < total_pages - 1:
            row_buttons.append(types.InlineKeyboardButton(text="След. ➡️", callback_data=f"history_page_{page + 1}"))

        if row_buttons:
            builder.row(*row_buttons)
        builder.row(types.InlineKeyboardButton(text="🏠 В меню", callback_data="history_to_main_menu"))

        parse_mode_to_use = "HTML"

        if isinstance(message_or_callback, types.Message):
            await message_or_callback.answer(response_text, reply_markup=builder.as_markup(),
                                             parse_mode=parse_mode_to_use, disable_web_page_preview=True)
        elif isinstance(message_or_callback, types.CallbackQuery):
            try:
                await message_or_callback.message.edit_text(response_text, reply_markup=builder.as_markup(),
                                                            parse_mode=parse_mode_to_use, disable_web_page_preview=True)
            except types.TelegramBadRequest as e:
                if "message is not modified" in str(e).lower():
                    logger.debug("Message not modified in history page display.")
                else:
                    raise  # Перевыбрасываем другие ошибки
            await message_or_callback.answer()

    except sqlite3.Error as e:
        error_msg = f"❌ Ошибка базы данных при загрузке истории: {str(e)}"
        logger.error(error_msg, exc_info=True)
        if isinstance(message_or_callback, types.Message):
            await message_or_callback.answer(error_msg, reply_markup=get_main_keyboard())
        elif isinstance(message_or_callback, types.CallbackQuery):
            await message_or_callback.message.edit_text(error_msg, reply_markup=None)
            await message_or_callback.answer("Ошибка БД", show_alert=True)
    except Exception as e:
        error_msg = f"❌ Неизвестная ошибка при загрузке истории: {str(e)}"
        logger.error(error_msg, exc_info=True)
        if isinstance(message_or_callback, types.Message):
            await message_or_callback.answer(error_msg, reply_markup=get_main_keyboard())
        elif isinstance(message_or_callback, types.CallbackQuery):
            await message_or_callback.message.edit_text(error_msg, reply_markup=None)
            await message_or_callback.answer("Неизвестная ошибка", show_alert=True)


# Обработчик для кнопок пагинации истории
@router.callback_query(F.data.startswith("history_page_"))
async def process_history_page_callback(callback: types.CallbackQuery):
    page = int(callback.data.split("_")[2])
    await display_history_page(callback, page=page)


# Обработчик для кнопки "В меню" из истории
@router.callback_query(F.data == "history_to_main_menu")
async def history_back_to_main_menu(callback: types.CallbackQuery):
    logger.info(f"User {callback.from_user.id} clicked 'history_to_main_menu'")
    await callback.answer()

    try:
        # Убираем инлайн-клавиатуру у текущего сообщения
        await callback.message.edit_reply_markup(reply_markup=None)
    except Exception as e:
        logger.error(f"Error editing reply markup in history_to_main_menu: {e}", exc_info=True)
        pass

    # Отправляем новое сообщение с текстом и ReplyKeyboard
    await callback.message.answer("Вы вернулись в главное меню.", reply_markup=get_main_keyboard())