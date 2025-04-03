from aiogram import F
from aiogram import Router, types
from aiogram.filters import Command
from aiogram.utils.keyboard import ReplyKeyboardBuilder

from handlers.channels import db

router = Router()

from aiogram.utils.keyboard import ReplyKeyboardBuilder


def get_main_keyboard():
    builder = ReplyKeyboardBuilder()
    builder.button(text="📝 Создать пост")
    builder.button(text="📢 Мои каналы")
    builder.button(text="➕ Добавить канал")
    builder.button(text="📚 Шаблоны")
    builder.button(text="📜 История")
    builder.button(text="🆘 Помощь")
    builder.adjust(2, 2, 2, 1)
    return builder.as_markup(resize_keyboard=True)


@router.message(Command("start"))
async def cmd_start(message: types.Message):
    await message.answer(
        "🤖 Добро пожаловать в TelePost Manager!",
        reply_markup=get_main_keyboard()
    )

@router.message(F.text == "🆘 Помощь")
async def cmd_help(message: types.Message):
    await message.answer(
        "📋 Все функции доступны через кнопки меню!\n"
        "Если что-то не работает:\n"
        "1. Проверьте права бота в канале\n"
        "2. Перезапустите бота командой /start",
        reply_markup=get_main_keyboard()
    )

@router.message(F.text == "📢 Мои каналы")
async def list_channels(message: types.Message):
    channels = db.cursor.execute("SELECT title FROM channels").fetchall()
    if channels:
        response = "📡 Ваши каналы:\n\n" + "\n".join([f"• {ch[0]}" for ch in channels])
    else:
        response = "❌ Вы еще не добавили ни одного канала"
    await message.answer(response, reply_markup=get_main_keyboard())