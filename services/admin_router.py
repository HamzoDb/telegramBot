# services/admin_router.py
import logging
from database.repository import (
    get_next_admin_in_turn,
    set_order_assigned_admin,
    reassign_order_to_next_admin,
    get_admin_by_group_id,
    set_order_monitoring_msg_id,
    set_order_original_text
)
from config import MONITORING_GROUP_ID

logger = logging.getLogger(__name__)

# معرف مجموعة الاستعلامات المركزية
# غيّره لاحقاً للرقم الحقيقي


async def route_order_to_admin(bot, order, request_text):
    """
    يوزّع الطلب على الأدمن التالي في الدورة.
    يرسل الطلب لمجموعة الأدمن + نسخة للمجموعة المركزية.
    يُعيد بيانات الأدمن المعيّن، أو None لو فشل.
    """
    admin = get_next_admin_in_turn()
    if not admin:
        logger.error("لا يوجد أدمن نشط في النظام")
        return None

    set_order_assigned_admin(order["order_code"], admin["telegram_id"])

    # أزرار القرار لمجموعة الأدمن
    from telegram import InlineKeyboardButton, InlineKeyboardMarkup
    service = order["service"]

    if service == "WALLET_DEPOSIT":
        action_approve = f"dep_adm|approve|{order['order_code']}"
        action_reject = f"dep_adm|reject_menu|{order['order_code']}"
    elif service == "WALLET_WITHDRAW":
        action_approve = f"wd_adm|approve|{order['order_code']}"
        action_reject = f"wd_adm|reject_menu|{order['order_code']}"
    elif service in ("GAME_DEPOSIT", "GAME_WITHDRAW"):
        action_approve = f"adm_game|approve|{order['order_code']}"
        action_reject = f"adm_game|reject_menu|{order['order_code']}"
    else:
        action_approve = f"admin|claim|{order['order_code']}"
        action_reject = f"admin|reject|{order['order_code']}"

    admin_keyboard = InlineKeyboardMarkup([
        [
            InlineKeyboardButton("✅ قبول", callback_data=action_approve),
            InlineKeyboardButton("❌ رفض", callback_data=action_reject),
        ]
    ])

    # إرسال للمجموعة الخاصة بالأدمن
    try:
        sent = await bot.send_message(
            chat_id=admin["group_id"],
            text=request_text,
            parse_mode="HTML",
            reply_markup=admin_keyboard,
        )
        set_order_original_text(order["order_code"], request_text, sent.message_id)
    except Exception as e:
        logger.error(f"فشل إرسال الطلب لمجموعة الأدمن {admin['name']}: {e}")
        return None

    # أزرار المجموعة المركزية (تخطي فقط، بدون قرار)
    monitoring_keyboard = InlineKeyboardMarkup([
        [
            InlineKeyboardButton(
                "⏭️ تخطي لأدمن آخر",
                callback_data=f"mon|skip|{order['order_code']}"
            )
        ]
    ])

    monitoring_text = (
        f"{request_text}\n"
        f"━━━━━━━━━━━━━━\n"
        f"📌 <b>مُعيَّن لـ:</b> {admin['name']}\n"
        f"📊 <b>الحالة:</b> ⏳ جاري الانتظار"
    )

    # إرسال نسخة للمجموعة المركزية وحفظ معرف الرسالة
    try:
        monitoring_msg = await bot.send_message(
            chat_id=MONITORING_GROUP_ID,
            text=monitoring_text,
            parse_mode="HTML",
            reply_markup=monitoring_keyboard,
        )
        set_order_monitoring_msg_id(order["order_code"], monitoring_msg.message_id)
    except Exception as e:
        logger.error(f"فشل إرسال نسخة للمجموعة المركزية: {e}")

    return admin


async def skip_order_to_next_admin(bot, order_code, current_monitoring_msg_id):
    """
    يحوّل طلب للأدمن التالي عند الضغط على زر التخطي.
    يُعيد الأدمن الجديد أو None لو فشل.
    """
    from database.repository import get_order_by_code, get_admin_by_telegram_id
    from telegram import InlineKeyboardButton, InlineKeyboardMarkup

    # حفظ الأدمن الحالي قبل التحديث
    current_order = get_order_by_code(order_code)
    if not current_order:
        return None

    current_admin_id = current_order["assigned_admin_id"]
    old_admin_msg_id = current_order["admin_msg_id"]

    # تحويل الطلب للأدمن التالي في قاعدة البيانات
    next_admin = reassign_order_to_next_admin(order_code)
    if not next_admin:
        logger.error(f"فشل تحويل الطلب {order_code} لأدمن آخر")
        return None

    # جلب بيانات الأدمن القديم لحذف أزراره
    if current_admin_id and old_admin_msg_id:
        old_admin_info = get_admin_by_telegram_id(current_admin_id)
        if old_admin_info:
            try:
                await bot.edit_message_reply_markup(
                    chat_id=old_admin_info["group_id"],
                    message_id=old_admin_msg_id,
                    reply_markup=None,
                )
            except Exception as e:
                logger.error(f"خطأ في حذف أزرار الأدمن القديم: {e}")

    # بناء أزرار القرار للأدمن الجديد
    service = current_order["service"]
    if service == "WALLET_DEPOSIT":
        action_approve = f"dep_adm|approve|{order_code}"
        action_reject = f"dep_adm|reject_menu|{order_code}"
    elif service == "WALLET_WITHDRAW":
        action_approve = f"wd_adm|approve|{order_code}"
        action_reject = f"wd_adm|reject_menu|{order_code}"
    elif service in ("GAME_DEPOSIT", "GAME_WITHDRAW"):
        action_approve = f"adm_game|approve|{order_code}"
        action_reject = f"adm_game|reject_menu|{order_code}"
    else:
        action_approve = f"admin|approve|{order_code}"
        action_reject = f"admin|reject|{order_code}"

    admin_keyboard = InlineKeyboardMarkup([
        [
            InlineKeyboardButton("✅ قبول", callback_data=action_approve),
            InlineKeyboardButton("❌ رفض", callback_data=action_reject),
        ]
    ])

    # إرسال الطلب لمجموعة الأدمن الجديد بالنص الأصلي
    original_text = current_order["original_text"] or f"طلب #{order_code}"
    try:
        new_sent = await bot.send_message(
            chat_id=next_admin["group_id"],
            text=original_text,
            parse_mode="HTML",
            reply_markup=admin_keyboard,
        )
        # تحديث admin_msg_id في قاعدة البيانات للرسالة الجديدة
        set_order_original_text(order_code, original_text, new_sent.message_id)
    except Exception as e:
        logger.error(f"فشل إرسال الطلب للأدمن الجديد {next_admin['name']}: {e}")
        return None

    return next_admin


async def update_monitoring_message(bot, message_id, new_status_text):
    """
    تحديث رسالة المجموعة المركزية عند تغيّر حالة الطلب.
    """
    try:
        await bot.edit_message_text(
            chat_id=MONITORING_GROUP_ID,
            message_id=message_id,
            text=new_status_text,
            parse_mode="HTML",
        )
    except Exception as e:
        logger.error(f"فشل تحديث رسالة المجموعة المركزية: {e}")