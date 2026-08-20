"""
تهيئة العملاء المشتركة (Bot, Dispatcher, Gemini, Telethon)
تُستورد هذه العناصر من هنا في كل مكان بدل إعادة إنشائها لتفادي التبعيات الدائرية.
"""
from aiogram import Bot, Dispatcher
from google import genai
from telethon import TelegramClient
from telethon.sessions import StringSession

from app import config

bot = Bot(token=config.BOT_TOKEN)
dp = Dispatcher()
ai_client = genai.Client(api_key=config.GEMINI_API_KEY)
user_client = TelegramClient(StringSession(config.SESSION_STRING), config.API_ID, config.API_HASH)
