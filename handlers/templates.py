from aiogram import Router, F, types
from aiogram.filters import Command
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup

from handlers.common import get_main_keyboard
from models.database import Database
from config import DATABASE_NAME
import sqlite3

router = Router()
db = Database(DATABASE_NAME)


class TemplateStates(StatesGroup):
    AWAITING_NAME = State()
    AWAITING_CONTENT = State()

@router.callback_query(F.data == "add_template")
async def add_template_start(callback: types.CallbackQuery, state: FSMContext):
    await callback.message.answer("📝 Введите название шаблона:")
    await state.set_state(TemplateStates.AWAITING_NAME)
    await callback.answer()



# Показ списка шаблонов
@router.message(F.text == "📚 Шаблоны")
async def list_templates_handler(message: types.Message):
    templates = db.cursor.execute("SELECT name FROM templates").fetchall()

    if not templates:
        keyboard = types.InlineKeyboardMarkup(inline_keyboard=[
            [types.InlineKeyboardButton(text="➕ Добавить шаблон", callback_data="add_template")]
        ])
        await message.answer("📭 Список шаблонов пуст.", reply_markup=keyboard)
        return

    keyboard = types.InlineKeyboardMarkup(inline_keyboard=[])
    for template in templates:
        keyboard.inline_keyboard.append([
            types.InlineKeyboardButton(text=template[0], callback_data=f"view_template_{template[0]}"),
            types.InlineKeyboardButton(text="❌ Удалить", callback_data=f"delete_ask_{template[0]}"),
        ])
    keyboard.inline_keyboard.append([
        types.InlineKeyboardButton(text="➕ Добавить шаблон", callback_data="add_template"),
        types.InlineKeyboardButton(text="📋 Переменные", callback_data="show_variables")
    ])

    await message.answer("📚 Доступные шаблоны:", reply_markup=keyboard)

@router.callback_query(F.data == "show_variables")
async def show_variables_callback(callback: types.CallbackQuery):
    await show_variables(callback.message)
    await callback.answer()


@router.callback_query(F.data.startswith("view_template_"))
async def view_template(callback: types.CallbackQuery):
    template_name = callback.data.split("_")[2]
    template = db.cursor.execute(
        "SELECT content FROM templates WHERE name = ?",
        (template_name,)
    ).fetchone()

    if template:
        await callback.message.answer(f"📄 Шаблон «{template_name}»:\n\n{template[0]}")
    else:
        await callback.message.answer("❌ Шаблон не найден!")
    await callback.answer()

# Применение шаблона
@router.callback_query(F.data.startswith("use_template_"))
async def use_template(callback: types.CallbackQuery, state: FSMContext):
    template_name = callback.data.split("_")[2]
    template = db.cursor.execute(
        "SELECT content FROM templates WHERE name = ?",
        (template_name,)
    ).fetchone()

    if template:
        await state.update_data(content=template[0])
        await callback.message.answer(f"📝 Шаблон применен: {template[0][:50]}...")
    else:
        await callback.message.answer("❌ Шаблон не найден!")
    await callback.answer()


# Удаление шаблона
@router.callback_query(F.data.startswith("delete_ask_"))
async def ask_delete_template(callback: types.CallbackQuery):
    template_name = callback.data.split("_")[2]
    keyboard = types.InlineKeyboardMarkup(inline_keyboard=[
        [
            types.InlineKeyboardButton(text="✅ Да", callback_data=f"delete_confirm_{template_name}"),
            types.InlineKeyboardButton(text="❌ Нет", callback_data="cancel_delete")
        ]
    ])
    await callback.message.answer(
        f"❓ Удалить шаблон «{template_name}»?",
        reply_markup=keyboard
    )
    await callback.answer()

@router.callback_query(F.data.startswith("delete_confirm_"))
async def delete_template(callback: types.CallbackQuery):
    template_name = callback.data.split("_")[2]
    db.cursor.execute("DELETE FROM templates WHERE name = ?", (template_name,))
    db.connection.commit()
    await callback.message.answer(f"🗑 Шаблон «{template_name}» удален!")
    await callback.answer()

@router.callback_query(F.data == "cancel_delete")
async def cancel_delete(callback: types.CallbackQuery):
    await callback.message.answer("❌ Удаление отменено.")
    await callback.answer()


# Сохранение шаблона
@router.message(Command("save_template"))
async def save_template(message: types.Message, state: FSMContext):
    if message.photo or message.video:
        media = message.photo[-1].file_id if message.photo else message.video.file_id
        await state.update_data(media=media)
    await message.answer("📝 Введите название шаблона:")
    await state.set_state(TemplateStates.AWAITING_NAME)

@router.message(TemplateStates.AWAITING_NAME)
async def process_template_name(message: types.Message, state: FSMContext):
    await state.update_data(template_name=message.text)
    await message.answer("📝 Отправьте текст шаблона (можно с медиа):")
    await state.set_state(TemplateStates.AWAITING_CONTENT)

@router.message(TemplateStates.AWAITING_CONTENT)
async def process_template_content(message: types.Message, state: FSMContext):
    data = await state.get_data()
    template_name = data["template_name"]
    content = message.text or message.caption
    media = message.photo[-1].file_id if message.photo else None

    try:
        db.cursor.execute(
            "INSERT INTO templates (name, content, media) VALUES (?, ?, ?)",
            (template_name, content, media)
        )
        db.connection.commit()
        await message.answer(f"✅ Шаблон «{template_name}» сохранен!")
    except sqlite3.IntegrityError:
        await message.answer("❌ Шаблон с таким названием уже существует.")
    await state.clear()

@router.message(F.text == "📋 Переменные")
async def show_variables(message: types.Message):
    variables_list = (
        "📌 Доступные переменные:\n\n"
        "• {дата} — текущая дата (ДД.ММ.ГГГГ)\n"
        "• {время} — текущее время (ЧЧ:ММ)\n"
        "• {текст_новости} — ваш текст\n"
        "• {автор} — ваше имя\n"
        "• {ссылка} — пример ссылки"
    )
    await message.answer(variables_list, reply_markup=get_main_keyboard())


