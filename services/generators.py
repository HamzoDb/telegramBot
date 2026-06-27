# services/generators.py
import string, random, time
from config import ACCOUNT_PREFIX, ACCOUNT_SUFFIX


def gen_short_token(length=4):
    chars = string.ascii_lowercase + string.digits
    return "".join(random.choice(chars) for _ in range(length))


def generate_account_name(base_name, user_id):
    # نأخذ حرفان عشوائيان كبيران
    random_letter = "".join(random.choice(string.ascii_uppercase) for _ in range(2))
    # نأخذ رقمان عشوائيان من 10 إلى 99
    random_number = random.randint(10, 99)

    # النتيجة: MW + الاسم الأساسي + حرفان + رقمان
    # مثال: MWhamzahBQ47
    return f"MW{base_name}{random_letter}{random_number}"
