"""
دوال مساعدة عامة
"""
import re


def normalize_arabic(text: str) -> str:
    """توحيد رسم الحروف العربية لضمان دقة المطابقة"""
    if not text:
        return ""
    text = re.sub(r"[إأآا]", "ا", text)
    text = re.sub(r"ة", "ه", text)
    text = re.sub(r"ى", "ي", text)
    text = re.sub(r"[ًٌٍَُِّْـ]", "", text)
    return text.strip().lower()
