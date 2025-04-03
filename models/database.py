import sqlite3


class Database:
    def __init__(self, db_name):
        self.connection = sqlite3.connect(db_name)
        self.cursor = self.connection.cursor()
        self._init_db()

    def _init_db(self):
        """Инициализация таблиц БД"""
        self.cursor.executescript("""
            -- Создание таблицы каналов
            CREATE TABLE IF NOT EXISTS channels (
                id INTEGER PRIMARY KEY,
                channel_id INTEGER UNIQUE,
                title TEXT
            );

            -- Создание таблицы постов
            CREATE TABLE IF NOT EXISTS posts (
                id INTEGER PRIMARY KEY,
                channel_id INTEGER,
                content TEXT,
                media TEXT,
                publish_time DATETIME,
                status TEXT,
                created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY(channel_id) REFERENCES channels(channel_id)
            );
        """)
        self.connection.commit()