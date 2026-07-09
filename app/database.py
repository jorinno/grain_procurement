"""
Database layer for the Grain Procurement Management System.

Uses SQLite for simplicity (no external services required). Schema mirrors
the entities described in section 2.5 of the Grain Purchase and Payment
Workflow document: suppliers, purchases, grain categories, prices,
commission rates, payment confirmations, purchase statuses, notifications,
and audit records.
"""

import sqlite3
from pathlib import Path
from contextlib import contextmanager

DB_PATH = Path(__file__).resolve().parent.parent / "grain_procurement.db"

SCHEMA = """
CREATE TABLE IF NOT EXISTS users (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    username TEXT UNIQUE NOT NULL,
    password TEXT NOT NULL,
    role TEXT NOT NULL CHECK (role IN ('AGENT', 'MANAGER', 'ADMIN')),
    active INTEGER NOT NULL DEFAULT 1
);

CREATE TABLE IF NOT EXISTS grain_categories (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    name TEXT UNIQUE NOT NULL,
    active INTEGER NOT NULL DEFAULT 1
);

CREATE TABLE IF NOT EXISTS grain_prices (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    category_id INTEGER NOT NULL REFERENCES grain_categories(id),
    price_per_kg REAL NOT NULL CHECK (price_per_kg > 0),
    effective_date TEXT NOT NULL,
    active INTEGER NOT NULL DEFAULT 1
);

CREATE TABLE IF NOT EXISTS commission_rates (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    category_id INTEGER NOT NULL REFERENCES grain_categories(id),
    rate_per_kg REAL NOT NULL CHECK (rate_per_kg > 0),
    effective_date TEXT NOT NULL,
    active INTEGER NOT NULL DEFAULT 1
);

CREATE TABLE IF NOT EXISTS suppliers (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    name TEXT NOT NULL,
    momo_provider TEXT NOT NULL,
    momo_number TEXT NOT NULL,
    id_info TEXT
);

CREATE TABLE IF NOT EXISTS purchases (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    purchase_ref TEXT UNIQUE NOT NULL,
    agent_id INTEGER NOT NULL REFERENCES users(id),
    supplier_id INTEGER NOT NULL REFERENCES suppliers(id),
    category_id INTEGER NOT NULL REFERENCES grain_categories(id),
    weight_kg REAL NOT NULL CHECK (weight_kg > 0),
    unit_price REAL NOT NULL,
    supplier_payout REAL NOT NULL,
    commission_rate REAL NOT NULL,
    commission_amount REAL NOT NULL,
    purchase_datetime TEXT NOT NULL,
    status TEXT NOT NULL DEFAULT 'PAYMENT_PENDING'
        CHECK (status IN (
            'DRAFT', 'CALCULATED', 'PAYMENT_PENDING',
            'PARTIALLY_PAID', 'COMPLETED', 'CANCELLED'
        )),
    supplier_payment_status TEXT NOT NULL DEFAULT 'PENDING'
        CHECK (supplier_payment_status IN ('PENDING', 'PAID')),
    agent_payment_status TEXT NOT NULL DEFAULT 'PENDING'
        CHECK (agent_payment_status IN ('PENDING', 'PAID'))
);

CREATE TABLE IF NOT EXISTS payment_confirmations (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    purchase_id INTEGER NOT NULL REFERENCES purchases(id),
    payment_type TEXT NOT NULL CHECK (payment_type IN ('SUPPLIER', 'AGENT')),
    transaction_reference TEXT UNIQUE NOT NULL,
    confirmed_by INTEGER NOT NULL REFERENCES users(id),
    confirmed_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS notifications (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    recipient_role TEXT NOT NULL,
    recipient_id INTEGER REFERENCES users(id),
    purchase_id INTEGER REFERENCES purchases(id),
    message TEXT NOT NULL,
    created_at TEXT NOT NULL,
    read_flag INTEGER NOT NULL DEFAULT 0
);

CREATE TABLE IF NOT EXISTS audit_log (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    actor TEXT NOT NULL,
    action TEXT NOT NULL,
    entity TEXT NOT NULL,
    details TEXT,
    timestamp TEXT NOT NULL
);
"""


def init_db(db_path: Path = DB_PATH) -> None:
    with sqlite3.connect(db_path) as conn:
        conn.executescript(SCHEMA)


@contextmanager
def get_connection(db_path: Path = DB_PATH):
    conn = sqlite3.connect(db_path)
    conn.execute("PRAGMA foreign_keys = ON")
    conn.row_factory = sqlite3.Row
    try:
        yield conn
        conn.commit()
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()
