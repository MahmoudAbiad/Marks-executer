import os
import json
import asyncio
from contextlib import asynccontextmanager
from fastapi import FastAPI, Request, Response
from aiogram import Bot, Dispatcher, types, F
from aiogram.filters import CommandStart
from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton
from telethon import TelegramClient, events
from telethon.errors import FloodWaitError
from google import genai
from google.genai import types as genai_types
import libsql_client
from dotenv import load_dotenv

load_dotenv()

# --- الإعدادات والمتغيرات ---
API_ID = int(os.getenv("API_ID", "0"))
API_HASH = os.getenv("API_HASH", "")
BOT_TOKEN = os.getenv("BOT_TOKEN", "")
GEMINI_API_KEY = os.getenv("GEMINI_API_KEY", "")
TURSO_DB_URL = os.getenv("TURSO_DB_URL", "")
TURSO_AUTH_TOKEN = os.getenv("TURSO_AUTH_TOKEN", "")
TARGET_CHANNEL = os.getenv("TARGET_CHANNEL", "EnvironmentalTechnologyEng")

# رابط الاستضافة الخاص بـ Render لتفعيل الويب هوك
WEBHOOK_HOST = os.getenv("RENDER_EXTERNAL_URL", "https://your-app-name.onrender.com")
WEBHOOK_PATH = f"/webhook/{BOT_TOKEN}"
WEBHOOK_URL = f"{WEBHOOK_HOST}{WEBHOOK_PATH}"

# تهيئة العملاء
bot = Bot(token=BOT_TOKEN)
dp = Dispatcher()
ai_client = genai.Client(api_key=GEMINI_API_KEY)
user_client = TelegramClient("user_session", API_ID, API_HASH)

notification_queue = asyncio.Queue()
user_registration_flow = {}

YEARS = ["السنة الأولى", "السنة الثانية", "السنة الثالثة", "السنة الرابعة", "السنة الخامسة"]
MAJORS = ["هندسة البيئة", "هندسة الأغذية", "هندسة المواد", "هندسة الأتمتة والتحكم"]

# --- قاعدة بيانات Turso ---

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
        for r in rs.rows:
            st = {"chat_id": r[0], "full_name": r[1], "seat_number": str(r[2]), "year": r[3], "major": r[4]}
            if (st["year"] in year or year in st["year"]) and (st["major"] in major or major in st["major"]):
                matched.append(st)
        return matched

# --- طابور الإرسال في الخلفية ---

async def message_worker():
    while True:
        chat_id, message_text = await notification_queue.get()
        sent = False
        while not sent:
            try:
                await bot.send_message(chat_id=chat_id, text=message_text, parse_mode="Markdown")
                sent = True
                await asyncio.sleep(0.05)
            except Exception as e:
                print(f"تعذر الإرسال للطالب {chat_id}: {e}")
                sent = True
        notification_queue.task_done()

# --- لوحات المفاتيح والأزرار ---

def main_keyboard():
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="📋 بياناتي المسجلة", callback_data="view_data"),
         InlineKeyboardButton(text="⚙️ تسجيل / تعديل البيانات", callback_data="start_reg")],
        [InlineKeyboardButton(text="ℹ️ حول البوت", callback_data="about_bot")]
    ])

# --- معالجات أحداث البوت (Aiogram) ---

@dp.message(CommandStart())
async def start_cmd(message: types.Message):
    await message.answer(
        "👋 **أهلاً بك في بوت نتائج كلية الهندسة التقنية!**\n\n"
        "يعمل البوت بنظام Webhook فائق السرعة لمراقبة وإرسال نتائجك لحظياً.",
        reply_markup=main_keyboard(),
        parse_mode="Markdown"
    )

@dp.callback_query(F.data == "view_data")
async def view_data_cb(query: types.CallbackQuery):
    student = await get_student(query.from_user.id)
    if student:
        msg = f"👤 **الاسم:** {student[0]}\n🔢 **رقم الاكتتاب:** {student[1]}\n📅 **السنة:** {student[2]}\n🏛 **الاختصاص:** {student[3]}"
    else:
        msg = "⚠️ لم تسجل بياناتك بعد. اضغط على تسجيل البيانات للبدء."
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
            f"✅ **تم تسجيل بياناتك بنجاح!**\n\n"
            f"👤 **الاسم:** {data['full_name']}\n🔢 **الاكتتاب:** {data['seat_number']}\n📅 **السنة:** {data['year']}\n🏛 **الاختصاص:** {major}",
            reply_markup=main_keyboard(),
            parse_mode="Markdown"
        )
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

# --- مراقبة القناة ومعالجة ملفات PDF ---

@user_client.on(events.NewMessage(chats=TARGET_CHANNEL))
async def channel_listener(event):
    if not event.file or not (event.file.name and event.file.name.lower().endswith(".pdf")):
        return

    temp_path = await event.download_media(file=f"temp_{event.file.name}")
    try:
        uploaded_pdf = ai_client.files.upload(file=temp_path)
        extraction_prompt = """
        حلل هذا المستند الامتحاني وأعد البيانات بصيغة JSON Object فقط:
        {
          "subject_name": "اسم المادة المكتوب بالترويسة",
          "target_year": "السنة الدراسية (مثال: الأولى، الثانية...)",
          "target_major": "الاختصاص (مثال: بيئة، أغذية...)",
          "students": [
            {
              "seat_number": "رقم الاكتتاب",
              "full_name": "اسم الطالب والشهرة",
              "practical_mark": "علامة العملي",
              "theory_mark": "علامة النظري",
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

    students = await get_students_by_target(year, major)
    if not students:
        return

    results_map = {}
    for r in results:
        seat = str(r.get("seat_number", "")).strip()
        name = str(r.get("full_name", "")).strip()
        if seat:
            results_map[seat] = r
        if name:
            results_map[name] = r

    for st in students:
        match = results_map.get(st["seat_number"]) or results_map.get(st["full_name"])
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

# --- خادم FastAPI ودورة حياة التطبيق (Lifespan) ---

@asynccontextmanager
async def lifespan(app: FastAPI):
    # بدء تشغيل قاعدة البيانات، الويب هوك، وعميل التلغرام
    await init_db()
    await bot.set_webhook(url=WEBHOOK_URL, drop_pending_updates=True)
    await user_client.start()
    asyncio.create_task(message_worker())
    print(f"🚀 تم تفعيل الويب هوك بنجاح على: {WEBHOOK_URL}")
    
    yield
    
    # الإغلاق الآمن
    await bot.delete_webhook()
    await user_client.disconnect()
    await bot.session.close()

app = FastAPI(lifespan=lifespan)

@app.post(WEBHOOK_PATH)
async def telegram_webhook(request: Request):
    update_data = await request.json()
    update = types.Update(**update_data)
    await dp.feed_update(bot=bot, update=update)
    return Response(status_code=200)

@app.get("/")
async def health_check():
    return {"status": "ok", "service": "Telegram Exam Bot Webhook"}
