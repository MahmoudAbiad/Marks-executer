"""
لوحات المفاتيح الشفافة (Inline Keyboards) الخاصة بالبوت
"""
from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton

from app.config import YEARS, MAJORS


def main_keyboard() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="📋 بياناتي المسجلة", callback_data="view_data"),
         InlineKeyboardButton(text="⚙️ تسجيل / تعديل البيانات", callback_data="start_reg")],
        [InlineKeyboardButton(text="ℹ️ حول البوت", callback_data="about_bot")]
    ])


def years_keyboard() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[[InlineKeyboardButton(text=y, callback_data=f"set_year:{y}")] for y in YEARS]
    )


def majors_keyboard() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[[InlineKeyboardButton(text=m, callback_data=f"set_major:{m}")] for m in MAJORS]
    )
