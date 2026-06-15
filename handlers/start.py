# handlers/start.py
from telegram.ext import CommandHandler, ConversationHandler
from telegram.constants import ParseMode
from keyboards.main import main_menu_keyboard  # تأكد من مطابقة الاسم الجديد
from database.repository import ensure_user, set_user_state, get_user_by_telegram
from handlers.navigation import clear_stack


async def start(update, context):
    await clear_stack(update, context)
    user = update.effective_user

    # 1. حذف الرسالة التي أرسلها المستخدم (/start) للحفاظ على نظافة الدردشة
    if update.message:
        try:
            await update.message.delete()
        except Exception:
            pass

    # 2. حذف رسالة البوت السابقة (القائمة القديمة) لتجنب التكرار
    last_msg_id = context.user_data.get("last_menu_msg_id")
    if last_msg_id:
        try:
            await context.bot.delete_message(
                chat_id=update.effective_chat.id, message_id=last_msg_id
            )
        except Exception:
            pass

    context.user_data.clear()

    # 3. التأكد من وجود المستخدم في قاعدة البيانات وجلب بياناته
    ensure_user(user)
    user_row = get_user_by_telegram(user.id)

    # تحديد دور المستخدم (أدمن أو مستخدم عادي) لعرض الأزرار المناسبة
    from config import ADMIN_IDS

    user_role = "admin" if user.id in ADMIN_IDS else "user"

    # إعادة ضبط حالة المستخدم
    set_user_state(user.id, "WAIT_SERVICE")

    user_name = user.first_name or "زميل"
    user_id = user.id
    balance = user_row["wallet_balance"] if user_row else 0

    welcome_text = (
        f"<blockquote><b>👋 أهلاً بك يا {user_name}</b></blockquote>\n\n"
        f"<b>🆔 آيدي حسابك:</b> <code>{user_id}</code>\n"
        f"<b>💰 رصيدك الحالي:</b> <code>{balance:,}</code> SYP\n\n"
        f"<b>اختر الخدمة المطلوبة من القائمة أدناه 📍</b>\n"
        f"‎" + "—" * 20
    )

    # 4. إرسال القائمة الرئيسية الجديدة وتخزين الـ ID
    new_msg = await context.bot.send_message(
        chat_id=update.effective_chat.id,
        text=welcome_text,
        reply_markup=main_menu_keyboard(user_role),  # استدعاء الاسم الصحيح مع الدور
        parse_mode=ParseMode.HTML,
    )
    context.user_data["last_menu_msg_id"] = new_msg.message_id

    # 5. إنهاء أي محادثة (Conversation) كانت نشطة
    return ConversationHandler.END


def register_start_handlers(app):
    app.add_handler(CommandHandler("start", start))
