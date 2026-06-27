# config.py
from dotenv import load_dotenv
import os

load_dotenv()

TOKEN = os.getenv("BOT_TOKEN")
if not TOKEN:
    raise RuntimeError("BOT_TOKEN is missing. Check your .env file")

MIN_DEPOSIT_AMOUNT = 25000

# قناة أرشيف المستخدمين (تبقى كما هي)
USER_ARCHIVE_CHANNEL_ID = int(os.getenv("USER_ARCHIVE_CHANNEL_ID") or 0)

# المجموعة المركزية للاستعلامات (تبقى في env)
MONITORING_GROUP_ID = int(os.getenv("MONITORING_GROUP_ID") or -1001999999999)

# ADMIN_IDS: تُجلب من قاعدة البيانات في النظام الجديد
# هذا السطر مؤقت للتوافق مع الكود القديم، سيُحذف في الخطوة 7
ADMIN_IDS = [
    int(x) for x in os.getenv("ADMIN_IDS", "").split(",") if x.strip().isdigit()
]
DB_PATH = os.getenv("DB_PATH") or "bot_database.db"

# Generation constants
ACCOUNT_PREFIX = os.getenv("ACCOUNT_PREFIX") or "fx_"
ACCOUNT_SUFFIX = os.getenv("ACCOUNT_SUFFIX") or "_h"
ORDER_PREFIX = os.getenv("ORDER_PREFIX") or "REQ-"
