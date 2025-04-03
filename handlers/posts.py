from datetime import datetime
from aiogram import Router, F, types, Bot
from aiogram.filters import Command
from aiogram.fsm.context import FSMContext
from models.database import Database
from config import DATABASE_NAME, BANNED_WORDS_FILE
from services.scheduler import add_scheduled_job
from post_states import PostCreation
import sqlite3

router = Router()
db = Database(DATABASE_NAME)

# Загрузка запрещенных слов из файла
with open(BANNED_WORDS_FILE, 'r', encoding='utf-8') as f:
    BANNED_WORDS = [word.strip().lower() for word in f.readlines()]


async def get_channels_keyboard():
    """Генерирует клавиатуру с подключенными каналами"""
    channels = db.cursor.execute("SELECT channel_id, title FROM channels").fetchall()
    return types.InlineKeyboardMarkup(inline_keyboard=[
        [types.InlineKeyboardButton(text=title, callback_data=f"channel_{cid}")]
        for cid, title in channels
    ])


@router.message(Command("new_post"))
async def start_post(message: types.Message, state: FSMContext):
    """Начало создания поста"""
    channels_count = db.cursor.execute("SELECT COUNT(*) FROM channels").fetchone()[0]

    if channels_count == 0:
        return await message.answer("❌ Сначала добавьте канал через /add_channel")

    await message.answer("📌 Выберите канал:", reply_markup=await get_channels_keyboard())
    await state.set_state(PostCreation.SELECT_CHANNEL)


@router.callback_query(F.data.startswith("channel_"), PostCreation.SELECT_CHANNEL)
async def select_channel(callback: types.CallbackQuery, state: FSMContext):
    """Обработка выбора канала"""
    channel_id = int(callback.data.split("_")[1])
    channel = db.cursor.execute(
        "SELECT title FROM channels WHERE channel_id = ?",
        (channel_id,)
    ).fetchone()

    if not channel:
        return await callback.answer("❌ Канал не найден!")

    await state.update_data(channel_id=channel_id, channel_title=channel[0])
    await callback.message.edit_text(f"✅ Выбран канал: {channel[0]}")
    await callback.message.answer("📝 Введите текст поста:")
    await state.set_state(PostCreation.CONTENT)


@router.message(PostCreation.CONTENT)
async def process_content(message: types.Message, state: FSMContext):
    """Проверка контента на запрещенные слова"""
    content = message.text.lower()

    # Поиск запрещенных слов
    found_banned = [word for word in BANNED_WORDS if word in content]

    if found_banned:
        return await message.answer(
            f"❌ Обнаружены запрещенные слова:\n" +
            "\n".join(found_banned) +
            "\n\nИсправьте текст и отправьте заново"
        )

    await state.update_data(content=message.text)
    await message.answer("📎 Прикрепите фото или нажмите /skip")
    await state.set_state(PostCreation.MEDIA)

# Изменения в обработчике process_media
@router.message(PostCreation.MEDIA, F.photo | F.video)
async def process_media(message: types.Message, state: FSMContext):
    try:
        if message.photo:
            media = message.photo[-1].file_id
        elif message.video:
            media = message.video.file_id
        else:
            return await message.answer("❌ Поддерживаются только фото/видео")

        await state.update_data(media=media)
        await message.answer("✅ Медиа добавлено! Введите время публикации (ДД.ММ.ГГГГ ЧЧ:ММ или 'сейчас'):")
        await state.set_state(PostCreation.SCHEDULE)
    except Exception as e:
        await message.answer(f"❌ Ошибка обработки медиа: {str(e)}")

@router.message(Command("skip"), PostCreation.MEDIA)
async def skip_media(message: types.Message, state: FSMContext):
    """Пропуск добавления медиа"""
    await state.update_data(media=None)
    await message.answer("⏰ Введите время публикации (ДД.ММ.ГГГГ ЧЧ:ММ или 'сейчас'):")
    await state.set_state(PostCreation.SCHEDULE)


@router.message(PostCreation.SCHEDULE)
async def process_schedule(message: types.Message, state: FSMContext):
    """Обработка времени публикации"""
    time_str = message.text.strip().lower()
    data = await state.get_data()

    try:
        publish_time = (
            datetime.now()
            if time_str == "сейчас"
            else datetime.strptime(time_str, "%d.%m.%Y %H:%M")
        )
    except ValueError:
        return await message.answer("❌ Неверный формат времени! Используйте ДД.ММ.ГГГГ ЧЧ:ММ")

    await state.update_data(publish_time=publish_time)

    # Формирование предпросмотра
    preview = (
        f"📋 Пост для {data['channel_title']}:\n\n"
        f"{data['content']}\n\n"
        f"⏰ Время публикации: {publish_time.strftime('%d.%m.%Y %H:%M')}"
    )

    if data.get('media'):
        await message.answer_photo(data['media'], caption=preview)
    else:
        await message.answer(preview)

    # Кнопки подтверждения
    keyboard = types.InlineKeyboardMarkup(inline_keyboard=[
        [types.InlineKeyboardButton(text="✅ Опубликовать", callback_data="confirm_yes"),
         types.InlineKeyboardButton(text="❌ Отменить", callback_data="confirm_no")]
    ])

    await message.answer("Подтвердите публикацию:", reply_markup=keyboard)
    await state.set_state(PostCreation.CONFIRM)


@router.callback_query(F.data.startswith("confirm_"))
async def confirm_post(callback: types.CallbackQuery, state: FSMContext, bot: Bot):
    """Обработка подтверждения публикации"""
    action = callback.data.split("_")[1]
    data = await state.get_data()

    if action == "no":
        await callback.message.answer("❌ Публикация отменена")
        await state.clear()
        return await callback.answer()

    try:
        # Публикация поста
        if data['publish_time'] <= datetime.now():
            method = (
                bot.send_photo if data.get('media')
                else bot.send_message
            )
            post = await method(
                chat_id=data['channel_id'],
                **(dict(photo=data['media'], caption=data['content']) if data.get('media')
                   else dict(text=data['content']))
            )
            status = "published"
        else:
            add_scheduled_job(bot, data)
            status = "scheduled"

        # Сохранение в БД
        db.cursor.execute(
            """INSERT INTO posts 
            (channel_id, content, media, publish_time, status) 
            VALUES (?, ?, ?, ?, ?)""",
            (
                data['channel_id'],
                data['content'],
                data.get('media'),
                data['publish_time'].isoformat(),  # Сохраняем в ISO формате
                status
            )
        )
        db.connection.commit()

        # В posts.py (в обработчике confirm_post)
        channel_id_str = str(data['channel_id']).replace('-100', '')  # Добавить эту строку
        await callback.message.answer(
            f"✅ Пост {'опубликован' if status == 'published' else 'запланирован'}!\n" +
            (f"👁‍🗨 Посмотреть: https://t.me/c/{channel_id_str}/{post.message_id}"
             if status == 'published' else "")
        )

    except Exception as e:
        await callback.message.answer(f"❌ Ошибка публикации: {str(e)}")
        db.connection.rollback()

    await state.clear()
    await callback.answer()

@router.message(F.text == "📝 Создать пост")
async def start_post_handler(message: types.Message, state: FSMContext):
    await start_post(message, state)  # Используем существующую функцию