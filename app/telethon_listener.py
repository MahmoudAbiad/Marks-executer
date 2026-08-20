"""
مراقبة قناة تيليجرام عبر Telethon، واستخراج النتائج وتوزيعها على الطلاب المسجلين
"""
import logging
from telethon import events, TelegramClient

from app import db
from app.ai_extractor import extract_results_from_pdf
from app.config import TARGET_CHANNEL
from app.state import notification_queue
from app.utils import normalize_arabic

logger = logging.getLogger(__name__)


def setup_telethon_listener(client: TelegramClient):
    """تسجيل مستمع الرسائل على كائن Telethon بعد إنشائه"""

    @client.on(events.NewMessage(chats=TARGET_CHANNEL))
    async def channel_listener(event):
        if not event.file or not (event.file.name and event.file.name.lower().endswith(".pdf")):
            return

        file_name = event.file.name
        logger.info("📥 تم رصد ملف جديد: %s", file_name)

        # تحميل الملف مباشرة كـ bytes داخل الذاكرة (RAM) بدون حفظ على القرص
        pdf_bytes = await event.download_media(file=bytes)
        if not pdf_bytes:
            logger.error("تعذّر تحميل محتوى الملف: %s", file_name)
            return

        parsed_data = await extract_results_from_pdf(pdf_bytes)
        if parsed_data is None:
            logger.error("تعذّر استخراج بيانات صالحة من الملف: %s", file_name)
            return

        await dispatch_notifications(parsed_data)


async def dispatch_notifications(parsed_data: dict):
    subject = parsed_data.get("subject_name", "مادة غير محددة")
    year = parsed_data.get("target_year", "")
    major = parsed_data.get("target_major", "")
    results = parsed_data.get("students", [])

    logger.info("📊 معالجة: %s | السنة: %s | الاختصاص: %s | الطلاب: %s", subject, year, major, len(results))

    students = await db.get_students_by_target(year, major)
    if not students:
        logger.info("ℹ️ لا يوجد طلاب مسجلين لهذه المادة.")
        return

    # فهرسة النتائج للبحث الفوري O(1)
    seat_map = {}
    name_map = {}
    for r in results:
        seat = str(r.get("seat_number", "")).strip()
        name = normalize_arabic(str(r.get("full_name", "")))
        if seat:
            seat_map[seat] = r
        if name:
            name_map[name] = r

    for st in students:
        target_seat = st["seat_number"].strip()
        target_name = normalize_arabic(st["full_name"])

        # المطابقة برقم الاكتتاب أولاً ثم بالاسم
        match = seat_map.get(target_seat) or name_map.get(target_name)

        if match:
            msg = (
                f"📢 **صدور نتيجة جديدة!**\n\n"
                f"📚 **المادة:** {subject}\n"
                f"🏛 **الاختصاص:** {st['major']} ({st['year']})\n"
                f"👤 **الاسم:** {match.get('full_name')}\n"
                f"🔢 **رقم الاكتتاب:** {match.get('seat_number')}\n"
                f"📝 **العملي:** {match.get('practical_mark', '-')}\n"
                f"📖 **النظري:** {match.get('theory_mark', '-')}\n"
                f"🎯 **المجموع النهائي:** {match.get('total_mark')}\n"
                f"📌 **الحالة:** {match.get('status')}"
            )
            await notification_queue.put((st["chat_id"], msg))