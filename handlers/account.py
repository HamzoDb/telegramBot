# handlers/account.py
import asyncio
import re
import logging
from telegram.ext import MessageHandler, filters
from telegram.constants import ParseMode
from strings import *
from database.repository import (
    get_user_by_telegram,
    create_account_record,
    create_order,
    set_user_state,
)
from keyboards.main import back_nav_markup, back_only_markup, main_menu_keyboard
from services.notifications import post_order_to_admin_group
from services.generators import generate_account_name
from services.scoring import update_live_card
from handlers.navigation import add_to_stack, clear_stack
from config import ADMIN_IDS


async def account_manager_handler(update, context):
    if update.message:
        await add_to_stack(context, update.message.message_id)
    user = update.effective_user
    chat_id = update.effective_chat.id
    user_msg_id = update.message.message_id
    user_row = get_user_by_telegram(user.id)

    if not user_row:
        return
    state = user_row["state"]
    text = update.message.text.strip()

    # دالة حذف الرسائل الأصلية التي كانت لديك لضمان نظافة الشات
    async def delete_msg(m_id):
        try:
            await context.bot.delete_message(chat_id, m_id)
        except Exception:
            pass

    # --- مرحلة 1: استلام الاسم ---
    if state == "CREATING_USERNAME":
        await delete_msg(user_msg_id)
        if not re.match(r"^[a-zA-Z]+$", text):
            msg = await update.message.reply_text(
                "⚠️ يرجى كتابة الاسم بالأحرف الإنجليزية فقط.",
                reply_markup=back_only_markup(),
            )
            await add_to_stack(context, msg.message_id)
            return

        # إذا نجح الاسم: نعدل الرسالة السابقة ونطلب الباسورد
        context.user_data["account_base"] = text
        last_msg_id = context.user_data.get("last_msg_id")
        if last_msg_id:
            try:
                # نستخدم edit_message_text لتغيير النص وحذف الأزرار
                await context.bot.edit_message_text(
                    chat_id=chat_id,
                    message_id=last_msg_id,
                    text=f"✅ تم استلام الاسم: <b>{text}</b>",
                    parse_mode="HTML",
                    reply_markup=None,  # حذف الزر
                )
            except Exception:
                pass

        context.user_data["account_base"] = text
        set_user_state(user.id, "CREATING_PASSWORD")
        new_msg = await update.message.reply_text(
            MSG_ASK_PASS, reply_markup=back_only_markup()
        )
        context.user_data["last_msg_id"] = new_msg.message_id
        await add_to_stack(context, new_msg.message_id)

    # --- مرحلة 2: استلام الباسورد والمعالجة (مع الأنيميشن الكامل) ---
    elif state == "CREATING_PASSWORD":
        await delete_msg(user_msg_id)
        if re.search(r"[\u0600-\u06FF]", text):
            msg = await update.message.reply_text(
                "⚠️ كلمة المرور يجب أن تكون بالإنجليزية.",
                reply_markup=back_only_markup(),
            )
            await add_to_stack(context, msg.message_id)
            return  # نتوقف هنا ليعيد المحاولة

        # إذا نجحت كلمة السر: نعدل رسالة طلب الباسورد السابقة
        last_msg_id = context.user_data.get("last_msg_id")
        if last_msg_id:
            try:
                await context.bot.edit_message_text(
                    chat_id=chat_id,
                    message_id=last_msg_id,
                    text=f"✅ تم استلام كلمة المرور بنجاح.",
                    reply_markup=None,
                )
            except Exception:
                pass

        # الآن تبدأ عملية المعالجة
        set_user_state(user.id, "PROCESSING")
        status_msg = await update.message.reply_text(ANIMATION_STEP_1)

        try:
            final_account_name = generate_account_name(
                context.user_data.get("account_base"), user.id
            )
            account = create_account_record(user_row["id"], final_account_name, text)

            order = create_order(
                user_row["id"], "create", account_id=account["id"], data="إنشاء حساب"
            )

            await update_live_card(context.bot, user_row["id"])
            await post_order_to_admin_group(context.application, order)

            # استعادة نظام الأنيميشن الأصلي بالكامل
            for step in [ANIMATION_STEP_2, ANIMATION_STEP_3, ANIMATION_STEP_4]:
                await asyncio.sleep(1.5)
                await status_msg.edit_text(step)

            await clear_stack(update, context)
            user_role = "admin" if user.id in ADMIN_IDS else "user"
            menu_msg = await status_msg.edit_text(
                MSG_SUCCESS_USER,
                parse_mode=ParseMode.HTML,
                reply_markup=main_menu_keyboard(user_role),
                )

            context.user_data["last_menu_msg_id"] = menu_msg.message_id

        except Exception as e:
            logging.error(f"Process Error: {e}")
            if "status_msg" in locals():
                await status_msg.edit_text("❌ حدث خطأ، يرجى المحاولة لاحقاً.")

        finally:
            set_user_state(user.id, "WAIT_SERVICE")
            context.user_data.pop("account_base", None)
            context.user_data.pop("last_error_id", None)


def register_account_handlers(app):
    app.add_handler(
        MessageHandler(filters.TEXT & ~filters.COMMAND, account_manager_handler)
    )
