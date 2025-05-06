# handlers/posts.py
import logging  # Добавим логгер
from datetime import datetime, timedelta
from aiogram import Router, F, types, Bot
from aiogram.filters import Command
from aiogram.fsm.context import FSMContext
from aiogram.utils.keyboard import InlineKeyboardBuilder
import sqlite3

# Импорты из проекта
from loader import get_db, scheduler, content_filter  # main_bot_instance здесь не нужен, bot передается
from bot_utils import get_main_keyboard, get_channels_keyboard, notify_user, notify_post_published, escape_html
from post_states import PostCreation
from services.scheduler import add_scheduled_job
from handlers.templates import AVAILABLE_TEMPLATE_VARIABLES  # Если этот импорт актуален

router = Router()
logger = logging.getLogger(__name__)  # Логгер для этого модуля


# --- Начало процесса создания поста ---
@router.message(Command("new_post"))
@router.message(F.text == "📝 Создать пост")
async def start_post_creation(message: types.Message, state: FSMContext):
    db = get_db()
    channels_count_data = db.fetchone("SELECT COUNT(*) FROM channels")  # Безопаснее проверить что данные есть
    channels_count = channels_count_data[0] if channels_count_data else 0
    if channels_count == 0:
        await message.answer(
            "❌ Сначала вам нужно добавить хотя бы один канал.\n"
            "Нажмите «➕ Добавить канал» в главном меню.",
            reply_markup=get_main_keyboard()
        )
        return

    templates_data = db.fetchall("SELECT id, name FROM templates ORDER BY name")
    builder = InlineKeyboardBuilder()
    if templates_data:
        for tpl_id, tpl_name in templates_data:
            # Экранируем имя шаблона для отображения в кнопке, если оно может содержать HTML символы
            builder.row(
                types.InlineKeyboardButton(text=f"📄 {escape_html(tpl_name)}", callback_data=f"post_tpl_use_{tpl_id}"))
        builder.row(types.InlineKeyboardButton(text="📝 Без шаблона / Ввести вручную", callback_data="post_tpl_skip"))
        await message.answer("✨ Выберите шаблон для поста или создайте пост вручную:", reply_markup=builder.as_markup())
        await state.set_state(PostCreation.SELECT_TEMPLATE)
    else:
        await message.answer("Шаблоны не найдены. Вы будете создавать пост вручную.")
        channels_kb_markup = await get_channels_keyboard()  # Переименовал для ясности
        if not channels_kb_markup.inline_keyboard:
            await message.answer("❌ Нет доступных каналов для публикации. Сначала добавьте их.",
                                 reply_markup=get_main_keyboard())
            await state.clear()
            return
        await message.answer("📌 В какой канал будем публиковать?", reply_markup=channels_kb_markup)
        await state.set_state(PostCreation.SELECT_CHANNEL)
        await state.update_data(template_id=None, template_content=None, template_media_id=None,
                                template_media_type=None)


# --- Этап 1: Выбор шаблона (или пропуск) ---
@router.callback_query(F.data.startswith("post_tpl_use_"), PostCreation.SELECT_TEMPLATE)
async def process_template_selection(callback: types.CallbackQuery, state: FSMContext):
    await callback.answer()
    template_id = int(callback.data.split("_")[3])
    db = get_db()
    # Убедимся, что media_type извлекается, если он есть в БД шаблонов
    template_data = db.fetchone("SELECT name, content, media, media_type FROM templates WHERE id = ?", (template_id,))

    if not template_data:
        await callback.message.edit_text("❌ Выбранный шаблон не найден. Попробуйте еще раз.")
        return

    tpl_name, tpl_content, tpl_media_id, tpl_media_type = template_data
    await state.update_data(
        template_id=template_id,
        template_name=tpl_name,
        template_content=tpl_content,
        template_media_id=tpl_media_id,
        template_media_type=tpl_media_type  # Сохраняем тип медиа из шаблона
    )

    if tpl_content and AVAILABLE_TEMPLATE_VARIABLES.get("{текст_новости}") and "{текст_новости}" in tpl_content:
        await callback.message.edit_text(f"📝 Шаблон «{escape_html(tpl_name)}» выбран.\n"  # Экранируем
                                         f"Теперь введите основную часть текста (для переменной <code>{{текст_новости}}</code>):",
                                         # Используем code для переменной
                                         parse_mode="HTML")
        await state.set_state(PostCreation.FILL_TEMPLATE)
    else:
        await callback.message.edit_text(
            f"✨ Шаблон «{escape_html(tpl_name)}» выбран. Заполнять переменные не требуется или они будут заполнены автоматически.")
        channels_kb_markup = await get_channels_keyboard()
        if not channels_kb_markup.inline_keyboard:
            await callback.message.answer("❌ Нет доступных каналов. Сначала добавьте их.",
                                          reply_markup=get_main_keyboard())
            await state.clear()
            return
        # Отправляем новое сообщение для выбора канала, чтобы не путать с предыдущим edit_text
        await callback.message.answer("📌 В какой канал будем публиковать?", reply_markup=channels_kb_markup)
        await state.set_state(PostCreation.SELECT_CHANNEL)


@router.callback_query(F.data == "post_tpl_skip", PostCreation.SELECT_TEMPLATE)
async def process_no_template(callback: types.CallbackQuery, state: FSMContext):
    await callback.answer()
    await state.update_data(template_id=None, template_content=None, template_media_id=None, template_media_type=None)
    channels_kb_markup = await get_channels_keyboard()
    if not channels_kb_markup.inline_keyboard:
        await callback.message.answer("❌ Нет доступных каналов. Сначала добавьте их.", reply_markup=get_main_keyboard())
        await state.clear()
        return
    await callback.message.edit_text("📌 Шаблон не используется. В какой канал будем публиковать?",
                                     reply_markup=channels_kb_markup)
    await state.set_state(PostCreation.SELECT_CHANNEL)


# --- Этап 2: Заполнение изменяемой части шаблона ---
@router.message(PostCreation.FILL_TEMPLATE, F.text)
async def process_fill_template_variable(message: types.Message, state: FSMContext):  # bot здесь не нужен
    user_text_for_template = message.text
    found_banned_words = content_filter.check_text(user_text_for_template)
    if found_banned_words:
        await message.answer(
            f"❌ В вашем тексте обнаружены запрещенные слова:\n" +
            f"<code>{escape_html(', '.join(found_banned_words))}</code>\n\n"  # Используем code и escape_html
            f"Пожалуйста, исправьте текст и отправьте его снова.",
            parse_mode="HTML"
        )
        return

    await state.update_data(user_input_for_template=user_text_for_template)
    channels_kb_markup = await get_channels_keyboard()
    if not channels_kb_markup.inline_keyboard:
        await message.answer("❌ Нет доступных каналов. Сначала добавьте их.", reply_markup=get_main_keyboard())
        await state.clear()
        return
    await message.answer("📌 Текст для шаблона принят. В какой канал будем публиковать?",
                         reply_markup=channels_kb_markup)
    await state.set_state(PostCreation.SELECT_CHANNEL)


# --- Этап 3: Выбор канала ---
@router.callback_query(F.data.startswith("channel_"), PostCreation.SELECT_CHANNEL)
async def process_channel_selection(callback: types.CallbackQuery, state: FSMContext):
    await callback.answer()
    channel_id = int(callback.data.split("_")[1])
    db = get_db()
    channel_data = db.fetchone("SELECT title FROM channels WHERE channel_id = ?", (channel_id,))

    if not channel_data:
        await callback.message.edit_text("❌ Выбранный канал не найден в базе. Попробуйте еще раз.")
        return

    channel_title = channel_data[0]
    escaped_channel_title = escape_html(channel_title)  # Экранируем для вывода
    await state.update_data(selected_channel_id=channel_id,
                            selected_channel_title=channel_title)  # Сохраняем неэкранированное

    current_data = await state.get_data()
    if current_data.get('template_id') is not None:
        template_content = current_data.get('template_content', '')
        user_input_for_template = current_data.get('user_input_for_template', '')
        author_name = callback.from_user.full_name or "Неизвестный автор"

        final_post_text = template_content
        if "{текст_новости}" in final_post_text:
            final_post_text = final_post_text.replace("{текст_новости}", user_input_for_template)
        final_post_text = final_post_text.replace("{дата}", datetime.now().strftime("%d.%m.%Y"))
        final_post_text = final_post_text.replace("{время}", datetime.now().strftime("%H:%M"))
        final_post_text = final_post_text.replace("{автор}", author_name)

        found_banned_template = content_filter.check_text(final_post_text)
        if found_banned_template:
            await callback.message.edit_text(
                f"❌ В тексте, сгенерированном из шаблона «{escape_html(current_data.get('template_name'))}», "
                f"обнаружены запрещенные слова:\n<code>{escape_html(', '.join(found_banned_template))}</code>\n\n"
                f"Этот шаблон не может быть использован. Пожалуйста, отредактируйте шаблон или выберите другой.",
                reply_markup=get_main_keyboard(), parse_mode="HTML"
            )
            await state.clear()
            return

        await state.update_data(final_post_content=final_post_text)

        msg_text_after_channel_select = f"✅ Канал «{escaped_channel_title}» выбран.\n"
        if current_data.get('template_media_id'):
            await state.update_data(
                final_post_media_id=current_data.get('template_media_id'),
                final_post_media_type=current_data.get('template_media_type')
            )
            msg_text_after_channel_select += "Будет использован текст и медиа из шаблона.\n"
            msg_text_after_channel_select += "⏰ Введите время публикации (ДД.ММ.ГГГГ ЧЧ:ММ или 'сейчас'):"
            await state.set_state(PostCreation.SCHEDULE)
        else:
            msg_text_after_channel_select += "Будет использован текст из шаблона.\n"
            msg_text_after_channel_select += "📎 Хотите добавить фото/видео к этому посту? Отправьте его или нажмите /skip_media."
            await state.set_state(PostCreation.MEDIA)

        await callback.message.edit_text(msg_text_after_channel_select, parse_mode="HTML")
    else:
        await callback.message.edit_text(f"✅ Канал «{escaped_channel_title}» выбран.\n"
                                         "📝 Теперь введите текст для вашего поста:", parse_mode="HTML")
        await state.set_state(PostCreation.CONTENT)


# --- Этап 4: Ввод контента ---
@router.message(PostCreation.CONTENT, F.text)
async def process_post_content(message: types.Message, state: FSMContext):
    post_text = message.text
    found_banned_words = content_filter.check_text(post_text)
    if found_banned_words:
        await message.answer(
            f"❌ В вашем тексте обнаружены запрещенные слова:\n"
            f"<code>{escape_html(', '.join(found_banned_words))}</code>\n\n"
            f"Пожалуйста, исправьте текст и отправьте его снова.",
            parse_mode="HTML"
        )
        return

    await state.update_data(final_post_content=post_text)
    await message.answer("📎 Текст принят. Хотите добавить фото/видео? Отправьте его или нажмите /skip_media.")
    await state.set_state(PostCreation.MEDIA)


# --- Этап 5: Добавление медиа ---
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
    if not media_id:  # Должно быть покрыто фильтрами, но на всякий случай
        await message.answer("❌ Не удалось распознать медиа. Попробуйте еще раз или /skip_media.")
        return
    # Дублировалось обновление state, убрал одно
    await state.update_data(final_post_media_id=media_id, final_post_media_type=media_type)
    await message.answer("✅ Медиа добавлено.\n"
                         "⏰ Введите время публикации (формат: ДД.ММ.ГГГГ ЧЧ:ММ, или напишите 'сейчас'):")
    await state.set_state(PostCreation.SCHEDULE)


@router.message(PostCreation.MEDIA, Command("skip_media"))
async def process_skip_media(message: types.Message, state: FSMContext):
    await state.update_data(final_post_media_id=None, final_post_media_type=None)
    await message.answer("Хорошо, пост будет без медиа.\n"
                         "⏰ Введите время публикации (формат: ДД.ММ.ГГГГ ЧЧ:ММ, или напишите 'сейчас'):")
    await state.set_state(PostCreation.SCHEDULE)


# --- Этап 6: Указание времени публикации и Предпросмотр ---
@router.message(PostCreation.SCHEDULE, F.text)
async def process_schedule_time(message: types.Message, state: FSMContext):
    time_str = message.text.strip().lower()
    publish_time_dt: datetime
    if time_str == "сейчас":
        publish_time_dt = datetime.now()
    else:
        try:
            publish_time_dt = datetime.strptime(time_str, "%d.%m.%Y %H:%M")
            if publish_time_dt < datetime.now() - timedelta(
                    minutes=1) and publish_time_dt.date() <= datetime.now().date():  # Исправлено условие для прошлого времени
                await message.answer("❌ Указанное время уже прошло. Введите корректное будущее время или 'сейчас'.")
                return
        except ValueError:
            await message.answer("❌ Неверный формат времени. Используйте ДД.ММ.ГГГГ ЧЧ:ММ или 'сейчас'.")
            return

    await state.update_data(publish_time=publish_time_dt.isoformat())
    current_data = await state.get_data()
    raw_final_text = current_data.get('final_post_content', "[Нет текста]")
    final_text_for_preview = escape_html(raw_final_text)
    channel_title_for_preview = escape_html(current_data.get('selected_channel_title', "Неизвестный канал"))
    publish_time_str_for_preview = escape_html(publish_time_dt.strftime('%d.%m.%Y %H:%M'))
    final_media_id = current_data.get('final_post_media_id')
    final_media_type = current_data.get('final_post_media_type')

    preview_caption_parts = [
        f"✨ <b>ПРЕДПРОСМОТР ПОСТА</b> ✨\n",
        f"📢 <b>Канал:</b> {channel_title_for_preview}",
        f"⏰ <b>Время публикации:</b> {publish_time_str_for_preview}",
        f"\n📝 <b>Текст поста:</b>\n{final_text_for_preview}"
    ]
    preview_caption = "\n".join(preview_caption_parts)
    confirm_kb = InlineKeyboardBuilder()
    confirm_kb.row(
        types.InlineKeyboardButton(text="✅ Опубликовать/Запланировать", callback_data="post_confirm_yes"),
        types.InlineKeyboardButton(text="❌ Отменить", callback_data="post_confirm_no")
    )
    parse_mode_to_use = "HTML"
    try:
        if final_media_id:
            if final_media_type == "photo":
                await message.answer_photo(photo=final_media_id, caption=preview_caption,
                                           reply_markup=confirm_kb.as_markup(), parse_mode=parse_mode_to_use)
            elif final_media_type == "video":
                await message.answer_video(video=final_media_id, caption=preview_caption,
                                           reply_markup=confirm_kb.as_markup(), parse_mode=parse_mode_to_use)
            else:
                logger.warning(f"Предпросмотр: Неизв. тип медиа ({final_media_type}) ID: {final_media_id}.")
                await message.answer(
                    f"[Не удалось отобразить медиа (тип: {final_media_type}, ID: {escape_html(final_media_id)})]\n\n{preview_caption}",
                    reply_markup=confirm_kb.as_markup(), parse_mode=parse_mode_to_use)
        else:
            await message.answer(preview_caption, reply_markup=confirm_kb.as_markup(), parse_mode=parse_mode_to_use)
    except Exception as e:
        logger.error(f"Ошибка отправки предпросмотра: {e}", exc_info=True)
        await message.answer("Произошла ошибка при формировании предпросмотра. Попробуйте снова.")
        return
    await state.set_state(PostCreation.CONFIRM)


# --- Этап 7: Подтверждение и Публикация/Планирование ---
@router.callback_query(F.data.startswith("post_confirm_"), PostCreation.CONFIRM)
async def process_post_confirmation(callback: types.CallbackQuery, state: FSMContext, bot: Bot):
    await callback.answer()  # Отвечаем на callback как можно раньше

    # Сначала убираем клавиатуру у сообщения с предпросмотром
    try:
        if callback.message.photo or callback.message.video or callback.message.document:  # Если сообщение с медиа
            await callback.message.edit_caption(caption=callback.message.caption,
                                                reply_markup=None)  # Убираем кнопки, оставляем caption
        else:  # Если текстовое сообщение
            await callback.message.edit_text(text=callback.message.text,
                                             reply_markup=None)  # Убираем кнопки, оставляем текст
    except Exception as e_edit_preview:
        logger.warning(f"Не удалось убрать кнопки у сообщения предпросмотра: {e_edit_preview}")
        # Не критично, продолжаем

    action = callback.data.split("_")[2]
    if action == "no":
        await state.clear()
        # Сообщение уже отредактировано (убраны кнопки), можно просто отправить новое
        await callback.message.answer("❌ Создание поста отменено.", reply_markup=get_main_keyboard())
        return

    current_data = await state.get_data()
    db = get_db()
    channel_id = current_data['selected_channel_id']
    channel_title = current_data['selected_channel_title']  # Не экранируем, это для внутреннего использования
    content_to_post = current_data.get('final_post_content', '')
    media_to_post = current_data.get('final_post_media_id')
    media_type_to_post = current_data.get('final_post_media_type')
    publish_time_iso = current_data['publish_time']
    publish_time_dt = datetime.fromisoformat(publish_time_iso)
    user_id_creator = callback.from_user.id
    post_status = "scheduled"

    message_to_user = ""  # Сообщение пользователю о результате

    try:
        cursor = db.execute(
            """INSERT INTO posts (channel_id, content, media, media_type, publish_time, status, user_id) 
               VALUES (?, ?, ?, ?, ?, ?, ?)""",  # Добавили media_type
            (channel_id, content_to_post, media_to_post, media_type_to_post,
             publish_time_iso, post_status, user_id_creator),
            commit=True
        )
        post_db_id = cursor.lastrowid

        if publish_time_dt <= datetime.now() + timedelta(seconds=15):  # Увеличил дельту для надежности
            published_message = None
            try:
                # Отправка поста в канал
                if media_to_post:
                    if media_type_to_post == "photo":
                        published_message = await bot.send_photo(chat_id=channel_id, photo=media_to_post,
                                                                 caption=content_to_post, parse_mode="HTML")
                    elif media_type_to_post == "video":
                        published_message = await bot.send_video(chat_id=channel_id, video=media_to_post,
                                                                 caption=content_to_post, parse_mode="HTML")
                    else:  # Пробуем отправить как текст с упоминанием медиа
                        logger.warning(f"Немедл. публ.: Неизв. тип медиа ({media_type_to_post}) ID {post_db_id}.")
                        published_message = await bot.send_message(chat_id=channel_id,
                                                                   text=f"{content_to_post}\n[Медиафайл: {media_to_post}]",
                                                                   parse_mode="HTML")
                else:  # Только текст
                    published_message = await bot.send_message(chat_id=channel_id, text=content_to_post,
                                                               parse_mode="HTML")

                post_status = "published"
                message_id_in_channel = published_message.message_id if published_message else None
                db.execute("UPDATE posts SET status = ?, message_id = ? WHERE id = ?",
                           (post_status, message_id_in_channel, post_db_id), commit=True)

                message_to_user = "✅ Пост успешно опубликован немедленно!"
                if message_id_in_channel:  # Для уведомления пользователя
                    await notify_post_published(bot, user_id_creator, channel_id, message_id_in_channel, channel_title)

            except Exception as e_publish:
                logger.error(f"Ошибка немедленной публикации поста ID {post_db_id}: {e_publish}", exc_info=True)
                post_status = "failed"
                db.execute("UPDATE posts SET status = ? WHERE id = ?", (post_status, post_db_id), commit=True)
                message_to_user = f"❌ Ошибка немедленной публикации: {escape_html(str(e_publish))}"
                # await notify_user(bot, user_id_creator, message_to_user) # Уже будет отправлено ниже
        else:  # Планируем публикацию
            scheduler_data = {
                'post_db_id': post_db_id, 'channel_id': channel_id, 'content': content_to_post,
                'media': media_to_post, 'media_type': media_type_to_post,
                'publish_time': publish_time_dt, 'user_id': user_id_creator, 'channel_title': channel_title
            }
            add_scheduled_job(scheduler, bot, scheduler_data)
            message_to_user = (f"✅ Пост запланирован на {publish_time_dt.strftime('%d.%m.%Y %H:%M')} "
                               f"в канал «{escape_html(channel_title)}».")
            # await notify_user(bot, user_id_creator, message_to_user) # Уже будет отправлено ниже

    except sqlite3.Error as e_db:
        logger.error(f"DB ошибка при подтверждении поста: {e_db}", exc_info=True)
        message_to_user = f"❌ Ошибка базы данных: {escape_html(str(e_db))}"
    except Exception as e_general:
        logger.error(f"Общая ошибка при подтверждении поста: {e_general}", exc_info=True)
        message_to_user = f"❌ Произошла непредвиденная ошибка: {escape_html(str(e_general))}"
    finally:
        await state.clear()
        # Отправляем итоговое сообщение пользователю
        if message_to_user:  # Если есть что сказать
            await callback.message.answer(message_to_user, reply_markup=get_main_keyboard(), parse_mode="HTML")
        else:  # Если вдруг message_to_user пустое, на всякий случай
            await callback.message.answer("Операция завершена.", reply_markup=get_main_keyboard())