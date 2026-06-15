# handlers/main_menu.py
import time
from telegram.ext import CallbackQueryHandler
from telegram import InlineKeyboardMarkup, InlineKeyboardButton

from keyboards.main import (
    back_nav_markup,
    account_actions_markup,
    confirm_delete_markup,
    back_only_markup,
)
from strings import (
    MSG_FLOOD_WARN,
    MSG_DELETE_USED,
    MSG_ACCOUNT_DELETED,
    MSG_CONFIRM_DELETE,
)
from database.repository import (
    get_user_by_telegram,
    get_accounts_by_user,
    set_user_state,
    count_user_accounts,
    get_user_delete_permission,
    delete_user_account_permanently,
    get_account_by_id,  # نحتاج هذه الدالة لجلب الحساب عند الإلغاء
)
from services.scoring import get_user_score_details_text
from config import ADMIN_IDS
from handlers.navigation import add_to_stack


async def main_menu_cb(update, context):
    query = update.callback_query

    # --- Anti-Flood ---
    current_time = time.time()
    last_click = context.user_data.get("last_click_time", 0)
    if current_time - last_click < 0.5:
        await query.answer(MSG_FLOOD_WARN, show_alert=False)
        return
    context.user_data["last_click_time"] = current_time

    data = query.data
    parts = data.split("|")
    user = update.effective_user
    user_row = get_user_by_telegram(user.id)

    # دالة مساعدة لعرض تفاصيل الحساب (لمنع تكرار الكود)
    async def show_account_details(account_data, show_pass=False):
        pass_display = (
            account_data["password"]
            if show_pass
            else "*" * len(account_data["password"])
        )
        btn_text = "🙈 إخفاء كلمة المرور" if show_pass else "👁️ إظهار كلمة المرور"
        next_state = "hide" if show_pass else "show"

        status_map = {
            "pending": "⏳ قيد المراجعة",
            "active": "✅ فعال",
            "completed": "✅ فعال",
        }
        status_text = status_map.get(account_data["status"], account_data["status"])

        info_text = (
            f"<blockquote><b>👤 تفاصيل حساب اللعبة</b></blockquote>\n\n"
            f"<b>🆔 تليجرام ID:</b> <code>{user.id}</code>\n"
            f"<b>🔖 الاسم:</b> <code>{account_data['account_name']}</code>\n"
            f"<b>🔐 كلمة المرور:</b> <code>{pass_display}</code>\n"
            f"<b>📡 الحالة:</b> {status_text}\n"
            f"‎" + "—" * 20
        )

        markup = account_actions_markup(account_data["id"])
        keyboard_list = list(markup.inline_keyboard)
        keyboard_list.append(
            [
                InlineKeyboardButton(
                    btn_text,
                    callback_data=f"act|toggle_pass|{next_state}|{account_data['id']}",
                )
            ]
        )

        msg = await query.edit_message_text(
            info_text,
            reply_markup=InlineKeyboardMarkup(keyboard_list),
            parse_mode="HTML",
        )
        context.user_data["last_menu_msg_id"] = msg.message_id

    # --- القوائم الرئيسية ---
    if parts[0] == "main":
        await query.answer()
        action = parts[1]

        if action == "account_manager":
            account_count = count_user_accounts(user_row["id"])
            if account_count > 0:
                accounts = get_accounts_by_user(user_row["id"])
                await show_account_details(accounts[0], show_pass=False)
            else:
                set_user_state(user.id, "CREATING_USERNAME")
                msg = await query.edit_message_text(
                    "📝 <b>لإنشاء حساب جديد:</b>\n\nأرسل الآن " \
                    "الاسم الذي تريده (أحرف إنجليزية فقط).",
                    parse_mode="HTML",
                    reply_markup=back_only_markup(),
                )
                context.user_data["last_msg_id"] = msg.message_id
                await add_to_stack(context, msg.message_id)

        elif action == "my_score":
            score_text = get_user_score_details_text(user_row)
            await query.edit_message_text(
                text=score_text, reply_markup=back_only_markup(), parse_mode="HTML"
            )

    # --- إجراءات الحساب ---
    elif parts[0] == "act":
        sub_action = parts[1]
        account_id = parts[2]

        if sub_action == "toggle_pass":
            target_state = parts[2]  # show/hide
            real_acc_id = parts[3]
            acc = get_account_by_id(real_acc_id)
            if acc:
                await show_account_details(acc, show_pass=(target_state == "show"))
            else:
                await query.answer("⚠️ الحساب غير موجود", show_alert=True)

        elif sub_action == "delete_req":
            await query.answer()
            if get_user_delete_permission(user_row["id"]) or user.id in ADMIN_IDS:
                await query.edit_message_text(
                    MSG_CONFIRM_DELETE, reply_markup=confirm_delete_markup(account_id)
                )
            else:
                await query.answer(MSG_DELETE_USED, show_alert=True)

        elif sub_action == "cancel_del":
            # إلغاء الحذف والعودة لعرض الحساب
            await query.answer("تم إلغاء الحذف")
            acc = get_account_by_id(account_id)
            if acc:
                await show_account_details(acc, show_pass=False)

        elif sub_action == "delete_confirm":
            await query.answer()
            if delete_user_account_permanently(user_row["id"], account_id):
                await query.edit_message_text(
                    MSG_ACCOUNT_DELETED, reply_markup=back_only_markup()
                )


def register_main_menu_handlers(app):
    app.add_handler(CallbackQueryHandler(main_menu_cb, pattern=r"^(main|act)\|"))
