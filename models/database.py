import sqlite3
import logging
from config import SUPER_ADMIN_ID

logger = logging.getLogger(__name__)


class Database:
    def __init__(self, db_name):
        self.db_name = db_name
        self.connection = sqlite3.connect(db_name, check_same_thread=False)  # check_same_thread=False для APScheduler
        self.cursor = self.connection.cursor()
        self._init_db()

    def _init_db(self):
        self.cursor.executescript("""
                                  CREATE TABLE IF NOT EXISTS bot_users
                                  (
                                      user_id
                                      INTEGER
                                      PRIMARY
                                      KEY,
                                      username
                                      TEXT,
                                      first_name
                                      TEXT,
                                      last_name
                                      TEXT,
                                      is_admin
                                      BOOLEAN
                                      DEFAULT
                                      FALSE,
                                      created_at
                                      DATETIME
                                      DEFAULT
                                      CURRENT_TIMESTAMP,
                                      last_seen_at
                                      DATETIME
                                      DEFAULT
                                      CURRENT_TIMESTAMP
                                  );

                                  CREATE TABLE IF NOT EXISTS channels
                                  (
                                      id
                                      INTEGER
                                      PRIMARY
                                      KEY
                                      AUTOINCREMENT,
                                      user_id
                                      INTEGER
                                      NOT
                                      NULL,
                                      channel_id
                                      INTEGER
                                      NOT
                                      NULL,
                                      title
                                      TEXT
                                      NOT
                                      NULL,
                                      FOREIGN
                                      KEY
                                  (
                                      user_id
                                  ) REFERENCES bot_users
                                  (
                                      user_id
                                  ) ON DELETE CASCADE,
                                      UNIQUE
                                  (
                                      user_id,
                                      channel_id
                                  )
                                      );

                                  CREATE TABLE IF NOT EXISTS posts
                                  (
                                      id
                                      INTEGER
                                      PRIMARY
                                      KEY
                                      AUTOINCREMENT,
                                      user_id
                                      INTEGER
                                      NOT
                                      NULL,
                                      channel_id
                                      INTEGER
                                      NOT
                                      NULL,
                                      content
                                      TEXT,
                                      media
                                      TEXT,
                                      media_type
                                      TEXT,
                                      publish_time
                                      DATETIME
                                      NOT
                                      NULL,
                                      status
                                      TEXT
                                      NOT
                                      NULL,
                                      message_id
                                      INTEGER,
                                      created_at
                                      DATETIME
                                      DEFAULT
                                      CURRENT_TIMESTAMP,
                                      FOREIGN
                                      KEY
                                  (
                                      user_id
                                  ) REFERENCES bot_users
                                  (
                                      user_id
                                  ) ON DELETE CASCADE
                                      );

                                  CREATE TABLE IF NOT EXISTS templates
                                  (
                                      id
                                      INTEGER
                                      PRIMARY
                                      KEY
                                      AUTOINCREMENT,
                                      user_id
                                      INTEGER
                                      NOT
                                      NULL
                                      DEFAULT
                                      0,
                                      name
                                      TEXT
                                      NOT
                                      NULL,
                                      content
                                      TEXT, -- Разрешаем NULL, если есть только медиа
                                      media
                                      TEXT,
                                      media_type
                                      TEXT,
                                      category
                                      TEXT,
                                      UNIQUE
                                  (
                                      user_id,
                                      name
                                  )
                                      );
                                  """)
        self.connection.commit()
        # Индекс для user_id=0 и name (Общие шаблоны)
        try:
            self.cursor.execute("""
                                CREATE UNIQUE INDEX IF NOT EXISTS idx_templates_common_name
                                    ON templates(name) WHERE user_id = 0;
                                """)
            # Индекс для user_id != 0 и name (Личные шаблоны)
            # Он уже покрывается UNIQUE(user_id, name), но для SQLite < 3.36.0
            # частичные индексы могут быть полезны, если бы основное ограничение было другим.
            # В данном случае существующее UNIQUE(user_id, name) достаточно.
            self.connection.commit()
        except sqlite3.Error as e:
            # "duplicate index name" может возникнуть, если индекс уже есть, это нормально
            if "duplicate index name" not in str(e).lower():
                logger.warning(f"Could not create unique index for common templates (возможно, уже существует): {e}")

    def execute(self, query, params=None, commit=False):
        try:
            self.cursor.execute(query, params or ())
            if commit:
                self.connection.commit()
            return self.cursor
        except sqlite3.Error as e:
            logger.error(f"Database error: {e} on query: {query} with params: {params}", exc_info=True)
            self.connection.rollback()  # Откатываем транзакцию в случае ошибки
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

    def upsert_user(self, user_id: int, username: str | None, first_name: str | None, last_name: str | None):
        is_super_admin_by_id = (user_id == SUPER_ADMIN_ID)

        try:
            existing_user = self.fetchone("SELECT is_admin FROM bot_users WHERE user_id = ?", (user_id,))

            if existing_user:
                current_is_admin_db_flag = existing_user[0]
                # Супер-админ всегда должен быть админом.
                # Если пользователь уже админ (не супер-админ), не снимаем с него админку.
                new_is_admin_status = 1 if is_super_admin_by_id or current_is_admin_db_flag == 1 else 0

                self.execute(
                    """UPDATE bot_users
                       SET username     = ?,
                           first_name   = ?,
                           last_name    = ?,
                           is_admin     = ?,
                           last_seen_at = CURRENT_TIMESTAMP
                       WHERE user_id = ?""",
                    (username, first_name, last_name, new_is_admin_status, user_id),
                    commit=True
                )
                logger.debug(f"User {user_id} updated. Is now admin: {new_is_admin_status == 1}")
            else:
                # Новый пользователь: админ, только если это SUPER_ADMIN_ID
                new_user_is_admin_status = 1 if is_super_admin_by_id else 0
                self.execute(
                    """INSERT INTO bot_users (user_id, username, first_name, last_name, is_admin, last_seen_at)
                       VALUES (?, ?, ?, ?, ?, CURRENT_TIMESTAMP)""",
                    (user_id, username, first_name, last_name, new_user_is_admin_status),
                    commit=True
                )
                logger.debug(f"User {user_id} inserted. Is admin: {new_user_is_admin_status == 1}")

        except Exception as e:
            logger.error(f"Error upserting user {user_id}: {e}", exc_info=True)