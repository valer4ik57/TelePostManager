import asyncio
import logging
from loader import bot, dp, db_manager, scheduler
from handlers import (
    common,
    channels,
    posts,
    history,
    templates,
    admin_features,
    scheduled_posts
)


async def main():
    logging.basicConfig(level=logging.INFO, format="%(asctime)s - %(levelname)s - %(name)s - %(message)s")

    await db_manager.startup()

    dp.include_router(common.router)
    dp.include_router(channels.router)
    dp.include_router(posts.router)
    dp.include_router(history.router)
    dp.include_router(templates.router)
    dp.include_router(admin_features.router)
    dp.include_router(scheduled_posts.router)

    scheduler.start()

    try:
        print("Бот запускается...")
        await dp.start_polling(bot)
    except Exception as e:
        logging.error(f"Ошибка при запуске бота: {e}", exc_info=True)
    finally:
        logging.info("Бот останавливается...")
        if bot.session and not bot.session.closed:
             await bot.session.close()
        scheduler.shutdown(wait=False)
        await db_manager.shutdown()
        logging.info("Бот остановлен.")


if __name__ == "__main__":
    asyncio.run(main())