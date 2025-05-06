# filters/admin.py
from aiogram.filters import Filter
from aiogram.types import Message, CallbackQuery
from loader import get_db


class IsAdmin(Filter):
    async def __call__(self, event: Message | CallbackQuery) -> bool:
        db = get_db()
        user_id = event.from_user.id

        admin_status = db.fetchone("SELECT is_admin FROM bot_users WHERE user_id = ?", (user_id,))

        # Проверяем, что запись найдена и is_admin == 1
        return bool(admin_status and admin_status[0] == 1)