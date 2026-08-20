"""
إعدادات التطبيق ومتغيرات البيئة
"""
import os
from dotenv import load_dotenv

load_dotenv()

# --- المتغيرات البيئية ---
API_ID = int(os.getenv("API_ID", "0"))
API_HASH = os.getenv("API_HASH", "")
BOT_TOKEN = os.getenv("BOT_TOKEN", "")
SESSION_STRING = os.getenv("SESSION_STRING", "")
GEMINI_API_KEY = os.getenv("GEMINI_API_KEY", "")
TURSO_DB_URL = os.getenv("TURSO_DB_URL", "")
TURSO_AUTH_TOKEN = os.getenv("TURSO_AUTH_TOKEN", "")

# تنظيف معرّف القناة ليعمل مع Telethon
_raw_channel = os.getenv("TARGET_CHANNEL", "EnvironmentalTechnologyEng")
TARGET_CHANNEL = _raw_channel.replace("https://t.me/", "").replace("@", "").strip()

# إعدادات الويب هوك
WEBHOOK_HOST = os.getenv("RENDER_EXTERNAL_URL", "https://marks-executer.onrender.com").rstrip("/")
WEBHOOK_PATH = f"/webhook/{BOT_TOKEN}"
WEBHOOK_URL = f"{WEBHOOK_HOST}{WEBHOOK_PATH}"

# --- ثوابت الواجهة ---
YEARS = ["السنة الأولى", "السنة الثانية", "السنة الثالثة", "السنة الرابعة", "السنة الخامسة"]
MAJORS = ["هندسة البيئة", "هندسة الأغذية", "هندسة المواد", "هندسة الأتمتة والتحكم"]

GEMINI_MODEL = "gemini-3.5-flash-lite"
