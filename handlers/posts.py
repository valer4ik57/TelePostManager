import logging
import re
from datetime import datetime, timedelta
from aiogram import Router, F, types, Bot
from aiogram.filters import Command
from aiogram.fsm.context import FSMContext
from aiogram.utils.keyboard import InlineKeyboardBuilder
import sqlite3

from loader import get_db, scheduler, content_filter
from bot_utils import get_main_keyboard, get_channels_keyboard, notify_user, notify_post_published, escape_html
from post_states import PostCreation
from services.scheduler import add_scheduled_job

router = Router()
logger = logging.getLogger(__name__)

# Регулярное выражение для поиска переменных вида {[имя]}
CUSTOM_VAR_REGEX = re.compile(r"{\[([^\]\[{}]+)\]}")


# Автоматические переменные полностью убираем из этой логики.
# Пользователь должен сам определить {[Автор]} или {[Дата]} в шаблоне, если они ему нужны.

@router.message(Command("new_post"))
@router.message(F.text == "📝 Создать пост")
async def start_post_creation(message: types.Message, state: FSMContext):
    db = get_db()
    current_user_id = message.from_user.id

    channels_count_data = db.fetchone(
        "SELECT COUNT(*) FROM channels WHERE user_id = ?", (current_user_id,)
    )
    channels_count = channels_count_data[0] if channels_count_data else 0

    if channels_count == 0:
        await message.answer(
            "❌ Сначала вам нужно добавить хотя бы один ваш канал.\n"
            "Нажмите «➕ Добавить канал» в главном меню.",
            reply_markup=get_main_keyboard()
        )
        return

    templates_data = db.fetchall(
        "SELECT id, name, user_id FROM templates WHERE user_id = 0 OR user_id = ? ORDER BY user_id ASC, name ASC",
        (current_user_id,)
    )

    builder = InlineKeyboardBuilder()
    if templates_data:
        for tpl_id, tpl_name, tpl_user_id in templates_data:
            display_name = escape_html(tpl_name)
            if tpl_user_id == 0:
                display_name += " (Общий)"
            builder.row(types.InlineKeyboardButton(text=f"📄 {display_name}", callback_data=f"post_tpl_use_{tpl_id}"))
        builder.row(types.InlineKeyboardButton(text="📝 Без шаблона / Ввести вручную", callback_data="post_tpl_skip"))

        # Удаляем сообщение с главным меню, если оно было от кнопки
        if message.reply_markup and message.reply_markup.resize_keyboard:
            try:
                await message.delete()  # Пытаемся удалить, если это было сообщение от кнопки меню
            except:
                pass  # Если не вышло (например, это /new_post), то не страшно
            await message.answer("✨ Выберите шаблон для поста или создайте пост вручную:",
                                 reply_markup=builder.as_markup())
        else:  # Если это была команда /new_post, то просто отвечаем
            await message.answer("✨ Выберите шаблон для поста или создайте пост вручную:",
                                 reply_markup=builder.as_markup())

        await state.set_state(PostCreation.SELECT_TEMPLATE)
    else:
        await message.answer("Шаблоны не найдены. Вы будете создавать пост вручную.")
        channels_kb_markup = await get_channels_keyboard(user_id=current_user_id)
        if not channels_kb_markup.inline_keyboard:
            await message.answer("❌ Нет доступных каналов для публикации у вас. Сначала добавьте их.",
                                 reply_markup=get_main_keyboard())
            await state.clear()
            return
        await message.answer("📌 В какой из ваших каналов будем публиковать?", reply_markup=channels_kb_markup)
        await state.set_state(PostCreation.SELECT_CHANNEL)
        await state.update_data(template_id=None, raw_template_content=None, template_media_id=None,
                                template_media_type=None,
                                variables_values={})  # variables_values вместо custom_vars_values


@router.callback_query(F.data.startswith("post_tpl_use_"), PostCreation.SELECT_TEMPLATE)
async def process_template_selection(callback: types.CallbackQuery, state: FSMContext):
    await callback.answer()
    template_id = int(callback.data.split("_")[3])
    current_user_id = callback.from_user.id
    db = get_db()

    template_data_row = db.fetchone(
        "SELECT name, content, media, media_type FROM templates WHERE id = ? AND (user_id = 0 OR user_id = ?)",
        (template_id, current_user_id)
    )

    if not template_data_row:
        await callback.message.edit_text("❌ Выбранный шаблон не найден или недоступен. Попробуйте еще раз.")
        return

    tpl_name, tpl_content, tpl_media_id, tpl_media_type = template_data_row

    found_variables = list(dict.fromkeys(CUSTOM_VAR_REGEX.findall(tpl_content or "")))

    await state.update_data(
        original_message_id=callback.message.message_id,  # Сохраняем ID сообщения с выбором шаблона
        template_id=template_id,
        template_name=tpl_name,
        raw_template_content=tpl_content,
        template_media_id=tpl_media_id,
        template_media_type=tpl_media_type,
        variables_to_fill=found_variables,
        current_variable_index=0,
        variables_values={}
    )

    if found_variables:
        next_var_name = found_variables[0]
        await callback.message.edit_text(
            f"Шаблон «{escape_html(tpl_name)}» выбран.\n"
            f"📝 Введите значение для переменной <code>{escape_html(next_var_name)}</code>:",
            parse_mode="HTML"
        )
        await state.set_state(PostCreation.FILL_CUSTOM_VARIABLES)
    else:
        await callback.message.edit_text(
            f"✨ Шаблон «{escape_html(tpl_name)}» выбран. Переменных для заполнения нет.")

        channels_kb_markup = await get_channels_keyboard(user_id=current_user_id)
        if not channels_kb_markup.inline_keyboard:
            # Это сообщение будет новым, т.к. предыдущее отредактировано
            await callback.message.answer("❌ У вас нет доступных каналов. Сначала добавьте их.",
                                          reply_markup=get_main_keyboard())
            await state.clear()
            return
        # Это сообщение будет новым
        await callback.message.answer("📌 В какой из ваших каналов будем публиковать?", reply_markup=channels_kb_markup)
        await state.set_state(PostCreation.SELECT_CHANNEL)


@router.callback_query(F.data == "post_tpl_skip", PostCreation.SELECT_TEMPLATE)
async def process_no_template(callback: types.CallbackQuery, state: FSMContext):
    await callback.answer()
    current_user_id = callback.from_user.id
    await state.update_data(
        original_message_id=callback.message.message_id,
        template_id=None, raw_template_content=None, template_media_id=None,
        template_media_type=None, variables_values={}
    )

    channels_kb_markup = await get_channels_keyboard(user_id=current_user_id)
    if not channels_kb_markup.inline_keyboard:
        await callback.message.answer("❌ У вас нет доступных каналов. Сначала добавьте их.",
                                      reply_markup=get_main_keyboard())
        await state.clear()
        return
    await callback.message.edit_text("📌 Шаблон не используется. В какой из ваших каналов будем публиковать?",
                                     reply_markup=channels_kb_markup)
    await state.set_state(PostCreation.SELECT_CHANNEL)


@router.message(PostCreation.FILL_CUSTOM_VARIABLES, F.text)
async def process_fill_custom_variable(message: types.Message, state: FSMContext):
    user_input_value = message.text
    # current_user_id = message.from_user.id # Не используется здесь напрямую

    fsm_data = await state.get_data()
    variables_to_fill = fsm_data.get('variables_to_fill', [])
    current_index = fsm_data.get('current_variable_index', 0)

    if current_index >= len(variables_to_fill):  # На всякий случай, если состояние не сменилось
        logger.warning(f"User {message.from_user.id} in FILL_CUSTOM_VARIABLES, but index out of bounds.")
        await message.answer("Произошла ошибка с переменными. Пожалуйста, начните создание поста заново с /cancel.",
                             reply_markup=get_main_keyboard())
        await state.clear()
        return

    var_name_being_filled = variables_to_fill[current_index]

    found_banned_words = content_filter.check_text(user_input_value)
    if found_banned_words:
        await message.answer(
            f"❌ В значении для переменной <code>{escape_html(var_name_being_filled)}</code> "
            f"обнаружены запрещенные слова:\n"
            f"<code>{escape_html(', '.join(found_banned_words))}</code>\n\n"
            f"Пожалуйста, введите другое значение для <code>{escape_html(var_name_being_filled)}</code>:",
            parse_mode="HTML"
        )
        return

    variables_values = fsm_data.get('variables_values', {})
    variables_values[var_name_being_filled] = user_input_value

    current_index += 1
    await state.update_data(variables_values=variables_values, current_variable_index=current_index)

    # Удаляем сообщение пользователя с введенным значением
    try:
        await message.delete()
    except:
        pass

    if current_index < len(variables_to_fill):
        next_var_name = variables_to_fill[current_index]
        # Редактируем предыдущее сообщение бота с запросом переменной
        original_bot_message_id = fsm_data.get("original_message_id")  # Это ID сообщения с выбором шаблона/пропуском
        # или ID предыдущего запроса переменной, если мы будем его сохранять
        # Чтобы редактировать сообщение с запросом переменной, нужно его ID передавать/сохранять
        # Пока будем отправлять новое сообщение для каждого запроса переменной, а старое удалять (если это сообщение пользователя)
        # Сообщение бота с предыдущим запросом останется, если мы его не удалим или не отредактируем.
        # Для лучшего UX, лучше редактировать.

        # Пока простой вариант: отправляем новое сообщение
        await message.answer(  # Отправляем новое
            f"✅ Значение для '{escape_html(var_name_being_filled)}' принято.\n"
            f"📝 Введите значение для переменной <code>{escape_html(next_var_name)}</code>:",
            parse_mode="HTML"
        )
    else:
        # Все переменные заполнены, удаляем последнее сообщение бота с запросом
        # (если бы мы его сохраняли)
        await message.answer("✅ Все переменные шаблона заполнены.")

        channels_kb_markup = await get_channels_keyboard(user_id=message.from_user.id)
        if not channels_kb_markup.inline_keyboard:
            await message.answer("❌ У вас нет доступных каналов. Сначала добавьте их.",
                                 reply_markup=get_main_keyboard())
            await state.clear()
            return
        await message.answer("📌 В какой из ваших каналов будем публиковать?", reply_markup=channels_kb_markup)
        await state.set_state(PostCreation.SELECT_CHANNEL)


@router.callback_query(F.data.startswith("channel_"), PostCreation.SELECT_CHANNEL)
async def process_channel_selection(callback: types.CallbackQuery, state: FSMContext):
    await callback.answer()
    selected_channel_telegram_id = int(callback.data.split("_")[1])
    current_user_id = callback.from_user.id
    db = get_db()

    channel_data_row = db.fetchone(
        "SELECT title FROM channels WHERE channel_id = ? AND user_id = ?",
        (selected_channel_telegram_id, current_user_id)
    )

    if not channel_data_row:
        # Редактируем сообщение с выбором канала
        await callback.message.edit_text(
            "❌ Выбранный канал не найден в вашем списке или недоступен. Попробуйте еще раз.")
        return

    channel_title = channel_data_row[0]
    escaped_channel_title = escape_html(channel_title)
    await state.update_data(
        selected_channel_id=selected_channel_telegram_id,
        selected_channel_title=channel_title
    )

    fsm_data = await state.get_data()
    final_post_text = ""  # Будет сформирован здесь

    if fsm_data.get('template_id') is not None:
        raw_template_content = fsm_data.get('raw_template_content', '')
        variables_values = fsm_data.get('variables_values', {})

        processed_text = raw_template_content
        for var_name, var_value in variables_values.items():
            # Пользовательский ввод для переменных уже проверен на banned_words и должен быть безопасен
            # Экранировать здесь var_value не нужно, если мы хотим, чтобы пользователь мог вставлять HTML в переменные
            # Но если мы хотим обезопасить вывод, то лучше var_value экранировать.
            # Пока оставим без экранирования var_value, предполагая, что пользователь знает, что делает,
            # или мы полагаемся на проверку content_filter для var_value.
            processed_text = processed_text.replace(f"{{[{var_name}]}}", var_value)
            # Убрал escape_html(var_value) для возможности HTML в переменных

        final_post_text = processed_text

        # Проверка итогового текста на запрещенные слова
        found_banned_final = content_filter.check_text(final_post_text)
        if found_banned_final:
            await callback.message.edit_text(  # Редактируем сообщение с выбором канала
                f"❌ В тексте, сгенерированном из шаблона «{escape_html(fsm_data.get('template_name'))}» "
                f"после подстановки ваших значений, обнаружены запрещенные слова:\n"
                f"<code>{escape_html(', '.join(found_banned_final))}</code>\n\n"
                f"Пожалуйста, начните создание поста заново.",
                reply_markup=get_main_keyboard(), parse_mode="HTML"
            )
            await state.clear()
            return

        await state.update_data(final_post_content=final_post_text)

        msg_text_after_channel_select = f"✅ Канал «{escaped_channel_title}» выбран.\n"
        if fsm_data.get('template_media_id'):
            await state.update_data(
                final_post_media_id=fsm_data.get('template_media_id'),
                final_post_media_type=fsm_data.get('template_media_type')
            )
            msg_text_after_channel_select += "Будет использован текст (с вашими данными) и медиа из шаблона.\n"
            msg_text_after_channel_select += "⏰ Введите время публикации (ДД.ММ.ГГГГ ЧЧ:ММ или 'сейчас'):"
            await state.set_state(PostCreation.SCHEDULE)
        else:
            msg_text_after_channel_select += "Будет использован текст из шаблона (с вашими данными).\n"
            msg_text_after_channel_select += "📎 Хотите добавить фото/видео к этому посту? Отправьте его или нажмите /skip_media."
            await state.set_state(PostCreation.MEDIA)

        # Редактируем сообщение с выбором канала
        await callback.message.edit_text(msg_text_after_channel_select, parse_mode="HTML",
                                         reply_markup=None)  # Убираем кнопки выбора канала

    else:  # Если шаблон НЕ использовался (ручной ввод)
        # Редактируем сообщение с выбором канала
        await callback.message.edit_text(f"✅ Канал «{escaped_channel_title}» выбран.\n"
                                         "📝 Теперь введите текст для вашего поста:",
                                         parse_mode="HTML", reply_markup=None)  # Убираем кнопки выбора канала
        await state.set_state(PostCreation.CONTENT)


@router.message(PostCreation.CONTENT, F.text)
async def process_post_content(message: types.Message, state: FSMContext):
    post_text = message.text
    # Удаляем сообщение пользователя с текстом поста
    try:
        await message.delete()
    except:
        pass

    found_banned_words = content_filter.check_text(post_text)
    if found_banned_words:
        await message.answer(  # Отправляем новое сообщение
            f"❌ В вашем тексте обнаружены запрещенные слова:\n"
            f"<code>{escape_html(', '.join(found_banned_words))}</code>\n\n"
            f"Пожалуйста, исправьте текст и отправьте его снова (или /cancel).",  # Добавил /cancel
            parse_mode="HTML"
        )
        return  # Остаемся в состоянии CONTENT, ждем новый ввод

    await state.update_data(final_post_content=post_text)  # Здесь нет авто-переменных
    await message.answer("📎 Текст принят. Хотите добавить фото/видео? Отправьте его или нажмите /skip_media.")
    await state.set_state(PostCreation.MEDIA)


@router.message(PostCreation.MEDIA, F.photo | F.video)
async def process_post_media(message: types.Message, state: FSMContext):
    media_id = None
    media_type = None
    if message.photo:
        media_id = message.photo[-1].file_id
        media_type = "photo"
    elif message.video:
        media_id = message.video.file_id
        media_type = "video"

    if not media_id:
        await message.answer("❌ Не удалось распознать медиа. Попробуйте еще раз или /skip_media.")
        return

    # Удаляем сообщение пользователя с медиа
    try:
        await message.delete()
    except:
        pass

    await state.update_data(final_post_media_id=media_id, final_post_media_type=media_type)
    await message.answer("✅ Медиа добавлено.\n"
                         "⏰ Введите время публикации (формат: ДД.ММ.ГГГГ ЧЧ:ММ, или напишите 'сейчас'):")
    await state.set_state(PostCreation.SCHEDULE)


@router.message(PostCreation.MEDIA, Command("skip_media"))
async def process_skip_media(message: types.Message, state: FSMContext):
    # Удаляем команду /skip_media
    try:
        await message.delete()
    except:
        pass
    await state.update_data(final_post_media_id=None, final_post_media_type=None)
    await message.answer("Хорошо, пост будет без медиа.\n"
                         "⏰ Введите время публикации (формат: ДД.ММ.ГГГГ ЧЧ:ММ, или напишите 'сейчас'):")
    await state.set_state(PostCreation.SCHEDULE)


@router.message(PostCreation.SCHEDULE, F.text)
async def process_schedule_time(message: types.Message, state: FSMContext):
    time_str = message.text.strip().lower()
    # Удаляем сообщение пользователя со временем
    try:
        await message.delete()
    except:
        pass

    publish_time_dt: datetime
    if time_str == "сейчас":
        publish_time_dt = datetime.now()
    else:
        try:
            publish_time_dt = datetime.strptime(time_str, "%d.%m.%Y %H:%M")
            if publish_time_dt < datetime.now() - timedelta(minutes=1):
                await message.answer("❌ Указанное время уже прошло. Введите корректное будущее время или 'сейчас'.")
                return
        except ValueError:
            await message.answer("❌ Неверный формат времени. Используйте ДД.ММ.ГГГГ ЧЧ:ММ или 'сейчас'.")
            return

    await state.update_data(publish_time_iso=publish_time_dt.isoformat())
    current_data = await state.get_data()

    # Текст поста УЖЕ должен быть полностью сформирован на предыдущих этапах
    # (либо из шаблона с подстановкой, либо ручной ввод)
    text_for_preview = current_data.get('final_post_content', "[Нет текста]")

    # Финальная проверка на запрещенные слова еще раз (на всякий случай, если что-то изменилось)
    found_banned_preview = content_filter.check_text(text_for_preview)
    if found_banned_preview:
        await message.answer(
            f"❌ В итоговом тексте поста обнаружены запрещенные слова:\n"
            f"<code>{escape_html(', '.join(found_banned_preview))}</code>\n\n"
            f"Пожалуйста, начните создание поста заново.",
            reply_markup=get_main_keyboard(), parse_mode="HTML"
        )
        await state.clear()
        return

    channel_title_for_preview = escape_html(current_data.get('selected_channel_title', "Неизвестный канал"))
    publish_time_str_for_preview = escape_html(publish_time_dt.strftime('%d.%m.%Y %H:%M'))
    final_media_id = current_data.get('final_post_media_id')
    final_media_type = current_data.get('final_post_media_type')

    preview_caption_parts = [
        f"✨ <b>ПРЕДПРОСМОТР ПОСТА</b> ✨\n",
        f"📢 <b>Канал:</b> {channel_title_for_preview}",
        f"⏰ <b>Время публикации:</b> {publish_time_str_for_preview}",
        f"\n📝 <b>Текст поста:</b>\n{text_for_preview}"
    ]
    preview_caption = "\n".join(preview_caption_parts)

    confirm_kb = InlineKeyboardBuilder()
    confirm_kb.row(
        types.InlineKeyboardButton(text="✅ Опубликовать/Запланировать", callback_data="post_confirm_yes"),
        types.InlineKeyboardButton(text="❌ Отменить", callback_data="post_confirm_no")
    )

    parse_mode_to_use = "HTML"

    try:
        # Отправляем предпросмотр как НОВОЕ сообщение
        if final_media_id:
            if final_media_type == "photo":
                sent_preview_message = await message.answer_photo(photo=final_media_id, caption=preview_caption,
                                                                  reply_markup=confirm_kb.as_markup(),
                                                                  parse_mode=parse_mode_to_use)
            elif final_media_type == "video":
                sent_preview_message = await message.answer_video(video=final_media_id, caption=preview_caption,
                                                                  reply_markup=confirm_kb.as_markup(),
                                                                  parse_mode=parse_mode_to_use)
            else:
                sent_preview_message = await message.answer(
                    f"[Не удалось отобразить медиа (тип: {escape_html(final_media_type)}, ID: {escape_html(final_media_id)})]\n\n{preview_caption}",
                    reply_markup=confirm_kb.as_markup(), parse_mode=parse_mode_to_use)
        else:
            sent_preview_message = await message.answer(preview_caption, reply_markup=confirm_kb.as_markup(),
                                                        parse_mode=parse_mode_to_use)

        await state.update_data(
            preview_message_id=sent_preview_message.message_id)  # Сохраняем ID предпросмотра для редактирования

    except Exception as e:
        logger.error(f"Ошибка отправки предпросмотра: {e}", exc_info=True)
        try:
            plain_text_preview = re.sub(r'<[^>]+>', '', preview_caption)
            # Отправляем новое, не сохраняя ID
            if final_media_id:
                await message.answer(
                    f"[Медиа есть, но предпросмотр с форматированием не удался]\n\n{plain_text_preview}",
                    reply_markup=confirm_kb.as_markup())
            else:
                await message.answer(plain_text_preview, reply_markup=confirm_kb.as_markup())
            await message.answer(
                "⚠️ Возникла ошибка при отображении предпросмотра с форматированием. Показан упрощенный вариант.")
        except Exception as e_fallback:
            logger.error(f"Ошибка отправки УПРОЩЕННОГО предпросмотра: {e_fallback}", exc_info=True)
            await message.answer(
                "Произошла ошибка при формировании предпросмотра. Попробуйте снова или отмените операцию.")
            # Не возвращаем на SCHEDULE, так как сообщение пользователя со временем уже удалено
            return  # Просто выходим, пользователь может нажать /cancel или начать заново

    await state.set_state(PostCreation.CONFIRM)


@router.callback_query(F.data.startswith("post_confirm_"), PostCreation.CONFIRM)
async def process_post_confirmation(callback: types.CallbackQuery, state: FSMContext, bot: Bot):
    await callback.answer()
    fsm_data = await state.get_data()
    preview_message_id = fsm_data.get("preview_message_id")

    if preview_message_id:  # Если есть ID сообщения с предпросмотром, редактируем его
        try:
            if callback.message.photo or callback.message.video or callback.message.document:
                await bot.edit_message_caption(chat_id=callback.message.chat.id, message_id=preview_message_id,
                                               caption=callback.message.caption, reply_markup=None)
            else:
                await bot.edit_message_text(text=callback.message.text, chat_id=callback.message.chat.id,
                                            message_id=preview_message_id, reply_markup=None)
        except types.TelegramBadRequest as e_edit_preview:
            if "message to edit not found" in str(e_edit_preview).lower() or "message can't be edited" in str(
                    e_edit_preview).lower() or "message is not modified" in str(e_edit_preview).lower():
                logger.warning(f"Не удалось убрать кнопки у предпросмотра (ID: {preview_message_id}): {e_edit_preview}")
            else:
                logger.error(
                    f"НЕожидаемая ошибка при редактировании предпросмотра (ID: {preview_message_id}): {e_edit_preview}",
                    exc_info=True)
        except Exception as e_edit_preview:
            logger.error(f"Общая ошибка при редактировании предпросмотра (ID: {preview_message_id}): {e_edit_preview}",
                         exc_info=True)
    else:  # Если ID предпросмотра не было, просто удаляем кнопки у текущего сообщения (которое и есть предпросмотр)
        try:
            if callback.message.photo or callback.message.video or callback.message.document:
                await callback.message.edit_caption(caption=callback.message.caption, reply_markup=None)
            else:
                await callback.message.edit_text(text=callback.message.text, reply_markup=None)
        except Exception as e_cb_edit:
            logger.warning(f"Не удалось убрать кнопки у callback-сообщения (предпросмотра): {e_cb_edit}")

    action = callback.data.split("_")[2]
    if action == "no":
        await state.clear()
        # Сообщение с предпросмотром уже отредактировано (убраны кнопки), отправляем новое
        await callback.message.answer("❌ Создание поста отменено.", reply_markup=get_main_keyboard())
        return

    current_data = fsm_data  # Используем уже полученные fsm_data
    db = get_db()

    channel_telegram_id = current_data['selected_channel_id']
    channel_title = current_data['selected_channel_title']
    content_to_post = current_data.get('final_post_content', '')  # Текст УЖЕ ПОЛНОСТЬЮ ГОТОВ
    media_to_post = current_data.get('final_post_media_id')
    media_type_to_post = current_data.get('final_post_media_type')
    publish_time_iso_from_state = current_data['publish_time_iso']
    publish_time_dt = datetime.fromisoformat(publish_time_iso_from_state)
    user_id_creator = callback.from_user.id
    post_status = "scheduled"
    message_to_user = ""

    try:
        cursor = db.execute(
            """INSERT INTO posts (user_id, channel_id, content, media, media_type, publish_time, status)
               VALUES (?, ?, ?, ?, ?, ?, ?)""",
            (user_id_creator, channel_telegram_id, content_to_post, media_to_post, media_type_to_post,
             publish_time_iso_from_state, post_status),
            commit=True
        )
        post_db_id = cursor.lastrowid
        logger.info(
            f"Post (DB ID: {post_db_id}) by user {user_id_creator} for channel {channel_telegram_id} saved to DB with status 'scheduled'.")

        if publish_time_dt <= datetime.now() + timedelta(seconds=20):
            # (логика немедленной публикации остается такой же)
            logger.info(f"Post (DB ID: {post_db_id}) is for immediate publication.")
            published_message = None
            try:
                if media_to_post:
                    if media_type_to_post == "photo":
                        published_message = await bot.send_photo(chat_id=channel_telegram_id, photo=media_to_post,
                                                                 caption=content_to_post, parse_mode="HTML")
                    elif media_type_to_post == "video":
                        published_message = await bot.send_video(chat_id=channel_telegram_id, video=media_to_post,
                                                                 caption=content_to_post, parse_mode="HTML")
                    else:
                        published_message = await bot.send_message(chat_id=channel_telegram_id,
                                                                   text=f"{content_to_post}\n[Медиафайл: {escape_html(media_to_post)}]",
                                                                   parse_mode="HTML")
                else:
                    published_message = await bot.send_message(chat_id=channel_telegram_id, text=content_to_post,
                                                               parse_mode="HTML")

                post_status = "published"
                message_id_in_channel = published_message.message_id if published_message else None
                db.execute("UPDATE posts SET status = ?, message_id = ? WHERE id = ?",
                           (post_status, message_id_in_channel, post_db_id), commit=True)
                logger.info(
                    f"Post (DB ID: {post_db_id}) published immediately. Channel Msg ID: {message_id_in_channel}")
                message_to_user = "✅ Пост успешно опубликован немедленно!"
                if message_id_in_channel:
                    await notify_post_published(bot, user_id_creator, channel_telegram_id, message_id_in_channel,
                                                channel_title)

            except Exception as e_publish:
                logger.error(f"Ошибка немедленной публикации поста ID {post_db_id}: {e_publish}", exc_info=True)
                post_status = "failed"
                db.execute("UPDATE posts SET status = ? WHERE id = ?", (post_status, post_db_id), commit=True)
                message_to_user = f"❌ Ошибка немедленной публикации: {escape_html(str(e_publish))}"
        else:
            scheduler_data = {
                'post_db_id': post_db_id, 'channel_id': channel_telegram_id, 'content': content_to_post,
                'media': media_to_post, 'media_type': media_type_to_post,
                'publish_time': publish_time_dt, 'user_id': user_id_creator, 'channel_title': channel_title
            }
            if add_scheduled_job(scheduler, bot, scheduler_data):
                logger.info(f"Post (DB ID: {post_db_id}) scheduled for {publish_time_dt.strftime('%d.%m.%Y %H:%M')}.")
                message_to_user = (f"✅ Пост запланирован на {publish_time_dt.strftime('%d.%m.%Y %H:%M')} "
                                   f"в канал «{escape_html(channel_title)}».")
            else:
                logger.error(f"Failed to schedule post DB ID {post_db_id}. Setting status to 'failed'.")
                db.execute("UPDATE posts SET status = 'failed' WHERE id = ?", (post_db_id,), commit=True)
                message_to_user = "❌ Ошибка при планировании поста. Пост не будет опубликован. Попробуйте снова."

    except sqlite3.Error as e_db:
        logger.error(f"DB ошибка при подтверждении поста (user {user_id_creator}): {e_db}", exc_info=True)
        message_to_user = f"❌ Ошибка базы данных: {escape_html(str(e_db))}"
    except Exception as e_general:
        logger.error(f"Общая ошибка при подтверждении поста (user {user_id_creator}): {e_general}", exc_info=True)
        message_to_user = f"❌ Произошла непредвиденная ошибка: {escape_html(str(e_general))}"
    finally:
        await state.clear()
        # Отправляем новое сообщение о результате
        if message_to_user:
            await callback.message.answer(message_to_user, reply_markup=get_main_keyboard(), parse_mode="HTML",
                                          disable_web_page_preview=True)
        else:
            await callback.message.answer("Операция завершена с неизвестным статусом.",
                                          reply_markup=get_main_keyboard())