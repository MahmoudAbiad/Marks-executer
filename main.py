import os
import json
import asyncio
from telethon import TelegramClient, events, Button
from telethon.errors import FloodWaitError
from google import genai
from google.genai import types
import libsql_client
from dotenv import load_dotenv

load_dotenv()

# --- المتغيرات البيئية ---
API_ID = int(os.getenv("API_ID", "0"))
API_HASH = os.getenv("API_HASH", "")
BOT_TOKEN = os.getenv("BOT_TOKEN", "")
GEMINI_API_KEY = os.getenv("GEMINI_API_KEY", "")
TURSO_DB_URL = os.getenv("TURSO_DB_URL", "")
TURSO_AUTH_TOKEN = os.getenv("TURSO_AUTH_TOKEN", "")
TARGET_CHANNEL = os.getenv("TARGET_CHANNEL", "EnvironmentalTechnologyEng")

# تهيئة العملاء
ai_client = genai.Client(api_key=GEMINI_API_KEY)
user_client = TelegramClient("user_session", API_ID, API_HASH)
bot = TelegramClient("bot_session", API_ID, API_HASH)

notification_queue = asyncio.Queue()
user_registration_flow = {}  # حفظ خطوات التسجيل المؤقتة

# قائمة الاختصاصات والسنوات
YEARS = ["السنة الأولى", "السنة الثانية", "السنة الثالثة", "السنة الرابعة", "السنة الخامسة"]
MAJORS = ["هندسة البيئة", "هندسة الأغذية", "هندسة المواد", "هندسة الأتمتة والتحكم"]

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
        # فلترة مرنة في بايثون لتجاوز اختلاف صياغة الكلمات (مثل: أولى / الأولى)
        matched = []
        for r in rs.rows:
            st = {"chat_id": r[0], "full_name": r[1], "seat_number": str(r[2]), "year": r[3], "major": r[4]}
            if (st["year"] in year or year in st["year"]) and (st["major"] in major or major in st["major"]):
                matched.append(st)
        return matched

# --- نظام طابور الرسائل (Worker) ---

async def message_worker():
    while True:
        chat_id, message_text = await notification_queue.get()
        sent = False
        while not sent:
            try:
                await bot.send_message(chat_id, message_text)
                sent = True
                await asyncio.sleep(0.05)
            except FloodWaitError as e:
                print(f"⚠️ FloodWait: إيقاف مؤقت لمدة {e.seconds} ثانية")
                await asyncio.sleep(e.seconds + 1)
            except Exception as e:
                print(f"فشل الإرسال إلى {chat_id}: {e}")
                sent = True
        notification_queue.task_done()

# --- واجهة المستخدم وأزرار التحكم ---

def main_keyboard():
    return [
        [Button.inline("📋 بياناتي المسجلة", b"view_data"), Button.inline("⚙️ تسجيل / تعديل البيانات", b"start_reg")],
        [Button.inline("ℹ️ حول البوت", b"about_bot")]
    ]

@bot.on(events.NewMessage(pattern=r"^/start"))
async def start_handler(event):
    await event.respond(
        "👋 **أهلاً بك في بوت نتائج كلية الهندسة التقنية!**\n\n"
        "يقوم البوت بمراقبة القناة تلقائياً واستخراج نتيجتك وإرسالها لك فور صدور الملف.\n"
        "سجل بياناتك لتبدأ المراقبة:",
        buttons=main_keyboard()
    )

@bot.on(events.CallbackQuery)
async def callback_handler(event):
    chat_id = event.chat_id
    data = event.data.decode("utf-8")

    if data == "view_data":
        student = await get_student(chat_id)
        if student:
            msg = (
                f"👤 **الاسم:** {student[0]}\n"
                f"🔢 **رقم الاكتتاب:** {student[1]}\n"
                f"📅 **السنة:** {student[2]}\n"
                f"🏛 **الاختصاص:** {student[3]}"
            )
        else:
            msg = "⚠️ لم تسجل بياناتك بعد. اضغط على الزر بالأسفل للبدء."
        await event.respond(msg, buttons=main_keyboard())

    elif data == "start_reg":
        user_registration_flow[chat_id] = {"step": "WAITING_NAME_SEAT"}
        await event.respond("✍️ أرسل **اسمك الثلاثي** و **رقم الاكتتاب** مفصولين بشرطة (-):\n\nمثال:\n`محمود ابيض - 3051`")

    elif data.startswith("set_year:"):
        year = data.split(":", 1)[1]
        if chat_id in user_registration_flow:
            user_registration_flow[chat_id]["year"] = year
            user_registration_flow[chat_id]["step"] = "SELECT_MAJOR"
            
            # أزرار اختيار الاختصاص
            major_buttons = [[Button.inline(m, f"set_major:{m}".encode("utf-8"))] for m in MAJORS]
            await event.respond("🏛 **اختر اختصاصك الجامعي:**", buttons=major_buttons)

    elif data.startswith("set_major:"):
        major = data.split(":", 1)[1]
        if chat_id in user_registration_flow:
            u_data = user_registration_flow.pop(chat_id)
            full_name = u_data["full_name"]
            seat_number = u_data["seat_number"]
            year = u_data["year"]

            await save_student(chat_id, full_name, seat_number, year, major)
            await event.respond(
                f"✅ **تم تسجيل وتحديث بياناتك بنجاح!**\n\n"
                f"👤 **الاسم:** {full_name}\n"
                f"🔢 **رقم الاكتتاب:** {seat_number}\n"
                f"📅 **السنة:** {year}\n"
                f"🏛 **الاختصاص:** {major}",
                buttons=main_keyboard()
            )

    elif data == "about_bot":
        await event.respond("🤖 نظام معالجة سحابي مدعوم بالذكاء الاصطناعي لفحص واستخراج العلامات الجامعية بدقة وسرعة.", buttons=main_keyboard())

@bot.on(events.NewMessage)
async def message_input_handler(event):
    if not event.is_private:
        return

    chat_id = event.chat_id
    if chat_id in user_registration_flow and user_registration_flow[chat_id].get("step") == "WAITING_NAME_SEAT":
        text = event.text.replace("،", "-").replace(",", "-")
        parts = [p.strip() for p in text.split("-") if p.strip()]

        if len(parts) >= 2:
            user_registration_flow[chat_id]["full_name"] = parts[0]
            user_registration_flow[chat_id]["seat_number"] = parts[1]
            user_registration_flow[chat_id]["step"] = "SELECT_YEAR"

            # أزرار اختيار السنة الدراسية
            year_buttons = [[Button.inline(y, f"set_year:{y}".encode("utf-8"))] for y in YEARS]
            await event.respond("📅 **اختر سنتك الدراسية:**", buttons=year_buttons)
        else:
            await event.respond("⚠️ يرجى كتابة البيانات بالصيغة: `الاسم الكامل - رقم الاكتتاب`")

# --- معالجة واستخراج ملفات الـ PDF عبر Gemini ---

@user_client.on(events.NewMessage(chats=TARGET_CHANNEL))
async def channel_listener(event):
    if not event.file or not (event.file.name and event.file.name.lower().endswith(".pdf")):
        return

    file_name = event.file.name
    print(f"📥 تم رصد ملف جديد: {file_name}")
    temp_path = await event.download_media(file=f"temp_{file_name}")

    try:
        uploaded_pdf = ai_client.files.upload(file=temp_path)

        # استخراج ترويسة المادة + جدول الطلاب دفعة واحدة
        extraction_prompt = """
        حلل هذا المستند الامتحاني الجامعي بدقة وأعد البيانات بصيغة JSON Object فقط بالهيكل التالي:
        {
          "subject_name": "اسم المادة المكتوب بالترويسة",
          "target_year": "السنة الدراسية (مثال: الأولى، الثانية، الثالثة...)",
          "target_major": "الاختصاص أو القسم (مثال: بيئة، أغذية، مواد، تحكم...)",
          "students": [
            {
              "seat_number": "رقم الاكتتاب كنص",
              "full_name": "اسم الطالب الثلاثي والشهرة",
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
            config=types.GenerateContentConfig(response_mime_type="application/json")
        )

        data = json.loads(response.text)
        await dispatch_notifications(data)

    except Exception as e:
        print(f"خطأ أثناء معالجة الملف: {e}")
    finally:
        if os.path.exists(temp_path):
            os.remove(temp_path)

# --- مطابقة الطلاب وإدراج الرسائل في الطابور ---

async def dispatch_notifications(parsed_data):
    subject = parsed_data.get("subject_name", "مادة غير محددة")
    year = parsed_data.get("target_year", "")
    major = parsed_data.get("target_major", "")
    results = parsed_data.get("students", [])

    print(f"📊 معالجة نتائج: {subject} | السنة: {year} | الاختصاص: {major} | عدد الطلاب المستخرجين: {len(results)}")

    # جلب الطلاب المطابقين للسنة والاختصاص فقط
    matching_students = await get_students_by_target(year, major)
    if not matching_students:
        print("ℹ️ لا يوجد طلاب مسجلين يطابقون هذه المادة.")
        return

    # فهرسة النتائج بالاسم ورقم الاكتتاب للوصول السريع
    results_map = {}
    for r in results:
        seat = str(r.get("seat_number", "")).strip()
        name = str(r.get("full_name", "")).strip()
        if seat:
            results_map[seat] = r
        if name:
            results_map[name] = r

    # مطابقة وإرسال الإشعارات
    for st in matching_students:
        target_seat = st["seat_number"]
        target_name = st["full_name"]

        match = results_map.get(target_seat) or results_map.get(target_name)
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

# --- نقطة الانطلاق الرئيسية ---

async def main():
    await init_db()
    await user_client.start()
    await bot.start(bot_token=BOT_TOKEN)
    
    asyncio.create_task(message_worker())
    
    print("🚀 البوت وقارئ القنوات يعملان بنجاح...")
    await bot.run_until_disconnected()

if __name__ == "__main__":
    asyncio.run(main())
