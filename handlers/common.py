# handlers/common.py
from aiogram import Router, F, types
from aiogram.filters import Command
from aiogram.fsm.context import FSMContext
import logging
from config import SUPER_ADMIN_ID # Предполагаем, что SUPER_ADMIN_ID в config.py


# Импортируем из loader и utils
from loader import get_db  # Убираем bot, если он не используется напрямую здесь
from bot_utils import get_main_keyboard

router = Router()
logger = logging.getLogger(__name__)


@router.message(Command("start"))
async def cmd_start(message: types.Message, state: FSMContext):
    db = get_db()
    user = message.from_user
    try:
        # upsert_user теперь сам установит is_admin для SUPER_ADMIN_ID
        db.upsert_user(
            user_id=user.id,
            username=user.username,
            first_name=user.first_name,
            last_name=user.last_name
        )
        logger.info(f"User {user.id} ({user.username or 'NoUsername'}) started/updated. SUPER_ADMIN_ID: {SUPER_ADMIN_ID}")
    except Exception as e:
        logger.error(f"Failed to upsert user {user.id} on /start: {e}", exc_info=True)

        # Можно отправить пользователю сообщение об ошибке, если это критично

    current_fsm_state = await state.get_state()  # Переименовал для ясности
    if current_fsm_state is not None:
        await state.clear()
        # Сообщение о сбросе состояния лучше отправлять только если оно действительно было
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
    help_text = (
        "📋 <b>Основные команды и функции:</b>\n\n"
        "▫️ /start - Перезапустить бота и показать главное меню.\n"
        "▫️ /help - Показать это сообщение.\n\n"
        "▫️ <b>📝 Создать пост</b> - Начать процесс создания нового поста для канала.\n"
        "▫️ <b>📢 Мои каналы</b> - Просмотреть список ваших подключенных каналов.\n"
        "▫️ <b>➕ Добавить канал</b> - Подключить новый канал для управления.\n"
        "▫️ <b>📚 Шаблоны</b> - Управлять шаблонами для постов (общие + ваши личные).\n"
        "▫️ <b>📜 История</b> - Посмотреть историю ваших публикаций.\n\n"
        "⚙️ <b>Как добавить канал:</b>\n"
        "1. Нажмите «➕ Добавить канал».\n"
        "2. Сделайте этого бота администратором вашего канала с правом на публикацию сообщений.\n"
        "3. Перешлите любое сообщение из вашего канала в чат с ботом.\n\n"
        "Если что-то не работает:\n"
        "1. Убедитесь, что бот является администратором в нужном канале и имеет права на публикацию.\n"
        "2. Попробуйте перезапустить бота командой /start."
    )
    await message.answer(help_text, reply_markup=get_main_keyboard(), parse_mode="HTML")


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