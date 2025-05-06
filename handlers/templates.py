# handlers/templates.py
import sqlite3
from aiogram import Router, F, types
from aiogram.fsm.context import FSMContext
from aiogram.utils.keyboard import InlineKeyboardBuilder
import logging

from loader import get_db
from bot_utils import get_main_keyboard, escape_html
from post_states import TemplateStates
from filters.admin import IsAdmin  # Импортируем фильтр IsAdmin

router = Router()
logger = logging.getLogger(__name__)

COMMON_TEMPLATE_USER_ID = 0  # ID для общих/системных шаблонов

AVAILABLE_TEMPLATE_VARIABLES = {
    "{дата}": "Текущая дата (ДД.ММ.ГГГГ)",
    "{время}": "Текущее время (ЧЧ:ММ)",
    "{текст_новости}": "Основной текст, который вводит пользователь",
    "{автор}": "Полное имя пользователя, создающего пост",
}


async def get_templates_for_user(user_id: int) -> list:
    db = get_db()
    query = """
        SELECT id, name, user_id FROM templates 
        WHERE user_id = ? OR user_id = ? 
        ORDER BY user_id ASC, name ASC 
    """
    return db.fetchall(query, (COMMON_TEMPLATE_USER_ID, user_id))


async def check_if_user_is_admin(user_id: int) -> bool:
    """Вспомогательная функция для проверки статуса администратора."""
    db = get_db()
    admin_status = db.fetchone("SELECT is_admin FROM bot_users WHERE user_id = ?", (user_id,))
    return bool(admin_status and admin_status[0] == 1)


async def templates_menu_keyboard_for_user(user_id: int):
    templates_list = await get_templates_for_user(user_id)
    user_is_admin = await check_if_user_is_admin(user_id)  # Проверяем, админ ли пользователь

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

            # Пользователь может удалять только свои личные шаблоны
            if is_personal_template:
                # action_buttons.append(types.InlineKeyboardButton(text="✏️", callback_data=f"tpl_edit_{tpl_id}")) # TODO: Редактирование
                action_buttons.append(types.InlineKeyboardButton(text="❌", callback_data=f"tpl_delete_ask_{tpl_id}"))
            # Админ может удалять и общие шаблоны (если это нужно, можно добавить условие)
            # elif user_is_admin and tpl_user_id == COMMON_TEMPLATE_USER_ID:
            #     action_buttons.append(types.InlineKeyboardButton(text="✏️ (Общий)", callback_data=f"tpl_edit_common_{tpl_id}"))
            #     action_buttons.append(types.InlineKeyboardButton(text="❌ (Общий)", callback_data=f"tpl_delete_common_ask_{tpl_id}"))

            builder.row(*action_buttons)

    # Кнопка для добавления ЛИЧНОГО шаблона (доступна всем)
    builder.row(types.InlineKeyboardButton(text="➕ Добавить свой шаблон", callback_data="tpl_add_personal"))

    # Кнопка для добавления ОБЩЕГО шаблона (доступна ТОЛЬКО АДМИНУ)
    if user_is_admin:
        builder.row(types.InlineKeyboardButton(text="👑 Добавить ОБЩИЙ шаблон", callback_data="tpl_add_common"))
        # Можно добавить и другие админские кнопки, например, для управления общими шаблонами

    builder.row(types.InlineKeyboardButton(text="📋 Показать доступные переменные", callback_data="tpl_show_vars"))
    builder.row(types.InlineKeyboardButton(text="⬅️ Назад в главное меню", callback_data="tpl_back_to_main"))
    return builder.as_markup()


@router.message(F.text == "📚 Шаблоны")
async def templates_menu(message: types.Message, state: FSMContext):
    current_fsm_state = await state.get_state()
    if current_fsm_state and isinstance(current_fsm_state, str) and current_fsm_state.startswith("TemplateStates"):
        await state.clear()
        await message.answer("Состояние создания/редактирования шаблона сброшено.")

    keyboard = await templates_menu_keyboard_for_user(message.from_user.id)
    user_templates = await get_templates_for_user(message.from_user.id)  # Повторный вызов для текста сообщения

    if not user_templates:  # Если нет ни общих, ни личных
        await message.answer("📭 Шаблоны не найдены (ни общие, ни ваши личные).", reply_markup=keyboard)
    else:
        await message.answer("📚 Шаблоны (общие и ваши личные):", reply_markup=keyboard)


@router.callback_query(F.data == "tpl_back_to_main")
async def tpl_back_to_main_menu_callback(callback: types.CallbackQuery):
    await callback.answer()
    try:
        await callback.message.edit_reply_markup(reply_markup=None)
    except:
        pass
    await callback.message.answer("Главное меню:", reply_markup=get_main_keyboard())


@router.callback_query(F.data == "tpl_show_vars")
async def show_template_variables_callback(callback: types.CallbackQuery):
    # ... (код без изменений) ...
    await callback.answer()
    variables_text_parts = ["📌 <b>Доступные переменные для использования в шаблонах:</b>\n"]
    for var, desc in AVAILABLE_TEMPLATE_VARIABLES.items():
        variables_text_parts.append(f"<code>{escape_html(var)}</code> — {escape_html(desc)}")
    variables_text_parts.append(
        "\nВы можете использовать их в тексте шаблона, и они будут автоматически заменены при создании поста.")
    await callback.message.answer("\n".join(variables_text_parts), parse_mode="HTML")


# Начало добавления ЛИЧНОГО шаблона (для обычных пользователей)
@router.callback_query(F.data == "tpl_add_personal")
async def add_personal_template_start(callback: types.CallbackQuery, state: FSMContext):
    await callback.answer()
    await callback.message.edit_text(
        "📝 Введите название для вашего нового личного шаблона (например, 'Утренняя новость'):")
    await state.set_state(TemplateStates.AWAITING_NAME)
    await state.update_data(is_creating_common_template=False)  # Явно указываем, что это НЕ общий


# Начало добавления ОБЩЕГО шаблона (ТОЛЬКО ДЛЯ АДМИНА)
@router.callback_query(F.data == "tpl_add_common", IsAdmin())  # Защищаем фильтром IsAdmin
async def add_common_template_start_callback(callback: types.CallbackQuery, state: FSMContext):
    await callback.answer()
    await callback.message.edit_text("👑 Режим администратора: Добавление общего шаблона.\n"
                                     "Введите название для нового ОБЩЕГО шаблона:")
    await state.set_state(TemplateStates.AWAITING_NAME)
    await state.update_data(is_creating_common_template=True)  # Устанавливаем флаг


# Если не админ пытается нажать кнопку tpl_add_common (фильтр IsAdmin не пропустит, но на всякий случай)
@router.callback_query(F.data == "tpl_add_common")
async def add_common_template_not_admin(callback: types.CallbackQuery):
    await callback.answer("У вас нет прав для выполнения этого действия.", show_alert=True)


# Этапы AWAITING_NAME и AWAITING_CONTENT теперь должны учитывать флаг is_creating_common_template
@router.message(TemplateStates.AWAITING_NAME, F.text)  # Убрал F.text, т.к. message.text и так есть
async def process_template_name(message: types.Message, state: FSMContext):
    db = get_db()
    template_name = message.text.strip()

    data = await state.get_data()
    is_common_being_created = data.get("is_creating_common_template", False)

    # Определяем, для какого user_id проверять уникальность и сохранять
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

    await state.update_data(template_name=template_name)  # is_creating_common_template уже в state
    await message.answer(
        f"📄 Теперь отправьте текст для {template_type_description} шаблона «{escape_html(template_name)}».\n"
        "Вы можете использовать переменные. Можно прикрепить ОДНО фото/видео."
    )
    await state.set_state(TemplateStates.AWAITING_CONTENT)


@router.message(TemplateStates.AWAITING_CONTENT, F.photo | F.video | F.text)
async def process_template_content(message: types.Message, state: FSMContext):
    data = await state.get_data()
    template_name = data.get("template_name")
    if not template_name:  # На случай если состояние "потерялось"
        logger.error(f"Template name not found in state for user {message.from_user.id} in AWAITING_CONTENT")
        await message.answer("Произошла ошибка, название шаблона не найдено. Пожалуйста, начните заново.",
                             reply_markup=get_main_keyboard())
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

    db = get_db()
    try:
        db.execute(
            "INSERT INTO templates (user_id, name, content, media, media_type) VALUES (?, ?, ?, ?, ?)",
            (template_owner_user_id, template_name, final_content_for_db, media_id, media_type_str),
            commit=True
        )
        logger.info(
            f"{template_type_description} template '{template_name}' (owner: {template_owner_user_id}) saved by user {message.from_user.id}")
        await message.answer(f"✅ {template_type_description} шаблон «{escape_html(template_name)}» успешно сохранен!",
                             reply_markup=get_main_keyboard())
    except sqlite3.IntegrityError:
        logger.error(
            f"IntegrityError on template save (owner {template_owner_user_id}, name {template_name}). Should be caught earlier.")
        await message.answer(
            f"❌ Шаблон с названием «{escape_html(template_name)}» уже существует для этого типа (ошибка).")
    except sqlite3.Error as e:
        logger.error(f"DB error saving template (owner {template_owner_user_id}): {e}", exc_info=True)
        await message.answer(f"❌ Ошибка базы данных при сохранении шаблона.")
    finally:
        await state.clear()


# Просмотр шаблона (остается как было, но учитывает COMMON_TEMPLATE_USER_ID)
@router.callback_query(F.data.startswith("tpl_view_"))
async def view_template_callback(callback: types.CallbackQuery):
    # ... (код без изменений, он уже должен корректно обрабатывать общие и личные) ...
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
        await callback.message.edit_text("❌ Шаблон не найден или недоступен.",
                                         reply_markup=await templates_menu_keyboard_for_user(current_user_id))
        return

    name, content, media_file_id, media_type_from_db, tpl_owner_id = template_data
    template_type_str = "(Общий)" if tpl_owner_id == COMMON_TEMPLATE_USER_ID else "(Личный)"

    text_to_send_parts = [f"📄 <b>Шаблон «{escape_html(name)}» {template_type_str}</b>"]
    if content:
        text_to_send_parts.append(f"\n{escape_html(content)}")
    else:
        text_to_send_parts.append("\n[Без текстового содержимого]")
    final_caption_for_media = "\n".join(text_to_send_parts)

    try:  # Обернем edit_text в try-except на случай если сообщение уже удалено
        await callback.message.edit_text(f"Просмотр шаблона «{escape_html(name)}»...", reply_markup=None)
    except Exception as e_edit:
        logger.info(f"Could not edit message before viewing template: {e_edit}")

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
                logger.warning(
                    f"Unknown media_type '{media_type_from_db}' for template ID {tpl_id_to_view} with media_id {media_file_id}")
                await callback.message.answer(
                    f"{final_caption_for_media}\n{media_info_text}\n(Не удалось точно определить тип медиа ID: {escape_html(media_file_id)})",
                    parse_mode="HTML")
        except Exception as e:
            logger.error(f"Error displaying media for template ID {tpl_id_to_view}: {e}", exc_info=True)
            await callback.message.answer(
                f"{final_caption_for_media}\n{media_info_text}\n(Ошибка отображения медиа: {escape_html(str(e))})",
                parse_mode="HTML")
    else:
        await callback.message.answer(final_caption_for_media, parse_mode="HTML")

    await callback.message.answer("📚 Управление шаблонами:",
                                  reply_markup=await templates_menu_keyboard_for_user(current_user_id))


# Удаление ЛИЧНОГО шаблона (остается как было)
@router.callback_query(F.data.startswith("tpl_delete_ask_"))
async def delete_template_ask_callback(callback: types.CallbackQuery):
    # ... (код без изменений, он уже проверяет, что user_id совпадает) ...
    await callback.answer()
    tpl_id_to_delete = int(callback.data.split("_")[3])
    current_user_id = callback.from_user.id
    db = get_db()

    template_data = db.fetchone(
        "SELECT name FROM templates WHERE id = ? AND user_id = ?",
        (tpl_id_to_delete, current_user_id)
    )

    if not template_data:
        logger.warning(
            f"User {current_user_id} tried to delete non-existent or not owned template ID {tpl_id_to_delete}")
        await callback.message.edit_text("❌ Шаблон не найден или это не ваш личный шаблон.",
                                         reply_markup=await templates_menu_keyboard_for_user(current_user_id))
        return

    template_name = template_data[0]
    builder = InlineKeyboardBuilder()
    builder.row(
        types.InlineKeyboardButton(text="✅ Да, удалить", callback_data=f"tpl_delete_do_{tpl_id_to_delete}"),
        types.InlineKeyboardButton(text="❌ Нет, отмена", callback_data="tpl_delete_cancel")
    )
    await callback.message.edit_text(
        f"❓ Вы уверены, что хотите удалить ваш личный шаблон «{escape_html(template_name)}»?",
        reply_markup=builder.as_markup(), parse_mode="HTML")


@router.callback_query(F.data == "tpl_delete_cancel")
async def delete_template_cancel_callback(callback: types.CallbackQuery):
    # ... (код без изменений) ...
    await callback.answer("Удаление отменено.")
    await callback.message.edit_text("📚 Управление шаблонами:",
                                     reply_markup=await templates_menu_keyboard_for_user(callback.from_user.id))


@router.callback_query(F.data.startswith("tpl_delete_do_"))
async def delete_template_confirm_callback(callback: types.CallbackQuery):
    # ... (код без изменений) ...
    await callback.answer()
    tpl_id_to_delete = int(callback.data.split("_")[3])
    current_user_id = callback.from_user.id
    db = get_db()

    template_data = db.fetchone(
        "SELECT name FROM templates WHERE id = ? AND user_id = ?",
        (tpl_id_to_delete, current_user_id)
    )

    if not template_data:
        await callback.message.edit_text("Шаблон уже удален или не найден.",
                                         reply_markup=await templates_menu_keyboard_for_user(current_user_id))
        return

    template_name = template_data[0]
    try:
        db.execute(
            "DELETE FROM templates WHERE id = ? AND user_id = ?",
            (tpl_id_to_delete, current_user_id),
            commit=True
        )
        if db.cursor.rowcount > 0:
            logger.info(f"User {current_user_id} deleted template '{template_name}' (DB ID {tpl_id_to_delete})")
            await callback.answer(f"🗑 Шаблон «{escape_html(template_name)}» удален.", show_alert=True)
        else:
            logger.warning(
                f"Template (DB ID {tpl_id_to_delete}) not found for user {current_user_id} at delete confirm.")
            await callback.answer("Не удалось удалить шаблон.", show_alert=True)

        await callback.message.edit_text("📚 Управление шаблонами:",
                                         reply_markup=await templates_menu_keyboard_for_user(current_user_id))
    except sqlite3.Error as e:
        logger.error(f"DB error deleting template (DB ID {tpl_id_to_delete}) for user {current_user_id}: {e}",
                     exc_info=True)
        await callback.message.edit_text(f"❌ Ошибка при удалении шаблона.",
                                         reply_markup=await templates_menu_keyboard_for_user(current_user_id))

# TODO: Админские функции для управления ОБЩИМИ шаблонами (удаление, редактирование)
# Например, tpl_delete_common_ask_ID, tpl_edit_common_ID, защищенные IsAdmin()