"""
استخراج بيانات النتائج من ملفات PDF عبر Gemini
"""
import json
import logging

from google.genai import types as genai_types

from app.clients import ai_client
from app.config import GEMINI_MODEL

logger = logging.getLogger(__name__)

EXTRACTION_PROMPT = """
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


async def extract_results_from_pdf(file_path: str) -> dict | None:
    """يرفع ملف PDF إلى Gemini ويستخرج بيانات النتائج منه كـ dict.

    يعيد None في حال فشل الاستخراج أو كان الرد غير صالح كـ JSON،
    بدل أن يرمي استثناء يوقف باقي المعالجة.
    """
    try:
        uploaded_pdf = ai_client.files.upload(file=file_path)
        response = ai_client.models.generate_content(
            model=GEMINI_MODEL,
            contents=[uploaded_pdf, EXTRACTION_PROMPT],
            config=genai_types.GenerateContentConfig(response_mime_type="application/json")
        )
    except Exception as e:
        logger.error("خطأ أثناء استدعاء Gemini: %s", e)
        return None

    try:
        return json.loads(response.text)
    except (json.JSONDecodeError, TypeError) as e:
        logger.error("رد Gemini ليس JSON صالحًا: %s", e)
        return None
