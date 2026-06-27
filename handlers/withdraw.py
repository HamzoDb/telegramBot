# handlers/withdraw.py
import logging
import re
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import ContextTypes, ConversationHandler
from database.repository import (
    get_user_by_telegram,
    create_order,
    update_order_status,
    update_user_wallet_balance,
    get_order_by_code,
    update_user_stats_after_transaction,
    get_bot_account_name,
    has_pending_withdraw,
    lock_order_for_admin,
)
from handlers.navigation import add_to_stack
from config import ADMIN_IDS
from services.scoring import (
    calculate_user_score,
    get_user_tier_info,
    update_live_card,
    get_archive_link,
)
from services.admin_router import route_order_to_admin
from keyboards.main import back_only_markup

logger = logging.getLogger(__name__)

# حالات المحادثة
WD_WAIT_AMOUNT, WD_WAIT_METHOD, WD_WAIT_DESTINATION = range(3)
MIN_WITHDRAW = 25000

# تعبيرات التحقق من صحة بيانات الاستلام
SYRIATEL_PHONE_RE = re.compile(r"^09\d{8}$")
SYRIATEL_CODE_RE = re.compile(r"^\d{8}$")
SHAM_ID_RE = re.compile(r"^[a-f0-9]{32}$")


async def start_withdraw(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()

    user = update.effective_user
    user_row = get_user_by_telegram(user.id)

    if has_pending_withdraw(user_row["id"]):
        await query.edit_message_text(
            "⚠️ لديك طلب سحب قيد الانتظار!\n\n"
            "يرجى الانتظار حتى يتم مراجعة طلبك الحالي قبل تقديم طلب جديد.",
            reply_markup=back_only_markup(),
        )
        return ConversationHandler.END

    text = (
        f"📤 <b>سحب من المحفظة</b>\n\n"
        f"💵 رصيدك الحالي: <code>{user_row['wallet_balance']:,}</code> SYP\n\n"
        f"أرسل الآن المبلغ الذي تريد سحبه:"
    )

    await query.edit_message_text(
        text, parse_mode="HTML", reply_markup=back_only_markup()
    )
    context.application.user_data[user.id]["withdraw_msg_id"] = query.message.message_id
    return WD_WAIT_AMOUNT


async def wd_receive_amount(update: Update, context: ContextTypes.DEFAULT_TYPE):
    text = update.message.text
    user_id = update.effective_user.id
    msg_id = context.user_data.get("withdraw_msg_id")
    chat_id = update.effective_chat.id

    try:
        await update.message.delete()
    except Exception as e:
        logger.error(f"خطأ في حذف رسالة مبلغ السحب: {e}")

    if not text.isdigit():
        try:
            await context.bot.edit_message_text(
                chat_id=chat_id,
                message_id=msg_id,
                text="⚠️ <b>خطأ:</b> الرجاء إرسال أرقام فقط (بدون أحرف أو رموز).\n\nأعد كتابة المبلغ:",
                parse_mode="HTML",
                reply_markup=back_only_markup(),
            )
        except Exception as e:
            logger.error(f"خطأ في تعديل رسالة مبلغ السحب: {e}")
        return WD_WAIT_AMOUNT

    amount = int(text)

    if amount < MIN_WITHDRAW:
        try:
            await context.bot.edit_message_text(
                chat_id=chat_id,
                message_id=msg_id,
                text=f"⚠️ <b>مبلغ غير مقبول!</b>\n"
                f"🔴 الحد الأدنى للسحب: {MIN_WITHDRAW:,} SYP\n\n"
                f"أعد كتابة المبلغ بشكل صحيح:",
                parse_mode="HTML",
            )
        except Exception as e:
            logger.error(f"خطأ في تعديل رسالة مبلغ السحب: {e}")
        return WD_WAIT_AMOUNT

    user_row = get_user_by_telegram(user_id)
    if amount > user_row["wallet_balance"]:
        try:
            await context.bot.edit_message_text(
                chat_id=chat_id,
                message_id=msg_id,
                text=f"⚠️ <b>رصيد غير كافٍ!</b>\n"
                f"💵 رصيدك الحالي: {user_row['wallet_balance']:,} SYP\n\n"
                f"أعد كتابة مبلغ ضمن رصيدك المتاح:",
                parse_mode="HTML",
            )
        except Exception as e:
            logger.error(f"خطأ في تعديل رسالة مبلغ السحب: {e}")
        return WD_WAIT_AMOUNT

    context.user_data["withdraw_amount"] = amount

    keyboard = [
        [
            InlineKeyboardButton("🔴 Syriatel Cash", callback_data="wdpay|syriatel"),
            InlineKeyboardButton("🟢 Sham Cash", callback_data="wdpay|sham"),
        ],
        [InlineKeyboardButton("🔙 إلغاء", callback_data="nav|home")],
    ]

    try:
        await context.bot.edit_message_text(
            chat_id=chat_id,
            message_id=msg_id,
            text=f"✅ مبلغ السحب: <b>{amount:,} SYP</b>\n\nاختر وسيلة الاستلام:",
            reply_markup=InlineKeyboardMarkup(keyboard),
            parse_mode="HTML",
        )
    except Exception as e:
        logger.error(f"خطأ في تعديل رسالة وسيلة السحب: {e}")
    return WD_WAIT_METHOD


async def wd_select_method(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    method = query.data.split("|")[1]
    context.user_data["withdraw_method"] = method

    if method == "syriatel":
        instruction = (
            "📤 <b>سحب عبر Syriatel Cash</b>\n\n"
            "أرسل الآن رقم هاتفك (مثال: 0991234567)\n"
            "أو كود محفظتك المكوّن من 8 أرقام:"
        )
    else:
        instruction = (
            "📤 <b>سحب عبر Sham Cash</b>\n\n"
            "أرسل الآن معرّف محفظتك (32 خانة، أرقام وحروف):"
        )

    await query.edit_message_text(instruction, parse_mode="HTML")
    return WD_WAIT_DESTINATION


async def wd_receive_destination(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_input = update.message.text.strip()
    method = context.user_data.get("withdraw_method")
    msg_id = context.user_data.get("withdraw_msg_id")
    amount = context.user_data.get("withdraw_amount")
    chat_id = update.effective_chat.id

    try:
        await update.message.delete()
    except Exception as e:
        logger.error(f"خطأ في حذف رسالة وجهة السحب: {e}")

    # التحقق من صحة الصيغة حسب الوسيلة
    valid = False
    if method == "syriatel":
        valid = bool(SYRIATEL_PHONE_RE.match(user_input)) or bool(
            SYRIATEL_CODE_RE.match(user_input)
        )
        error_text = (
            "⚠️ <b>خطأ:</b> أرسل رقم هاتف صحيح (09xxxxxxxx) أو كود من 8 أرقام:"
        )
    else:
        valid = bool(SHAM_ID_RE.match(user_input.lower()))
        error_text = "⚠️ <b>خطأ:</b> المعرف يجب أن يتكون من 32 خانة (أرقام وحروف):"

    if not valid:
        try:
            await context.bot.edit_message_text(
                chat_id=chat_id, message_id=msg_id, text=error_text, parse_mode="HTML"
            )
        except Exception as e:
            logger.error(f"خطأ في تعديل رسالة خطأ وجهة السحب: {e}")
        return WD_WAIT_DESTINATION

    # --- خصم الرصيد فوراً ---
    user = update.effective_user
    user_row = get_user_by_telegram(user.id)

    if not user_row or user_row["wallet_balance"] < amount:
        try:
            await context.bot.edit_message_text(
                chat_id=chat_id,
                message_id=msg_id,
                text="⚠️ <b>رصيدك تغيّر منذ بدء الطلب، يرجى البدء من جديد.</b>",
                parse_mode="HTML",
            )
        except Exception as e:
            logger.error(f"خطأ في رسالة فشل خصم السحب: {e}")
        return ConversationHandler.END

    update_user_wallet_balance(user_row["id"], -amount)

    order = create_order(
        user_id=user_row["id"],
        service="WALLET_WITHDRAW",
        amount=amount,
        data=f"Method: {method} | Destination: {user_input}",
    )

    score = calculate_user_score(user_row)
    tier_info = get_user_tier_info(score)
    archive_url = get_archive_link(user_row)
    user_tg_link = f"<a href='tg://user?id={user.id}'>{user.first_name}</a>"
    bot_account_name = get_bot_account_name(user_row["id"]) or "بدون اسم"

    if archive_url:
        account_link = f"<a href='{archive_url}'>{bot_account_name}</a>"
    else:
        account_link = f"<code>{bot_account_name}</code> (لا يوجد ارشيف)"

    admin_text = (
        f"📤 <b>طلب سحب جديد (#{order['order_code']})</b>\n"
        f"━━━━━━━━━━━━━━\n"
        f"👤 <b>المستخدم:</b> {user_tg_link} | {tier_info['name']}\n"
        f"🗂 <b>الحساب: </b> {account_link}\n"
        f"📊 <b>التقييم:</b> {tier_info['stars']} ({score} نقطة)\n"
        f"━━━━━━━━━━━━━━\n"
        f"💰 <b>المبلغ:</b> {amount:,} SYP\n"
        f"🏦 <b>الوسيلة:</b> {method}\n"
        f"📍 <b>وجهة التحويل:</b> <code>{user_input}</code>\n"
    )

    assigned_admin = await route_order_to_admin(context.bot, order, admin_text)
    if not assigned_admin:
        logger.error(f"فشل توزيع طلب السحب {order['order_code']} على أي أدمن")

    try:
        await context.bot.edit_message_text(
            chat_id=chat_id,
            message_id=msg_id,
            text=(
                f"✅ <b>تم استلام طلب السحب بنجاح!</b>\n"
                f"💰 تم خصم {amount:,} SYP من رصيدك.\n"
                f"سيتم التحويل ومراجعة الطلب من قبل الإدارة قريباً."
            ),
            parse_mode="HTML",
        )
    except Exception as e:
        logger.error(f"خطأ في تأكيد طلب السحب للمستخدم {chat_id}: {e}")

    await add_to_stack(context, msg_id)
    return ConversationHandler.END


async def cancel_withdraw(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    if query:
        await query.answer("تم الإلغاء")
    return ConversationHandler.END


async def admin_withdraw_decision(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    from database.repository import get_admin_by_telegram_id
    if not get_admin_by_telegram_id(query.from_user.id):
        return

    data = query.data.split("|")
    action, order_code = data[1], data[2]
    order = get_order_by_code(order_code)

    if not order or order["status"] != "pending":
        await query.answer("⚠️ تم التعامل معه مسبقاً.")
        return

    from database.repository import get_user_by_id_helper
    user_db = get_user_by_id_helper(order["user_id"])

    if action == "approve":
        locked = lock_order_for_admin(order_code, query.from_user.id)
        if not locked:
            await query.answer(
                "⚠️ هذا الطلب تتم معالجته من قبل أدمن آخر حالياً.", show_alert=True
            )
            return

        context.bot_data.setdefault("awaiting_wd_code", {})
        context.bot_data["awaiting_wd_code"][query.from_user.id] = {
            "order_code": order_code,
            "admin_msg_id": query.message.message_id,
            "admin_msg_text": query.message.text,
        }
        await query.answer()
        await query.answer()
        from database.repository import get_admin_by_telegram_id
        admin_info = get_admin_by_telegram_id(query.from_user.id)
        if admin_info:
            try:
                await context.bot.send_message(
                    chat_id=admin_info["group_id"],
                    text=(
                        f"🔐 <b>مطلوب كود التحويل</b>\n"
                        f"━━━━━━━━━━━━━━\n"
                        f"الطلب: <code>{order_code}</code>\n\n"
                        f"أرسل الآن كود عملية التحويل في هذه المجموعة:"
                    ),
                    parse_mode="HTML",
                )
            except Exception as e:
                logger.error(f"خطأ في إرسال طلب الكود للمجموعة: {e}")
        try:
            await query.edit_message_reply_markup(reply_markup=None)
        except Exception as e:
            logger.error(f"خطأ في إزالة أزرار الطلب المقفول: {e}")

            
        # تحديث رسالة الاستعلامات فوراً
        from database.repository import get_admin_by_telegram_id as _get_adm
        from services.admin_router import update_monitoring_message
        _admin = _get_adm(query.from_user.id)
        _fresh_order = get_order_by_code(order_code)
        if _fresh_order and _fresh_order["monitoring_msg_id"]:
            _new_text = (
                query.message.text +
                f"\n━━━━━━━━━━━━━━\n"
                f"📌 <b>مُعيَّن لـ:</b> {_admin['name'] if _admin else 'أدمن'}\n"
                f"📊 <b>الحالة:</b> 🔄 جاري التحويل"
            )
            await update_monitoring_message(
                context.bot,
                _fresh_order["monitoring_msg_id"],
                _new_text,
            )

    elif action == "reject_menu":
        keyboard = [
            [InlineKeyboardButton("❌ بيانات استلام خاطئة", callback_data=f"wd_adm|do_reject|{order_code}|wrong_dest")],
            [InlineKeyboardButton("❌ مشكلة تقنية بالتحويل", callback_data=f"wd_adm|do_reject|{order_code}|tech_issue")],
            [InlineKeyboardButton("❌ سبب آخر", callback_data=f"wd_adm|do_reject|{order_code}|other")],
        ]
        await query.edit_message_reply_markup(reply_markup=InlineKeyboardMarkup(keyboard))

    elif action == "do_reject":
        reason_key = data[3]
        if reason_key == "wrong_dest":
            reason_text = "بيانات الاستلام المرسلة غير صحيحة."
        elif reason_key == "tech_issue":
            reason_text = "حدثت مشكلة تقنية أثناء التحويل."
        else:
            reason_text = "تعذر إتمام عملية السحب."

        # إعادة الرصيد المخصوم
        update_user_wallet_balance(user_db["id"], order["amount"])

        update_order_status(
            order_code, "rejected", rejection_reason=reason_text, processed_by=query.from_user.id
        )
        update_user_stats_after_transaction(
            user_db["id"], 0, is_deposit=False, is_success=False
        )

        await query.edit_message_text(f"{query.message.text}\n\n🚫 تم الرفض بسبب: {reason_text}\n💰 تم إرجاع المبلغ للمستخدم.")

        try:
            await context.bot.send_message(
                chat_id=user_db["telegram_id"],
                text=(
                    f"❌ <b>نعتذر منك، تم رفض طلب السحب (#{order_code})</b>\n\n"
                    f"📝 <b>السبب:</b> {reason_text}\n"
                    f"💰 تم إرجاع مبلغ {order['amount']:,} SYP إلى رصيدك."
                ),
                parse_mode="HTML",
            )
        except Exception as e:
            logger.error(f"خطأ في إرسال رفض السحب للمستخدم: {e}")


async def admin_receive_withdraw_code(update: Update, context: ContextTypes.DEFAULT_TYPE):
    admin_id = update.effective_user.id
    pending = context.bot_data.get("awaiting_wd_code", {})

    if admin_id not in pending:
        return

    info = pending.pop(admin_id)
    order_code = info["order_code"]
    transfer_code = update.message.text.strip()

    order = get_order_by_code(order_code)
    if not order or order["status"] != "processing" or order["locked_by_admin_id"] != admin_id:
        await update.message.reply_text("⚠️ هذا الطلب تمت معالجته مسبقاً أو ليس بانتظارك.")
        return

    from database.repository import get_user_by_id_helper
    user_db = get_user_by_id_helper(order["user_id"])

    update_order_status(order_code, "completed", processed_by=admin_id)
    update_user_stats_after_transaction(
        user_db["id"], order["amount"], is_deposit=False, is_success=True
    )
    await update_live_card(context.bot, user_db["id"])

    from database.repository import get_admin_by_telegram_id
    admin_info = get_admin_by_telegram_id(admin_id)
    if admin_info:
        try:
            await context.bot.edit_message_text(
                chat_id=admin_info["group_id"],
                message_id=info["admin_msg_id"],
                text=info["admin_msg_text"]
                + f"\n\n✅ تم التحويل بواسطة: {update.effective_user.first_name}"
                + f"\n🔢 كود العملية: {transfer_code}",
            )
        except Exception as e:
            logger.error(f"خطأ في تحديث رسالة مجموعة الأدمن بعد إدخال كود السحب: {e}")

    try:
        await context.bot.send_message(
            chat_id=user_db["telegram_id"],
            text=(
                f"✅ <b>تم تحويل مبلغ سحبك {order['amount']:,} SYP بنجاح!</b>\n"
                f"🔢 <b>كود عملية التحويل:</b> <code>{transfer_code}</code>"
            ),
            parse_mode="HTML",
        )
    except Exception as e:
        logger.error(f"خطأ في إرسال تأكيد السحب للمستخدم: {e}")

    await update.message.reply_text("✅ تم إرسال التأكيد للمستخدم بنجاح.")
    