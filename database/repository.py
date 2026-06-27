# database/repository.py
import sqlite3
from database.db import get_conn
from datetime import datetime


# --- Users Basic ---
def get_user_by_telegram(telegram_id):
    conn = get_conn()
    cur = conn.cursor()
    cur.execute("SELECT * FROM users WHERE telegram_id=?", (telegram_id,))
    row = cur.fetchone()
    conn.close()
    return row


def create_user(telegram_user):
    conn = get_conn()
    cur = conn.cursor()
    now = datetime.utcnow().isoformat()
    cur.execute(
        "INSERT INTO users (telegram_id, first_name, username, created_at, state, last_active, wallet_balance, can_delete) VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
        (
            telegram_user.id,
            telegram_user.first_name or "",
            telegram_user.username or "",
            now,
            "START",
            now,
            0.0,
            1,
        ),
    )
    conn.commit()
    user_id = cur.lastrowid
    conn.close()
    return user_id


def ensure_user(telegram_user):
    row = get_user_by_telegram(telegram_user.id)
    if row:
        conn = get_conn()
        cur = conn.cursor()
        cur.execute(
            "UPDATE users SET first_name=?, username=?, last_active=? WHERE telegram_id=?",
            (
                telegram_user.first_name or "",
                telegram_user.username or "",
                datetime.utcnow().isoformat(),
                telegram_user.id,
            ),
        )
        conn.commit()
        conn.close()
        return row
    else:
        create_user(telegram_user)
        return get_user_by_telegram(telegram_user.id)


def set_user_state(telegram_id, state):
    conn = get_conn()
    cur = conn.cursor()
    cur.execute(
        "UPDATE users SET state=?, last_active=? WHERE telegram_id=?",
        (state, datetime.utcnow().isoformat(), telegram_id),
    )
    conn.commit()
    conn.close()


def get_all_users_ids():
    conn = get_conn()
    cur = conn.cursor()
    cur.execute("SELECT telegram_id FROM users")
    rows = cur.fetchall()
    conn.close()
    return [row["telegram_id"] for row in rows]


# --- Stats & Scoring Updates (New) ---
def update_user_stats_after_transaction(user_id, amount, is_deposit, is_success):
    """
    تحديث الإحصائيات:
    1. زيادة العداد المناسب (نجاح/فشل).
    2. خصم 1 من العمليات غير المكتملة لأن العملية انتهت.
    """
    conn = get_conn()
    cur = conn.cursor()

    # أولاً: خصم العملية من "غير المكتملة" لأنها انتهت بقرار (سواء قبول أو رفض)
    cur.execute(
        "UPDATE users SET total_incomplete_orders = MAX(0, total_incomplete_orders - 1) WHERE id=?",
        (user_id,),
    )

    if is_success:
        # عملية ناجحة
        col_amount = "total_deposit_amount" if is_deposit else "total_withdraw_amount"
        cur.execute(
            f"UPDATE users SET total_successful_orders = total_successful_orders + 1, {col_amount} = {col_amount} + ? WHERE id=?",
            (amount, user_id),
        )
    else:
        # عملية مرفوضة
        cur.execute(
            "UPDATE users SET total_rejected_orders = total_rejected_orders + 1 WHERE id=?",
            (user_id,),
        )

    conn.commit()
    conn.close()


def increment_incomplete_orders(user_id):
    conn = get_conn()
    cur = conn.cursor()
    cur.execute(
        "UPDATE users SET total_incomplete_orders = total_incomplete_orders + 1 WHERE id=?",
        (user_id,),
    )
    conn.commit()
    conn.close()


def get_user_archive_id(user_id):
    conn = get_conn()
    cur = conn.cursor()
    cur.execute("SELECT archive_message_id FROM users WHERE id=?", (user_id,))
    res = cur.fetchone()
    conn.close()
    return res["archive_message_id"] if res else None


def set_user_archive_id(user_id, message_id):
    conn = get_conn()
    cur = conn.cursor()
    cur.execute(
        "UPDATE users SET archive_message_id=? WHERE id=?", (message_id, user_id)
    )
    conn.commit()
    conn.close()


# --- Ban System ---
def ban_user(telegram_id, duration_date=None):
    conn = get_conn()
    cur = conn.cursor()
    cur.execute(
        "UPDATE users SET is_blocked=1, ban_expires_at=? WHERE telegram_id=?",
        (duration_date, telegram_id),
    )
    conn.commit()
    conn.close()


def unban_user(telegram_id):
    conn = get_conn()
    cur = conn.cursor()
    cur.execute(
        "UPDATE users SET is_blocked=0, ban_expires_at=NULL WHERE telegram_id=?",
        (telegram_id,),
    )
    conn.commit()
    conn.close()


def check_user_ban_status(telegram_id):
    user = get_user_by_telegram(telegram_id)
    if not user:
        return False, None

    if user["is_blocked"]:
        if user["ban_expires_at"]:
            expires = datetime.fromisoformat(user["ban_expires_at"])
            if datetime.utcnow() > expires:
                unban_user(telegram_id)
                return False, None
            else:
                return True, f"🚫 أنت محظور مؤقتاً حتى: {user['ban_expires_at']}"
        else:
            return True, "🚫 تم حظر حسابك نهائياً."
    return False, None


# --- Payment Settings ---
def update_payment_number_db(method_name, new_number):
    conn = get_conn()
    cur = conn.cursor()
    cur.execute(
        "UPDATE payment_settings SET phone_number=? WHERE method_name=?",
        (new_number, method_name),
    )
    if cur.rowcount == 0:
        cur.execute(
            "INSERT INTO payment_settings (method_name, phone_number, currency) VALUES (?, ?, ?)",
            (method_name, new_number, "SYP"),
        )
    conn.commit()
    conn.close()


def get_payment_numbers():
    """تجلب جميع الأرقام وتضعها في قاموس"""
    conn = get_conn()
    cur = conn.cursor()
    # تأكد من اسم الجدول (هل هو payment_settings أم payment_methods؟)
    # سأفترض أنه payment_settings بناءً على كودك الأخير
    cur.execute("SELECT method_name, phone_number FROM payment_settings")
    rows = cur.fetchall()
    conn.close()
    return {row['method_name']: row['phone_number'] for row in rows}


# --- Accounts ---
def create_account_record(user_id, account_name, password):
    conn = get_conn()
    cur = conn.cursor()
    now = datetime.utcnow().isoformat()
    try:
        cur.execute(
            "INSERT INTO accounts (user_id, account_name, password, status, created_at) VALUES (?, ?, ?, ?, ?)",
            (user_id, account_name, password, "pending", now),
        )
        conn.commit()
        acc_id = cur.lastrowid
        return get_account_by_id(acc_id)
    except sqlite3.IntegrityError:
        conn.rollback()
        return None
    finally:
        conn.close()


def get_accounts_by_user(user_id):
    conn = get_conn()
    cur = conn.cursor()
    cur.execute("SELECT * FROM accounts WHERE user_id=?", (user_id,))
    rows = cur.fetchall()
    conn.close()
    return rows


def get_account_by_id(account_id):
    conn = get_conn()
    cur = conn.cursor()
    cur.execute("SELECT * FROM accounts WHERE id=?", (account_id,))
    row = cur.fetchone()
    conn.close()
    return row


def get_account(account_id):
    return get_account_by_id(account_id)


def update_account_balance(account_id, new_balance):
    conn = get_conn()
    cur = conn.cursor()
    cur.execute("UPDATE accounts SET balance=? WHERE id=?", (new_balance, account_id))
    conn.commit()
    conn.close()


def set_account_status(account_id, status):
    conn = get_conn()
    cur = conn.cursor()
    cur.execute("UPDATE accounts SET status=? WHERE id=?", (status, account_id))
    conn.commit()
    conn.close()


def update_account_name(account_id, new_name):
    conn = get_conn()
    cur = conn.cursor()
    cur.execute("UPDATE accounts SET account_name=? WHERE id=?", (new_name, account_id))
    conn.commit()
    conn.close()


def count_user_accounts(user_id):
    conn = get_conn()
    cur = conn.cursor()
    cur.execute("SELECT COUNT(*) FROM accounts WHERE user_id=?", (user_id,))
    count = cur.fetchone()[0]
    conn.close()
    return count


# --- Orders & Security ---
def has_pending_deposit(user_id):
    conn = get_conn()
    cur = conn.cursor()
    cur.execute(
        "SELECT 1 FROM orders WHERE user_id=? AND status='pending' AND service='WALLET_DEPOSIT'",
        (user_id,),
    )
    res = cur.fetchone()
    conn.close()
    return True if res else False


def has_pending_withdraw(user_id):
    conn = get_conn()
    cur = conn.cursor()
    cur.execute(
        "SELECT 1 FROM orders WHERE user_id=? AND status IN('pending', 'processing') AND service='WALLET_WITHDRAW'",
        (user_id,),
    )
    res = cur.fetchone()
    conn.close()
    return True if res else False


def is_transaction_used(transaction_code):
    conn = get_conn()
    cur = conn.cursor()
    cur.execute("SELECT 1 FROM orders WHERE transaction_code=?", (transaction_code,))
    res = cur.fetchone()
    conn.close()
    return True if res else False


def create_order(
    user_id,
    service,
    account_id=None,
    amount=None,
    data=None,
    proof_file_id=None,
    transaction_code=None,
):
    conn = get_conn()
    cur = conn.cursor()
    now = datetime.utcnow()
    timestamp = now.strftime("%Y%m%dT%H%M%S%f")
    try:
        cur.execute(
            "INSERT INTO orders (order_code, transaction_code, user_id, account_id, service, amount, data, proof_file_id, status, created_at, updated_at) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
            (
                None,
                transaction_code,
                user_id,
                account_id,
                service,
                amount,
                data,
                proof_file_id,
                "pending",
                now.isoformat(),
                now.isoformat(),
            ),
        )
        oid = cur.lastrowid
        code = f"REQ-{timestamp}-{oid}"
        cur.execute("UPDATE orders SET order_code=? WHERE id=?", (code, oid))
        conn.commit()
        return get_order_by_code(code)
    except sqlite3.IntegrityError:
        conn.rollback()
        return None
    finally:
        conn.close()


def get_order_by_code(order_code):
    conn = get_conn()
    cur = conn.cursor()
    cur.execute("SELECT * FROM orders WHERE order_code=?", (order_code,))
    row = cur.fetchone()
    conn.close()
    return row


def update_order_status(order_code, status, rejection_reason=None, processed_by=None):
    conn = get_conn()
    cur = conn.cursor()

    sql = "UPDATE orders SET status=?, updated_at=?"
    params = [status, datetime.utcnow().isoformat()]

    if rejection_reason:
        sql += ", rejection_reason=?"
        params.append(rejection_reason)

    if processed_by:
        sql += ", processed_by_admin_id=?"
        params.append(processed_by)

    sql += " WHERE order_code=?"
    params.append(order_code)

    cur.execute(sql, tuple(params))
    conn.commit()
    conn.close()


def lock_order_for_admin(order_code, admin_id):
    """
    يحاول قفل طلب السحب لأدمن معيّن، فقط إذا كان لا يزال pending.
    يُعيد True لو نجح القفل (هذا الأدمن أصبح المسؤول)، False لو سبقه أحد.
    """
    conn = get_conn()
    cur = conn.cursor()
    cur.execute(
        "UPDATE orders SET status='processing', locked_by_admin_id=? "
        "WHERE order_code=? AND status='pending'",
        (admin_id, order_code),
    )
    conn.commit()
    success = cur.rowcount > 0
    conn.close()
    return success


def unlock_order(order_code):
    """يعيد الطلب إلى pending (احتياطي للتراجع لاحقاً)"""
    conn = get_conn()
    cur = conn.cursor()
    cur.execute(
        "UPDATE orders SET status='pending', locked_by_admin_id=NULL WHERE order_code=?",
        (order_code,),
    )
    conn.commit()
    conn.close()


# --- Helpers ---
def map_group_message(group_message_id, order_code):
    conn = get_conn()
    cur = conn.cursor()
    cur.execute(
        "INSERT OR REPLACE INTO group_map (group_message_id, order_code) VALUES (?, ?)",
        (group_message_id, order_code),
    )
    conn.commit()
    conn.close()


def find_order_code_by_group_message(group_message_id):
    conn = get_conn()
    cur = conn.cursor()
    cur.execute(
        "SELECT order_code FROM group_map WHERE group_message_id=?", (group_message_id,)
    )
    row = cur.fetchone()
    conn.close()
    return row["order_code"] if row else None


# --- Wallet & Deletion ---
def get_user_delete_permission(user_id):
    conn = get_conn()
    cur = conn.cursor()
    cur.execute("SELECT can_delete FROM users WHERE id=?", (user_id,))
    res = cur.fetchone()
    conn.close()
    return res["can_delete"] if res else 0


def delete_user_account_permanently(user_id, account_id):
    conn = get_conn()
    cur = conn.cursor()
    try:
        cur.execute(
            "DELETE FROM accounts WHERE id=? AND user_id=?", (account_id, user_id)
        )
        cur.execute("UPDATE users SET can_delete=0 WHERE id=?", (user_id,))
        conn.commit()
        return True
    except:
        conn.rollback()
        return False
    finally:
        conn.close()


def update_user_wallet_balance(user_id, amount):
    conn = get_conn()
    cur = conn.cursor()
    try:
        cur.execute(
            "UPDATE users SET wallet_balance = wallet_balance + ? WHERE id=?",
            (amount, user_id)
        )
        conn.commit()
        cur.execute("SELECT wallet_balance FROM users WHERE id=?", (user_id,))
        res = cur.fetchone()
        return res["wallet_balance"] if res else 0.0
    except Exception as e:
        conn.rollback()
        import logging
        logging.getLogger(__name__).error(f"فشل تحديث رصيد المستخدم {user_id}: {e}")
        return None
    finally:
        conn.close()


def seed_payment_methods():
    conn = get_conn()
    cur = conn.cursor()
    cur.execute("SELECT count(*) FROM payment_settings")
    if cur.fetchone()[0] == 0:
        cur.execute(
            "INSERT INTO payment_settings (method_name, phone_number, currency) VALUES (?, ?, ?)",
            ("syriatel", "0930000000", "SYP"),
        )
        cur.execute(
            "INSERT INTO payment_settings (method_name, phone_number, currency) VALUES (?, ?, ?)",
            ("sham", "0990000000", "SYP"),
        )
        conn.commit()
    conn.close()


def get_user_by_id_helper(db_id):
    conn = get_conn()
    cur = conn.cursor()
    cur.execute("SELECT * FROM users WHERE id=?", (db_id,))
    res = cur.fetchone()
    conn.close()
    return res


def get_bot_account_name(user_id):
    """جلب اسم حساب المستخدم من جدول accounts"""
    conn = get_conn()
    cur = conn.cursor()

    cur.execute("SELECT account_name From accounts WHERE user_id=? LIMIT 1", (user_id,))
    res = cur.fetchone()
    return res["account_name"] if res else None