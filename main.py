# main.py
import asyncio
import logging  # Используем стандартный logging
from loader import bot, dp, db_manager, scheduler  # Импортируем из loader
from handlers import common, channels, posts, history, templates


async def main():
    # Настройка логирования
    logging.basicConfig(level=logging.INFO, format="%(asctime)s - %(levelname)s - %(name)s - %(message)s")

    # Подключение к БД при старте
    await db_manager.startup()

    # Подключение роутеров
    dp.include_router(common.router)
    dp.include_router(channels.router)
    dp.include_router(posts.router)
    dp.include_router(history.router)
    dp.include_router(templates.router)

    # Запуск планировщика
    scheduler.start()

    try:
        print("Бот запускается...")
        await dp.start_polling(bot)
    except Exception as e:
        logging.error(f"Ошибка при запуске бота: {e}", exc_info=True)
    finally:
        logging.info("Бот останавливается...")
        await bot.session.close()
        scheduler.shutdown(wait=False)  # wait=False чтобы не блокировать завершение, если есть задачи
        await db_manager.shutdown()  # Закрытие соединения с БД
        logging.info("Бот остановлен.")


if __name__ == "__main__":
    asyncio.run(main())