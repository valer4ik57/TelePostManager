import os
from dotenv import load_dotenv
from aiogram import Bot, Dispatcher
from apscheduler.schedulers.asyncio import AsyncIOScheduler

from models.database import Database
from services.content_filter import ContentFilter # Опечатка исправлена на ContentFilter
from config import BOT_TOKEN, DATABASE_NAME, BANNED_WORDS_FILE

load_dotenv()

# Инициализация бота и диспетчера
bot = Bot(token=BOT_TOKEN)
dp = Dispatcher()

# Класс-обертка для управления соединением с БД
class DBManager:
    def __init__(self, db_name_param): # Изменено имя параметра во избежание путаницы
        self._db_name = db_name_param
        self.db_instance = None # Переименовано для ясности

    async def startup(self):
        """Инициализирует соединение с базой данных."""
        self.db_instance = Database(self._db_name)
        # logger.info("Database connected.") # Логирование лучше делать в main.py или специализированном логгере

    async def shutdown(self):
        """Закрывает соединение с базой данных."""
        if self.db_instance and self.db_instance.connection:
            self.db_instance.close() # Используем метод close из класса Database
            # logger.info("Database disconnected.")

db_manager = DBManager(DATABASE_NAME)

# Инициализация планировщика задач APScheduler
scheduler = AsyncIOScheduler(timezone="Europe/Moscow") # Рекомендуется указать таймзону

# Инициализация фильтра контента
content_filter_instance = ContentFilter(BANNED_WORDS_FILE) # Переименовано для ясности

def get_db() -> Database:
    """Возвращает активный экземпляр подключения к базе данных."""
    if db_manager.db_instance is None:
        # Это состояние не должно возникать в нормально работающем боте после startup
        raise RuntimeError("Database is not initialized. Call db_manager.startup() first.")
    return db_manager.db_instance

content_filter = content_filter_instance