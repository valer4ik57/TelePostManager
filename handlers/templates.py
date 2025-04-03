from aiogram import Router, F, types
from aiogram.filters import Command
from aiogram.fsm.context import FSMContext
from models.database import Database
from config import DATABASE_NAME

router = Router()
db = Database(DATABASE_NAME)


@router.message(Command("save_template"))
async def save_template(message: types.Message):
    # Логика сохранения шаблона
    ...


@router.message(Command("templates"))
async def list_templates(message: types.Message):
    templates = db.cursor.execute(
        "SELECT name, content FROM templates"
    ).fetchall()

    keyboard = types.InlineKeyboardMarkup(inline_keyboard=[])
    for template in templates:
        keyboard.inline_keyboard.append([
            types.InlineKeyboardButton(
                text=template[0],
                callback_data=f"use_template_{template[0]}"
            )
        ])

    await message.answer("📚 Доступные шаблоны:", reply_markup=keyboard)

@router.message(F.text == "📚 Шаблоны")
async def list_templates_handler(message: types.Message):
    await list_templates(message)  # Используем существующую функцию