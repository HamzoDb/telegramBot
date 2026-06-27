# handlers/admin.py
import asyncio
from telegram import InlineKeyboardMarkup, InlineKeyboardButton, Update
from telegram.ext import ContextTypes, CallbackQueryHandler, CommandHandler
from telegram.constants import ParseMode
from config import ADMIN_IDS
from database.repository import (
    get_order_by_code,
    update_order_status,
    get_account_by_id,
    update_account_name,
    get_conn,
    get_all_users_ids,
    update_payment_number_db,
    set_account_status,
)
from services.generators import generate_account_name
from keyboards.main import back_only_markup

# --- دوال الإذاعة والتحكم ---


async def broadcast_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    if user.id not in ADMIN_IDS:
        return
    message = " ".join(context.args)
    if not message:
        await update.message.reply_text("⚠️ الرجاء كتابة الرسالة بعد الأمر.")
        return
    await update.message.reply_text(f"⏳ جاري بدء الإذاعة...")
    users = get_all_users_ids()
    count, blocked = 0, 0
    for user_id in users:
        try:
            await context.bot.send_message(
                chat_id=user_id,
                text=f"📢 <b>رسالة عامة</b>\n\n{message}",
                parse_mode=ParseMode.HTML,
            )
            count += 1
            if count % 20 == 0:
                await asyncio.sleep(1)
        except:
            blocked += 1
    await update.message.reply_text(
        f"✅ تم الإرسال لـ: {count}\n🚫 حظروا البوت: {blocked}"
    )


async def dm_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    if user.id not in ADMIN_IDS:
        return
    if len(context.args) < 2:
        await update.message.reply_text("⚠️ الاستخدام: `/dm [ID] [الرسالة]`")
        return
    target_id, message = context.args[0], " ".join(context.args[1:])
    try:
        await context.bot.send_message(
            chat_id=int(target_id),
            text=f"📩 <b>رسالة من الإدارة:</b>\n\n{message}",
            parse_mode=ParseMode.HTML,
        )
        await update.message.reply_text(f"✅ تم الإرسال إلى {target_id}")
    except Exception as e:
        await update.message.reply_text(f"❌ فشل: {e}")


async def set_payment_number_command(
    update: Update, context: ContextTypes.DEFAULT_TYPE
):
    user = update.effective_user
    if user.id not in ADMIN_IDS:
        return
    command = update.message.text.split()[0].replace("/", "")
    if len(context.args) < 1:
        await update.message.reply_text(f"⚠️ الرجاء وضع الرقم الجديد.")
        return
    new_number = context.args[0]
    method = "syriatel" if "syriatel" in command else "sham"
    update_payment_number_db(method, new_number)
    await update.message.reply_text(
        f"✅ تم تحديث رقم {method.upper()} إلى: {new_number}"
    )


# --- معالج أزرار الإدارة ---


async def admin_cb(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    user = update.effective_user
    if user.id not in ADMIN_IDS:
        await query.answer("⛔ ليس لديك صلاحية.", show_alert=True)
        return

    data_parts = query.data.split("|")
    action = data_parts[1]

    # إصلاح IndexError: التحقق من زر لوحة التحكم
    if action == "dashboard":
        await query.answer()
        text = (
            "🛠️ <b>لوحة تحكم المشرفين:</b>\n\n"
            "<code>/broadcast [نص]</code> - إذاعة للكل\n"
            "<code>/dm [آيدي] [نص]</code> - رسالة خاصة\n"
            "<code>/set_syriatel [رقم]</code> - تحديث سيريتيل\n"
            "<code>/set_sham [رقم]</code> - تحديث شام"
        )
        await query.edit_message_text(text, parse_mode=ParseMode.HTML, reply_markup=back_only_markup())
        return

    if len(data_parts) < 3:
        return
    order_code = data_parts[2]
    order = get_order_by_code(order_code)
    if not order:
        await query.answer("❌ الطلب غير موجود", show_alert=True)
        return

    async def safe_edit(new_text, new_markup):
        try:
            if query.message.photo:
                await query.edit_message_caption(
                    caption=new_text, reply_markup=new_markup, parse_mode=ParseMode.HTML
                )
            else:
                await query.edit_message_text(
                    text=new_text, reply_markup=new_markup, parse_mode=ParseMode.HTML
                )
        except:
            pass

    if action == "claim":
        await query.answer("✅ بدأت المعالجة")
        current_text = (
            query.message.caption_html
            if query.message.photo
            else query.message.text_html
        )
        new_text = (
            current_text + f"\n\n⏳ <b>قيد المعالجة بواسطة:</b> {user.first_name}"
        )
        keyboard = [
            [
                InlineKeyboardButton(
                    "✅ تم", callback_data=f"admin|confirm|{order_code}"
                ),
                InlineKeyboardButton(
                    "❌ رفض", callback_data=f"admin|reject|{order_code}"
                ),
            ],
            [
                InlineKeyboardButton(
                    "🔄 إعادة توليد الاسم",
                    callback_data=f"admin|regen_ask|{order_code}",
                )
            ],
        ]
        await safe_edit(new_text, InlineKeyboardMarkup(keyboard))

    elif action == "regen_ask":
        await query.answer()
        keyboard = [
            [
                InlineKeyboardButton(
                    "نعم، غيّر الاسم", callback_data=f"admin|regen_do|{order_code}"
                ),
                InlineKeyboardButton(
                    "تراجع", callback_data=f"admin|regen_cancel|{order_code}"
                ),
            ]
        ]
        await query.edit_message_reply_markup(
            reply_markup=InlineKeyboardMarkup(keyboard)
        )

    elif action == "regen_do":
        account = get_account_by_id(order["account_id"])
        import re
        match = re.match(r"^MW(.+?)[A-Z]{2}\d{2}$", account["account_name"])
        base_name = match.group(1) if match else account["account_name"]
        new_name = generate_account_name(base_name, user.id)
        update_account_name(account["id"], new_name)
        await query.answer("🔄 تم التغيير!")
        current_text = (
            query.message.caption_html
            if query.message.photo
            else query.message.text_html
        )
        updated_text = (
            current_text.split("\n\n✏️")[0]
            + f"\n\n✏️ <b>الاسم الجديد:</b> <code>{new_name}</code>"
        )
        keyboard = [
            [
                InlineKeyboardButton(
                    "✅ تم", callback_data=f"admin|confirm|{order_code}"
                ),
                InlineKeyboardButton(
                    "❌ رفض", callback_data=f"admin|reject|{order_code}"
                ),
            ]
        ]
        await safe_edit(updated_text, InlineKeyboardMarkup(keyboard))

    elif action == "confirm":
        account = get_account_by_id(order["account_id"])
        conn = get_conn()
        user_row = conn.execute(
            "SELECT telegram_id FROM users WHERE id=?", (order["user_id"],)
        ).fetchone()
        conn.close()
        if user_row:
            try:
                msg = f"✅ <b>تم تفعيل حسابك</b>\n\n👤 <b>الاسم:</b> <code>{account['account_name']}</code>\n🔑 <b>الباسورد:</b> <code>{account['password']}</code>"
                await context.bot.send_message(
                    chat_id=user_row["telegram_id"], text=msg, parse_mode=ParseMode.HTML
                )
            except:
                pass
        update_order_status(order_code, "completed", processed_by=user.id)
        set_account_status(account["id"], "فعال ✅")
        await query.answer("✅ تم")
        await safe_edit("✅ تم التنفيذ بنجاح.", None)

    elif action == "reject":
        update_order_status(order_code, "rejected", processed_by=user.id)
        await query.answer("❌ تم الرفض")
        await safe_edit("❌ تم رفض الطلب.", None)


def register_admin_handlers(app):
    app.add_handler(CallbackQueryHandler(admin_cb, pattern=r"^adm\|"))
    app.add_handler(CallbackQueryHandler(monitoring_skip_cb, pattern=r"^mon\|skip\|"))
    app.add_handler(CommandHandler("broadcast", broadcast_command))
    app.add_handler(CommandHandler("dm", dm_command))
    app.add_handler(CommandHandler("set_syriatel", set_payment_number_command))
    app.add_handler(CommandHandler("set_sham", set_payment_number_command))


async def monitoring_skip_cb(update, context):
    query = update.callback_query
    from database.repository import get_admin_by_telegram_id
    admin = get_admin_by_telegram_id(query.from_user.id)
    if not admin:
        await query.answer("⛔ ليس لديك صلاحية.", show_alert=True)
        return

    data = query.data.split("|")
    order_code = data[2]

    from database.repository import get_order_by_code
    order = get_order_by_code(order_code)
    if not order or order["status"] not in ("pending", "processing"):
        await query.answer("⚠️ تم التعامل مع هذا الطلب مسبقاً.")
        return

    from services.admin_router import skip_order_to_next_admin
    next_admin = await skip_order_to_next_admin(
        context.bot, order_code, query.message.message_id
    )

    if next_admin:
        from telegram import InlineKeyboardButton, InlineKeyboardMarkup
        await query.edit_message_text(
            query.message.text
            + f"\n\n⏭️ تم التحويل لـ: {next_admin['name']}",
            parse_mode="HTML",
            reply_markup=InlineKeyboardMarkup([
                [InlineKeyboardButton(
                    "⏭️ تخطي مرة أخرى",
                    callback_data=f"mon|skip|{order_code}"
                )]
            ]),
        )
        await query.answer(f"✅ تم التحويل لـ {next_admin['name']}")
    else:
        await query.answer("⚠️ فشل التحويل، لا يوجد أدمن آخر متاح.", show_alert=True)
