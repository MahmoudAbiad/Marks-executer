# Marks Executer

بوت تيليجرام يراقب قناة معيّنة، ويستخرج نتائج الامتحانات تلقائيًا من ملفات PDF عبر Gemini،
ثم يشعر كل طالب مسجَّل بنتيجته حسب رقم الاكتتاب أو الاسم.

## البنية

```
Marks-executer/
├── app/
│   ├── config.py            # متغيرات البيئة والثوابت (YEARS, MAJORS...)
│   ├── clients.py           # عناصر مشتركة: bot, dp, ai_client, user_client
│   ├── state.py             # حالة تشغيل مشتركة: طابور الإشعارات، تدفق التسجيل
│   ├── utils.py             # normalize_arabic
│   ├── db.py                # طبقة قاعدة بيانات Turso
│   ├── ai_extractor.py      # استدعاء Gemini لاستخراج بيانات النتائج من PDF
│   ├── worker.py            # معالج طابور الرسائل (يتعامل مع FloodWaitError)
│   ├── telethon_listener.py # مراقبة القناة وتوزيع الإشعارات
│   └── bot/
│       ├── keyboards.py     # لوحات المفاتيح الشفافة
│       └── handlers.py      # أوامر وأزرار البوت (aiogram)
├── main.py                  # تطبيق FastAPI + webhook + lifespan
├── requirements.txt
├── .env.example
└── .gitignore
```

## الإعداد

1. انسخ `.env.example` إلى `.env` واملأ القيم:
   ```bash
   cp .env.example .env
   ```
2. ثبّت الاعتماديات:
   ```bash
   pip install -r requirements.txt
   ```
   > الإصدارات في `requirements.txt` مثبَّتة (pinned) كنقطة بداية معقولة؛ يُفضّل تشغيل
   > `pip install -r requirements.txt` في بيئة اختبار أولاً والتأكد من التوافق قبل الإنتاج،
   > وتحديثها دوريًا بعد اختبارها.
3. شغّل محليًا:
   ```bash
   python main.py
   ```

## النشر على Render

- اضبط كل متغيرات `.env.example` كـ Environment Variables في لوحة تحكم Render.
- تأكد أن `RENDER_EXTERNAL_URL` يطابق رابط الخدمة الفعلي (Render يضبطه تلقائيًا عادةً).
- أمر التشغيل (Start Command):
  ```bash
  uvicorn main:app --host 0.0.0.0 --port $PORT
  ```

## ملاحظات مهمة

- `SESSION_STRING` حساس جدًا (يمنح وصولاً كاملاً لحساب تيليجرام المستخدَم للمراقبة) — لا يُرفع أبدًا لأي مستودع عام.
- `app/state.py` يحتفظ بحالة التسجيل في الذاكرة فقط؛ عند إعادة تشغيل الخادم (شائع في الخطط المجانية على Render)
  يفقد أي مستخدم في منتصف عملية التسجيل تقدمه. للإنتاج الجاد، انقل هذه الحالة إلى قاعدة البيانات.
- سجلات التشغيل تستخدم الآن `logging` بدل `print` لتسهيل المتابعة في بيئة الإنتاج.
