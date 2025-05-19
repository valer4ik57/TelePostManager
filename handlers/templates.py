import sqlite3
from aiogram import Router, F, types, Bot
from aiogram.fsm.context import FSMContext
from aiogram.utils.keyboard import InlineKeyboardBuilder
import logging

from loader import get_db
from bot_utils import get_main_keyboard, escape_html
from post_states import TemplateStates
from filters.admin import IsAdmin
from config import SUPER_ADMIN_ID

router = Router()
logger = logging.getLogger(__name__)

COMMON_TEMPLATE_USER_ID = 0

async def get_templates_for_user(user_id: int) -> list:
    db = get_db()
    query = """
            SELECT id, name, user_id \
            FROM templates
            WHERE user_id = ? \
               OR user_id = ?
            ORDER BY user_id ASC, name ASC \
            """
    return db.fetchall(query, (COMMON_TEMPLATE_USER_ID, user_id))


async def check_if_user_is_admin_for_display(user_id: int) -> bool:
    if user_id == SUPER_ADMIN_ID:
        return True
    db = get_db()
    admin_status = db.fetchone("SELECT is_admin FROM bot_users WHERE user_id = ?", (user_id,))
    return bool(admin_status and admin_status[0] == 1)


async def templates_menu_keyboard_for_user(user_id: int, message_id_to_edit: int | None = None):
    templates_list = await get_templates_for_user(user_id)
    user_can_manage_common_templates = await check_if_user_is_admin_for_display(user_id)

    builder = InlineKeyboardBuilder()
    if templates_list:
        for tpl_id, tpl_name, tpl_user_id in templates_list:
            display_name = escape_html(tpl_name)
            is_personal_template = (tpl_user_id == user_id and tpl_user_id != COMMON_TEMPLATE_USER_ID)

            if tpl_user_id == COMMON_TEMPLATE_USER_ID:
                display_name += " (Общий)"

            action_buttons = [
                types.InlineKeyboardButton(text=f"📄 {display_name}", callback_data=f"tpl_view_{tpl_id}")
            ]

            if is_personal_template:
                action_buttons.append(types.InlineKeyboardButton(text="❌", callback_data=f"tpl_delete_ask_{tpl_id}"))

            builder.row(*action_buttons)

    builder.row(types.InlineKeyboardButton(text="➕ Добавить свой шаблон", callback_data="tpl_add_personal"))

    if user_can_manage_common_templates:
        builder.row(types.InlineKeyboardButton(text="👑 Добавить ОБЩИЙ шаблон", callback_data="tpl_add_common"))
        manage_common_callback = f"tpl_manage_common"
        builder.row(
            types.InlineKeyboardButton(text="🗂️ Управление ОБЩИМИ шаблонами", callback_data=manage_common_callback))

    builder.row(types.InlineKeyboardButton(text="ℹ️ О переменных", callback_data="tpl_info_vars")) # Изменил callback_data для ясности
    builder.row(types.InlineKeyboardButton(text="⬅️ Назад в главное меню", callback_data="tpl_back_to_main"))
    return builder.as_markup()


@router.message(F.text == "📚 Шаблоны")
async def templates_menu(message: types.Message, state: FSMContext):
    current_fsm_state = await state.get_state()
    if current_fsm_state and isinstance(current_fsm_state, str) and current_fsm_state.startswith("TemplateStates"):
        await state.clear()
        await message.answer("Состояние создания/редактирования шаблона сброшено.")

    keyboard = await templates_menu_keyboard_for_user(message.from_user.id, message.message_id)
    user_templates_count_query = await get_templates_for_user(message.from_user.id)

    if not user_templates_count_query:
        await message.answer("📭 Шаблоны не найдены (ни общие, ни ваши личные).", reply_markup=keyboard)
    else:
        await message.answer("📚 Шаблоны (общие и ваши личные):", reply_markup=keyboard)


@router.callback_query(F.data == "tpl_back_to_main")
async def tpl_back_to_main_menu_callback(callback: types.CallbackQuery):
    await callback.answer()
    try:
        await callback.message.edit_reply_markup(reply_markup=None)
    except Exception:
        pass
    await callback.message.answer("Главное меню:", reply_markup=get_main_keyboard())


@router.callback_query(F.data == "tpl_info_vars") # Изменен callback_data
async def tpl_info_variables_callback(callback: types.CallbackQuery): # Изменено имя функции
    await callback.answer()
    info_text = (
        "✨ <b>Переменные в шаблонах</b> ✨\n\n"
        "Вы можете создавать свои собственные переменные прямо в тексте шаблона, "
        "чтобы затем заполнять их уникальным содержимым при создании поста.\n\n"
        "<b>Как создать переменную:</b>\n"
        "Используйте формат: <code>{[название_вашей_переменной]}</code>\n"
        "<i>Например:</i> <code>{[Заголовок новости]}</code> или <code>{[Имя клиента]}</code>\n\n"
        "▫️ Название переменной может состоять из букв, цифр, пробелов (внутри названия).\n"
        "▫️ <b>Важно:</b> не используйте символы <code>{</code>, <code>}</code>, <code>[</code>, <code>]</code> внутри самого <u>названия</u> переменной.\n"
        "▫️ При создании поста бот автоматически найдет все такие переменные в выбранном шаблоне "
        "и последовательно запросит у вас значения для каждой из них.\n\n"
        "<b>Пример шаблона:</b>\n"
        "<code>Привет, {[Имя друга]}! Поздравляю с {[Событие]}!</code>\n\n"
        "При использовании этого шаблона бот спросит:\n"
        "1. Введите значение для 'Имя друга':\n"
        "2. Введите значение для 'Событие':\n\n"
        "Это позволяет создавать очень гибкие и персонализированные шаблоны!"
    )
    await callback.message.answer(info_text, parse_mode="HTML")


@router.callback_query(F.data == "tpl_add_personal")
async def add_personal_template_start(callback: types.CallbackQuery, state: FSMContext):
    await callback.answer()
    await callback.message.edit_text(
        "📝 Введите название для вашего нового личного шаблона (например, 'Утренняя новость'):")
    await state.set_state(TemplateStates.AWAITING_NAME)
    await state.update_data(is_creating_common_template=False, original_message_id=callback.message.message_id)


@router.callback_query(F.data == "tpl_add_common", IsAdmin())
async def add_common_template_start_callback(callback: types.CallbackQuery, state: FSMContext):
    await callback.answer()
    await callback.message.edit_text(
        "👑 Режим администратора: Добавление общего шаблона.\n"
        "Введите название для нового ОБЩЕГО шаблона:")
    await state.set_state(TemplateStates.AWAITING_NAME)
    await state.update_data(is_creating_common_template=True, original_message_id=callback.message.message_id)


@router.callback_query(F.data == "tpl_add_common")
async def add_common_template_not_admin(callback: types.CallbackQuery):
    await callback.answer("⛔ У вас нет прав для выполнения этого действия.", show_alert=True)


@router.message(TemplateStates.AWAITING_NAME, F.text)
async def process_template_name(message: types.Message, state: FSMContext):
    db = get_db()
    template_name = message.text.strip()
    data = await state.get_data()
    is_common_being_created = data.get("is_creating_common_template", False)
    target_user_id_for_db = COMMON_TEMPLATE_USER_ID if is_common_being_created else message.from_user.id
    template_type_description = "общего" if is_common_being_created else "вашего личного"

    if not template_name:
        await message.answer("Название шаблона не может быть пустым. Попробуйте еще раз.")
        return

    existing_template = db.fetchone(
        "SELECT id FROM templates WHERE user_id = ? AND name = ?",
        (target_user_id_for_db, template_name)
    )
    if existing_template:
        await message.answer(
            f"❌ Уже существует {template_type_description} шаблон с названием «{escape_html(template_name)}». Придумайте другое название.")
        return

    await state.update_data(template_name=template_name)
    try:
        await message.delete()
    except Exception:
        logger.warning(f"Could not delete message with template name request from user {message.from_user.id}")

    await message.answer(
        f"📄 Теперь отправьте текст для {template_type_description} шаблона «{escape_html(template_name)}».\n"
        "Используйте переменные вида <code>{[название]}</code>, чтобы потом их заполнить. " # Обновлен текст
        "Можно также прикрепить ОДНО фото/видео."
        "\n\n<i>Для отмены введите /cancel или 'отмена'.</i>",
        parse_mode="HTML"
    )
    await state.set_state(TemplateStates.AWAITING_CONTENT)

# ... (остальная часть handlers/templates.py остается такой же, как в твоей версии)
# process_template_content, view_template_callback, delete_... и manage_common_templates_...
# не требуют изменений для этой конкретной задачи унификации переменных.

# ... (код для view_template_callback и далее остается как в твоей версии) ...
@router.message(TemplateStates.AWAITING_CONTENT, F.photo | F.video | F.text)
async def process_template_content(message: types.Message, state: FSMContext):
    data = await state.get_data()
    template_name = data.get("template_name")
    original_message_id = data.get("original_message_id")

    if not template_name:
        logger.error(f"Template name not found in state for user {message.from_user.id} in AWAITING_CONTENT")
        await message.answer("Произошла ошибка (имя шаблона не найдено). Пожалуйста, начните заново.",
                             reply_markup=get_main_keyboard())
        if original_message_id:
            try:
                keyboard_fallback = await templates_menu_keyboard_for_user(message.from_user.id, original_message_id)
                await message.bot.edit_message_text("Ошибка. Возврат в меню шаблонов.", chat_id=message.chat.id,
                                                    message_id=original_message_id, reply_markup=keyboard_fallback)
            except Exception:
                pass
        await state.clear()
        return

    is_common_being_created = data.get("is_creating_common_template", False)
    template_owner_user_id = COMMON_TEMPLATE_USER_ID if is_common_being_created else message.from_user.id
    template_type_description = "Общий" if is_common_being_created else "Ваш личный"

    content_from_user = message.text or message.caption
    media_id = None
    media_type_str = None

    if message.photo:
        media_id = message.photo[-1].file_id
        media_type_str = "photo"
    elif message.video:
        media_id = message.video.file_id
        media_type_str = "video"

    if not content_from_user and not media_id:
        await message.answer("Шаблон должен содержать текст или медиа. Попробуйте еще раз.")
        return

    final_content_for_db = content_from_user if content_from_user is not None else ""
    try:
        await message.delete()
    except Exception:
        logger.warning(f"Could not delete message with template content from user {message.from_user.id}")

    db = get_db()
    try:
        db.execute(
            "INSERT INTO templates (user_id, name, content, media, media_type) VALUES (?, ?, ?, ?, ?)",
            (template_owner_user_id, template_name, final_content_for_db, media_id, media_type_str),
            commit=True
        )
        logger.info(
            f"{template_type_description} template '{template_name}' (owner: {template_owner_user_id}) saved by user {message.from_user.id}")

        await message.answer(f"✅ {template_type_description} шаблон «{escape_html(template_name)}» успешно сохранен!")

        if original_message_id:
            if is_common_being_created:
                await manage_common_templates_menu_logic(message.from_user.id, message.bot, original_message_id,
                                                         message.chat.id)
            else:
                keyboard = await templates_menu_keyboard_for_user(message.from_user.id, original_message_id) # Передаем ID для ред.
                await message.bot.edit_message_text("📚 Шаблоны (общие и ваши личные):",
                                                    chat_id=message.chat.id,
                                                    message_id=original_message_id,
                                                    reply_markup=keyboard)
        else:
            keyboard_fallback = await templates_menu_keyboard_for_user(message.from_user.id)
            await message.answer("📚 Шаблоны (общие и ваши личные):", reply_markup=keyboard_fallback)

    except sqlite3.IntegrityError:
        logger.error(f"IntegrityError on template save (owner {template_owner_user_id}, name {template_name}).")
        await message.answer(f"❌ Шаблон с названием «{escape_html(template_name)}» уже существует для этого типа.")
    except sqlite3.Error as e:
        logger.error(f"DB error saving template (owner {template_owner_user_id}): {e}", exc_info=True)
        await message.answer(f"❌ Ошибка базы данных при сохранении шаблона.")
    finally:
        await state.clear()


@router.callback_query(F.data.startswith("tpl_view_"))
async def view_template_callback(callback: types.CallbackQuery):
    await callback.answer()
    tpl_id_to_view = int(callback.data.split("_")[2])
    current_user_id = callback.from_user.id
    db = get_db()

    template_data = db.fetchone(
        "SELECT name, content, media, media_type, user_id FROM templates WHERE id = ? AND (user_id = ? OR user_id = ?)",
        (tpl_id_to_view, current_user_id, COMMON_TEMPLATE_USER_ID)
    )
    if not template_data:
        logger.warning(
            f"User {current_user_id} tried to view non-existent or non-accessible template ID {tpl_id_to_view}")
        keyboard = await templates_menu_keyboard_for_user(current_user_id, callback.message.message_id)
        await callback.message.edit_text("❌ Шаблон не найден или недоступен.", reply_markup=keyboard)
        return

    name, content, media_file_id, media_type_from_db, tpl_owner_id = template_data
    template_type_str = "(Общий)" if tpl_owner_id == COMMON_TEMPLATE_USER_ID else "(Личный)"

    text_to_send_parts = [f"📄 <b>Шаблон «{escape_html(name)}» {template_type_str}</b>"]
    if content:
        text_to_send_parts.append(f"\n{escape_html(content)}")
    else:
        text_to_send_parts.append("\n[Без текстового содержимого]")

    final_caption_for_media = "\n".join(text_to_send_parts)

    if media_file_id:
        media_info_text = "🖼️ <i>К шаблону прикреплено медиа.</i>"
        try:
            if media_type_from_db == "photo":
                await callback.message.answer_photo(media_file_id,
                                                    caption=f"{final_caption_for_media}\n{media_info_text}",
                                                    parse_mode="HTML")
            elif media_type_from_db == "video":
                await callback.message.answer_video(media_file_id,
                                                    caption=f"{final_caption_for_media}\n{media_info_text}",
                                                    parse_mode="HTML")
            else:
                logger.warning(f"Unknown media_type '{media_type_from_db}' for template ID {tpl_id_to_view}")
                await callback.message.answer(
                    f"{final_caption_for_media}\n{media_info_text}\n(Неизвестный тип медиа ID: {escape_html(str(media_file_id))})",
                    parse_mode="HTML")
        except Exception as e:
            logger.error(f"Error displaying media for template ID {tpl_id_to_view}: {e}", exc_info=True)
            await callback.message.answer(
                f"{final_caption_for_media}\n{media_info_text}\n(Ошибка отображения медиа: {escape_html(str(e))})",
                parse_mode="HTML")
    else:
        await callback.message.answer(final_caption_for_media, parse_mode="HTML")


@router.callback_query(F.data.startswith("tpl_delete_ask_"))
async def delete_personal_template_ask_callback(callback: types.CallbackQuery):
    await callback.answer()
    tpl_id_to_delete = int(callback.data.split("_")[3])
    current_user_id = callback.from_user.id
    db = get_db()

    template_data = db.fetchone(
        "SELECT name FROM templates WHERE id = ? AND user_id = ? AND user_id != ?",
        (tpl_id_to_delete, current_user_id, COMMON_TEMPLATE_USER_ID)
    )

    if not template_data:
        logger.warning(
            f"User {current_user_id} tried to delete non-existent, not owned, or common template ID {tpl_id_to_delete} via personal delete.")
        keyboard = await templates_menu_keyboard_for_user(current_user_id, callback.message.message_id)
        await callback.message.edit_text("❌ Шаблон не найден, это не ваш личный шаблон или он уже удален.",
                                         reply_markup=keyboard)
        return

    template_name = template_data[0]
    builder = InlineKeyboardBuilder()
    builder.row(
        types.InlineKeyboardButton(text="✅ Да, удалить", callback_data=f"tpl_delete_do_{tpl_id_to_delete}"),
        types.InlineKeyboardButton(text="❌ Нет, отмена", callback_data="tpl_delete_personal_cancel")
    )
    await callback.message.edit_text(
        f"❓ Вы уверены, что хотите удалить ваш личный шаблон «{escape_html(template_name)}»?",
        reply_markup=builder.as_markup(), parse_mode="HTML")


@router.callback_query(F.data == "tpl_delete_personal_cancel")
async def delete_personal_template_cancel_callback(callback: types.CallbackQuery):
    await callback.answer("Удаление отменено.")
    keyboard = await templates_menu_keyboard_for_user(callback.from_user.id, callback.message.message_id)
    await callback.message.edit_text("📚 Управление шаблонами:", reply_markup=keyboard)


@router.callback_query(F.data.startswith("tpl_delete_do_"))
async def delete_personal_template_confirm_callback(callback: types.CallbackQuery):
    await callback.answer()
    tpl_id_to_delete = int(callback.data.split("_")[3])
    current_user_id = callback.from_user.id
    db = get_db()

    template_data = db.fetchone(
        "SELECT name FROM templates WHERE id = ? AND user_id = ? AND user_id != ?",
        (tpl_id_to_delete, current_user_id, COMMON_TEMPLATE_USER_ID)
    )

    if not template_data:
        keyboard = await templates_menu_keyboard_for_user(current_user_id, callback.message.message_id)
        await callback.message.edit_text("Шаблон уже удален, не найден или это не ваш личный шаблон.",
                                         reply_markup=keyboard)
        return

    template_name = template_data[0]
    try:
        db.execute(
            "DELETE FROM templates WHERE id = ? AND user_id = ?",
            (tpl_id_to_delete, current_user_id),
            commit=True
        )
        if db.cursor.rowcount > 0:
            logger.info(
                f"User {current_user_id} deleted personal template '{template_name}' (DB ID {tpl_id_to_delete})")
            await callback.answer(f"🗑 Личный шаблон «{escape_html(template_name)}» удален.", show_alert=True)
        else:
            logger.warning(
                f"Personal template (DB ID {tpl_id_to_delete}) not found for user {current_user_id} at delete confirm.")
            await callback.answer("Не удалось удалить личный шаблон.", show_alert=True)

        keyboard = await templates_menu_keyboard_for_user(current_user_id, callback.message.message_id)
        await callback.message.edit_text("📚 Управление шаблонами:", reply_markup=keyboard)
    except sqlite3.Error as e:
        logger.error(f"DB error deleting personal template (DB ID {tpl_id_to_delete}) for user {current_user_id}: {e}",
                     exc_info=True)
        keyboard = await templates_menu_keyboard_for_user(current_user_id, callback.message.message_id)
        await callback.message.edit_text(f"❌ Ошибка при удалении личного шаблона.",
                                         reply_markup=keyboard)


# --- Управление ОБЩИМИ шаблонами (для админа) ---

async def manage_common_templates_menu_logic(user_id: int, bot_instance: Bot, message_id_to_edit: int,
                                             chat_id: int):
    db = get_db()
    common_templates = db.fetchall(
        "SELECT id, name FROM templates WHERE user_id = ? ORDER BY name ASC",
        (COMMON_TEMPLATE_USER_ID,)
    )

    builder = InlineKeyboardBuilder()
    if common_templates:
        for tpl_id, tpl_name in common_templates:
            builder.row(
                types.InlineKeyboardButton(text=f"📄 {escape_html(tpl_name)}", callback_data=f"tpl_view_{tpl_id}"),
                types.InlineKeyboardButton(text="❌ Удал.",
                                           callback_data=f"tpl_delete_common_ask_{tpl_id}:{message_id_to_edit}")
            )

    builder.row(types.InlineKeyboardButton(text="➕ Добавить ОБЩИЙ шаблон", callback_data=f"tpl_add_common"))
    builder.row(types.InlineKeyboardButton(text="⬅️ Назад в основное меню шаблонов",
                                           callback_data=f"tpl_back_to_main_tpl_menu:{message_id_to_edit}"))

    try:
        await bot_instance.edit_message_text(
            text="👑 Управление ОБЩИМИ шаблонами:" + ("\n\n(Общие шаблоны не найдены)" if not common_templates else ""),
            chat_id=chat_id,
            message_id=message_id_to_edit,
            reply_markup=builder.as_markup()
        )
    except Exception as e:
        logger.error(f"Error editing common templates menu for user {user_id}, msg_id {message_id_to_edit}: {e}",
                     exc_info=True)


@router.callback_query(F.data.startswith("tpl_manage_common"), IsAdmin())
async def manage_common_templates_menu_callback(callback: types.CallbackQuery):
    await callback.answer()
    await manage_common_templates_menu_logic(callback.from_user.id, callback.bot, callback.message.message_id,
                                             callback.message.chat.id)


@router.callback_query(F.data.startswith("tpl_back_to_main_tpl_menu:"), IsAdmin())
async def back_to_main_templates_menu_from_common_mgm(callback: types.CallbackQuery):
    await callback.answer()
    message_id_to_edit = int(callback.data.split(":")[1])
    # При возврате в основное меню передаем ID сообщения для его редактирования
    keyboard = await templates_menu_keyboard_for_user(callback.from_user.id, message_id_to_edit)
    try:
        await callback.message.edit_text("📚 Шаблоны (общие и ваши личные):", reply_markup=keyboard)
    except Exception as e:
        logger.warning(f"Could not edit message {message_id_to_edit} back to main templates menu: {e}")
        new_keyboard = await templates_menu_keyboard_for_user(callback.from_user.id)
        await callback.message.answer("📚 Шаблоны (общие и ваши личные):", reply_markup=new_keyboard)


@router.callback_query(F.data.startswith("tpl_delete_common_ask_"), IsAdmin())
async def delete_common_template_ask_callback(callback: types.CallbackQuery):
    await callback.answer()
    parts = callback.data.split(":")
    tpl_id_to_delete = int(parts[0].split("_")[4])
    original_message_id_for_menu = int(parts[1])
    db = get_db()

    template_data = db.fetchone(
        "SELECT name FROM templates WHERE id = ? AND user_id = ?",
        (tpl_id_to_delete, COMMON_TEMPLATE_USER_ID)
    )

    if not template_data:
        logger.warning(
            f"Admin {callback.from_user.id} tried to delete non-existent common template ID {tpl_id_to_delete}")
        await callback.answer("Общий шаблон не найден или уже удален.", show_alert=True)
        await manage_common_templates_menu_logic(callback.from_user.id, callback.bot, original_message_id_for_menu,
                                                 callback.message.chat.id)
        return

    template_name = template_data[0]
    builder = InlineKeyboardBuilder()
    builder.row(
        types.InlineKeyboardButton(text="✅ Да, удалить общий",
                                   callback_data=f"tpl_del_com_do_{tpl_id_to_delete}:{original_message_id_for_menu}"),
        types.InlineKeyboardButton(text="❌ Нет, отмена",
                                   callback_data=f"tpl_del_com_cancel:{original_message_id_for_menu}")
    )
    await callback.message.edit_text(
        f"👑 Вы уверены, что хотите удалить ОБЩИЙ шаблон «{escape_html(template_name)}»?",
        reply_markup=builder.as_markup(), parse_mode="HTML")


@router.callback_query(F.data.startswith("tpl_del_com_cancel:"), IsAdmin())
async def delete_common_template_cancel_callback(callback: types.CallbackQuery):
    await callback.answer("Удаление общего шаблона отменено.")
    original_message_id_for_menu = int(callback.data.split(":")[1])
    await manage_common_templates_menu_logic(callback.from_user.id, callback.bot, original_message_id_for_menu,
                                             callback.message.chat.id)


@router.callback_query(F.data.startswith("tpl_del_com_do_"), IsAdmin())
async def delete_common_template_confirm_callback(callback: types.CallbackQuery):
    await callback.answer()
    parts = callback.data.split(":")
    tpl_id_to_delete = int(parts[0].split("_")[4])
    original_message_id_for_menu = int(parts[1])
    db = get_db()

    template_data = db.fetchone(
        "SELECT name FROM templates WHERE id = ? AND user_id = ?",
        (tpl_id_to_delete, COMMON_TEMPLATE_USER_ID)
    )

    if not template_data:
        await callback.answer("Общий шаблон уже удален или не найден.", show_alert=True)
        await manage_common_templates_menu_logic(callback.from_user.id, callback.bot, original_message_id_for_menu,
                                                 callback.message.chat.id)
        return

    template_name = template_data[0]
    try:
        db.execute(
            "DELETE FROM templates WHERE id = ? AND user_id = ?",
            (tpl_id_to_delete, COMMON_TEMPLATE_USER_ID),
            commit=True
        )
        if db.cursor.rowcount > 0:
            logger.info(
                f"Admin {callback.from_user.id} deleted COMMON template '{template_name}' (DB ID {tpl_id_to_delete})")
            await callback.answer(f"🗑 Общий шаблон «{escape_html(template_name)}» удален.", show_alert=True)
        else:
            logger.warning(
                f"COMMON template (DB ID {tpl_id_to_delete}) not found at delete confirm by admin {callback.from_user.id}.")
            await callback.answer("Не удалось удалить общий шаблон.", show_alert=True)

    except sqlite3.Error as e:
        logger.error(
            f"DB error deleting COMMON template (DB ID {tpl_id_to_delete}) by admin {callback.from_user.id}: {e}",
            exc_info=True)
        await callback.answer(f"❌ Ошибка при удалении общего шаблона.", show_alert=True)
    finally:
        await manage_common_templates_menu_logic(callback.from_user.id, callback.bot, original_message_id_for_menu,
                                                 callback.message.chat.id)