# models/database.py
import sqlite3
import logging
from config import SUPER_ADMIN_ID # Предполагаем, что SUPER_ADMIN_ID в config.py


logger = logging.getLogger(__name__)


class Database:
    def __init__(self, db_name):
        self.db_name = db_name
        self.connection = sqlite3.connect(db_name)
        self.cursor = self.connection.cursor()
        self._init_db()

    def _init_db(self):
        """Инициализация таблиц БД"""

        # Попытка добавить новые колонки, если их нет (для плавной миграции существующей БД)
        # Это будет работать, только если таблицы уже существуют. При первой инициализации это не нужно.
        # Для чистого старта проще удалить старый файл БД.
        # Но если вы хотите попытаться обновить существующую, раскомментируйте и адаптируйте:
        # try:
        #     self.cursor.execute("ALTER TABLE channels ADD COLUMN user_id INTEGER NOT NULL DEFAULT 0") # DEFAULT 0 - временная заглушка
        #     self.connection.commit()
        #     logger.info("SUCCESS: Column 'user_id' added to 'channels' table.")
        # except sqlite3.OperationalError as e:
        #     if "duplicate column name" in str(e).lower():
        #         logger.info("INFO: Column 'user_id' already exists in 'channels' table.")
        #     else:
        #         logger.warning(f"Could not add 'user_id' to 'channels'. Error: {e}")
        #
        # try: # Для templates, user_id может быть NULL для старых общих, или 0 для новых общих
        #     self.cursor.execute("ALTER TABLE templates ADD COLUMN user_id INTEGER DEFAULT 0") # 0 для общих
        #     self.connection.commit()
        #     logger.info("SUCCESS: Column 'user_id' added to 'templates' table.")
        # except sqlite3.OperationalError as e:
        #     if "duplicate column name" in str(e).lower():
        #         logger.info("INFO: Column 'user_id' already exists in 'templates' table.")
        #     else:
        #         logger.warning(f"Could not add 'user_id' to 'templates'. Error: {e}")

        self.cursor.executescript("""
            CREATE TABLE IF NOT EXISTS bot_users ( -- Таблица для пользователей бота
                user_id INTEGER PRIMARY KEY,
                username TEXT,
                first_name TEXT,
                last_name TEXT,
                is_admin BOOLEAN DEFAULT FALSE, -- Для админских функций бота
                created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
                last_seen_at DATETIME DEFAULT CURRENT_TIMESTAMP
            );

            CREATE TABLE IF NOT EXISTS channels (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id INTEGER NOT NULL,           -- ID пользователя, добавившего канал
                channel_id INTEGER NOT NULL,        -- Telegram ID канала
                title TEXT NOT NULL,
                FOREIGN KEY(user_id) REFERENCES bot_users(user_id) ON DELETE CASCADE,
                UNIQUE(user_id, channel_id)      -- Пользователь не может добавить один и тот же канал дважды
            );

            CREATE TABLE IF NOT EXISTS posts (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id INTEGER NOT NULL,           -- ID пользователя, создавшего пост
                channel_id INTEGER NOT NULL,        -- Telegram ID канала, в который был сделан пост
                                                    -- Для связи с конкретным "подключением" канала, можно использовать
                                                    -- channel_db_id INTEGER REFERENCES channels(id)
                content TEXT,
                media TEXT,
                media_type TEXT,
                publish_time DATETIME NOT NULL,
                status TEXT NOT NULL,
                message_id INTEGER,
                created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY(user_id) REFERENCES bot_users(user_id) ON DELETE CASCADE
            );

            CREATE TABLE IF NOT EXISTS templates (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id INTEGER NOT NULL DEFAULT 0, -- 0 для общих/системных, >0 для пользовательских
                name TEXT NOT NULL,
                content TEXT NOT NULL,
                media TEXT,
                media_type TEXT,
                category TEXT, 
                -- Если user_id=0 ссылается на фиктивного юзера в bot_users или не ссылается вообще
                -- FOREIGN KEY(user_id) REFERENCES bot_users(user_id) ON DELETE CASCADE, (если 0 не будет в bot_users, то FK нарушится)
                -- Лучше убрать FK для user_id=0 или создать запись для системного пользователя
                UNIQUE(user_id, name) -- Имя шаблона уникально в рамках пользователя (или для общих, если user_id=0)
            );
        """)
        self.connection.commit()

        # Создание уникальных индексов для шаблонов (если не созданы)
        # Общие шаблоны (user_id = 0) должны иметь уникальные имена
        try:
            self.cursor.execute("""
                CREATE UNIQUE INDEX IF NOT EXISTS idx_templates_common_name 
                ON templates(name) WHERE user_id = 0;
            """)
            # Пользовательские шаблоны: пара (user_id, name) уникальна (уже покрывается UNIQUE(user_id, name) выше,
            # но частичный индекс может быть более явным, если бы основное ограничение было другим)
            # self.cursor.execute("""
            #     CREATE UNIQUE INDEX IF NOT EXISTS idx_templates_user_name
            #     ON templates(user_id, name) WHERE user_id != 0;
            # """)
            self.connection.commit()
        except sqlite3.Error as e:
            logger.warning(f"Could not create unique indexes for templates: {e}")

    def execute(self, query, params=None, commit=False):
        try:
            self.cursor.execute(query, params or ())
            if commit:
                self.connection.commit()
            return self.cursor
        except sqlite3.Error as e:
            logger.error(f"Database error: {e} on query: {query} with params: {params}", exc_info=True)
            raise

    def fetchone(self, query, params=None):
        return self.execute(query, params).fetchone()

    def fetchall(self, query, params=None):
        return self.execute(query, params).fetchall()

    def close(self):
        if self.connection:
            self.connection.close()
            self.connection = None
            logger.info("Database connection closed by Database.close()")

    # Метод для добавления/обновления пользователя
    def upsert_user(self, user_id: int, username: str | None, first_name: str | None, last_name: str | None):
        is_super_admin = (user_id == SUPER_ADMIN_ID)  # Проверяем, является ли пользователь супер-админом

        try:
            # Сначала проверяем, существует ли пользователь
            existing_user = self.fetchone("SELECT is_admin FROM bot_users WHERE user_id = ?", (user_id,))

            if existing_user:
                # Пользователь существует, обновляем его данные
                # Если он супер-админ, убедимся, что is_admin = 1.
                # Если он не супер-админ, НЕ МЕНЯЕМ его текущий is_admin статус (если он был назначен вручную)
                # Либо можно решить всегда сбрасывать is_admin, если он не SUPER_ADMIN_ID - зависит от вашей логики.
                # Текущий вариант: супер-админ всегда админ, статус других не трогаем при обновлении,
                # если только он не был назначен ранее.

                current_is_admin_db = existing_user[0]
                new_is_admin_status = 1 if is_super_admin else current_is_admin_db  # Супер-админ всегда админ, остальных не понижаем автоматом

                self.execute(
                    """UPDATE bot_users SET
                           username = ?,
                           first_name = ?,
                           last_name = ?,
                           is_admin = ?, 
                           last_seen_at = CURRENT_TIMESTAMP
                       WHERE user_id = ?""",
                    (username, first_name, last_name, new_is_admin_status, user_id),
                    commit=True
                )
                logger.debug(f"User {user_id} updated. Is admin: {new_is_admin_status == 1}")
            else:
                # Пользователь не существует, вставляем новую запись
                # Устанавливаем is_admin в зависимости от того, является ли он супер-админом
                self.execute(
                    """INSERT INTO bot_users (user_id, username, first_name, last_name, is_admin, last_seen_at)
                       VALUES (?, ?, ?, ?, ?, CURRENT_TIMESTAMP)""",
                    (user_id, username, first_name, last_name, 1 if is_super_admin else 0),
                    commit=True
                )
                logger.debug(f"User {user_id} inserted. Is admin: {is_super_admin}")

        except Exception as e:
            logger.error(f"Error upserting user {user_id}: {e}", exc_info=True)