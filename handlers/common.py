from aiogram import Router, F, types
from aiogram.filters import Command
from aiogram.fsm.context import FSMContext
import logging
from config import SUPER_ADMIN_ID

from loader import get_db
from bot_utils import get_main_keyboard  # Не импортируем IsAdmin здесь, он не нужен для /help

# from filters.admin import IsAdmin # Убираем, если не используется в других функциях этого файла

router = Router()
logger = logging.getLogger(__name__)


@router.message(Command("start"))
async def cmd_start(message: types.Message, state: FSMContext):
    db = get_db()
    user = message.from_user
    try:
        db.upsert_user(
            user_id=user.id,
            username=user.username,
            first_name=user.first_name,
            last_name=user.last_name
        )
        logger.info(f"User {user.id} ({user.username or 'NoUsername'}) started/updated.")
    except Exception as e:
        logger.error(f"Failed to upsert user {user.id} on /start: {e}", exc_info=True)

    current_fsm_state = await state.get_state()
    if current_fsm_state is not None:
        await state.clear()
        await message.answer("Состояние предыдущей операции сброшено. Начинаем сначала.",
                             reply_markup=get_main_keyboard())

    await message.answer(
        "🤖 Добро пожаловать в TelePost Manager!\n"
        "Я помогу вам управлять публикациями в ваших Telegram-каналах.",
        reply_markup=get_main_keyboard()
    )


@router.message(F.text == "🆘 Помощь")
@router.message(Command("help"))
async def cmd_help(message: types.Message):
    user_id = message.from_user.id
    # Проверяем, является ли пользователь супер-админом, напрямую сравнивая ID
    is_super_admin_user = (user_id == SUPER_ADMIN_ID)

    help_text_parts = [
        "<b>TelePost Manager Bot</b> - ваш помощник для управления публикациями в Telegram-каналах.\n",
        "📋 <b>Основные команды и функции:</b>\n",
        "▫️ /start - Перезапустить бота, показать главное меню.",
        "▫️ /help - Показать это справочное сообщение.\n",
        "▫️ /cancel - Отменить текущее действие (например, создание поста или шаблона).\n",

        "<b>Управление контентом:</b>",
        "▫️ <b>📝 Создать пост</b> (или /new_post) - Начать процесс создания нового поста для вашего канала.",
        "▫️ <b>🗓️ Запланированные</b> (или /my_scheduled) - Просмотреть и отменить ваши запланированные посты.\n",

        "<b>Управление каналами:</b>",
        "▫️ <b>📢 Мои каналы</b> (или /my_channels) - Просмотреть список ваших подключенных каналов и удалить их.",
        "▫️ <b>➕ Добавить канал</b> (или /add_channel) - Подключить новый канал для управления.\n",

        "<b>Шаблоны:</b>",
        "▫️ <b>📚 Шаблоны</b> (или /templates) - Управлять шаблонами для постов (просмотр общих, создание/удаление личных).",
        "   - Внутри меню шаблонов можно посмотреть доступные переменные.\n",

        "<b>История:</b>",
        "▫️ <b>📜 История</b> (или /history) - Посмотреть историю ваших публикаций.\n",

        "⚙️ <b>Как добавить канал:</b>",
        "1. Нажмите «➕ Добавить канал» или введите /add_channel.",
        "2. Сделайте этого бота администратором вашего канала с правом на публикацию сообщений.",
        "3. Перешлите любое сообщение из вашего канала в чат с ботом.\n",

        "Если что-то не работает:",
        "1. Убедитесь, что бот является администратором в нужном канале и имеет права на публикацию.",
        "2. Попробуйте перезапустить бота командой /start.",
        "3. Используйте команду /cancel для сброса текущего состояния, если бот 'завис'."
    ]

    if is_super_admin_user:
        help_text_parts.extend([
            "\n👑 <b>Команды Супер-Администратора:</b>\n",
            "▫️ /add_banned_word <i>слово</i> - Добавить слово в глобальный черный список.",
            "▫️ /remove_banned_word <i>слово</i> - Удалить слово из черного списка.",
            "▫️ /list_banned_words - Показать текущий черный список слов.\n",
            "▫️ /admin_stats - Показать статистику использования бота.",
            "▫️ /list_users <i>N</i> - Показать последних N зарегистрированных пользователей (по умолчанию 10)."
        ])

    await message.answer("\n".join(help_text_parts), reply_markup=get_main_keyboard(), parse_mode="HTML")


@router.message(Command("cancel"))
@router.message(F.text.lower() == "отмена")
async def cmd_cancel(message: types.Message, state: FSMContext):
    current_fsm_state = await state.get_state()
    if current_fsm_state is None:
        await message.answer("Нет активного действия для отмены.", reply_markup=get_main_keyboard())
        return

    logger.info(f"User {message.from_user.id} cancelled state {current_fsm_state}")
    await state.clear()
    await message.answer("Действие отменено.", reply_markup=get_main_keyboard())