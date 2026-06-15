# database/db.py
import sqlite3
from config import DB_PATH
import logging


def get_conn():
    conn = sqlite3.connect(DB_PATH, timeout=30)
    conn.row_factory = sqlite3.Row
    return conn


def init_db():
    conn = get_conn()
    cur = conn.cursor()

    # 1. جدول المستخدمين (تمت إضافة إحصائيات التقييم ورابط الأرشيف)
    cur.execute(
        """
    CREATE TABLE IF NOT EXISTS users (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        telegram_id INTEGER UNIQUE,
        first_name TEXT,
        username TEXT,
        created_at TEXT,
        state TEXT,
        last_active TEXT,
        wallet_balance REAL DEFAULT 0.0,
        can_delete INTEGER DEFAULT 1,
        is_blocked INTEGER DEFAULT 0,
        ban_expires_at TEXT,
        admin_notes TEXT,
        
        -- أعمدة التقييم الجديدة
        total_successful_orders INTEGER DEFAULT 0,
        total_rejected_orders INTEGER DEFAULT 0,
        total_incomplete_orders INTEGER DEFAULT 0,
        total_deposit_amount REAL DEFAULT 0.0,
        total_withdraw_amount REAL DEFAULT 0.0,
        archive_message_id INTEGER DEFAULT NULL -- لحفظ معرف رسالة البطاقة في قناة الأرشيف
    )"""
    )

    # 2. جدول إعدادات الدفع
    cur.execute(
        """
    CREATE TABLE IF NOT EXISTS payment_settings (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        method_name TEXT UNIQUE,
        phone_number TEXT,
        currency TEXT,
        is_active INTEGER DEFAULT 1
    )"""
    )

    # 3. جدول الحسابات
    cur.execute(
        """
    CREATE TABLE IF NOT EXISTS accounts (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        user_id INTEGER,
        account_name TEXT UNIQUE,
        display_name TEXT,
        password TEXT,
        status TEXT,
        created_at TEXT,
        balance REAL DEFAULT 0.0
    )"""
    )

    # 4. جدول الطلبات
    cur.execute(
        """
    CREATE TABLE IF NOT EXISTS orders (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        order_code TEXT UNIQUE,
        transaction_code TEXT,
        user_id INTEGER,
        account_id INTEGER,
        service TEXT,
        amount REAL,
        actual_amount REAL,
        data TEXT,
        proof_file_id TEXT,
        status TEXT,
        rejection_reason TEXT,
        processed_by_admin_id INTEGER,
        created_at TEXT,
        updated_at TEXT
    )"""
    )

    # 5. جدول إجراءات الإدمن
    cur.execute(
        """
    CREATE TABLE IF NOT EXISTS admin_actions (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        order_code TEXT,
        admin_telegram_id INTEGER,
        action TEXT,
        note TEXT,
        timestamp TEXT
    )"""
    )

    # 6. جدول خرائط الرسائل
    cur.execute(
        """
    CREATE TABLE IF NOT EXISTS group_map (
        group_message_id INTEGER PRIMARY KEY,
        order_code TEXT
    )"""
    )

    _migrate_tables(cur)

    conn.commit()
    conn.close()


def _migrate_tables(cur):
    """تحديث الجداول القديمة بالأعمدة الجديدة"""
    columns_to_add = [
        ("users", "is_blocked", "INTEGER DEFAULT 0"),
        ("users", "ban_expires_at", "TEXT"),
        ("users", "total_successful_orders", "INTEGER DEFAULT 0"),
        ("users", "total_rejected_orders", "INTEGER DEFAULT 0"),
        ("users", "total_incomplete_orders", "INTEGER DEFAULT 0"),
        ("users", "total_deposit_amount", "REAL DEFAULT 0.0"),
        ("users", "total_withdraw_amount", "REAL DEFAULT 0.0"),
        ("users", "archive_message_id", "INTEGER DEFAULT NULL"),
        ("orders", "actual_amount", "REAL"),
        ("orders", "rejection_reason", "TEXT"),
        ("orders", "processed_by_admin_id", "INTEGER"),
    ]

    for table, col, type_def in columns_to_add:
        try:
            cur.execute(f"ALTER TABLE {table} ADD COLUMN {col} {type_def}")
        except sqlite3.OperationalError:
            pass
