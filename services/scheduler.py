# services/scheduler.py
from datetime import datetime
from apscheduler.schedulers.asyncio import AsyncIOScheduler  # Для аннотации типа
from aiogram import Bot
import logging  # Для логирования

# Импортируем нужные функции и экземпляры
from loader import get_db
from bot_utils import notify_post_published, notify_user

logger = logging.getLogger(__name__)  # Логгер для этого модуля


def add_scheduled_job(scheduler_instance: AsyncIOScheduler, bot_instance: Bot, data: dict):
    """
    Добавление отложенной публикации.
    data должен содержать:
    'post_db_id': int,      # ID поста из нашей базы данных
    'publish_time': datetime, # Объект datetime для времени публикации
    'channel_id': int,
    'content': str,
    'media': str | None,    # Optional[str] - file_id медиа
    'media_type': str | None, # <--- Добавляем media_type в docstring и ожидаем его в data
    'user_id': int,         # ID пользователя для уведомления
    'channel_title': str    # Название канала для уведомления
    """
    # Убедимся, что все необходимые ключи есть в data
    required_keys = ['post_db_id', 'publish_time', 'channel_id', 'user_id', 'channel_title']
    for key in required_keys:
        if key not in data:
            if data.get('media') and 'media_type' not in data:  # Если есть медиа, должен быть и тип
                logger.error(f"Ошибка планирования: отсутствует ключ '{key}' в данных задачи.")
            if 'user_id' in data:
                async def send_error_notification():
                    await notify_user(bot_instance, data['user_id'],
                                      f"Произошла внутренняя ошибка при планировании поста. Ключ {key} отсутствует.")
                # Рекомендация: лучше, чтобы эта логика была в вызывающем коде (handlers/posts.py),
                # чтобы он мог корректно обработать await.
                # Здесь просто логируем и выходим.
            return

    # Используем post_db_id для уникальности ID задачи
    # ЭТУ СТРОКУ НУЖНО ПЕРЕМЕСТИТЬ СЮДА, ПЕРЕД TRY:
    job_id = f"post_{data['post_db_id']}"

    try:
        scheduler_instance.add_job(
            send_scheduled_post,
            trigger='date',  # Явно указываем trigger
            run_date=data['publish_time'],  # Должен быть datetime объектом
            args=(bot_instance, data),  # Передаем инстанс бота и данные
            id=job_id,
            name=f"Post to {data['channel_title']} at {data['publish_time']}",  # Имя задачи для логов планировщика
            replace_existing=True  # Заменять, если задача с таким ID уже есть
        )
        logger.info(
            f"Job {job_id} (Post ID: {data['post_db_id']}) added for {data['publish_time']} to channel {data['channel_title']}")
    except Exception as e:
        logger.error(f"Ошибка добавления задачи {job_id} в планировщик: {e}", exc_info=True)
        # Уведомляем пользователя об ошибке планирования
        if 'user_id' in data:
            async def send_error_notification():  # Обертка для await
                await notify_user(bot_instance, data['user_id'],
                                  f"❌ Произошла ошибка при планировании вашего поста для канала «{data['channel_title']}». Пожалуйста, попробуйте снова или обратитесь к администратору.")
            # Запуск асинхронной функции (аналогично выше)
            # asyncio.create_task(send_error_notification())


async def send_scheduled_post(bot_instance: Bot, data: dict):
    """Отправка запланированного поста. Вызывается планировщиком."""
    db = get_db()

    # Извлекаем данные, предполагая, что они все есть (проверено в add_scheduled_job)
    post_db_id = data['post_db_id']
    user_id_to_notify = data['user_id']
    channel_id = data['channel_id']
    channel_title = data['channel_title']
    content_to_send = data.get('content', '')  # Может быть пустым, если только медиа
    media_to_send = data.get('media')
    media_type_to_send = data.get('media_type') # <--- Извлекаем тип


    post_status_final = "failed"  # Статус по умолчанию, если что-то пойдет не так
    published_message_id_in_channel = None

    logger.info(f"Attempting to send scheduled post (DB ID: {post_db_id}) to channel {channel_title} ({channel_id})")

    try:
        # Проверяем, не был ли пост уже опубликован или отменен (на всякий случай)
        current_post_status_query = db.fetchone("SELECT status FROM posts WHERE id = ?", (post_db_id,))
        if current_post_status_query and current_post_status_query[0] != 'scheduled':
            logger.warning(
                f"Post (DB ID: {post_db_id}) is not in 'scheduled' state (current: {current_post_status_query[0]}). Skipping.")
            return  # Ничего не делаем, если статус уже не 'scheduled'

        published_message = None
        if media_to_send:
            if media_type_to_send == "photo":  # <--- Используем media_type
                published_message = await bot_instance.send_photo(
                    chat_id=channel_id, photo=media_to_send, caption=content_to_send, parse_mode="HTML"
                )
            elif media_type_to_send == "video":  # <--- Используем media_type
                published_message = await bot_instance.send_video(
                    chat_id=channel_id, video=media_to_send, caption=content_to_send, parse_mode="HTML"
                )
            else:
                logger.warning(
                    f"Неизвестный или отсутствующий media_type ({media_type_to_send}) для медиа {media_to_send} поста {post_db_id}.")
                # Можно попытаться отправить как документ или просто текст с упоминанием медиа
                # Для простоты, если тип не определен, а контент есть, отправим только контент.
                # Если контента нет, а только неизвестное медиа - это проблема.
                if content_to_send:  # Если есть текст, отправляем его
                    published_message = await bot_instance.send_message(
                        chat_id=channel_id,
                        text=f"{content_to_send}\n[Медиафайл не удалось обработать: {media_to_send}]"
                    )
                else:  # Если нет ни текста, ни понятного медиа
                    raise ValueError(
                        f"Не удалось отправить пост {post_db_id}: нет текста и неизвестный тип медиа {media_to_send}")
        else:  # Только текст
            published_message = await bot_instance.send_message(
                chat_id=channel_id,
                text=content_to_send,
                parse_mode="HTML"  # <--- HTML
            )

        post_status_final = "published"
        published_message_id_in_channel = published_message.message_id if published_message else None

        logger.info(
            f"Scheduled post (DB ID: {post_db_id}) successfully sent to channel {channel_title}. Message ID in channel: {published_message_id_in_channel}")

        if user_id_to_notify and published_message_id_in_channel:
            await notify_post_published(bot_instance, user_id_to_notify, channel_id, published_message_id_in_channel,
                                        channel_title)

    except Exception as e:
        logger.error(f"Ошибка публикации запланированного поста (DB ID: {post_db_id}) в канал «{channel_title}»: {e}",
                     exc_info=True)
        post_status_final = "failed"  # Статус уже такой по умолчанию, но для явности
        if user_id_to_notify:
            await notify_user(bot_instance, user_id_to_notify,
                              f"❌ Ошибка публикации вашего запланированного поста (ID в системе: {post_db_id}) для канала «{channel_title}».\nПричина: {e}")
    finally:
        # Обновление статуса и message_id в БД по post_db_id
        try:
            db.execute(
                "UPDATE posts SET status = ?, message_id = ? WHERE id = ?",
                (post_status_final, published_message_id_in_channel, post_db_id),
                commit=True
            )
            if db.cursor.rowcount > 0:
                logger.info(f"Status for post (DB ID: {post_db_id}) updated to '{post_status_final}' in DB.")
            else:
                logger.warning(
                    f"Failed to update status in DB for post (DB ID: {post_db_id}). Post not found or status already updated.")
        except Exception as db_e:
            logger.error(
                f"Критическая ошибка: не удалось обновить статус поста (DB ID: {post_db_id}) в БД после попытки публикации: {db_e}",
                exc_info=True)
            # Здесь можно отправить уведомление администратору бота о критической ошибке
            # await notify_admin_critical_error(bot_instance, ...)