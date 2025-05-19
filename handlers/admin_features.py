from aiogram import Router, types, F
from aiogram.filters import Command, CommandObject

from loader import content_filter, get_db  # Добавляем get_db
from filters.admin import IsAdmin
from bot_utils import escape_html

router = Router()
router.message.filter(IsAdmin())
router.callback_query.filter(IsAdmin())


@router.message(Command("add_banned_word"))
async def admin_add_banned_word(message: types.Message, command: CommandObject):
    if command.args is None:
        await message.answer(
            "Пожалуйста, укажите слово для добавления.\n"
            "Пример: <code>/add_banned_word плохой</code>",
            parse_mode="HTML"
        )
        return

    word_to_add = command.args.strip().lower()
    if not word_to_add:
        await message.answer("Слово не может быть пустым.")
        return

    if " " in word_to_add:
        await message.answer("Пожалуйста, добавляйте слова по одному, без пробелов.")
        return

    if len(word_to_add) > 50:
        await message.answer("Слишком длинное слово (максимум 50 символов).")
        return

    if word_to_add in content_filter.banned_words:
        await message.answer(f"Слово «{escape_html(word_to_add)}» уже есть в списке.")
        return

    if content_filter.add_word(word_to_add):
        await message.answer(f"✅ Слово «{escape_html(word_to_add)}» успешно добавлено в список запрещенных.")
    else:
        await message.answer(f"❌ Не удалось добавить слово «{escape_html(word_to_add)}». Проверьте логи.")


@router.message(Command("remove_banned_word"))
async def admin_remove_banned_word(message: types.Message, command: CommandObject):
    if command.args is None:
        await message.answer(
            "Пожалуйста, укажите слово для удаления.\n"
            "Пример: <code>/remove_banned_word плохой</code>",
            parse_mode="HTML"
        )
        return

    word_to_remove = command.args.strip().lower()
    if not word_to_remove:
        await message.answer("Слово не может быть пустым.")
        return

    if word_to_remove not in content_filter.banned_words:
        await message.answer(f"Слова «{escape_html(word_to_remove)}» нет в списке запрещенных.")
        return

    if content_filter.remove_word(word_to_remove):
        await message.answer(f"🗑️ Слово «{escape_html(word_to_remove)}» успешно удалено из списка.")
    else:
        await message.answer(f"❌ Не удалось удалить слово «{escape_html(word_to_remove)}». Проверьте логи.")


@router.message(Command("list_banned_words"))
async def admin_list_banned_words(message: types.Message):
    if not content_filter.banned_words:
        await message.answer("Список запрещенных слов пуст.")
        return

    header = "📜 <b>Текущий список запрещенных слов:</b>\n\n"
    words_text = ""
    message_parts = []

    for word in sorted(content_filter.banned_words):
        word_line = f"• <code>{escape_html(word)}</code>\n"
        if len(header) + len(words_text) + len(word_line) > 4000:
            message_parts.append(header + words_text)
            words_text = ""
            header = ""
        words_text += word_line

    if words_text or not message_parts:
        message_parts.append(header + words_text)

    for part in message_parts:
        if part.strip():
            await message.answer(part, parse_mode="HTML")


# --- НОВЫЕ АДМИНСКИЕ ФУНКЦИИ ---

@router.message(Command("admin_stats"))
async def admin_stats(message: types.Message):
    db = get_db()
    stats_text_parts = ["📊 <b>Статистика бота:</b>\n"]

    # Пользователи
    users_count = db.fetchone("SELECT COUNT(*) FROM bot_users")[0]
    admins_count = db.fetchone("SELECT COUNT(*) FROM bot_users WHERE is_admin = TRUE")[0]
    stats_text_parts.append(f"<b>Пользователи:</b>")
    stats_text_parts.append(f"  ▫️ Всего зарегистрировано: {users_count}")
    stats_text_parts.append(f"  ▫️ Из них администраторов бота: {admins_count}\n")

    # Каналы
    channels_count = db.fetchone("SELECT COUNT(*) FROM channels")[0]
    stats_text_parts.append(f"<b>Каналы:</b>")
    stats_text_parts.append(f"  ▫️ Всего подключено каналов: {channels_count}\n")

    # Посты
    posts_total_count = db.fetchone("SELECT COUNT(*) FROM posts")[0]
    posts_scheduled = db.fetchone("SELECT COUNT(*) FROM posts WHERE status = 'scheduled'")[0]
    posts_published = db.fetchone("SELECT COUNT(*) FROM posts WHERE status = 'published'")[0]
    posts_failed = db.fetchone("SELECT COUNT(*) FROM posts WHERE status = 'failed'")[0]
    posts_cancelled = db.fetchone("SELECT COUNT(*) FROM posts WHERE status = 'cancelled'")[0]
    stats_text_parts.append(f"<b>Посты:</b>")
    stats_text_parts.append(f"  ▫️ Всего постов в системе: {posts_total_count}")
    stats_text_parts.append(f"  ▫️ Запланировано: {posts_scheduled}")
    stats_text_parts.append(f"  ▫️ Опубликовано: {posts_published}")
    stats_text_parts.append(f"  ▫️ Ошибок публикации: {posts_failed}")
    stats_text_parts.append(f"  ▫️ Отменено пользователями: {posts_cancelled}\n")

    # Шаблоны
    templates_total_count = db.fetchone("SELECT COUNT(*) FROM templates")[0]
    # COMMON_TEMPLATE_USER_ID = 0 (из handlers.templates, но лучше определить его в config или общем месте)
    # Для простоты здесь используем 0 напрямую
    templates_common = db.fetchone("SELECT COUNT(*) FROM templates WHERE user_id = 0")[0]
    templates_personal = db.fetchone("SELECT COUNT(*) FROM templates WHERE user_id != 0")[0]
    stats_text_parts.append(f"<b>Шаблоны:</b>")
    stats_text_parts.append(f"  ▫️ Всего шаблонов: {templates_total_count}")
    stats_text_parts.append(f"  ▫️ Общих шаблонов: {templates_common}")
    stats_text_parts.append(f"  ▫️ Личных шаблонов: {templates_personal}\n")

    # Можно добавить количество активных задач в APScheduler, если это нужно,
    # но это требует доступа к `scheduler.get_jobs()` и их анализа.

    await message.answer("\n".join(stats_text_parts), parse_mode="HTML")


@router.message(Command("list_users"))
async def admin_list_users(message: types.Message, command: CommandObject):
    db = get_db()
    limit = 10  # Значение по умолчанию
    if command.args and command.args.isdigit():
        limit = int(command.args)
        if limit <= 0:
            limit = 10
        if limit > 50:  # Ограничение, чтобы не выводить слишком много
            limit = 50
            await message.answer("ℹ️ Максимальное количество пользователей для вывода ограничено до 50.")

    users_data = db.fetchall(
        """SELECT user_id, username, first_name, is_admin, created_at
           FROM bot_users
           ORDER BY created_at DESC LIMIT ?""",
        (limit,)
    )

    if not users_data:
        await message.answer("👥 Пользователи не найдены в базе данных.")
        return

    response_header = f"👥 <b>Список последних {len(users_data)} зарегистрированных пользователей:</b>\n\n"
    user_lines = []
    for user_id, username, first_name, is_admin, created_at_iso in users_data:
        uname = f"@{username}" if username else "N/A"
        fname = first_name if first_name else ""
        admin_status = "👑 Admin" if is_admin else "👤 User"
        # Преобразование даты/времени, если нужно, но для простоты оставим ISO
        user_lines.append(
            f"🆔 <code>{user_id}</code> ({escape_html(fname) or uname})\n"
            f"   Статус: {admin_status}\n"
            f"   Зарегистрирован: {escape_html(created_at_iso.split('.')[0])}\n"  # Убираем миллисекунды для краткости
            f"   ---"
        )

    response_text = response_header + "\n".join(user_lines)

    # Разбивка на части, если сообщение слишком длинное
    MAX_MESSAGE_LENGTH = 4096
    if len(response_text) > MAX_MESSAGE_LENGTH:
        current_part = response_header
        for line in user_lines:
            if len(current_part) + len(line) + 1 > MAX_MESSAGE_LENGTH:
                await message.answer(current_part, parse_mode="HTML")
                current_part = ""  # Начинаем новую часть без заголовка
            current_part += line + "\n"
        if current_part.strip():  # Отправляем остаток
            await message.answer(current_part, parse_mode="HTML")
    else:
        await message.answer(response_text, parse_mode="HTML")