# handlers/history.py
import sqlite3
from datetime import datetime
from aiogram import Router, types, F
from aiogram.filters import Command
from aiogram.utils.keyboard import InlineKeyboardBuilder  # Для возможной пагинации
import logging # Добавьте импорт



# Импортируем из loader и utils
from loader import get_db
from bot_utils import get_main_keyboard  # Используем bot_utils
from bot_utils import escape_html # <--- ДОБАВИТЬ ИМПОРТ

router = Router()

POSTS_PER_PAGE = 5  # Количество постов на одной странице истории


@router.message(Command("history"))
@router.message(F.text == "📜 История")
async def show_history_command(message: types.Message):
    # При вызове команды или нажатии кнопки показываем первую страницу
    await display_history_page(message, page=0)


async def display_history_page(message_or_callback: types.Message | types.CallbackQuery, page: int):
    db = get_db()
    offset = page * POSTS_PER_PAGE

    try:
        # Считаем общее количество постов для пагинации
        total_posts_query = db.fetchone("SELECT COUNT(*) FROM posts")
        total_posts = total_posts_query[0] if total_posts_query else 0

        # Запрос постов для текущей страницы
        posts_data = db.fetchall(
            f"""SELECT 
                posts.id, 
                channels.title, 
                posts.content, 
                posts.publish_time, 
                posts.status,
                posts.message_id,  -- ID сообщения в канале
                posts.channel_id   -- Telegram ID канала
            FROM posts
            JOIN channels ON posts.channel_id = channels.channel_id -- Используем JOIN вместо LEFT JOIN, если пост без канала не имеет смысла
            ORDER BY posts.publish_time DESC 
            LIMIT ? OFFSET ?""",
            (POSTS_PER_PAGE, offset)
        )

        if not posts_data and page == 0:  # Если вообще нет постов
            response_text = "📭 История публикаций пуста."
            reply_markup = get_main_keyboard()
            if isinstance(message_or_callback, types.Message):
                await message_or_callback.answer(response_text, reply_markup=reply_markup)
            elif isinstance(message_or_callback, types.CallbackQuery):
                await message_or_callback.message.edit_text(response_text, reply_markup=reply_markup)
                await message_or_callback.answer()
            return

        if not posts_data and page > 0:  # Если нет постов на этой странице (но были на предыдущих)
            response_text = "📭 Больше нет записей в истории."
            # Можно добавить кнопку "Назад" на предыдущую страницу
            builder = InlineKeyboardBuilder()
            if page > 0:
                builder.button(text="⬅️ Назад", callback_data=f"history_page_{page - 1}")
            builder.button(text="🏠 В меню", callback_data="history_to_main_menu")
            reply_markup = builder.as_markup()

            if isinstance(message_or_callback, types.Message):  # Не должно случиться для page > 0 без коллбэка
                await message_or_callback.answer(response_text, reply_markup=reply_markup)
            elif isinstance(message_or_callback, types.CallbackQuery):
                await message_or_callback.message.edit_text(response_text, reply_markup=reply_markup)
                await message_or_callback.answer()
            return

        response_parts = [f"📜 <b>История публикаций (Страница {page + 1}):</b>\n"]
        for post_id, ch_title, content, pub_time_iso, status, msg_id, ch_id_tg in posts_data:
            # Экранирование
            safe_ch_title = escape_html(ch_title)
            safe_content_preview = escape_html(
                content[:70] + "..." if content and len(content) > 70 else (content or ""))

            # ... (логика publish_time_str, status_emoji) ...
            publish_time_dt = datetime.fromisoformat(pub_time_iso)
            publish_time_str = escape_html(publish_time_dt.strftime('%d.%m.%Y %H:%M'))

            status_emoji = {
                "published": "✅",
                "scheduled": "⏳",
                "failed": "❌",
                "cancelled": "🚫"  # Пример нового статуса
            }.get(status, "❓")

            safe_status_capitalized = escape_html(status.capitalize())

            post_link_html = ""
            if status == "published" and msg_id and ch_id_tg:
                channel_id_str_for_link = str(ch_id_tg).replace('-100', '')
                # URL сам по себе не нужно экранировать для href, но текст ссылки - да
                link_url = f"https://t.me/c/{channel_id_str_for_link}/{msg_id}"
                post_link_html = f' (<a href="{link_url}">Посмотреть</a>)'

            response_parts.append(
                f"🆔 <b>Пост:</b> {post_id}\n"
                f"📢 <b>Канал:</b> {safe_ch_title}\n"
                f"⏰ <b>Время:</b> {publish_time_str}\n"
                f"📝 <b>Текст:</b> {safe_content_preview}\n"
                f"🔸 <b>Статус:</b> {status_emoji} {safe_status_capitalized}{post_link_html}\n"
            )

        response_text = "\n".join(response_parts)

        # Кнопки пагинации
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


        parse_mode_to_use = "HTML" # <--- HTML

        if isinstance(message_or_callback, types.Message):
            await message_or_callback.answer(response_text, reply_markup=builder.as_markup(),
                                             parse_mode=parse_mode_to_use, disable_web_page_preview=True)
        elif isinstance(message_or_callback, types.CallbackQuery):
            # ... (проверка MessageNotModified) ...
            await message_or_callback.message.edit_text(response_text, reply_markup=builder.as_markup(),
                                                        parse_mode=parse_mode_to_use, disable_web_page_preview=True)
            await message_or_callback.answer()

    except sqlite3.Error as e:
        error_msg = f"❌ Ошибка базы данных при загрузке истории: {str(e)}"
        print(error_msg)  # Логирование
        if isinstance(message_or_callback, types.Message):
            await message_or_callback.answer(error_msg, reply_markup=get_main_keyboard())
        elif isinstance(message_or_callback, types.CallbackQuery):
            await message_or_callback.message.edit_text(error_msg)  # reply_markup не меняем или ставим главное меню
            await message_or_callback.answer("Ошибка БД", show_alert=True)
    except Exception as e:
        error_msg = f"❌ Неизвестная ошибка при загрузке истории: {str(e)}"
        print(error_msg)  # Логирование
        if isinstance(message_or_callback, types.Message):
            await message_or_callback.answer(error_msg, reply_markup=get_main_keyboard())
        elif isinstance(message_or_callback, types.CallbackQuery):
            await message_or_callback.message.edit_text(error_msg)
            await message_or_callback.answer("Неизвестная ошибка", show_alert=True)


logger_history = logging.getLogger(__name__) # Создайте логгер
# Обработчик для кнопок пагинации истории
@router.callback_query(F.data == "history_to_main_menu")
async def history_back_to_main_menu(callback: types.CallbackQuery):
    logger_history.info(f"!!! ATTENTION: history_to_main_menu CALLED by user {callback.from_user.id} !!!")
    await callback.answer()  # Отвечаем на коллбэк, чтобы убрать "часики"

    try:
        # Сначала удаляем инлайн-клавиатуру у текущего сообщения
        # или меняем текст, чтобы показать, что действие выполнено
        await callback.message.edit_text("Возврат в главное меню...", reply_markup=None)
        # Альтернатива: await callback.message.delete() # если хотите полностью удалить старое сообщение
    except Exception as e:
        logger_history.error(f"Error editing/deleting message in history_to_main_menu: {e}", exc_info=True)
        # Если не удалось отредактировать/удалить, не страшно, просто отправим новое
        pass # Ошибка здесь не должна прерывать отправку нового сообщения

    # Отправляем новое сообщение с текстом и ReplyKeyboard
    try:
        await callback.message.answer("Вы вернулись в главное меню.", reply_markup=get_main_keyboard())
    except Exception as e:
        logger_history.error(f"Error sending main menu message in history_to_main_menu: {e}", exc_info=True)


# Обработчик для кнопки "В меню" из истории
@router.callback_query(F.data == "history_to_main_menu")
async def history_back_to_main_menu(callback: types.CallbackQuery):
    logger_history.info(f"!!! ATTENTION: history_to_main_menu CALLED by user {callback.from_user.id} !!!")
    await callback.answer() # Отвечаем на коллбэк, чтобы убрать "часики"

    try:
        # Сначала удаляем сообщение с инлайн-кнопками (или просто убираем его клавиатуру)
        await callback.message.edit_reply_markup(reply_markup=None)
        # или await callback.message.delete() # если хотите полностью удалить старое сообщение
    except Exception as e:
        logger_history.error(f"Error modifying/deleting message in history_to_main_menu: {e}", exc_info=True)
        # Если не удалось отредактировать/удалить, не страшно, просто отправим новое
        pass

    # Отправляем новое сообщение с текстом и ReplyKeyboard
    await callback.message.answer("Вы вернулись в главное меню.", reply_markup=get_main_keyboard())