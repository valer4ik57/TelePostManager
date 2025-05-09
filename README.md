# 🤖 TelePost Manager: Ваш Telegram-ассистент для управления каналами

**TelePost Manager** — это мощный и удобный Telegram-бот, предназначенный для централизованного управления публикациями в ваших Telegram-каналах. Автоматизируйте создание постов, планируйте публикации, используйте шаблоны и контролируйте контент — всё в одном интуитивно понятном интерфейсе.

---

## 📌 Почему это удобно?

- **🌐 Все каналы под рукой**  
  Больше не нужно переключаться между чатами.  
- **⏱ Экономия времени**  
  Публикуйте в 10 каналах одновременно за 2 минуты.  
- **🔐 Безопасность**  
  Только вы решаете, какие каналы подключить.  

---

## 🌟 Ключевые возможности

*   **🎛️ Централизованное управление каналами:**
    *   **Многопользовательский режим:** Каждый пользователь управляет своим независимым списком каналов. Ваши каналы видны и доступны только вам.
    *   **Простое подключение:** Легко добавляйте каналы, сделав бота администратором с правом публикации.
    *   **Быстрый доступ:** Все подключенные вами каналы всегда под рукой для создания и планирования постов.

*   **📝 Гибкое создание постов:**
    *   **Публикация в выбранные каналы:** Создавайте пост один раз и публикуйте его в один или несколько ваших каналов.
    *   **Поддержка текста и медиа:** Публикуйте текстовые посты, а также посты с фотографиями и видео.
    *   **Предпросмотр:** Перед публикацией вы всегда можете увидеть, как будет выглядеть ваш пост.

*   **📅 Планирование публикаций:**
    *   **Отложенный постинг:** Запланируйте выход ваших постов на любую дату и время. Бот автоматически опубликует их в указанный срок.
    *   **Публикация "сейчас":** Для немедленной отправки контента.

*   **📄 Шаблоны постов:**
    *   **Общие и личные шаблоны:** Используйте предустановленные общие шаблоны или создавайте свои личные для быстрого формирования однотипных постов.
    *   **Поддержка переменных:** Вставляйте в шаблоны динамические данные, такие как `{дата}`, `{время}`, `{текст_новости}`, `{автор}`.
    *   **Медиа в шаблонах:** Сохраняйте шаблоны не только с текстом, но и с прикрепленными фото или видео.
    *   **Администрирование общих шаблонов:** Администратор бота может создавать и (в будущем) управлять общими шаблонами, доступными всем пользователям.

*   **🛡️ Контроль контента:**
    *   **Фильтр запрещенных слов:** Бот автоматически проверяет текст поста (включая текст из шаблонов) на наличие слов из настраиваемого стоп-листа.

*   **📜 История публикаций:**
    *   **Отслеживание постов:** Просматривайте историю своих опубликованных и запланированных постов с указанием статуса, канала и времени публикации.
    *   **Пагинация:** Удобный просмотр большого количества записей.

---

## 🚀 Технологический стек

*   **Язык программирования:** Python 3.x
*   **Фреймворк для Telegram-бота:** [aiogram 3.x](https://aiogram.dev/)
*   **База данных:** SQLite (легковесная, не требует отдельного сервера)
*   **Планировщик задач (отложенные посты):** APScheduler
*   **Логирование:** Модуль `logging` Python

---

## 🎮 Начало работы

1.  **Найдите бота в Telegram:** [@TelePostManager_bot](https://t.me/TelePostManager_bot)
2.  **Отправьте команду `/start`** для инициализации и регистрации в системе.
3.  **Добавьте ваши каналы:**
    *   Нажмите кнопку "➕ Добавить канал" в главном меню.
    *   Убедитесь, что бот добавлен как администратор в ваш Telegram-канал с правом на публикацию сообщений.
    *   Перешлите любое сообщение из вашего канала в чат с ботом. Канал будет добавлен в ваш личный список.
4.  **Создавайте и публикуйте посты:**
    *   Используйте кнопку "📝 Создать пост" для запуска мастера создания публикаций.
    *   Выбирайте каналы, используйте шаблоны, прикрепляйте медиа и планируйте время выхода.

---


**🤖 Попробуйте TelePost Manager прямо сейчас: [@TelePostManager_bot](https://t.me/TelePostManager_bot)!**
