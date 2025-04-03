import sqlite3
from aiogram import Router, Bot, types, F
from aiogram.filters import Command
from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton
from models.database import Database
from config import DATABASE_NAME

router = Router()
db = Database(DATABASE_NAME)

async def check_channel_admin(bot: Bot, user_id: int, channel_id: int) -> bool:
    try:
        member = await bot.get_chat_member(chat_id=channel_id, user_id=user_id)
        return member.status in ['creator', 'administrator']
    except Exception as e:
        return False


@router.message(Command("add_channel"))
async def add_channel(message: types.Message, bot: Bot):
    # Получаем информацию о боте
    bot_info = await bot.get_me()

    keyboard = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(
            text="Добавить канал ➕",
            url=f"t.me/{bot_info.username}?startchannel=true"
        )],
    ])

    await message.answer(
        "1. Сделайте бота администратором вашего канала\n"
        "2. Перешлите любое сообщение из канала сюда\n\n"
        "Или нажмите кнопку ниже чтобы добавить канал:",
        reply_markup=keyboard
    )

@router.message(F.forward_from_chat)
async def handle_forwarded_channel(message: types.Message, bot: Bot):  # Исправлено здесь
    user_id = message.from_user.id
    channel = message.forward_from_chat

    if not await check_channel_admin(bot, user_id, channel.id):
        return await message.answer("❌ Вы должны быть администратором этого канала!")

    try:
        db.cursor.execute("INSERT INTO channels (channel_id, title) VALUES (?, ?)",
                        (channel.id, channel.title))
        db.connection.commit()
        await message.answer(f"✅ Канал {channel.title} успешно добавлен!")
    except sqlite3.IntegrityError:
        await message.answer("⚠️ Этот канал уже был добавлен ранее")

@router.message(F.text == "➕ Добавить канал")
async def add_channel_button(message: types.Message, bot: Bot):
    await add_channel(message, bot)  # Используем существующую функцию