import os
import re
import json
import asyncio
from contextlib import asynccontextmanager
from fastapi import FastAPI, Request, Response
from aiogram import Bot, Dispatcher, types, F
from aiogram.filters import CommandStart
from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton
from telethon import TelegramClient, events
from telethon.sessions import StringSession
from telethon.errors import FloodWaitError
from google import genai
from google.genai import types as genai_types
import libsql_client
from dotenv import load_dotenv

load_dotenv()

# --- المتغيرات البيئية ---
API_ID = int(os.getenv("API_ID", "0"))
API_HASH = os.getenv("API_HASH", "")
BOT_TOKEN = os.getenv("BOT_TOKEN", "")
SESSION_STRING = os.getenv("SESSION_STRING", "")
GEMINI_API_KEY = os.getenv("GEMINI_API_KEY", "")
TURSO_DB_URL = os.getenv("TURSO_DB_URL", "")
TURSO_AUTH_TOKEN = os.getenv("TURSO_AUTH_TOKEN", "")

# تنظيف معرّف القناة ليعمل مع Telethon
raw_channel = os.getenv("TARGET_CHANNEL", "EnvironmentalTechnologyEng")
TARGET_CHANNEL = raw_channel.replace("https://t.me/", "").replace("@", "").strip()

# إعدادات الويب هوك
WEBHOOK_HOST = os.getenv("RENDER_EXTERNAL_URL", "https://marks-executer.onrender.com").rstrip("/")
WEBHOOK_PATH = f"/webhook/{BOT_TOKEN}"
WEBHOOK_URL = f"{WEBHOOK_HOST}{WEBHOOK_PATH}"

# تهيئة العملاء
bot = Bot(token=BOT_TOKEN)
dp = Dispatcher()
ai_client = genai.Client(api_key=GEMINI_API_KEY)
user_client = TelegramClient(StringSession(SESSION_STRING), API_ID, API_HASH)

notification_queue = asyncio.Queue()
user_registration_flow = {}

YEARS = ["السنة الأولى", "السنة الثانية", "السنة الثالثة", "السنة الرابعة", "السنة الخامسة"]
MAJORS = ["هندسة البيئة", "هندسة الأغذية", "هندسة المواد", "هندسة الأتمتة والتحكم"]

# --- دوال مساعدة لتطبيع النصوص العربية ---

def normalize_arabic(text: str) -> str:
    """توحيد رسم الحروف العربية لضمان دقة المطابقة"""
    if not text:
        return ""
    text = re.sub(r"[إأآا]", "ا", text)
    text = re.sub(r"ة", "ه", text)
    text = re.sub(r"ى", "ي", text)
    text = re.sub(r"[ًٌٍَُِّْـ]", "", text)
    return text.strip().lower()

# --- إدارة قاعدة بيانات Turso ---

async def get_db():
    return libsql_client.create_client_async(url=TURSO_DB_URL, auth_token=TURSO_AUTH_TOKEN)

async def init_db():
    async with await get_db() as db:
        await db.execute("""
            CREATE TABLE IF NOT EXISTS students (
                chat_id INTEGER PRIMARY KEY,
                full_name TEXT NOT NULL,
                seat_number TEXT NOT NULL,
                year TEXT NOT NULL,
                major TEXT NOT NULL
            );
        """)

async def save_student(chat_id: int, full_name: str, seat_number: str, year: str, major: str):
    async with await get_db() as db:
        await db.execute(
            """
            INSERT INTO students (chat_id, full_name, seat_number, year, major)
            VALUES (?, ?, ?, ?, ?)
            ON CONFLICT(chat_id) DO UPDATE SET
                full_name = excluded.full_name,
                seat_number = excluded.seat_number,
                year = excluded.year,
                major = excluded.major;
            """,
            (chat_id, full_name, seat_number, year, major)
        )

async def get_student(chat_id: int):
    async with await get_db() as db:
        rs = await db.execute("SELECT full_name, seat_number, year, major FROM students WHERE chat_id = ?;", (chat_id,))
        return rs.rows[0] if rs.rows else None

async def get_students_by_target(year: str, major: str):
    async with await get_db() as db:
        rs = await db.execute("SELECT chat_id, full_name, seat_number, year, major FROM students;")
        matched = []
        norm_target_year = normalize_arabic(year)
        norm_target_major = normalize_arabic(major)

        for r in rs.rows:
            st = {"chat_id": r[0], "full_name": r[1], "seat_number": str(r[2]), "year": r[3], "major": r[4]}
            norm_db_year = normalize_arabic(st["year"])
            norm_db_major = normalize_arabic(st["major"])

            # مطابقة ذكية مع تجنب النصوص الفارغة
            year_match = bool(norm_target_year and (norm_target_year in norm_db_year or norm_db_year in norm_target_year))
            major_match = bool(norm_target_major and (norm_target_major in norm_db_major or norm_db_major in norm_target_major))

            if year_match and major_match:
                matched.append(st)
        return matched

# --- نظام طابور الرسائل (Worker) ---

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
                print(f"⚠️ ضغط إرسال: انتظار {e.seconds} ثانية")
                await asyncio.sleep(e.seconds + 1)
            except Exception as e:
                print(f"تعذر الإرسال للطالب {chat_id}: {e}")
                sent = True
        notification_queue.task_done()

# --- واجهة وأزرار البوت ---

def main_keyboard():
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="📋 بياناتي المسجلة", callback_data="view_data"),
         InlineKeyboardButton(text="⚙️ تسجيل / تعديل البيانات", callback_data="start_reg")],
        [InlineKeyboardButton(text="ℹ️ حول البوت", callback_data="about_bot")]
    ])

@dp.message(CommandStart())
async def start_cmd(message: types.Message):
    await message.answer(
        "👋 **أهلاً بك في بوت نتائج كلية الهندسة التقنية!**\n\n"
        "يقوم البوت بمراقبة القناة تلقائياً واستخراج نتيجتك فور صدور الملف.\n"
        "يرجى تسجيل بياناتك لتبدأ المراقبة:",
        reply_markup=main_keyboard(),
        parse_mode="Markdown"
    )

@dp.callback_query(F.data == "view_data")
async def view_data_cb(query: types.CallbackQuery):
    student = await get_student(query.from_user.id)
    if student:
        msg = f"👤 **الاسم:** {student[0]}\n🔢 **رقم الاكتتاب:** {student[1]}\n📅 **السنة:** {student[2]}\n🏛 **الاختصاص:** {student[3]}"
    else:
        msg = "⚠️ لم تسجل بياناتك بعد. اضغط على الزر بالأسفل للبدء."
    await query.message.answer(msg, reply_markup=main_keyboard(), parse_mode="Markdown")
    await query.answer()

@dp.callback_query(F.data == "start_reg")
async def start_reg_cb(query: types.CallbackQuery):
    user_registration_flow[query.from_user.id] = {"step": "WAITING_NAME_SEAT"}
    await query.message.answer("✍️ أرسل **اسمك الثلاثي** و **رقم الاكتتاب** مفصولين بشرطة (-):\n\nمثال:\n`محمود ابيض - 3051`", parse_mode="Markdown")
    await query.answer()

@dp.callback_query(F.data.startswith("set_year:"))
async def set_year_cb(query: types.CallbackQuery):
    year = query.data.split(":", 1)[1]
    chat_id = query.from_user.id
    if chat_id in user_registration_flow:
        user_registration_flow[chat_id]["year"] = year
        user_registration_flow[chat_id]["step"] = "SELECT_MAJOR"
        kb = InlineKeyboardMarkup(inline_keyboard=[[InlineKeyboardButton(text=m, callback_data=f"set_major:{m}")] for m in MAJORS])
        await query.message.answer("🏛 **اختر اختصاصك الجامعي:**", reply_markup=kb, parse_mode="Markdown")
    await query.answer()

@dp.callback_query(F.data.startswith("set_major:"))
async def set_major_cb(query: types.CallbackQuery):
    major = query.data.split(":", 1)[1]
    chat_id = query.from_user.id
    if chat_id in user_registration_flow:
        data = user_registration_flow.pop(chat_id)
        await save_student(chat_id, data["full_name"], data["seat_number"], data["year"], major)
        await query.message.answer(
            f"✅ **تم تسجيل وتحديث بياناتك بنجاح!**\n\n"
            f"👤 **الاسم:** {data['full_name']}\n🔢 **الاكتتاب:** {data['seat_number']}\n📅 **السنة:** {data['year']}\n🏛 **الاختصاص:** {major}",
            reply_markup=main_keyboard(),
            parse_mode="Markdown"
        )
    await query.answer()

@dp.callback_query(F.data == "about_bot")
async def about_cb(query: types.CallbackQuery):
    await query.message.answer("🤖 نظام مؤتمت بالذكاء الاصطناعي لفحص واستخراج نتائج الامتحانات الجامعية فور صدورها.", reply_markup=main_keyboard())
    await query.answer()

@dp.message()
async def text_input_handler(message: types.Message):
    chat_id = message.from_user.id
    if chat_id in user_registration_flow and user_registration_flow[chat_id].get("step") == "WAITING_NAME_SEAT":
        text = message.text.replace("،", "-").replace(",", "-")
        parts = [p.strip() for p in text.split("-") if p.strip()]
        if len(parts) >= 2:
            user_registration_flow[chat_id]["full_name"] = parts[0]
            user_registration_flow[chat_id]["seat_number"] = parts[1]
            user_registration_flow[chat_id]["step"] = "SELECT_YEAR"
            kb = InlineKeyboardMarkup(inline_keyboard=[[InlineKeyboardButton(text=y, callback_data=f"set_year:{y}")] for y in YEARS])
            await message.answer("📅 **اختر سنتك الدراسية:**", reply_markup=kb, parse_mode="Markdown")
        else:
            await message.answer("⚠️ يرجى كتابة البيانات بالصيغة: `الاسم - رقم الاكتتاب`", parse_mode="Markdown")

# --- مراقبة القناة واستخراج النتائج ---

@user_client.on(events.NewMessage(chats=TARGET_CHANNEL))
async def channel_listener(event):
    if not event.file or not (event.file.name and event.file.name.lower().endswith(".pdf")):
        return

    file_name = event.file.name
    print(f"📥 تم رصد ملف جديد: {file_name}")
    temp_path = await event.download_media(file=f"temp_{file_name}")

    try:
        uploaded_pdf = ai_client.files.upload(file=temp_path)
        extraction_prompt = """
        حلل هذا المستند الامتحاني وأعد البيانات بصيغة JSON Object فقط:
        {
          "subject_name": "اسم المادة المكتوب بالترويسة",
          "target_year": "السنة الدراسية (مثال: الأولى، الثانية، الثالثة...)",
          "target_major": "الاختصاص (مثال: بيئة، أغذية، مواد، أتمتة...)",
          "students": [
            {
              "seat_number": "رقم الاكتتاب كنص",
              "full_name": "اسم الطالب والشهرة",
              "practical_mark": "علامة العملي إن وجدت",
              "theory_mark": "علامة النظري إن وجدت",
              "total_mark": "المحصلة النهائية رقماً",
              "status": "النتيجة (ناجح / راسب / غائب)"
            }
          ]
        }
        """
        response = ai_client.models.generate_content(
            model="gemini-2.5-flash",
            contents=[uploaded_pdf, extraction_prompt],
            config=genai_types.GenerateContentConfig(response_mime_type="application/json")
        )
        data = json.loads(response.text)
        await dispatch_notifications(data)
    except Exception as e:
        print(f"خطأ أثناء معالجة الملف: {e}")
    finally:
        if os.path.exists(temp_path):
            os.remove(temp_path)

async def dispatch_notifications(parsed_data):
    subject = parsed_data.get("subject_name", "مادة غير محددة")
    year = parsed_data.get("target_year", "")
    major = parsed_data.get("target_major", "")
    results = parsed_data.get("students", [])

    print(f"📊 معالجة: {subject} | السنة: {year} | الاختصاص: {major} | الطلاب: {len(results)}")

    students = await get_students_by_target(year, major)
    if not students:
        print("ℹ️ لا يوجد طلاب مسجلين لهذه المادة.")
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

# --- تشغيل التطبيق وخادم FastAPI ---

@asynccontextmanager
async def lifespan(app: FastAPI):
    await init_db()
    await bot.set_webhook(url=WEBHOOK_URL, drop_pending_updates=True)
    
    # تشغيل Telethon دون تعليق السيرفر
    await user_client.connect()
    if not await user_client.is_user_authorized():
        print("❌ خطأ: كود SESSION_STRING غير صالح أو منتهي الصلاحية!")
    else:
        print("✅ تم تسجيل دخول حساب المراقبة (Telethon) بنجاح.")

    asyncio.create_task(message_worker())
    print(f"🚀 تم تفعيل الويب هوك على: {WEBHOOK_URL}")
    
    yield
    
    await bot.delete_webhook()
    await user_client.disconnect()
    await bot.session.close()

app = FastAPI(lifespan=lifespan)

@app.post(WEBHOOK_PATH)
async def telegram_webhook(request: Request):
    update_data = await request.json()
    await dp.feed_raw_update(bot=bot, update=update_data)
    return Response(status_code=200)

@app.get("/")
async def health_check():
    return {"status": "ok", "service": "Telegram Exam Bot Webhook"}