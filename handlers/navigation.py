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

    await clear_stack(update, context)

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
        await query.edit_message_text(
            text=welcome_text,
            reply_markup=main_menu_keyboard(user_role),
            parse_mode="HTML",
        )
    except BadRequest as e:
        if "Message is not modified" in str(e):
            # المستخدم ضغط رجوع وهو أصلاً في القائمة، لا تفعل شيئاً ولا تطبع خطأ
            pass
        else:
            # إذا كان خطأ آخر حقيقي، اطبعه
            print(f"Error in navigation: {e}")


def register_navigation_handlers(app):
    app.add_handler(CallbackQueryHandler(nav_handler, pattern="^nav\|"))


async def add_to_stack(context, msg_id):
    """اضافة رسالة  الى قائمة الحذف المؤجل"""
    if "msg_stack" not in context.user_data:
        context.user_data["msg_stack"] = []
    context.user_data["msg_stack"].append(msg_id)


async def clear_stack(update, context):
    """تشغيل المكنسةوحذف كل ما تم تسجيله"""
    chat_id = update.effective_chat.id
    stack = context.user_data.get("msg_stack", [])
    for m_id in stack:
        try:
            await context.bot.delete_message(chat_id=chat_id, message_id=m_id)
        except Exception:
            pass
    context.user_data["msg_stack"] = []
