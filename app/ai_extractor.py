"""
استخراج بيانات النتائج من ملفات PDF عبر Gemini (تقسيم ذكي متوازي + إيقاف التفكير)
"""
import asyncio
import io
import json
import logging
import math

from google.genai import types as genai_types
from pypdf import PdfReader, PdfWriter

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


def _split_pdf_into_chunks(pdf_bytes: bytes) -> list[bytes]:
    """تقسيم الـ PDF إلى أجزاء (1 إلى 3 كحد أقصى) وفق عدد الصفحات."""
    reader = PdfReader(io.BytesIO(pdf_bytes))
    total_pages = len(reader.pages)

    if total_pages == 0:
        return []

    # تحديد عدد الأجزاء حسب حجم الملف
    if total_pages <= 5:
        num_chunks = 1
    elif total_pages <= 10:
        num_chunks = 2
    else:
        num_chunks = 3

    chunk_size = math.ceil(total_pages / num_chunks)
    chunks = []

    for i in range(0, total_pages, chunk_size):
        writer = PdfWriter()
        for page in reader.pages[i:i + chunk_size]:
            writer.add_page(page)
        out_buf = io.BytesIO()
        writer.write(out_buf)
        chunks.append(out_buf.getvalue())

    return chunks


async def _extract_chunk(pdf_chunk_bytes: bytes) -> dict | None:
    """إرسال جزء من الـ PDF إلى Gemini مع تعطيل التفكير لسرعة الرد."""
    try:
        response = await ai_client.aio.models.generate_content(
            model=GEMINI_MODEL,
            contents=[
                genai_types.Part.from_bytes(data=pdf_chunk_bytes, mime_type="application/pdf"),
                EXTRACTION_PROMPT
            ],
            config=genai_types.GenerateContentConfig(
                response_mime_type="application/json",
                thinking_config=genai_types.ThinkingConfig(thinking_budget=0)
            )
        )
        return json.loads(response.text)
    except Exception as e:
        logger.error("خطأ أثناء استخراج جزء من الملف عبر Gemini: %s", e)
        return None


async def extract_results_from_pdf(pdf_bytes: bytes) -> dict | None:
    """تقطيع الملف وإرسال الأجزاء بالتوازي ثم دمج النتائج."""
    try:
        chunks = _split_pdf_into_chunks(pdf_bytes)
    except Exception as e:
        logger.error("فشل قراءة ملف الـ PDF عبر pypdf: %s", e)
        chunks = [pdf_bytes]

    if not chunks:
        return None

    # إذا كان الملف جزءاً واحداً (5 صفحات أو أقل) يُعالج مباشرة
    if len(chunks) == 1:
        return await _extract_chunk(chunks[0])

    # معالجة الأجزاء بالتوازي
    results = await asyncio.gather(*[_extract_chunk(chunk) for chunk in chunks])

    merged_data = {
        "subject_name": "",
        "target_year": "",
        "target_major": "",
        "students": []
    }

    for res in results:
        if not res or not isinstance(res, dict):
            continue

        # استخراج بيانات المادة من أول جزء يحتوي عليها
        if not merged_data["subject_name"] and res.get("subject_name"):
            merged_data["subject_name"] = res.get("subject_name", "")
        if not merged_data["target_year"] and res.get("target_year"):
            merged_data["target_year"] = res.get("target_year", "")
        if not merged_data["target_major"] and res.get("target_major"):
            merged_data["target_major"] = res.get("target_major", "")

        # دمج مصفوفات الطلاب
        students = res.get("students", [])
        if isinstance(students, list):
            merged_data["students"].extend(students)

    if not merged_data["students"] and not merged_data["subject_name"]:
        logger.error("تعذر استخراج بيانات صالحة من أي جزء من الملف.")
        return None

    return merged_data