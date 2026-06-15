# config.py
from dotenv import load_dotenv
import os

load_dotenv()

TOKEN = os.getenv("BOT_TOKEN")
if not TOKEN:
    raise RuntimeError("BOT_TOKEN is missing. Check your .env file")

MIN_DEPOSIT_AMOUNT = 25000

# المجموعات الإدارية
ADMIN_GROUP_ID = int(os.getenv("ADMIN_GROUP_ID") or -1001234567890)
DEPOSITS_GROUP_ID = int(
    os.getenv("DEPOSITS_GROUP_ID") or -1001234567890
)  # مجموعة الإيداعات
WITHDRAWS_GROUP_ID = int(os.getenv("WITHDRAWS_GROUP_ID") or -1001234567890)

# قنوات التوثيق والأرشيف (الجديدة)
ACCEPTED_LOG_CHANNEL_ID = int(
    os.getenv("ACCEPTED_LOG_CHANNEL_ID") or 0
)  # قناة الطلبات المقبولة
REJECTED_LOG_CHANNEL_ID = int(
    os.getenv("REJECTED_LOG_CHANNEL_ID") or 0
)  # قناة الطلبات المرفوضة
USER_ARCHIVE_CHANNEL_ID = int(
    os.getenv("USER_ARCHIVE_CHANNEL_ID") or 0
)  # قناة أرشيف المستخدمين

# ADMIN_IDS: comma separated list of integer telegram IDs
ADMIN_IDS = [
    int(x) for x in os.getenv("ADMIN_IDS", "").split(",") if x.strip().isdigit()
]
DB_PATH = os.getenv("DB_PATH") or "bot_database.db"

# Generation constants
ACCOUNT_PREFIX = os.getenv("ACCOUNT_PREFIX") or "fx_"
ACCOUNT_SUFFIX = os.getenv("ACCOUNT_SUFFIX") or "_h"
ORDER_PREFIX = os.getenv("ORDER_PREFIX") or "REQ-"
