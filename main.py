"""
نقطة تشغيل التطبيق: خادم FastAPI + Webhook تيليجرام + مراقبة القناة
"""
import asyncio
import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI, Request, Response

from app import config
from app.clients import bot, dp, user_client
from app.db import init_db
from app.worker import message_worker

# تسجيل المعالجات والمستمعين (الاستيراد وحده يكفي لتفعيل الديكوريتورز)
from app.bot import handlers  # noqa: F401
from app import telethon_listener  # noqa: F401

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(name)s: %(message)s")
logger = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI):
    await init_db()
    await bot.set_webhook(url=config.WEBHOOK_URL, drop_pending_updates=True)

    await user_client.connect()
    if not await user_client.is_user_authorized():
        logger.error("❌ خطأ: كود SESSION_STRING غير صالح أو منتهي الصلاحية!")
    else:
        logger.info("✅ تم تسجيل دخول حساب المراقبة (Telethon) بنجاح.")

    asyncio.create_task(message_worker())
    logger.info("🚀 تم تفعيل الويب هوك على: %s", config.WEBHOOK_URL)

    yield

    await bot.delete_webhook()
    await user_client.disconnect()
    await bot.session.close()


app = FastAPI(lifespan=lifespan)


@app.post(config.WEBHOOK_PATH)
async def telegram_webhook(request: Request):
    update_data = await request.json()
    await dp.feed_raw_update(bot=bot, update=update_data)
    return Response(status_code=200)


@app.get("/")
async def health_check():
    return {"status": "ok", "service": "Telegram Exam Bot Webhook"}


if __name__ == "__main__":
    import os
    import uvicorn
    port = int(os.getenv("PORT", 8000))
    uvicorn.run("main:app", host="0.0.0.0", port=port)
