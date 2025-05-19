from datetime import datetime
from apscheduler.schedulers.asyncio import AsyncIOScheduler
from apscheduler.jobstores.base import JobLookupError  # Для обработки ошибки, если задача не найдена
from aiogram import Bot
import logging

from loader import get_db
from bot_utils import notify_post_published, notify_user, escape_html

logger = logging.getLogger(__name__)


def add_scheduled_job(scheduler_instance: AsyncIOScheduler, bot_instance: Bot, data: dict):
    required_keys = ['post_db_id', 'publish_time', 'channel_id', 'user_id', 'channel_title']
    # Проверка на media_type если есть media
    if data.get('media') and 'media_type' not in data:
        logger.error(
            f"Ошибка планирования: есть 'media', но отсутствует 'media_type' в данных для поста {data.get('post_db_id')}.")
        # Уведомление пользователя должно происходить в вызывающем коде (handlers/posts.py)
        # Здесь просто прекращаем выполнение, чтобы не запланировать некорректную задачу.
        return False  # Возвращаем False при ошибке

    for key in required_keys:
        if key not in data:
            logger.error(
                f"Ошибка планирования: отсутствует ключ '{key}' в данных задачи для поста {data.get('post_db_id')}.")
            return False  # Возвращаем False при ошибке

    job_id = f"post_{data['post_db_id']}"

    try:
        scheduler_instance.add_job(
            send_scheduled_post,
            trigger='date',
            run_date=data['publish_time'],
            args=(bot_instance, data),
            id=job_id,
            name=f"Post to {data.get('channel_title', 'N/A')} at {data['publish_time']}",
            replace_existing=True
        )
        logger.info(
            f"Job {job_id} (Post ID: {data['post_db_id']}) added for {data['publish_time']} to channel {data.get('channel_title', 'N/A')}")
        return True  # Возвращаем True при успехе
    except Exception as e:
        logger.error(f"Ошибка добавления задачи {job_id} в планировщик: {e}", exc_info=True)
        return False  # Возвращаем False при ошибке


def remove_scheduled_job(scheduler_instance: AsyncIOScheduler, job_id: str) -> bool:
    """
    Удаляет задачу из планировщика по ее ID.
    Возвращает True, если задача была найдена и удалена, иначе False.
    """
    try:
        scheduler_instance.remove_job(job_id)
        logger.info(f"Scheduled job '{job_id}' successfully removed.")
        return True
    except JobLookupError:
        logger.warning(f"Scheduled job '{job_id}' not found for removal (may have already run or been removed).")
        return False  # Задача не найдена
    except Exception as e:
        logger.error(f"Error removing scheduled job '{job_id}': {e}", exc_info=True)
        return False  # Другая ошибка


async def send_scheduled_post(bot_instance: Bot, data: dict):
    db = get_db()
    post_db_id = data['post_db_id']
    user_id_to_notify = data['user_id']
    channel_id = data['channel_id']
    channel_title = data['channel_title']
    content_to_send = data.get('content', '')
    media_to_send = data.get('media')
    media_type_to_send = data.get('media_type')

    post_status_final = "failed"
    published_message_id_in_channel = None

    logger.info(f"Attempting to send scheduled post (DB ID: {post_db_id}) to channel {channel_title} ({channel_id})")

    try:
        current_post_status_query = db.fetchone("SELECT status FROM posts WHERE id = ?", (post_db_id,))
        if not current_post_status_query:
            logger.warning(f"Post (DB ID: {post_db_id}) not found in DB. Skipping scheduled send.")
            return
        if current_post_status_query[0] != 'scheduled':
            logger.warning(
                f"Post (DB ID: {post_db_id}) is not in 'scheduled' state (current: {current_post_status_query[0]}). Skipping.")
            return

        published_message = None
        parse_mode_for_send = "HTML"  # По умолчанию HTML

        if media_to_send:
            if media_type_to_send == "photo":
                published_message = await bot_instance.send_photo(
                    chat_id=channel_id, photo=media_to_send, caption=content_to_send, parse_mode=parse_mode_for_send
                )
            elif media_type_to_send == "video":
                published_message = await bot_instance.send_video(
                    chat_id=channel_id, video=media_to_send, caption=content_to_send, parse_mode=parse_mode_for_send
                )
            else:
                logger.warning(
                    f"Неизвестный или отсутствующий media_type ({media_type_to_send}) для медиа {media_to_send} поста {post_db_id}.")
                if content_to_send:
                    published_message = await bot_instance.send_message(
                        chat_id=channel_id,
                        text=f"{content_to_send}\n[Медиафайл: {escape_html(str(media_to_send))}]",
                        # Добавил escape_html
                        parse_mode=parse_mode_for_send
                    )
                else:
                    raise ValueError(
                        f"Не удалось отправить пост {post_db_id}: нет текста и неизвестный тип медиа {media_to_send}")
        else:
            published_message = await bot_instance.send_message(
                chat_id=channel_id,
                text=content_to_send,
                parse_mode=parse_mode_for_send
            )

        post_status_final = "published"
        published_message_id_in_channel = published_message.message_id if published_message else None

        logger.info(
            f"Scheduled post (DB ID: {post_db_id}) successfully sent to channel {channel_title}. Message ID: {published_message_id_in_channel}")

        if user_id_to_notify and published_message_id_in_channel:
            await notify_post_published(bot_instance, user_id_to_notify, channel_id, published_message_id_in_channel,
                                        channel_title)

    except Exception as e:
        logger.error(f"Ошибка публикации запланированного поста (DB ID: {post_db_id}) в «{channel_title}»: {e}",
                     exc_info=True)
        post_status_final = "failed"
        if user_id_to_notify:
            await notify_user(bot_instance, user_id_to_notify,
                              f"❌ Ошибка публикации вашего запланированного поста (ID: {post_db_id}) для «{escape_html(channel_title)}».\nПричина: {escape_html(str(e))}")
    finally:
        try:
            db.execute(
                "UPDATE posts SET status = ?, message_id = ? WHERE id = ?",
                (post_status_final, published_message_id_in_channel, post_db_id),
                commit=True
            )
            if db.cursor.rowcount > 0:
                logger.info(f"Status for post (DB ID: {post_db_id}) updated to '{post_status_final}' in DB.")
            else:  # Поста уже нет или статус не 'scheduled'
                logger.warning(
                    f"Could not update status in DB for post (DB ID: {post_db_id}). Post not found or status was not 'scheduled'.")
        except Exception as db_e:
            logger.critical(
                f"Критическая ошибка: не удалось обновить статус поста (DB ID: {post_db_id}) в БД после попытки публикации: {db_e}",
                exc_info=True)