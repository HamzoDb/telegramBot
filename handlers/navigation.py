# handlers/navigation.py
from telegram.ext import CallbackQueryHandler
from telegram.error import BadRequest
from keyboards.main import main_menu_keyboard
from database.repository import set_user_state, get_user_by_telegram
from config import ADMIN_IDS


async def nav_handler(update, context):
    query = update.callback_query
    data = query.data
    user = update.effective_user

    # الرد السريع
    try:
        await query.answer()
    except Exception:
        pass

    # نحذف Stack بعد التعديل وليس قبله

    try:
        action = data.split("|")[1]
    except (IndexError, AttributeError):
        return

    # منع الرجوع أثناء إنشاء الحساب
    user_row = get_user_by_telegram(user.id)
    current_state = user_row["state"] if user_row else "START"
    if action == "back" and current_state == "CREATING_USERNAME":
        await query.answer("⚠️ أكمل إنشاء الحساب أو أرسل /start", show_alert=True)
        return

    set_user_state(user.id, "START")

    user_name = user.first_name or "زميل"
    db_id = user_row["telegram_id"] if user_row else user.id
    wallet = user_row["wallet_balance"] if user_row else 0.0
    user_role = "admin" if user.id in ADMIN_IDS else "user"

    welcome_text = (
        f"<blockquote><b>👋 أهلاً {user_name}</b></blockquote>\n\n"
        f"<b>🆔 آيدي حسابك:</b> <code>{db_id}</code>\n"
        f"<b>💰 الرصيد الحالي:</b> <code>{wallet:,}</code> SYP\n"
        f"‎" + "—" * 20 + "\n"
        f"<b>اختر الخدمة المطلوبة:</b>"
    )

    # -------------------------------------------------------
    # ✅ الإصلاح: تجاهل خطأ "Message is not modified" تماماً
    # -------------------------------------------------------
    try:
        edited = await query.edit_message_text(
            text=welcome_text,
            reply_markup=main_menu_keyboard(user_role),
            parse_mode="HTML",
        )
        context.user_data["last_menu_msg_id"] = edited.message_id
    except BadRequest as e:
        if "Message is not modified" in str(e):
            pass
        elif "Message to edit not found" in str(e):
            sent = await context.bot.send_message(
                chat_id=update.effective_chat.id,
                text=welcome_text,
                reply_markup=main_menu_keyboard(user_role),
                parse_mode="HTML",
            )
            # نمسح الـ stack قبل إضافة الرسالة الجديدة لمنع حذفها
            context.user_data["msg_stack"] = []
            context.user_data["last_menu_msg_id"] = sent.message_id
            return
        else:
            print(f"Error in navigation: {e}")

    await clear_stack(update, context)


def register_navigation_handlers(app):
    app.add_handler(CallbackQueryHandler(nav_handler, pattern="^nav\|"))


async def add_to_stack(context, msg_id):
    """اضافة رسالة  الى قائمة الحذف المؤجل"""
    if "msg_stack" not in context.user_data:
        context.user_data["msg_stack"] = []
    context.user_data["msg_stack"].append(msg_id)


async def clear_stack(update, context):
    """تشغيل المكنسة وحذف كل ما تم تسجيله، مع استثناء رسالة القائمة الرئيسية"""
    chat_id = update.effective_chat.id
    stack = context.user_data.get("msg_stack", [])
    protected_id = context.user_data.get("last_menu_msg_id")

    for m_id in stack:
        if m_id == protected_id:
            continue
        try:
            await context.bot.delete_message(chat_id=chat_id, message_id=m_id)
        except Exception:
            pass
    context.user_data["msg_stack"] = []
