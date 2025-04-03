import asyncio
from aiogram import Bot, Dispatcher, types
from config import BOT_TOKEN
from handlers import common, channels, posts, history, templates  # Добавлен импорт common
from services.scheduler import scheduler


async def main():
    bot = Bot(token=BOT_TOKEN)
    dp = Dispatcher()

    # Подключение ВСЕХ роутеров
    dp.include_router(common.router)  # Добавлена эта строка
    dp.include_router(channels.router)
    dp.include_router(posts.router)
    dp.include_router(history.router)
    dp.include_router(templates.router)

    scheduler.start()

    try:
        await dp.start_polling(bot)
    finally:
        await bot.session.close()
        scheduler.shutdown()


if __name__ == "__main__":
    asyncio.run(main())