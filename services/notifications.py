# services/notifications.py
from telegram import InlineKeyboardMarkup, InlineKeyboardButton
from telegram.constants import ParseMode
from config import MONITORING_GROUP_ID
from database.repository import get_account_by_id
from strings import *
from datetime import datetime

async def post_order_to_admin_group(app, order_row, include_photo_file_id=None):
    # 1. جلب تفاصيل الحساب المرتبط بالطلب
    account_details = get_account_by_id(order_row['account_id'])

    # تجهيز البيانات للعرض
    order_code = order_row['order_code']
    service_type = order_row['service']
    user_id = order_row['user_id']

    # إذا كان الطلب إنشاء حساب، نظهر الاسم والباسورد
    account_info = ""
    if account_details:
        acc_name = account_details['account_name']
        acc_pass = account_details['password']
        account_info = (
            f"👤 <b>اسم الحساب:</b> <code>{acc_name}</code>\n"
            f"🔑 <b>كلمة المرور:</b> <code>{acc_pass}</code>\n"
        )

    # المبلغ (إن وجد)
    amount_info = ""
    if order_row['amount']:
        amount_info = f"💰 <b>المبلغ:</b> {order_row['amount']}\n"

    # تجميع نص الرسالة
    text = (
        f"{ADMIN_NEW_ORDER_TITLE}\n\n"
        f"📌 <b>كود الطلب:</b> <code>{order_code}</code>\n"
        f"🧾 <b>النوع:</b> {service_type}\n"
        f"🆔 <b>معرف المستخدم:</b> <code>{user_id}</code>\n"
        f"------------------------\n"
        f"{account_info}"
        f"{amount_info}"
        f"------------------------\n"
        f"🕒 {datetime.utcnow().strftime('%Y-%m-%d %H:%M')}"
    )

    # الأزرار الجديدة (واضحة ومعربة)
    keyboard = [
        [
            InlineKeyboardButton(ADMIN_BTN_CLAIM, callback_data=f"admin|claim|{order_code}"),
        ],
        [
            InlineKeyboardButton(ADMIN_BTN_REJECT, callback_data=f"admin|reject|{order_code}")
        ]
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)

    # الإرسال
    if include_photo_file_id:
        msg = await app.bot.send_photo(
            chat_id=MONITORING_GROUP_ID,
            photo=include_photo_file_id,
            caption=text,
            reply_markup=reply_markup,
            parse_mode=ParseMode.HTML
        )
    else:
        msg = await app.bot.send_message(
            chat_id=MONITORING_GROUP_ID,
            text=text,
            reply_markup=reply_markup,
            parse_mode=ParseMode.HTML
        )
    
    # (اختياري) ربط الرسالة بالكود في قاعدة البيانات إذا كنت تستخدم map_group_message
    # map_group_message(msg.message_id, order_code) 
