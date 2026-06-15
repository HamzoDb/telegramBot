# services/generators.py
import string, random, time
from config import ACCOUNT_PREFIX, ACCOUNT_SUFFIX


def gen_short_token(length=4):
    chars = string.ascii_lowercase + string.digits
    return "".join(random.choice(chars) for _ in range(length))


def generate_account_name(base_name, user_id):
    # نأخذ حرفاً واحداً عشوائياً (كبير)
    random_letter = random.choice(string.ascii_uppercase)
    # نأخذ رقماً واحداً عشوائياً من 1 إلى 9
    random_number = random.randint(1, 9)

    # النتيجة ستكون: BaseName + RF + الحرف + الرقم
    # مثال: HamzahRFA1
    return f"MW{base_name}{random_letter}{random_number}"
