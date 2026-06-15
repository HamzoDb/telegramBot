# keyboards/main.py
from telegram import InlineKeyboardButton, InlineKeyboardMarkup

try:
    from strings import BTN_BACK, BTN_MAIN_MENU
except ImportError:
    BTN_BACK = "🔙 رجوع"
    BTN_MAIN_MENU = "🏠 القائمة الرئيسية"


def main_menu_keyboard(user_role="user"):
    keyboard = [
        [
            InlineKeyboardButton(
                "👤 إدارة الحساب (Game Account)", callback_data="main|account_manager"
            )
        ],
        [
            # هذا هو زر الإيداع الذي سنراقبه
            InlineKeyboardButton(
                "📥 إيداع للمحفظة (Bot Wallet)", callback_data="dep|start"
            ),
            InlineKeyboardButton(
                "📤 سحب من المحفظة", callback_data="main|wallet_withdraw"
            ),
        ],
        [
            InlineKeyboardButton("🏆 نقاطي وتقييمي", callback_data="main|my_score"),
        ],
        [
            InlineKeyboardButton("🔄 السجلات", callback_data="main|logs"),
            InlineKeyboardButton("💬 الدعم الفني", callback_data="main|support"),
        ],
    ]
    if user_role == "admin":
        keyboard.append(
            [InlineKeyboardButton("🔒 لوحة الإدارة", callback_data="admin|dashboard")]
        )
    return InlineKeyboardMarkup(keyboard)


def back_nav_markup():
    keyboard = [
        [
            InlineKeyboardButton(BTN_BACK, callback_data="nav|back"),
            InlineKeyboardButton(BTN_MAIN_MENU, callback_data="nav|home"),
        ]
    ]
    return InlineKeyboardMarkup(keyboard)


def back_only_markup(callback="nav|home"):
    keyboard = [
        [
            InlineKeyboardButton(BTN_BACK, callback_data=callback)
        ]
    ]
    return InlineKeyboardMarkup(keyboard)


def account_actions_markup(account_id):
    keyboard = [
        [
            InlineKeyboardButton(
                "💰 شحن الحساب (من المحفظة)",
                callback_data=f"act|deposit_game|{account_id}",
            )
        ],
        [
            InlineKeyboardButton(
                "💸 سحب من الحساب", callback_data=f"act|withdraw_game|{account_id}"
            )
        ],
        [
            InlineKeyboardButton(
                "🗑️ حذف الحساب (طلب)", callback_data=f"act|delete_req|{account_id}"
            ),
        ],
        # -----------------------------------------------------------
        # ✅ الإصلاح هنا: زر الرجوع يعود للقائمة الرئيسية (nav|home)
        # بدلاً من العودة لنفس الصفحة (main|account_manager) مما يسبب الخطأ
        # -----------------------------------------------------------
        [InlineKeyboardButton("🔙 رجوع", callback_data="nav|home")],
    ]
    return InlineKeyboardMarkup(keyboard)


def confirm_delete_markup(account_id):
    keyboard = [
        [
            InlineKeyboardButton(
                "✅ نعم، احذف الحساب نهائياً",
                callback_data=f"act|delete_confirm|{account_id}",
            )
        ],
        [
            InlineKeyboardButton(
                "❌ إلغاء", callback_data=f"act|cancel_del|{account_id}"
            )
        ],
    ]
    return InlineKeyboardMarkup(keyboard)
