# services/scoring.py
from datetime import datetime
from database.repository import (
    get_user_by_id_helper,  # تأكد من أن هذه الدالة متاحة أو استخدم get_user_by_telegram وقم بتعديلها
    get_user_archive_id,
    set_user_archive_id,
    get_bot_account_name,
)
from database.db import get_conn

# ملاحظة: سنحتاج ARCHIVE_CHANNEL_ID من ملف config.py
from config import USER_ARCHIVE_CHANNEL_ID

# --- تعريف الرتب ---
TIERS = {
    "GUEST": {"name": "زائر ⚪️", "min_score": -9999, "color": "#B0B0B0", "stars": "⭐"},
    "ACTIVE": {
        "name": "عضو نشيط 🔵",
        "min_score": 50,
        "color": "#0000FF",
        "stars": "⭐⭐",
    },
    "TRUSTED": {
        "name": "موثوق 🟢",
        "min_score": 300,
        "color": "#008000",
        "stars": "⭐⭐⭐",
    },
    "VIP": {
        "name": "VIP 🟠",
        "min_score": 1000,
        "color": "#FFA500",
        "stars": "⭐⭐⭐⭐",
    },
    "KING": {
        "name": "الملك 🟣",
        "min_score": 5000,
        "color": "#800080",
        "stars": "⭐⭐⭐⭐⭐",
    },
}


def calculate_user_score(user_data):
    """
    معادلة حساب التقييم:
    Score = (Success * 10) + (Money / 50k) + (Age * 2) - (Reject * 50) - (Incomplete * 2)
    """
    success = user_data["total_successful_orders"] or 0
    rejected = user_data["total_rejected_orders"] or 0
    incomplete = user_data["total_incomplete_orders"] or 0

    total_money = (user_data["total_deposit_amount"] or 0) + (
        user_data["total_withdraw_amount"] or 0
    )

    # حساب العمر بالأشهر
    try:
        created_at = datetime.fromisoformat(user_data["created_at"])
        months_old = (datetime.utcnow() - created_at).days // 30
    except:
        months_old = 0

    score = (
        (success * 10)
        + (total_money / 50000)
        + (months_old * 2)
        - (rejected * 50)
        - (incomplete * 2)
    )

    return int(score)


def get_user_tier_info(score):
    """تحديد الرتبة بناءً على النقاط"""
    current_tier = TIERS["GUEST"]
    for key, tier in TIERS.items():
        if score >= tier["min_score"]:
            current_tier = tier
    return current_tier


def generate_card_text(user_data, score, tier_info):
    """توليد نص بطاقة الأرشيف"""

    user_link = f"<a href='tg://user?id={user_data['telegram_id']}'>{user_data['first_name']}</a>"
    bot_username = get_bot_account_name(user_data["id"]) or "غير معرف"

    # تنسيق المبالغ
    dep = (
        f"{user_data['total_deposit_amount']:,.0f}"
        if user_data["total_deposit_amount"]
        else "0"
    )
    withd = (
        f"{user_data['total_withdraw_amount']:,.0f}"
        if user_data["total_withdraw_amount"]
        else "0"
    )

    text = (
        f"🆔 <b>ID:</b> <code>{user_data['telegram_id']}</code>\n"
        f"👤 <b>اسم المستخدم:</b> {user_link}\n"
        f"<b>🔐اسم الحساب : </b><code>{bot_username}</code>\n"
        f"📅 <b>تاريخ الانضمام:</b> {user_data['created_at'][:10]}\n"
        f"🎖 <b>الرتبة:</b> {tier_info['name']}\n"
        f"{tier_info['stars']} (Points: {score})\n"
        f"━━━━━━━━━━━━━━━━━━\n"
        f"📊 <b>سجل العمليات:</b>\n"
        f"• ✅ عمليات ناجحة: <b>{user_data['total_successful_orders']}</b>\n"
        f"• ❌ عمليات مرفوضة: <b>{user_data['total_rejected_orders']}</b>\n"
        f"• ⚠️ غير مكتملة: <b>{user_data['total_incomplete_orders']}</b>\n\n"
        f"💰 <b>التدفق المالي:</b>\n"
        f"• 📥 مجموع الإيداع: <b>{dep}</b> SYP\n"
        f"• 📤 مجموع السحب: <b>{withd}</b> SYP\n\n"
        f"🔄 <b>آخر تحديث:</b> {datetime.utcnow().strftime('%Y-%m-%d %H:%M')}"
    )
    return text


async def update_live_card(bot, user_id_db):
    """
    الدالة الرئيسية التي تستدعى بعد كل عملية لتحديث البطاقة في القناة
    """
    # جلب بيانات المستخدم المحدثة
    conn = get_conn()
    cur = conn.cursor()
    cur.execute("SELECT * FROM users WHERE id=?", (user_id_db,))
    user_data = cur.fetchone()
    conn.close()

    if not user_data:
        return

    score = calculate_user_score(user_data)
    tier = get_user_tier_info(score)
    text = generate_card_text(user_data, score, tier)

    archive_msg_id = user_data["archive_message_id"]

    try:
        if archive_msg_id:
            try:
                # محاولة تعديل الرسالة الموجودة
                await bot.edit_message_text(
                    chat_id=USER_ARCHIVE_CHANNEL_ID,
                    message_id=archive_msg_id,
                    text=text,
                    parse_mode="HTML",
                )
                print(f"✅ تم تحديث بطاقة الأرشيف للمستخدم {user_id_db}")
            except Exception as e:
                # إذا فشل التعديل (مثلاً الرسالة حذفت)، نرسل واحدة جديدة
                print(f"⚠️ فشل التعديل، جاري إرسال بطاقة جديدة: {e}")
                msg = await bot.send_message(
                    chat_id=USER_ARCHIVE_CHANNEL_ID, text=text, parse_mode="HTML"
                )
                set_user_archive_id(user_id_db, msg.message_id)
        else:
            # إرسال رسالة جديدة لأول مرة
            msg = await bot.send_message(
                chat_id=USER_ARCHIVE_CHANNEL_ID, text=text, parse_mode="HTML"
            )
            set_user_archive_id(user_id_db, msg.message_id)
            print(f"🆕 تم إنشاء بطاقة أرشيف جديدة للمستخدم {user_id_db}")

    except Exception as e:
        # هنا يطبع الخطأ الحقيقي (مثل: Chat not found أو Need admin rights)
        print(f"❌ خطأ فادح في نظام الأرشيف: {e}")


def get_archive_link(user_data):
    """توليد رابط مباشر لرسالة المستخدم في قناة الارشيف"""

    try:
        msg_id = user_data["archive_message_id"]
        if msg_id:
            USER_ARCHIVE_CHANNEL_ID
            # تحويل آيدي القناة لشكل رابط (حذف -100 من البداية إذا وجدت)
            channel_id_str = str(USER_ARCHIVE_CHANNEL_ID).replace("-100", "")
            return f"https://t.me/c/{channel_id_str}/{msg_id}"
    except (IndexError, KeyError, TypeError):
        pass
    return None


def get_user_score_details_text(user_data):
    """نص رسالة (نقاطي) التي تظهر للمستخدم"""
    score = calculate_user_score(user_data)
    tier = get_user_tier_info(score)

    next_tier = None
    points_needed = 0

    # البحث عن الرتبة التالية
    sorted_tiers = sorted(TIERS.values(), key=lambda x: x["min_score"])
    for t in sorted_tiers:
        if t["min_score"] > score:
            next_tier = t
            points_needed = t["min_score"] - score
            break

    text = (
        f"🏆 <b>لوحة التقييم الشخصي</b>\n\n"
        f"🔰 <b>رتبتك الحالية:</b> {tier['name']}\n"
        f"⭐️ <b>النجوم:</b> {tier['stars']}\n"
        f"💎 <b>نقاطك:</b> <code>{score}</code> نقطة\n"
        f"━━━━━━━━━━━━━━\n"
    )

    if next_tier:
        text += (
            f"🚀 <b>الهدف القادم:</b> {next_tier['name']}\n"
            f"💡 تحتاج <b>{points_needed}</b> نقطة للترقية.\n"
        )
    else:
        text += "👑 <b>أنت في قمة المجد!</b>\n"

    text += (
        f"\n📊 <b>إحصائياتك:</b>\n"
        f"✅ عمليات ناجحة: {user_data['total_successful_orders']}\n"
        f"❌ عمليات مرفوضة: {user_data['total_rejected_orders']}"
    )

    return text
