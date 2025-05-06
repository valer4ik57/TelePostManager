# config.py
import os
from dotenv import load_dotenv

load_dotenv()

BOT_TOKEN = os.getenv("BOT_TOKEN")
DATABASE_NAME = os.getenv("DATABASE_NAME", "database.db") # Значение по умолчанию, если не задано
BANNED_WORDS_FILE = os.getenv("BANNED_WORDS_FILE", "banned_words.txt") # Значение по умолчанию
SUPER_ADMIN_ID = int(os.getenv("SUPER_ADMIN_ID", 0)) # 0 если не задано, чтобы не было ошибки


