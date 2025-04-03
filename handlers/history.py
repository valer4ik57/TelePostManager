import sqlite3  # Добавить эту строку в начало файла
from datetime import datetime
from aiogram import Router, types, F
from aiogram.filters import Command
from models.database import Database
from config import DATABASE_NAME

router = Router()
db = Database(DATABASE_NAME)


@router.message(Command("history"))
async def show_history(message: types.Message):
    """Показ последних 5 публикаций"""
    try:
        posts = db.cursor.execute(
            """SELECT 
                posts.id, 
                channels.title, 
                posts.content, 
                posts.publish_time, 
                posts.status 
            FROM posts
            LEFT JOIN channels 
                ON posts.channel_id = channels.channel_id
            ORDER BY posts.publish_time DESC 
            LIMIT 5"""
        ).fetchall()

        if not posts:
            return await message.answer("📭 История публикаций пуста")

        response = "📜 Последние 5 публикаций:\n\n"
        for post in posts:
            # Исправленный формат времени
            publish_time = datetime.fromisoformat(post[3]).strftime('%d.%m.%Y %H:%M')

            response += (
                f"🆔 ID: {post[0]}\n"
                f"📢 Канал: {post[1]}\n"
                f"⏰ Время: {publish_time}\n"
                f"📝 Текст: {post[2][:50]}...\n"
                f"🔸 Статус: {post[4]}\n\n"
            )

        await message.answer(response)

    except sqlite3.Error as e:
        await message.answer(f"❌ Ошибка базы данных: {str(e)}")
    except Exception as e:
        await message.answer(f"❌ Неизвестная ошибка: {str(e)}")

@router.message(F.text == "📜 История")
async def show_history_handler(message: types.Message):
    await show_history(message)  # Используем существующую функцию