# bot.py
import logging
from telegram import BotCommand, Update
from telegram.ext import (
    ApplicationBuilder,
    CallbackQueryHandler,
    ConversationHandler,
    MessageHandler,
    CommandHandler,
    ContextTypes,
    filters,
    TypeHandler,  # نحتاجه للتتبع
)
from config import TOKEN, ADMIN_IDS
from database.db import init_db
from database.repository import seed_payment_methods

# استيراد الـ Handlers
from handlers.start import start, register_start_handlers
from handlers.wallet import (
    start_deposit,
    receive_amount,
    receive_transaction_code,
    cancel_deposit,
    select_payment_method,
    admin_deposit_decision,
    WAIT_AMOUNT,
    WAIT_CODE,
)

from handlers.withdraw import (
    start_withdraw,
    wd_receive_amount,
    wd_select_method,
    wd_receive_destination,
    cancel_withdraw,
    admin_withdraw_decision,
    admin_receive_withdraw_code,
    WD_WAIT_AMOUNT,
    WD_WAIT_METHOD,
    WD_WAIT_DESTINATION,
)
from handlers.main_menu import register_main_menu_handlers
from handlers.account import register_account_handlers
from handlers.deposit_withdraw import register_deposit_withdraw_handlers
from handlers.admin import register_admin_handlers
from handlers.navigation import register_navigation_handlers, nav_handler

logging.basicConfig(
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s", level=logging.INFO
)
logger = logging.getLogger(__name__)


async def error_handler(update: object, context: ContextTypes.DEFAULT_TYPE) -> None:
    logger.error(msg="Exception while handling an update:", exc_info=context.error)


# --- دالة التتبع الجديدة ---
async def debug_sniffer(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """تطبع أي زر يتم ضغطه في التيرمنال للتأكد من وصوله"""
    if update.callback_query:
        print(f"🕵️ DEBUG: Button Clicked -> {update.callback_query.data}")


async def post_init(application):
    await application.bot.set_my_commands([BotCommand("start", "القائمة الرئيسية 🏠")])


def main():
    init_db()
    seed_payment_methods()

    app = ApplicationBuilder().token(TOKEN).post_init(post_init).build()
    app.add_error_handler(error_handler)

    # 1. إضافة متتبع الأزرار (أول شيء ليرى كل شيء)
    app.add_handler(TypeHandler(Update, debug_sniffer), group=-1)

    # 2. نظام الإيداع (الأولوية القصوى)
    deposit_conv = ConversationHandler(
        entry_points=[
            # استخدمنا تعبير نمطي بسيط جداً لضمان التقاط الزر
            CallbackQueryHandler(start_deposit, pattern=r"^dep\|start")
        ],
        states={
            WAIT_AMOUNT: [
                MessageHandler(filters.TEXT & ~filters.COMMAND, receive_amount)
            ],
            WAIT_CODE: [

                CallbackQueryHandler(
                    select_payment_method, pattern=r"^pay\|"
                    ),
                MessageHandler(
                    filters.TEXT & ~filters.COMMAND, receive_transaction_code
                )
            ],
        },
        fallbacks=[
            CallbackQueryHandler(nav_handler, pattern=r"^nav\|home$"),
            CommandHandler("start", start),
        ],
        allow_reentry=True,
    )
    app.add_handler(deposit_conv)

    withdraw_conv = ConversationHandler(
        entry_points=[
            CallbackQueryHandler(start_withdraw, pattern=r"^wd\|start")
        ],
        states={
            WD_WAIT_AMOUNT: [
                MessageHandler(filters.TEXT & ~filters.COMMAND, wd_receive_amount)
            ],
            WD_WAIT_METHOD: [
                CallbackQueryHandler(wd_select_method, pattern=r"^wdpay\|")
            ],
            WD_WAIT_DESTINATION: [
                MessageHandler(filters.TEXT & ~filters.COMMAND, wd_receive_destination)
            ],
        },
        fallbacks=[
            CallbackQueryHandler(nav_handler, pattern=r"^nav\|home$"),
            CommandHandler("start", start),
        ],
        allow_reentry=True,
    )
    app.add_handler(withdraw_conv)

    # 3. بقية الهاندلرز
    app.add_handler(CommandHandler("start", start))
    app.add_handler(CallbackQueryHandler(select_payment_method, pattern=r"^pay\|"))
    app.add_handler(CallbackQueryHandler(admin_deposit_decision, pattern=r"^dep_adm\|"))
    app.add_handler(CallbackQueryHandler(admin_withdraw_decision, pattern=r"^wd_adm\|"))
    app.add_handler(
        MessageHandler(
            filters.TEXT & ~filters.COMMAND & filters.User(user_id=ADMIN_IDS),
            admin_receive_withdraw_code,
        ),
        group=1,
    )

    register_main_menu_handlers(app)
    register_account_handlers(app)
    register_deposit_withdraw_handlers(app)
    register_admin_handlers(app)
    register_navigation_handlers(app)
    register_start_handlers(app)

    print(
        "🚀 البوت يعمل في وضع التصحيح (Debug Mode)... جرب زر الإيداع الآن وراقب التيرمنال."
    )
    app.run_polling()


if __name__ == "__main__":
    main()