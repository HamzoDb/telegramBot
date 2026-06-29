# handlers/game_account.py
import logging
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import ContextTypes, ConversationHandler, CallbackQueryHandler, MessageHandler, filters
from database.repository import (
    get_user_by_telegram,
    get_account_by_id,
    get_order_by_code,
    create_order,
    update_order_status,
    update_user_wallet_balance,
    update_user_stats_after_transaction,
    get_user_by_id_helper,
    has_pending_game_deposit,
    has_pending_game_withdraw,
)
from services.admin_router import route_order_to_admin
from services.scoring import (
    calculate_user_score,
    get_user_tier_info,
    update_live_card,
    get_archive_link,
)
from keyboards.main import back_only_markup
from handlers.navigation import add_to_stack

logger = logging.getLogger(__name__)

# حالات المحادثة
GA_WAIT_AMOUNT = 0
MIN_AMOUNT = 25000


# ──────────────────────────────────────────
# إيداع للحساب (خصم من المحفظة)
# ──────────────────────────────────────────

async def start_game_deposit(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()

    account_id = query.data.split("|")[2]
    user = update.effective_user
    user_row = get_user_by_telegram(user.id)
    account = get_account_by_id(account_id)

    if not account or account["status"] not in ("active", "completed"):
        await query.edit_message_text(
            "⚠️ لا يمكن الإيداع لحساب غير فعال.",
            reply_markup=back_only_markup(),
        )
        return ConversationHandler.END

    if has_pending_game_deposit(user_row["id"]):
        await query.edit_message_text(
            "⚠️ لديك طلب إيداع للحساب قيد المراجعة، يرجى الانتظار.",
            reply_markup=back_only_markup(),
        )
        return ConversationHandler.END

    if user_row["wallet_balance"] < MIN_AMOUNT:
        await query.edit_message_text(
            f"⚠️ رصيد محفظتك غير كافٍ.\n"
            f"💵 رصيدك الحالي: <code>{user_row['wallet_balance']:,}</code> SYP\n"
            f"🔴 الحد الأدنى: <b>{MIN_AMOUNT:,}</b> SYP",
            parse_mode="HTML",
            reply_markup=back_only_markup(),
        )
        return ConversationHandler.END

    context.user_data["game_account_id"] = account_id
    context.user_data["game_action"] = "deposit"

    msg = await query.edit_message_text(
        f"💰 <b>إيداع للحساب</b>\n\n"
        f"🔖 الحساب: <code>{account['account_name']}</code>\n"
        f"💵 رصيد محفظتك: <code>{user_row['wallet_balance']:,}</code> SYP\n"
        f"🔴 الحد الأدنى: <b>{MIN_AMOUNT:,}</b> SYP\n\n"
        f"أرسل المبلغ الذي تريد إيداعه:",
        parse_mode="HTML",
        reply_markup=back_only_markup(),
    )
    context.user_data["game_msg_id"] = msg.message_id
    return GA_WAIT_AMOUNT


async def start_game_withdraw(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()

    account_id = query.data.split("|")[2]
    user = update.effective_user
    user_row = get_user_by_telegram(user.id)
    account = get_account_by_id(account_id)

    if not account or account["status"] not in ("active", "completed"):
        await query.edit_message_text(
            "⚠️ لا يمكن السحب من حساب غير فعال.",
            reply_markup=back_only_markup(),
        )
        return ConversationHandler.END

    if has_pending_game_withdraw(user_row["id"]):
        await query.edit_message_text(
            "⚠️ لديك طلب سحب من الحساب قيد المراجعة، يرجى الانتظار.",
            reply_markup=back_only_markup(),
        )
        return ConversationHandler.END

    context.user_data["game_account_id"] = account_id
    context.user_data["game_action"] = "withdraw"

    msg = await query.edit_message_text(
        f"💸 <b>سحب من حساب اللعبة</b>\n\n"
        f"🔖 الحساب: <code>{account['account_name']}</code>\n"
        f"🔴 الحد الأدنى: <b>{MIN_AMOUNT:,}</b> SYP\n\n"
        f"أرسل المبلغ الذي تريد سحبه من الحساب:",
        parse_mode="HTML",
        reply_markup=back_only_markup(),
    )
    context.user_data["game_msg_id"] = msg.message_id
    return GA_WAIT_AMOUNT


async def ga_receive_amount(update: Update, context: ContextTypes.DEFAULT_TYPE):
    text = update.message.text
    user = update.effective_user
    user_row = get_user_by_telegram(user.id)
    msg_id = context.user_data.get("game_msg_id")
    account_id = context.user_data.get("game_account_id")
    action = context.user_data.get("game_action")
    chat_id = update.effective_chat.id

    try:
        await update.message.delete()
    except Exception as e:
        logger.error(f"خطأ في حذف رسالة المبلغ: {e}")

    if not text.isdigit():
        try:
            await context.bot.edit_message_text(
                chat_id=chat_id, message_id=msg_id,
                text="⚠️ أرسل أرقام فقط، أعد المحاولة:",
                parse_mode="HTML", reply_markup=back_only_markup(),
            )
        except Exception as e:
            logger.error(f"خطأ في تعديل رسالة المبلغ: {e}")
        return GA_WAIT_AMOUNT

    amount = int(text)

    if amount < MIN_AMOUNT:
        try:
            await context.bot.edit_message_text(
                chat_id=chat_id, message_id=msg_id,
                text=f"⚠️ <b>مبلغ غير مقبول!</b>\n🔴 الحد الأدنى: {MIN_AMOUNT:,} SYP\n\nأعد إرسال المبلغ:",
                parse_mode="HTML",
            )
        except Exception as e:
            logger.error(f"خطأ في تعديل رسالة المبلغ: {e}")
        return GA_WAIT_AMOUNT

    if action == "deposit" and amount > user_row["wallet_balance"]:
        try:
            await context.bot.edit_message_text(
                chat_id=chat_id, message_id=msg_id,
                text=f"⚠️ <b>رصيد غير كافٍ!</b>\n💵 رصيدك: {user_row['wallet_balance']:,} SYP\n\nأعد إرسال مبلغ ضمن رصيدك:",
                parse_mode="HTML",
            )
        except Exception as e:
            logger.error(f"خطأ في تعديل رسالة المبلغ: {e}")
        return GA_WAIT_AMOUNT

    account = get_account_by_id(account_id)

    # خصم فوري من المحفظة عند إيداع للحساب
    if action == "deposit":
        update_user_wallet_balance(user_row["id"], -amount)
        service = "GAME_DEPOSIT"
        emoji = "💰"
        action_text = "إيداع لحساب اللعبة"
    else:
        service = "GAME_WITHDRAW"
        emoji = "💸"
        action_text = "سحب من حساب اللعبة"

    order = create_order(
        user_id=user_row["id"],
        service=service,
        account_id=int(account_id),
        amount=amount,
    )

    if not order:
        if action == "deposit":
            update_user_wallet_balance(user_row["id"], amount)
        try:
            await context.bot.edit_message_text(
                chat_id=chat_id, message_id=msg_id,
                text="⚠️ حدث خطأ أثناء إنشاء الطلب، يرجى المحاولة لاحقاً.",
                parse_mode="HTML", reply_markup=back_only_markup(),
            )
        except Exception as e:
            logger.error(f"خطأ في رسالة فشل إنشاء الطلب: {e}")
        return ConversationHandler.END

    score = calculate_user_score(user_row)
    tier_info = get_user_tier_info(score)
    archive_url = get_archive_link(user_row)
    user_tg_link = f"<a href='tg://user?id={user.id}'>{user.first_name}</a>"
    bot_account_name = account["account_name"] if account else "غير معروف"

    if archive_url:
        account_link = f"<a href='{archive_url}'>{bot_account_name}</a>"
    else:
        account_link = f"<code>{bot_account_name}</code>"

    admin_text = (
        f"{emoji} <b>طلب {action_text} (#{order['order_code']})</b>\n"
        f"━━━━━━━━━━━━━━\n"
        f"👤 <b>المستخدم:</b> {user_tg_link} | {tier_info['name']}\n"
        f"🗂 <b>الحساب:</b> {account_link}\n"
        f"📊 <b>التقييم:</b> {tier_info['stars']} ({score} نقطة)\n"
        f"━━━━━━━━━━━━━━\n"
        f"💰 <b>المبلغ:</b> {amount:,} SYP\n"
        f"🎮 <b>النوع:</b> {'إيداع للحساب من المحفظة' if action == 'deposit' else 'سحب من حساب اللعبة للمحفظة'}\n"
    )

    assigned_admin = await route_order_to_admin(context.bot, order, admin_text)
    if not assigned_admin:
        logger.error(f"فشل توزيع طلب {service} {order['order_code']} على أي أدمن")

    if action == "deposit":
        confirm_text = (
            f"✅ <b>تم استلام طلب الإيداع للحساب!</b>\n"
            f"💰 تم خصم <b>{amount:,} SYP</b> من محفظتك.\n"
            f"سيتم الإيداع في حسابك بعد مراجعة الإدارة."
        )
    else:
        confirm_text = (
            f"✅ <b>تم استلام طلب السحب من الحساب!</b>\n"
            f"💰 المبلغ المطلوب: <b>{amount:,} SYP</b>\n"
            f"سيتم إضافة الرصيد لمحفظتك بعد مراجعة الإدارة."
        )

    try:
        await context.bot.edit_message_text(
            chat_id=chat_id, message_id=msg_id,
            text=confirm_text, parse_mode="HTML",
        )
    except Exception as e:
        logger.error(f"خطأ في رسالة تأكيد طلب اللعبة: {e}")

    await add_to_stack(context, msg_id)
    return ConversationHandler.END


# ──────────────────────────────────────────
# قرار الأدمن
# ──────────────────────────────────────────

async def admin_game_decision(update: Update, context: ContextTypes.DEFAULT_TYPE):
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

    user_db = get_user_by_id_helper(order["user_id"])
    is_deposit = order["service"] == "GAME_DEPOSIT"

    if action == "approve":
        update_order_status(order_code, "completed", processed_by=query.from_user.id)

        if not is_deposit:
            # سحب من اللعبة: أضف للمحفظة عند الموافقة
            update_user_wallet_balance(user_db["id"], order["amount"])

        update_user_stats_after_transaction(
            user_db["id"], order["amount"],
            is_deposit=is_deposit, is_success=True,
        )
        await update_live_card(context.bot, user_db["id"])

        await query.edit_message_text(
            query.message.text +
            f"\n\n✅ تمت الموافقة بواسطة: {query.from_user.first_name}"
        )

        action_done = "تم الإيداع في حسابك بنجاح" if is_deposit else "تم إضافة الرصيد لمحفظتك بنجاح"
        try:
            await context.bot.send_message(
                chat_id=user_db["telegram_id"],
                text=(
                    f"✅ <b>{action_done}!</b>\n"
                    f"💰 المبلغ: <b>{order['amount']:,} SYP</b>"
                ),
                parse_mode="HTML",
            )
        except Exception as e:
            logger.error(f"خطأ في إرسال تأكيد قرار اللعبة للمستخدم: {e}")

    elif action == "reject_menu":
        if is_deposit:
            reasons = [
                ("❌ رصيد المحفظة غير كافٍ", "low_balance"),
                ("❌ خطأ تقني، نعمل على الإصلاح", "tech_error"),
                ("❌ الموقع يواجه مشكلة عامة", "site_issue"),
                ("❌ بيانات الحساب غير صحيحة", "wrong_info"),
            ]
        else:
            reasons = [
                ("❌ رصيد الحساب في الموقع غير كافٍ", "low_game_balance"),
                ("❌ خطأ تقني، نعمل على الإصلاح", "tech_error"),
                ("❌ الموقع يواجه مشكلة عامة", "site_issue"),
                ("❌ بيانات الحساب غير صحيحة", "wrong_info"),
            ]

        keyboard = [
            [InlineKeyboardButton(
                text, callback_data=f"adm_game|do_reject|{order_code}|{key}"
            )]
            for text, key in reasons
        ]
        await query.edit_message_reply_markup(
            reply_markup=InlineKeyboardMarkup(keyboard)
        )

    elif action == "do_reject":
        reason_key = data[3]
        reason_map = {
            "low_balance":      "رصيد المحفظة غير كافٍ لإتمام عملية الإيداع.",
            "low_game_balance": "رصيد حسابك في الموقع غير كافٍ لإتمام عملية السحب.",
            "tech_error":       "حدث خطأ تقني، نعمل على إصلاحه في أقرب وقت.",
            "site_issue":       "الموقع يواجه مشكلة عامة حالياً، يرجى المحاولة لاحقاً.",
            "wrong_info":       "بيانات الحساب غير صحيحة أو غير مكتملة.",
        }
        reason_text = reason_map.get(reason_key, "تعذر إتمام العملية.")

        if is_deposit:
            # إعادة المبلغ المخصوم عند رفض إيداع اللعبة
            update_user_wallet_balance(user_db["id"], order["amount"])

        update_order_status(
            order_code, "rejected",
            rejection_reason=reason_text,
            processed_by=query.from_user.id,
        )
        update_user_stats_after_transaction(
            user_db["id"], 0, is_deposit=is_deposit, is_success=False
        )

        await query.edit_message_text(
            query.message.text +
            f"\n\n🚫 تم الرفض بسبب: {reason_text}"
            + ("\n💰 تم إرجاع المبلغ للمستخدم." if is_deposit else "")
        )

        refund_note = f"\n💰 تم إرجاع <b>{order['amount']:,} SYP</b> لمحفظتك." if is_deposit else ""
        try:
            await context.bot.send_message(
                chat_id=user_db["telegram_id"],
                text=(
                    f"❌ <b>تم رفض طلبك (#{order_code})</b>\n\n"
                    f"📝 <b>السبب:</b> {reason_text}"
                    f"{refund_note}"
                ),
                parse_mode="HTML",
            )
        except Exception as e:
            logger.error(f"خطأ في إرسال رفض طلب اللعبة للمستخدم: {e}")


def register_game_account_handlers(app):
    from telegram.ext import ConversationHandler

    game_conv = ConversationHandler(
        entry_points=[
            CallbackQueryHandler(start_game_deposit, pattern=r"^act\|deposit_game\|"),
            CallbackQueryHandler(start_game_withdraw, pattern=r"^act\|withdraw_game\|"),
        ],
        states={
            GA_WAIT_AMOUNT: [
                MessageHandler(filters.TEXT & ~filters.COMMAND, ga_receive_amount)
            ],
        },
        fallbacks=[],
        allow_reentry=True,
    )
    app.add_handler(game_conv)
    app.add_handler(
        CallbackQueryHandler(admin_game_decision, pattern=r"^adm_game\|")
    )
