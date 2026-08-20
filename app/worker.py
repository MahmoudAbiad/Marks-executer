"""
نظام طابور الرسائل (Worker) - يرسل الإشعارات للطلاب مع التعامل مع FloodWaitError
"""
import asyncio
import logging

from telethon.errors import FloodWaitError

from app.clients import bot
from app.state import notification_queue

logger = logging.getLogger(__name__)


async def message_worker():
    while True:
        chat_id, message_text = await notification_queue.get()
        sent = False
        while not sent:
            try:
                await bot.send_message(chat_id=chat_id, text=message_text, parse_mode="Markdown")
                sent = True
                await asyncio.sleep(0.05)
            except FloodWaitError as e:
                logger.warning("ضغط إرسال: انتظار %s ثانية", e.seconds)
                await asyncio.sleep(e.seconds + 1)
            except Exception as e:
                logger.error("تعذر الإرسال للطالب %s: %s", chat_id, e)
                sent = True
        notification_queue.task_done()
