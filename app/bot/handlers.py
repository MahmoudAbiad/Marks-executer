"""
معالجات (Handlers) بوت تيليجرام - أوامر، أزرار، وإدخال نصي
استيراد هذه الوحدة يكفي لتسجيل كل المعالجات على dp (تُسجَّل عبر الديكوريتور @dp...).
"""
from aiogram import types, F
from aiogram.filters import CommandStart

from app import db
from app.clients import dp
from app.state import user_registration_flow
from app.bot.keyboards import main_keyboard, years_keyboard, majors_keyboard


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
    student = await db.get_student(query.from_user.id)
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
        await query.message.answer("🏛 **اختر اختصاصك الجامعي:**", reply_markup=majors_keyboard(), parse_mode="Markdown")
    await query.answer()


@dp.callback_query(F.data.startswith("set_major:"))
async def set_major_cb(query: types.CallbackQuery):
    major = query.data.split(":", 1)[1]
    chat_id = query.from_user.id
    if chat_id in user_registration_flow:
        data = user_registration_flow.pop(chat_id)
        await db.save_student(chat_id, data["full_name"], data["seat_number"], data["year"], major)
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
            await message.answer("📅 **اختر سنتك الدراسية:**", reply_markup=years_keyboard(), parse_mode="Markdown")
        else:
            await message.answer("⚠️ يرجى كتابة البيانات بالصيغة: `الاسم - رقم الاكتتاب`", parse_mode="Markdown")
