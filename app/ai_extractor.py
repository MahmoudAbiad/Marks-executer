"""
استخراج بيانات النتائج من ملفات PDF عبر Gemini (غير متزامن ومن الذاكرة مباشرة)
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


async def extract_results_from_pdf(pdf_bytes: bytes) -> dict | None:
    """إرسال بايتات الـ PDF مباشرة إلى Gemini واستخراج JSON بدون حفظ على القرص.

    يعيد None في حال فشل الاستخراج أو كان الرد غير صالح كـ JSON.
    """
    try:
        response = await ai_client.aio.models.generate_content(
            model=GEMINI_MODEL,
            contents=[
                genai_types.Part.from_bytes(data=pdf_bytes, mime_type="application/pdf"),
                EXTRACTION_PROMPT
            ],
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