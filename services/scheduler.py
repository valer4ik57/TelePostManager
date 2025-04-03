from apscheduler.schedulers.asyncio import AsyncIOScheduler
from models.database import Database
from config import DATABASE_NAME
from aiogram import Bot
from datetime import datetime

scheduler = AsyncIOScheduler()


def add_scheduled_job(bot: Bot, data: dict):
    """Добавление отложенной публикации"""
    scheduler.add_job(
        send_scheduled_post,
        'date',
        run_date=data['publish_time'],
        args=(bot, data),
        id=f"post_{data['channel_id']}_{data['publish_time'].timestamp()}"
    )


async def send_scheduled_post(bot: Bot, data: dict):
    """Отправка запланированного поста"""
    try:
        db = Database(DATABASE_NAME)

        if data.get('media'):
            await bot.send_photo(
                chat_id=data['channel_id'],
                photo=data['media'],
                caption=data['content']
            )
        else:
            await bot.send_message(
                chat_id=data['channel_id'],
                text=data['content']
            )

        # Обновление статуса
        db.cursor.execute(
            "UPDATE posts SET status = 'published' WHERE channel_id = ? AND publish_time = ?",
            (data['channel_id'], data['publish_time'])
        )
        db.connection.commit()

    except Exception as e:
        db.cursor.execute(
            "UPDATE posts SET status = 'failed' WHERE channel_id = ? AND publish_time = ?",
            (data['channel_id'], data['publish_time'])
        )
        db.connection.commit()
        print(f"Ошибка публикации: {str(e)}")