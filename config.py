import os
from dotenv import load_dotenv

load_dotenv()

BOT_TOKEN = os.getenv("BOT_TOKEN")
DATABASE_NAME = "database.db"
BANNED_WORDS_FILE = "banned_words.txt"