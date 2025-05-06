# handlers/channels.py
import sqlite3
from aiogram import Router, Bot, types, F
from aiogram.filters import Command
# ReplyKeyboardRemove не используется, можно убрать, если только он не нужен в другом месте этого файла
# from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton, ReplyKeyboardRemove
from aiogram.utils.keyboard import InlineKeyboardBuilder
import logging

# Импортируем из loader и utils
from loader import get_db
from bot_utils import get_main_keyboard, check_user_is_channel_admin, check_bot_is_channel_admin, escape_html

router = Router()
logger = logging.getLogger(__name__)


# Команда и кнопка для добавления канала
@router.message(Command("add_channel"))
@router.message(F.text == "➕ Добавить канал")
async def add_channel_start(message: types.Message):  # bot здесь не нужен, его передаст aiogram в handle_forwarded
    await message.answer(
        "Чтобы добавить канал:\n"
        "1. Сделайте этого бота администратором вашего канала (с правами на публикацию сообщений).\n"
        "2. Перешлите сюда любое сообщение из этого канала.",
        reply_markup=get_main_keyboard()
    )


# Обработка пересланного сообщения из канала
@router.message(F.forward_from_chat)
async def handle_forwarded_channel_message(message: types.Message, bot: Bot):  # bot нужен для check_..._admin
    db = get_db()
    user_id_who_adds = message.from_user.id  # Пользователь, который пытается добавить канал
    forwarded_chat = message.forward_from_chat

    if not forwarded_chat:
        await message.answer("❌ Не удалось определить канал из пересланного сообщения.")
        return

    if forwarded_chat.type not in ['channel']:
        await message.answer("❌ Пожалуйста, перешлите сообщение из КАНАЛА.")
        return

    channel_id_telegram = forwarded_chat.id
    channel_title = forwarded_chat.title
    escaped_channel_title = escape_html(channel_title)  # Для безопасного вывода в сообщениях

    # Проверка, является ли БОТ админом в этом канале
    bot_is_admin_with_rights = await check_bot_is_channel_admin(bot, channel_id_telegram)
    if not bot_is_admin_with_rights:
        await message.answer(
            f"❌ Бот должен быть администратором канала «{escaped_channel_title}» "
            f"и иметь право на публикацию сообщений. Пожалуйста, проверьте настройки канала."
        )
        return

    try:
        db.execute(
            "INSERT INTO channels (user_id, channel_id, title) VALUES (?, ?, ?)",
            (user_id_who_adds, channel_id_telegram, channel_title),  # Сохраняем оригинальный title
            commit=True
        )
        logger.info(f"User {user_id_who_adds} added channel {channel_title} ({channel_id_telegram})")
        await message.answer(f"✅ Канал «{escaped_channel_title}» успешно добавлен!", reply_markup=get_main_keyboard())
    except sqlite3.IntegrityError:  # Ошибка уникальности (user_id, channel_id)
        logger.warning(f"User {user_id_who_adds} tried to re-add channel {channel_title} ({channel_id_telegram})")
        await message.answer(f"⚠️ Канал «{escaped_channel_title}» уже был добавлен вами ранее.",
                             reply_markup=get_main_keyboard())
    except sqlite3.Error as e:
        logger.error(f"DB error adding channel for user {user_id_who_adds}: {e}", exc_info=True)
        await message.answer(f"❌ Произошла ошибка базы данных при добавлении канала. Попробуйте позже.")


# Просмотр списка МОИХ подключенных каналов
@router.message(F.text == "📢 Мои каналы")
@router.message(Command("my_channels"))
async def list_my_channels(message: types.Message):
    db = get_db()
    current_user_id = message.from_user.id

    channels_data = db.fetchall(
        "SELECT id, channel_id, title FROM channels WHERE user_id = ? ORDER BY title",
        (current_user_id,)
    )

    if not channels_data:
        await message.answer("❌ Вы еще не добавили ни одного канала.\n"
                             "Нажмите «➕ Добавить канал», чтобы начать.",
                             reply_markup=get_main_keyboard())
        return

    builder = InlineKeyboardBuilder()
    response_text_parts = ["📡 <b>Ваши подключенные каналы:</b>\n"]
    for db_id, channel_id_telegram, title in channels_data:
        escaped_title = escape_html(title)
        escaped_channel_id_telegram = escape_html(str(channel_id_telegram))
        response_text_parts.append(f"• {escaped_title} (ID: <code>{escaped_channel_id_telegram}</code>)")
        builder.row(
            # В callback_data передаем id из нашей БД (PK)
            types.InlineKeyboardButton(text=f"🗑️ {escaped_title}", callback_data=f"ch_delete_ask_{db_id}")
        )

    await message.answer("\n".join(response_text_parts), reply_markup=builder.as_markup(), parse_mode="HTML")


# Запрос подтверждения на удаление канала
@router.callback_query(F.data.startswith("ch_delete_ask_"))
async def confirm_delete_channel(callback: types.CallbackQuery):
    await callback.answer()
    db_channel_id_to_delete = int(callback.data.split("_")[3])  # ch_delete_ask_ID
    current_user_id = callback.from_user.id
    db = get_db()

    # Проверяем, что канал принадлежит этому пользователю
    channel_info = db.fetchone(
        "SELECT title FROM channels WHERE id = ? AND user_id = ?",
        (db_channel_id_to_delete, current_user_id)
    )

    if not channel_info:
        logger.warning(
            f"User {current_user_id} tried to access/delete non-existent or not owned channel (DB ID {db_channel_id_to_delete})")
        await callback.message.edit_text("❌ Канал не найден или у вас нет прав на его удаление.")
        return

    channel_title = channel_info[0]
    escaped_channel_title = escape_html(channel_title)

    builder = InlineKeyboardBuilder()
    builder.row(
        types.InlineKeyboardButton(text="✅ Да, удалить", callback_data=f"ch_delete_do_{db_channel_id_to_delete}"),
        types.InlineKeyboardButton(text="❌ Нет, отмена", callback_data="ch_delete_cancel")  # Общий cancel
    )
    await callback.message.edit_text(
        f"❓ Вы уверены, что хотите удалить канал «{escaped_channel_title}» из вашего списка?\n"
        f"(Это не удалит сам Telegram канал, только отключит его от бота для вас.)",
        reply_markup=builder.as_markup(),
        parse_mode="HTML"
    )


# Отмена удаления канала
@router.callback_query(F.data == "ch_delete_cancel")
async def cancel_delete_channel_action(callback: types.CallbackQuery):
    await callback.answer("Удаление отменено.")
    # Обновляем сообщение, чтобы показать список каналов (или главное меню)
    # Чтобы показать список каналов, нужно передать `message` объект, а у нас `callback`.
    # Проще всего отредактировать на простое сообщение и предложить нажать кнопку из меню.
    await callback.message.edit_text("Удаление канала отменено. Вы можете просмотреть список каналов через меню.",
                                     reply_markup=None)
    # Если бы у нас был доступ к message из list_my_channels, можно было бы его вызвать.
    # Или отправить новое сообщение со списком каналов:
    # await list_my_channels(callback.message) # Неправильно, callback.message - это сообщение с кнопками
    # await callback.message.answer("Обновленный список каналов:", reply_markup=await get_channels_for_user_keyboard(callback.from_user.id))


# Подтверждение и удаление канала
@router.callback_query(F.data.startswith("ch_delete_do_"))
async def process_delete_channel(callback: types.CallbackQuery):
    await callback.answer()
    db_channel_id_to_delete = int(callback.data.split("_")[3])  # ch_delete_do_ID
    current_user_id = callback.from_user.id
    db = get_db()

    # Еще раз проверяем принадлежность канала перед удалением
    channel_info = db.fetchone(
        "SELECT title FROM channels WHERE id = ? AND user_id = ?",
        (db_channel_id_to_delete, current_user_id)
    )
    if not channel_info:
        logger.warning(
            f"User {current_user_id} tried to delete non-existent or not owned channel after confirm (DB ID {db_channel_id_to_delete})")
        await callback.message.edit_text("❌ Канал уже удален или не найден.")
        return

    channel_title = channel_info[0]
    escaped_channel_title = escape_html(channel_title)

    try:
        # При удалении канала из таблицы `channels`, благодаря `ON DELETE CASCADE` для `posts.user_id`
        # (если бы связь была posts.channel_db_id -> channels.id), связанные посты бы удалились.
        # В текущей структуре (posts.channel_id это Telegram ID), посты этого пользователя из этого канала
        # останутся в истории, но при отображении истории, если канал удален из `channels`,
        # мы не сможем получить его название из `channels` через JOIN. Это нужно будет учесть в `history.py`.
        # Пока просто удаляем канал из списка пользователя.

        db.execute(
            "DELETE FROM channels WHERE id = ? AND user_id = ?",
            (db_channel_id_to_delete, current_user_id),
            commit=True
        )
        if db.cursor.rowcount > 0:
            logger.info(f"User {current_user_id} deleted channel {channel_title} (DB ID {db_channel_id_to_delete})")
            await callback.message.edit_text(f"✅ Канал «{escaped_channel_title}» успешно удален из вашего списка.",
                                             reply_markup=None, parse_mode="HTML")
        else:  # На случай, если между подтверждением и удалением что-то произошло
            logger.warning(f"Channel (DB ID {db_channel_id_to_delete}) not found for user {current_user_id} at delete.")
            await callback.message.edit_text("Не удалось удалить канал (возможно, он уже был удален).",
                                             reply_markup=None)

    except sqlite3.Error as e:
        logger.error(f"DB error deleting channel (DB ID {db_channel_id_to_delete}) for user {current_user_id}: {e}",
                     exc_info=True)
        await callback.message.edit_text(f"❌ Ошибка при удалении канала «{escaped_channel_title}».",
                                         reply_markup=None, parse_mode="HTML")