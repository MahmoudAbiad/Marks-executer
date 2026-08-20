"""
حالة التشغيل المشتركة بين وحدات التطبيق.

ملاحظة: هذه الحالة موجودة في الذاكرة فقط وتُفقد عند إعادة تشغيل الخادم.
لأغراض الإنتاج (خصوصًا على منصّات تعيد التشغيل بشكل متكرر مثل Render Free Tier)
يُفضّل نقل user_registration_flow لاحقًا إلى قاعدة البيانات أو Redis.
"""
import asyncio

# طابور الرسائل المرسلة للطلاب
notification_queue: asyncio.Queue = asyncio.Queue()

# حالة تسجيل كل مستخدم أثناء تعبئة بياناته (chat_id -> dict)
user_registration_flow: dict = {}
