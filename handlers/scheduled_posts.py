import sqlite3
from datetime import datetime
from aiogram import Router, types, F, Bot
from aiogram.filters import Command
from aiogram.fsm.context import FSMContext
from aiogram.utils.keyboard import InlineKeyboardBuilder
import logging

from loader import get_db, scheduler  # Импортируем scheduler
from bot_utils import get_main_keyboard, escape_html, notify_user
from services.scheduler import remove_scheduled_job  # Импортируем функцию удаления задачи

router = Router()
logger = logging.getLogger(__name__)

SCHEDULED_POSTS_PER_PAGE = 5


@router.message(Command("my_scheduled"))
@router.message(F.text == "🗓️ Запланированные")  # Предположим, такая кнопка будет
async def show_scheduled_posts_command(message: types.Message):
    await display_scheduled_posts_page(message, page=0)


async def display_scheduled_posts_page(message_or_callback: types.Message | types.CallbackQuery, page: int):
    db = get_db()
    current_user_id = message_or_callback.from_user.id
    offset = page * SCHEDULED_POSTS_PER_PAGE

    try:
        # Считаем общее количество ЗАПЛАНИРОВАННЫХ постов для текущего пользователя
        total_scheduled_posts_query = db.fetchone(
            "SELECT COUNT(*) FROM posts WHERE user_id = ? AND status = 'scheduled'",
            (current_user_id,)
        )
        total_scheduled_posts = total_scheduled_posts_query[0] if total_scheduled_posts_query else 0

        # Запрос запланированных постов для текущей страницы
        scheduled_posts_data = db.fetchall(
            f"""SELECT 
                p.id, 
                ch.title, 
                p.content, 
                p.publish_time,
                p.channel_id -- Telegram ID канала из таблицы posts
            FROM posts p
            LEFT JOIN channels ch ON p.channel_id = ch.channel_id AND p.user_id = ch.user_id
            WHERE p.user_id = ? AND p.status = 'scheduled'
            ORDER BY p.publish_time ASC -- Показываем ближайшие по времени сначала
            LIMIT ? OFFSET ?""",
            (current_user_id, SCHEDULED_POSTS_PER_PAGE, offset)
        )

        if not scheduled_posts_data and page == 0:
            response_text = "🗓️ У вас нет запланированных постов."
            reply_markup = get_main_keyboard() if isinstance(message_or_callback, types.Message) else None
            if isinstance(message_or_callback, types.Message):
                await message_or_callback.answer(response_text, reply_markup=reply_markup)
            elif isinstance(message_or_callback, types.CallbackQuery):
                await message_or_callback.message.edit_text(response_text, reply_markup=reply_markup)
                await message_or_callback.answer()
            return

        if not scheduled_posts_data and page > 0:
            response_text = "🗓️ Больше нет запланированных постов."
            builder = InlineKeyboardBuilder()
            if page > 0:
                builder.button(text="⬅️ Назад", callback_data=f"sched_page_{page - 1}")
            builder.button(text="🏠 В меню", callback_data="sched_to_main_menu")
            reply_markup = builder.as_markup()

            if isinstance(message_or_callback, types.CallbackQuery):
                await message_or_callback.message.edit_text(response_text, reply_markup=reply_markup)
                await message_or_callback.answer()
            return

        response_parts = [f"🗓️ <b>Ваши запланированные посты (Страница {page + 1}):</b>\n"]
        builder = InlineKeyboardBuilder()  # Клавиатура для кнопок отмены и пагинации

        for post_db_id, ch_title_from_db, content, pub_time_iso, ch_id_tg_from_post in scheduled_posts_data:
            safe_content_preview = escape_html(
                content[:50] + "..." if content and len(content) > 50 else (content or "[Без текста]")
            )
            publish_time_dt = datetime.fromisoformat(pub_time_iso)
            publish_time_str = escape_html(publish_time_dt.strftime('%d.%m.%Y %H:%M'))

            safe_ch_title_display: str
            if ch_title_from_db:
                safe_ch_title_display = escape_html(ch_title_from_db)
            else:
                escaped_ch_id_tg = escape_html(str(ch_id_tg_from_post))
                safe_ch_title_display = f"<i>Канал (ID: <code>{escaped_ch_id_tg}</code>)</i>"

            response_parts.append(
                f"🔹 <b>ID:</b> {post_db_id}\n"
                f"📢 <b>Канал:</b> {safe_ch_title_display}\n"
                f"⏰ <b>Время:</b> {publish_time_str}\n"
                f"📝 <b>Текст:</b> {safe_content_preview}\n"
            )
            # Кнопка отмены для каждого поста
            builder.row(
                types.InlineKeyboardButton(
                    text=f"🚫 Отменить пост ID {post_db_id}",
                    callback_data=f"sched_cancel_ask_{post_db_id}"
                )
            )
            response_parts.append("-" * 20)  # Разделитель

        response_text = "\n".join(response_parts)

        # Кнопки пагинации
        pagination_buttons = []
        if page > 0:
            pagination_buttons.append(
                types.InlineKeyboardButton(text="⬅️ Пред.", callback_data=f"sched_page_{page - 1}"))

        total_pages = (total_scheduled_posts + SCHEDULED_POSTS_PER_PAGE - 1) // SCHEDULED_POSTS_PER_PAGE
        if page < total_pages - 1:
            pagination_buttons.append(
                types.InlineKeyboardButton(text="След. ➡️", callback_data=f"sched_page_{page + 1}"))

        if pagination_buttons:
            builder.row(*pagination_buttons)
        builder.row(types.InlineKeyboardButton(text="🏠 В меню", callback_data="sched_to_main_menu"))

        parse_mode_to_use = "HTML"

        if isinstance(message_or_callback, types.Message):
            await message_or_callback.answer(response_text, reply_markup=builder.as_markup(),
                                             parse_mode=parse_mode_to_use, disable_web_page_preview=True)
        elif isinstance(message_or_callback, types.CallbackQuery):
            try:
                await message_or_callback.message.edit_text(response_text, reply_markup=builder.as_markup(),
                                                            parse_mode=parse_mode_to_use, disable_web_page_preview=True)
            except types.TelegramBadRequest as e:
                if "message is not modified" not in str(e).lower(): raise
            await message_or_callback.answer()

    except sqlite3.Error as e:
        error_msg = f"❌ Ошибка БД при загрузке запланированных постов: {str(e)}"
        logger.error(error_msg, exc_info=True)
        reply_markup = get_main_keyboard() if isinstance(message_or_callback, types.Message) else None
        if isinstance(message_or_callback, types.Message):
            await message_or_callback.answer(error_msg, reply_markup=reply_markup)
        elif isinstance(message_or_callback, types.CallbackQuery):
            await message_or_callback.message.edit_text(error_msg, reply_markup=reply_markup)
            await message_or_callback.answer("Ошибка БД", show_alert=True)
    except Exception as e:
        error_msg = f"❌ Неизвестная ошибка: {str(e)}"
        logger.error(error_msg, exc_info=True)
        reply_markup = get_main_keyboard() if isinstance(message_or_callback, types.Message) else None
        if isinstance(message_or_callback, types.Message):
            await message_or_callback.answer(error_msg, reply_markup=reply_markup)
        elif isinstance(message_or_callback, types.CallbackQuery):
            await message_or_callback.message.edit_text(error_msg, reply_markup=reply_markup)
            await message_or_callback.answer("Неизвестная ошибка", show_alert=True)


# Пагинация
@router.callback_query(F.data.startswith("sched_page_"))
async def process_scheduled_page_callback(callback: types.CallbackQuery):
    page = int(callback.data.split("_")[2])
    await display_scheduled_posts_page(callback, page=page)


# Возврат в меню
@router.callback_query(F.data == "sched_to_main_menu")
async def scheduled_back_to_main_menu(callback: types.CallbackQuery):
    logger.info(f"User {callback.from_user.id} clicked 'sched_to_main_menu'")
    await callback.answer()
    try:
        await callback.message.edit_reply_markup(reply_markup=None)
    except Exception:
        pass
    await callback.message.answer("Вы вернулись в главное меню.", reply_markup=get_main_keyboard())


# Запрос подтверждения отмены запланированного поста
@router.callback_query(F.data.startswith("sched_cancel_ask_"))
async def confirm_cancel_scheduled_post(callback: types.CallbackQuery, bot: Bot):
    await callback.answer()
    post_db_id_to_cancel = int(callback.data.split("_")[3])
    current_user_id = callback.from_user.id
    db = get_db()

    post_info = db.fetchone(
        "SELECT channel_id, publish_time FROM posts WHERE id = ? AND user_id = ? AND status = 'scheduled'",
        (post_db_id_to_cancel, current_user_id)
    )

    if not post_info:
        await callback.message.edit_text("❌ Запланированный пост не найден, уже выполнен или отменен.",
                                         reply_markup=None)
        return

    builder = InlineKeyboardBuilder()
    builder.row(
        types.InlineKeyboardButton(text="✅ Да, отменить", callback_data=f"sched_cancel_do_{post_db_id_to_cancel}"),
        types.InlineKeyboardButton(text="❌ Нет", callback_data=f"sched_cancel_no_{post_db_id_to_cancel}")
    )
    await callback.message.edit_text(
        f"❓ Вы уверены, что хотите отменить запланированный пост ID {post_db_id_to_cancel}?",
        reply_markup=builder.as_markup()
    )


# Отмена действия (не отменять пост)
@router.callback_query(F.data.startswith("sched_cancel_no_"))
async def decline_cancel_scheduled_post(callback: types.CallbackQuery):
    await callback.answer("Отмена действия.")
    # Возвращаем пользователя к списку запланированных постов (предполагаем, что он был на странице 0)
    # Чтобы вернуться на ту же страницу, нужно было бы сохранить page в callback_data кнопки "Нет"
    await display_scheduled_posts_page(callback, page=0)


# Выполнение отмены запланированного поста
@router.callback_query(F.data.startswith("sched_cancel_do_"))
async def process_cancel_scheduled_post(callback: types.CallbackQuery, bot: Bot):
    await callback.answer()
    post_db_id_to_cancel = int(callback.data.split("_")[3])
    current_user_id = callback.from_user.id
    db = get_db()

    # Еще раз проверяем пост перед действием
    post_info = db.fetchone(
        "SELECT channel_id, publish_time FROM posts WHERE id = ? AND user_id = ? AND status = 'scheduled'",
        (post_db_id_to_cancel, current_user_id)
    )

    if not post_info:
        await callback.message.edit_text("❌ Запланированный пост не найден, уже выполнен или отменен.",
                                         reply_markup=None)
        return

    job_id = f"post_{post_db_id_to_cancel}"
    removed_from_scheduler = remove_scheduled_job(scheduler, job_id)

    if removed_from_scheduler:
        try:
            db.execute(
                "UPDATE posts SET status = 'cancelled' WHERE id = ? AND user_id = ?",
                (post_db_id_to_cancel, current_user_id),
                commit=True
            )
            if db.cursor.rowcount > 0:
                logger.info(
                    f"User {current_user_id} cancelled scheduled post DB ID {post_db_id_to_cancel}. Status updated. Job removed.")
                await callback.message.edit_text(f"✅ Запланированный пост ID {post_db_id_to_cancel} успешно отменен.",
                                                 reply_markup=None)
                # await notify_user(bot, current_user_id, f"Ваш запланированный пост (ID: {post_db_id_to_cancel}) был отменен.")
            else:  # Маловероятно, если первая проверка прошла
                logger.warning(
                    f"Failed to update status to 'cancelled' for post DB ID {post_db_id_to_cancel} for user {current_user_id}, though job was removed.")
                await callback.message.edit_text(
                    "⚠️ Пост удален из расписания, но произошла ошибка обновления статуса в БД.", reply_markup=None)

        except sqlite3.Error as e_db:
            logger.error(f"DB error updating post {post_db_id_to_cancel} to cancelled: {e_db}", exc_info=True)
            await callback.message.edit_text("❌ Ошибка базы данных при отмене поста. Пост мог остаться в расписании.",
                                             reply_markup=None)
            # Здесь можно попытаться передобавить задачу, если отмена в БД не удалась, но это усложнит логику
    else:
        # Если задача не найдена в планировщике, возможно, она уже выполнилась или была удалена ранее.
        # Проверим статус в БД еще раз.
        current_status_info = db.fetchone("SELECT status FROM posts WHERE id = ?", (post_db_id_to_cancel,))
        current_status = current_status_info[0] if current_status_info else "unknown"

        if current_status == 'scheduled':
            # Это странная ситуация: в планировщике нет, а в БД 'scheduled'
            logger.error(
                f"Job {job_id} for post {post_db_id_to_cancel} not found in scheduler, but DB status is 'scheduled'. Attempting to set 'failed'.")
            db.execute("UPDATE posts SET status = 'failed' WHERE id = ?", (post_db_id_to_cancel,),
                       commit=True)  # или 'cancelled_error'
            await callback.message.edit_text(
                "⚠️ Пост не найден в активном расписании. Его статус в БД обновлен на 'ошибка'.", reply_markup=None)
        elif current_status == 'published':
            await callback.message.edit_text("ℹ️ Этот пост уже был опубликован.", reply_markup=None)
        elif current_status == 'cancelled':
            await callback.message.edit_text("ℹ️ Этот пост уже был отменен ранее.", reply_markup=None)
        else:  # failed или другой статус
            await callback.message.edit_text(
                f"ℹ️ Не удалось отменить пост. Текущий статус: {escape_html(current_status)}.", reply_markup=None)
            logger.warning(
                f"Could not cancel post {post_db_id_to_cancel}. Job not in scheduler. DB status: {current_status}.")

    # После действия, можно предложить вернуться к списку или в меню
    # Для простоты пока просто убираем клавиатуру. Пользователь может нажать кнопку "Запланированные" снова.
    # await display_scheduled_posts_page(callback, page=0) # Вернуть к списку