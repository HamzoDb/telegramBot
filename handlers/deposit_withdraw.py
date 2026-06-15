# handlers/deposit_withdraw.py
from telegram.ext import MessageHandler, filters
from database.repository import get_user_by_telegram, get_accounts_by_user, create_order
from services.notifications import post_order_to_admin_group
from database.repository import get_account, update_account_balance, set_user_state

# Simplified flow using text inputs for demo:
# - After selecting account (client side), user will send amount as text
# - For deposit: after amount, ask for photo then create order with proof_photo in photo handler


async def generic_text_handler(update, context):
    user = update.effective_user
    row = get_user_by_telegram(user.id)
    if not row:
        await update.message.reply_text("ابدأ أولاً بإرسال /start")
        return
    state = row["state"]
    text = update.message.text.strip()
    if state and state.startswith("DEPOSIT_AMOUNT::"):
        account_id = int(state.split("::", 1)[1])
        try:
            amount = float(text)
        except:
            await update.message.reply_text("ادخل مبلغًا صحيحًا بالأرقام.")
            return
        # store in user_data and change state to wait proof
        context.user_data["pending_deposit"] = {
            "account_id": account_id,
            "amount": amount,
        }
        set_user_state(user.id, "DEPOSIT_WAIT_PROOF")
        await update.message.reply_text("أرسل الآن صورة إثبات التحويل (لقطة).")
        return
    if state and state.startswith("WITHDRAW_AMOUNT::"):
        account_id = int(state.split("::", 1)[1])
        try:
            amount = float(text)
        except:
            await update.message.reply_text("ادخل مبلغًا صحيحًا بالأرقام.")
            return
        acc = get_account(account_id)
        if not acc:
            await update.message.reply_text("حصل خطأ: الحساب غير موجود.")
            set_user_state(user.id, "WAIT_SERVICE")
            return
        if acc["balance"] < amount:
            await update.message.reply_text(f"رصيد غير كافِ. رصيدك: {acc['balance']}")
            set_user_state(user.id, "WAIT_SERVICE")
            return
        order = create_order(
            user.id, "withdraw", account_id=account_id, amount=amount, data="طلب سحب"
        )
        await post_order_to_admin_group(context.application, order)
        await update.message.reply_text(
            "تم إرسال طلب السحب للمشرفين. سيتم إعلامك بعد التنفيذ."
        )
        set_user_state(user.id, "WAIT_SERVICE")
        return


# photo handler for deposit proof
async def photo_handler(update, context):
    user = update.effective_user
    row = get_user_by_telegram(user.id)
    if not row or row["state"] != "DEPOSIT_WAIT_PROOF":
        return
    pending = context.user_data.get("pending_deposit")
    if not pending:
        await update.message.reply_text("لا يوجد عملية تعبئة معلقة.")
        set_user_state(user.id, "WAIT_SERVICE")
        return
    photo = update.message.photo[-1]
    file_id = photo.file_id
    account_id = pending["account_id"]
    amount = pending["amount"]
    order = create_order(
        user.id,
        "deposit",
        account_id=account_id,
        amount=amount,
        data="تعبئة",
        proof_file_id=file_id,
    )
    await post_order_to_admin_group(
        context.application, order, include_photo_file_id=file_id
    )
    await update.message.reply_text(
        "تم استلام إثبات التحويل. سيتم مراجعته من قبل المشرفين."
    )
    context.user_data.pop("pending_deposit", None)
    set_user_state(user.id, "WAIT_SERVICE")


def register_deposit_withdraw_handlers(app):
    app.add_handler(MessageHandler(filters.PHOTO & ~filters.COMMAND, photo_handler))
    app.add_handler(
        MessageHandler(filters.TEXT & ~filters.COMMAND, generic_text_handler)
    )
