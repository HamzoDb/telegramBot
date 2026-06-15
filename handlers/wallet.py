# handlers/wallet.py
import logging
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import ContextTypes, ConversationHandler
from database.repository import (
    get_user_by_telegram,
    set_user_state,
    create_order,
    update_order_status,
    update_user_wallet_balance,
    get_order_by_code,
    has_pending_deposit,
    is_transaction_used,
    increment_incomplete_orders,
    update_user_stats_after_transaction,
    get_payment_numbers,
    get_bot_account_name,
)
from handlers.navigation import add_to_stack
from database.db import get_conn
from config import DEPOSITS_GROUP_ID, ADMIN_IDS
from services.scoring import (
    calculate_user_score,
    get_user_tier_info,
    update_live_card,
    get_archive_link,
)
from keyboards.main import back_only_markup

# إعداد السجلات للتتبع
logger = logging.getLogger(__name__)

# تعريف الحالات
WAIT_AMOUNT, WAIT_CODE = range(2)
MIN_DEPOSIT = 25000
MAX_DEPOSIT = 10000000


def get_user_by_id_helper(db_id):
    conn = get_conn()
    cur = conn.cursor()
    cur.execute("SELECT * FROM users WHERE id=?", (db_id,))
    res = cur.fetchone()
    conn.close()
    return res


async def start_deposit(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()

    print("🚀 [WALLET] دخلنا دالة start_deposit")  # تتبع في التيرمنال

    user = update.effective_user
    user_row = get_user_by_telegram(user.id)

    if has_pending_deposit(user_row["id"]):
        await query.edit_message_text(
            "⚠️ لديك طلب إيداع قيد المراجعة حالياً، يرجى الانتظار.",
            reply_markup=back_only_markup(),
        )
        return ConversationHandler.END

    increment_incomplete_orders(user_row["id"])

    text = (
        f"💰 <b>إيداع رصيد (المحفظة)</b>\n\n"
        f"💵 رصيدك الحالي: <code>{user_row['wallet_balance']:,}</code> SYP\n"
        f"⚠️ الحد الأدنى للإيداع: <b>{MIN_DEPOSIT:,}</b> SYP\n\n"
        f"أرسل الآن المبلغ الذي تود شحنه:"
    )

    await query.edit_message_text(
        text, parse_mode="HTML", reply_markup=back_only_markup()
    )
    context.application.user_data[user.id]["deposit_msg_id"] = query.message.message_id
    return WAIT_AMOUNT


async def receive_amount(update: Update, context: ContextTypes.DEFAULT_TYPE):
    text = update.message.text
    user_id = update.effective_user.id
    msg_id = context.user_data.get("deposit_msg_id")

    # 1. حذف رسالة المستخدم فوراً (تنظيف)
    try:
        await update.message.delete()
    except:
        pass

    # 2. التحقق: هل النص أرقام فقط؟
    if not text.isdigit():
        # إذا أرسل نصاً، نعيد طلب المبلغ مع تنبيه
        try:
            await context.bot.edit_message_text(
                chat_id=user_id,
                message_id=msg_id,
                text=f"⚠️ <b>خطأ:</b> الرجاء إرسال أرقام فقط (بدون أحرف أو رموز).\n\nأعد كتابة المبلغ:",
                parse_mode="HTML",
                reply_markup=back_only_markup(),
            )
        except:
            pass
        return WAIT_AMOUNT

    amount = int(text)

    # 3. التحقق: هل المبلغ ضمن الحدود (بين 25 ألف و 5 مليون)؟
    if amount < MIN_DEPOSIT or amount > MAX_DEPOSIT:
        try:
            await context.bot.edit_message_text(
                chat_id=user_id,
                message_id=msg_id,
                text=f"⚠️ <b>مبلغ غير مقبول!</b>\n"
                f"🔴 الحد الأدنى: {MIN_DEPOSIT:,}\n"
                f"🔴 الحد الأعلى: {MAX_DEPOSIT:,}\n\n"
                f"أعد كتابة المبلغ بشكل صحيح:",
                parse_mode="HTML",
            )
        except:
            pass
        return WAIT_AMOUNT

    # ✅ المبلغ سليم، ننتقل للتالي
    context.user_data["deposit_amount"] = amount

    keyboard = [
        [
            InlineKeyboardButton("🔴 Syriatel Cash", callback_data="pay|syriatel"),
            InlineKeyboardButton("🟢 Sham Cash", callback_data="pay|sham"),
        ],
        [InlineKeyboardButton("🔙 إلغاء", callback_data="nav|home")],
    ]

    if msg_id:
        try:
            await context.bot.edit_message_text(
                chat_id=update.effective_chat.id,
                message_id=msg_id,
                text=f"✅ المبلغ المطلوب: <b>{amount:,} SYP</b>\n\nاختر وسيلة الدفع:",
                reply_markup=InlineKeyboardMarkup(keyboard),
                parse_mode="HTML",
            )
        except Exception:
            pass
    return WAIT_CODE  # ننتظر اختيار الوسيلة ثم الكود


async def select_payment_method(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    method = query.data.split("|")[1]
    context.user_data["payment_method"] = method

    print(f"💳 [WALLET] تم اختيار الوسيلة: {method}")

    # جلب الأرقام من الداتا بيس بدلاً من الأرقام الثابتة
    from database.repository import get_payment_numbers

    numbers = get_payment_numbers()
    phone = numbers.get(method, "09xxxxxxxx")

    instruction = (
        f"📥 <b>تعليمات الدفع ({method.upper()})</b>\n"
        f"━━━━━━━━━━━━━━\n"
        f"يرجى التحويل إلى الرقم: <code>{phone}</code>\n"
        f"المبلغ المطلوب: <b>{context.user_data['deposit_amount']:,}</b> SYP\n\n"
        f"⚠️ <b>أرسل رمز العملية الآن لتأكيد الطلب:</b>"
    )
    await query.edit_message_text(instruction, parse_mode="HTML")
    return WAIT_CODE


async def receive_transaction_code(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_code = update.message.text.strip()
    method = context.user_data.get("payment_method")
    msg_id = context.user_data.get("deposit_msg_id")
    amount = context.user_data.get("deposit_amount")
    chat_id = update.effective_chat.id

    print(f"🔢 [WALLET] تم استلام الكود: {user_code}")

    # 1. حذف رسالة المستخدم فوراً
    try:
        await update.message.delete()
    except Exception:
        pass

    # 2. تحديد الطول المطلوب بناءً على الوسيلة
    required_len = 12 if method == "syriatel" else 8

    # 3. فحص الأخطاء (أحرف أو طول غير متطابق)
    error_msg = None
    if not user_code.isdigit():
        error_msg = (
            "⚠️ <b>خطأ:</b> الكود يجب أن يتكون من أرقام فقط.\nأعد إرسال الكود الصحيح:"
        )
    elif len(user_code) != required_len:
        error_msg = f"⚠️ <b>خطأ:</b> كود {method.upper()} يجب أن يكون {required_len} رقم.\nأنت أرسلت {len(user_code)} رقم. أعد المحاولة:"

    if error_msg:
        try:
            await context.bot.edit_message_text(
                chat_id=chat_id, message_id=msg_id, text=error_msg, parse_mode="HTML"
            )
        except:
            pass
        return WAIT_CODE

    # 4. فحص التكرار (مع تعديل الرسالة بدلاً من إرسال واحدة جديدة)
    if is_transaction_used(user_code):
        try:
            await context.bot.edit_message_text(
                chat_id=chat_id,
                message_id=msg_id,
                text="⚠️ <b>عذراً:</b> هذا الكود مستخدم مسبقاً في عملية أخرى.\nتأكد من الكود وأعد إرساله:",
                parse_mode="HTML",
            )
        except:
            pass
        return WAIT_CODE

    # --- إذا اجتاز الفحوصات، نكمل الإجراءات ---
    user = update.effective_user
    user_row = get_user_by_telegram(user.id)

    if not user_row:
        return ConversationHandler.END

    order = create_order(
        user_id=user_row["id"],
        service="WALLET_DEPOSIT",
        amount=amount,
        data=f"Method: {method}",
        transaction_code=user_code,
    )

    # جلب معلومات التقييم والأرشفة
    score = calculate_user_score(user_row)
    tier_info = get_user_tier_info(score)
    archive_url = get_archive_link(user_row)
    user_tg_link = f"<a href='tg://user?id={user.id}'>{user.first_name}</a>"

    bot_account_name = get_bot_account_name(user_row["id"]) or "بدون اسم"

    if archive_url:
        account_link = f"<a href='{archive_url}'>{bot_account_name}</a>"
    else:
        account_link = f"<code>{bot_account_name}</code> (لا يوجد ارشيف)"

    # تحضير رسالة المشرف (تجهيزاً للروابط الزرقاء في الخطوة القادمة)
    admin_text = (
        f"📥 <b>طلب إيداع جديد (#{order['order_code']})</b>\n"
        f"━━━━━━━━━━━━━━\n"
        f"👤 <b>المستخدم:</b> {user_tg_link} | {tier_info['name']}\n"
        f"🗂 <b>الحساب: </b> {account_link}\n"
        f"📊 <b>التقييم:</b> {tier_info['stars']} ({score} نقطة)\n"
        f"━━━━━━━━━━━━━━\n"
        f"💰 <b>المبلغ:</b> {amount:,} SYP\n"
        f"🏦 <b>الوسيلة:</b> {method}\n"
        f"🔢 <b>الكود:</b> <code>{user_code}</code>\n"
    )

    keyboard = [
        [
            InlineKeyboardButton(
                "✅ قبول", callback_data=f"dep_adm|approve|{order['order_code']}"
            ),
            InlineKeyboardButton(
                "❌ رفض", callback_data=f"dep_adm|reject_menu|{order['order_code']}"
            ),
        ]
    ]

    await context.bot.send_message(
        chat_id=DEPOSITS_GROUP_ID,
        text=admin_text,
        parse_mode="HTML",
        reply_markup=InlineKeyboardMarkup(keyboard),
    )

    await context.bot.edit_message_text(
        chat_id=chat_id,
        message_id=msg_id,
        text="✅ <b>تم استلام طلبك بنجاح!</b>\nسيتم إشعارك فور معالجة الطلب من قبل الإدارة.",
        parse_mode="HTML",
    )
    await add_to_stack(context, msg_id)

    return ConversationHandler.END


async def admin_deposit_decision(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    if query.from_user.id not in ADMIN_IDS:
        return

    data = query.data.split("|")
    action, order_code = data[1], data[2]
    order = get_order_by_code(order_code)

    if not order or order["status"] != "pending":
        await query.answer("⚠️ تم التعامل معه مسبقاً.")
        return

    user_db = get_user_by_id_helper(order["user_id"])

    if action == "approve":
        # 1. تحديثات الداتابيز (تأكد أن هذا الجزء يعمل لديك)
        update_order_status(order_code, "completed", processed_by=query.from_user.id)
        update_user_wallet_balance(user_db["id"], order["amount"])
        update_user_stats_after_transaction(
            user_db["id"], order["amount"], is_deposit=True, is_success=True
        )
        await update_live_card(context.bot, user_db["id"])

        # 2. تحديث رسالة الإدارة
        await query.edit_message_text(
            query.message.text + f"\n\n✅ تم القبول بواسطة: {query.from_user.first_name}"
        )

        # --- التصحيح هنا ---
        user_id_tg = user_db["telegram_id"]

        # الوصول لذاكرة المستخدم بشكل آمن
        user_data = context.application.user_data.get(user_id_tg, {})

        # جلب آيدي الرسالة القديمة من الذاكرة (وليس من user_db)
        old_msg_id = user_data.get("deposit_msg_id")

        # 3. محاولة حذف الرسالة القديمة
        if old_msg_id:
            try:
                await context.bot.delete_message(chat_id=user_id_tg, message_id=old_msg_id)
            except Exception as e:
                logging.error(f"Error deleting old deposit msg: {e}")

        # 4. إرسال رسالة النجاح للمستخدم
        sent_msg = await context.bot.send_message(
            chat_id=user_id_tg,
            text=f"✅ <b>تم قبول إيداعك بمبلغ {order['amount']:,} SYP بنجاح!</b>\nتمت إضافة الرصيد إلى محفظتك.",
            parse_mode="HTML"
        )

        # 5. إضافة الرسالة الجديدة للمكنسة (تأكد من إنشاء الـ stack إذا لم يكن موجوداً)
        if "msg_stack" not in user_data:
            context.application.user_data[user_id_tg]["msg_stack"] = []

        context.application.user_data[user_id_tg]["msg_stack"].append(sent_msg.message_id)

    elif action == "reject_menu":
        keyboard = [
            [InlineKeyboardButton("❌ مبلغ غير متطابق", callback_data=f"dep_adm|do_reject|{order_code}|mismatch")],
            [InlineKeyboardButton("❌ كود عملية خاطئ", callback_data=f"dep_adm|do_reject|{order_code}|wrong_code")],
            [InlineKeyboardButton("❌ لم يصلنا أي مبلغ", callback_data=f"dep_adm|do_reject|{order_code}|not_received")],
            [InlineKeyboardButton("🔙 تراجع", callback_data=f"dep_adm|back_to_main|{order_code}")]
        ]
        await query.edit_message_reply_markup(
            reply_markup=InlineKeyboardMarkup(keyboard)
        )

    elif action == "do_reject":
        reason_key = data[3]

        # 1. تحديد نص السبب بناءً على المفتاح القادم من الزر
        if reason_key == "mismatch":
            reason_text = "المبلغ المحول غير مطابق للمبلغ المسجل في الطلب."
        elif reason_key == "wrong_code":
            reason_text = "كود العملية المرسل غير صحيح أو غير مكتمل."
        elif reason_key == "not_received":
            reason_text = "لم يصلنا أي إشعار بتحويل بهذا الكود حتى الآن."
        else:
            reason_text = "مخالفة شروط الإيداع."

        # 2. تحديث قاعدة البيانات
        update_order_status(
            order_code,
            "rejected",
            rejection_reason=reason_text,
            processed_by=query.from_user.id,
        )
        update_user_stats_after_transaction(
            user_db["id"], 0, is_deposit=True, is_success=False
        )

        # 3. تعديل رسالة الإدارة لتوضيح أنه تم الرفض مع السبب
        await query.edit_message_text(f"{query.message.text}\n\n🚫 تم الرفض بسبب: {reason_text}")

        # 4. إرسال الإشعار اللبق للمستخدم
        try:
            user_msg = (
                f"❌ <b>نعتذر منك، تم رفض طلب الإيداع (#{order_code})</b>\n\n"
                f"📝 <b>السبب:</b> {reason_text}\n"
                f"💡 يرجى التأكد من بيانات التحويل وإعادة المحاولة بطلب جديد."
            )
            await context.bot.send_message(
                chat_id=user_db["telegram_id"],
                text=user_msg,
                parse_mode="HTML"
            )
        except Exception as e:
            logger.error(f"Failed to send rejection to user: {e}")



async def cancel_deposit(update: Update, context: ContextTypes.DEFAULT_TYPE):
    # بدلاً من الاستدعاء الدائري، نستخدم الرد المباشر
    query = update.callback_query
    if query:
        await query.answer("تم الإلغاء")
    return ConversationHandler.END
