# loader.py
import os
from dotenv import load_dotenv
from aiogram import Bot, Dispatcher
from apscheduler.schedulers.asyncio import AsyncIOScheduler
import sqlite3 # Для аннотации типов, если понадобится
from models.database import Database
from services.content_filter import ContentFilter
from config import BOT_TOKEN, DATABASE_NAME, BANNED_WORDS_FILE

# Загрузка переменных окружения
load_dotenv()

# Инициализация бота и диспетчера
bot = Bot(token=BOT_TOKEN)
dp = Dispatcher()

# Инициализация базы данных
# Обертка для безопасного закрытия соединения, хотя Database класс уже может это делать
class DBManager:
    def __init__(self, db_name):
        self._db_name = db_name
        self.db = None

    async def startup(self):
        self.db = Database(self._db_name)
        print("Database connected.")

    async def shutdown(self):
        if self.db and self.db.connection:
            self.db.connection.close()
            print("Database disconnected.")

db_manager = DBManager(DATABASE_NAME)
# Прямой доступ к экземпляру Database после стартапа
# Будем использовать db_manager.db в хэндлерах
# Чтобы избежать прямого импорта db = Database() повсюду,
# передадим db_manager.db или будем импортировать db_manager из loader

# Инициализация планировщика
scheduler = AsyncIOScheduler()

# Инициализация фильтра контента
content_filter = ContentFilter(BANNED_WORDS_FILE)

# Можно добавить функцию для получения текущего экземпляра БД
def get_db():
    if db_manager.db is None:
        # Этого не должно происходить в работающем боте, если startup был вызван
        # но как предохранитель или для тестов
        raise RuntimeError("Database is not initialized. Call db_manager.startup() first.")
    return db_manager.db