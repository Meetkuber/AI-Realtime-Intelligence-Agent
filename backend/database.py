"""
database.py — Real SQLite persistence layer
============================================================
Replaces pure in-memory dicts with an actual SQLite database.
On startup, seeds product catalog from FakeStore API (real HTTP call).
All tool functions now do real CRUD — demonstrable with sqlite3 CLI.
"""
from __future__ import annotations

import json
import logging
import random
import sqlite3
import string
from contextlib import contextmanager
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any

import httpx

logger = logging.getLogger(__name__)

DB_PATH = Path(__file__).parent.parent / "aria.db"

# ─────────────────────────────────────────────────────────────
# Schema
# ─────────────────────────────────────────────────────────────
SCHEMA = """
CREATE TABLE IF NOT EXISTS orders (
    id          TEXT PRIMARY KEY,
    customer_id TEXT NOT NULL,
    customer_name TEXT NOT NULL,
    items_json  TEXT NOT NULL,
    total       REAL NOT NULL,
    status      TEXT NOT NULL,
    placed_at   TEXT NOT NULL,
    estimated_delivery TEXT,
    delivered_at TEXT,
    tracking    TEXT,
    address     TEXT,
    refundable  INTEGER NOT NULL DEFAULT 0
);

CREATE TABLE IF NOT EXISTS refunds (
    id          TEXT PRIMARY KEY,
    order_id    TEXT NOT NULL,
    amount      REAL NOT NULL,
    reason      TEXT NOT NULL,
    status      TEXT NOT NULL DEFAULT 'pending',
    created_at  TEXT NOT NULL,
    eta_date    TEXT NOT NULL,
    FOREIGN KEY (order_id) REFERENCES orders(id)
);

CREATE TABLE IF NOT EXISTS tickets (
    id          TEXT PRIMARY KEY,
    issue       TEXT NOT NULL,
    priority    TEXT NOT NULL,
    status      TEXT NOT NULL DEFAULT 'open',
    created_at  TEXT NOT NULL,
    sla_hours   INTEGER NOT NULL
);

CREATE TABLE IF NOT EXISTS customers (
    id          TEXT PRIMARY KEY,
    name        TEXT NOT NULL,
    points      INTEGER NOT NULL DEFAULT 0,
    tier        TEXT NOT NULL DEFAULT 'Bronze',
    points_expiry TEXT
);

CREATE TABLE IF NOT EXISTS products (
    id          INTEGER PRIMARY KEY,
    title       TEXT NOT NULL,
    price       REAL NOT NULL,
    category    TEXT NOT NULL,
    image       TEXT
);

CREATE TABLE IF NOT EXISTS metrics (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    event_type  TEXT NOT NULL,
    tool_name   TEXT,
    duration_ms REAL,
    success     INTEGER,
    ts          TEXT NOT NULL
);
"""

SEED_ORDERS = [
    {
        "id": "ORD-1234",
        "customer_id": "CUST-001",
        "customer_name": "Alex Johnson",
        "items_json": json.dumps([{"name": "Nike Air Max 270", "qty": 1, "price": 129.99}]),
        "total": 129.99,
        "status": "Delivered",
        "placed_at": "2025-06-25",
        "estimated_delivery": "2025-06-29",
        "delivered_at": "2025-06-28",
        "tracking": "1Z999AA1012345678",
        "address": "123 Elm Street, Austin, TX 78701",
        "refundable": 1,
    },
    {
        "id": "ORD-5678",
        "customer_id": "CUST-002",
        "customer_name": "Maria Chen",
        "items_json": json.dumps([
            {"name": "MacBook Sleeve 15\"", "qty": 1, "price": 45.00},
            {"name": "USB-C Hub 7-in-1",   "qty": 1, "price": 39.99},
        ]),
        "total": 84.99,
        "status": "In Transit",
        "placed_at": "2025-07-01",
        "estimated_delivery": "2025-07-05",
        "delivered_at": None,
        "tracking": "9400111899223937813800",
        "address": "456 Oak Avenue, Seattle, WA 98101",
        "refundable": 0,
    },
    {
        "id": "ORD-9012",
        "customer_id": "CUST-003",
        "customer_name": "James Williams",
        "items_json": json.dumps([{"name": "Sony WH-1000XM5 Headphones", "qty": 1, "price": 349.99}]),
        "total": 349.99,
        "status": "Processing",
        "placed_at": "2025-07-02",
        "estimated_delivery": "2025-07-07",
        "delivered_at": None,
        "tracking": None,
        "address": "789 Pine Road, Chicago, IL 60601",
        "refundable": 0,
    },
    {
        "id": "ORD-3456",
        "customer_id": "CUST-004",
        "customer_name": "Sarah Miller",
        "items_json": json.dumps([{"name": "Kindle Paperwhite 16GB", "qty": 1, "price": 149.99}]),
        "total": 149.99,
        "status": "Cancelled",
        "placed_at": "2025-06-20",
        "estimated_delivery": None,
        "delivered_at": None,
        "tracking": None,
        "address": "321 Maple Drive, Boston, MA 02101",
        "refundable": 1,
    },
]

SEED_CUSTOMERS = [
    {"id": "CUST-001", "name": "Alex Johnson",  "points": 2450, "tier": "Gold",     "points_expiry": "2027-01-01"},
    {"id": "CUST-002", "name": "Maria Chen",    "points": 870,  "tier": "Silver",   "points_expiry": "2027-01-01"},
    {"id": "CUST-003", "name": "James Williams","points": 150,  "tier": "Bronze",   "points_expiry": "2027-01-01"},
    {"id": "CUST-004", "name": "Sarah Miller",  "points": 5100, "tier": "Platinum", "points_expiry": "2027-01-01"},
]


# ─────────────────────────────────────────────────────────────
# Connection helper
# ─────────────────────────────────────────────────────────────

@contextmanager
def get_db():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL")
    try:
        yield conn
        conn.commit()
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()


# ─────────────────────────────────────────────────────────────
# Initialization
# ─────────────────────────────────────────────────────────────

def init_db() -> None:
    """Create schema and seed data. Safe to call multiple times (idempotent)."""
    with get_db() as conn:
        conn.executescript(SCHEMA)

        # Seed orders
        for o in SEED_ORDERS:
            conn.execute(
                """INSERT OR IGNORE INTO orders
                   (id,customer_id,customer_name,items_json,total,status,
                    placed_at,estimated_delivery,delivered_at,tracking,address,refundable)
                   VALUES (?,?,?,?,?,?,?,?,?,?,?,?)""",
                (o["id"], o["customer_id"], o["customer_name"], o["items_json"],
                 o["total"], o["status"], o["placed_at"], o["estimated_delivery"],
                 o["delivered_at"], o["tracking"], o["address"], o["refundable"]),
            )

        # Seed customers
        for c in SEED_CUSTOMERS:
            conn.execute(
                "INSERT OR IGNORE INTO customers (id,name,points,tier,points_expiry) VALUES (?,?,?,?,?)",
                (c["id"], c["name"], c["points"], c["tier"], c["points_expiry"]),
            )

    logger.info(f"[DB] Initialized SQLite at {DB_PATH}")
    _seed_products_from_fakestore()


def _seed_products_from_fakestore() -> None:
    """
    Fetch real product catalog from FakeStore API and persist to SQLite.
    This is the 'real integration' — an actual HTTP call to a live API.
    FakeStore API: https://fakestoreapi.com — free, no auth required.
    """
    with get_db() as conn:
        count = conn.execute("SELECT COUNT(*) FROM products").fetchone()[0]
        if count > 0:
            logger.info(f"[DB] Products already seeded ({count} items), skipping FakeStore fetch")
            return

    try:
        logger.info("[DB] Fetching product catalog from FakeStore API…")
        resp = httpx.get("https://fakestoreapi.com/products", timeout=10.0)
        resp.raise_for_status()
        products = resp.json()

        with get_db() as conn:
            for p in products:
                conn.execute(
                    "INSERT OR IGNORE INTO products (id,title,price,category,image) VALUES (?,?,?,?,?)",
                    (p["id"], p["title"], p["price"], p["category"], p.get("image")),
                )

        logger.info(f"[DB] Seeded {len(products)} products from FakeStore API ✅")

    except Exception as exc:
        logger.warning(f"[DB] FakeStore API unavailable ({exc}), products table empty — non-fatal")


# ─────────────────────────────────────────────────────────────
# CRUD Operations (used by tools.py)
# ─────────────────────────────────────────────────────────────

def db_get_order(order_id: str) -> dict | None:
    with get_db() as conn:
        row = conn.execute("SELECT * FROM orders WHERE id=?", (order_id.upper(),)).fetchone()
    if not row:
        return None
    d = dict(row)
    d["items"] = json.loads(d.pop("items_json"))
    d["refundable"] = bool(d["refundable"])
    return d


def db_get_all_orders() -> list[dict]:
    with get_db() as conn:
        rows = conn.execute("SELECT * FROM orders ORDER BY placed_at DESC").fetchall()
    result = []
    for row in rows:
        d = dict(row)
        d["items"] = json.loads(d.pop("items_json"))
        d["refundable"] = bool(d["refundable"])
        result.append(d)
    return result


def db_create_refund(order_id: str, amount: float, reason: str, eta_date: str) -> str:
    refund_id = "REF-" + "".join(random.choices(string.digits, k=6))
    now = datetime.now().isoformat()
    with get_db() as conn:
        conn.execute(
            "INSERT INTO refunds (id,order_id,amount,reason,status,created_at,eta_date) VALUES (?,?,?,?,?,?,?)",
            (refund_id, order_id, amount, reason, "pending", now, eta_date),
        )
    return refund_id


def db_create_ticket(issue: str, priority: str, sla_hours: int) -> str:
    ticket_id = "TKT-" + "".join(random.choices(string.ascii_uppercase + string.digits, k=8))
    now = datetime.now().isoformat()
    with get_db() as conn:
        conn.execute(
            "INSERT INTO tickets (id,issue,priority,status,created_at,sla_hours) VALUES (?,?,?,?,?,?)",
            (ticket_id, issue[:500], priority, "open", now, sla_hours),
        )
    return ticket_id


def db_get_customer(customer_id: str) -> dict | None:
    with get_db() as conn:
        row = conn.execute("SELECT * FROM customers WHERE id=?", (customer_id.upper(),)).fetchone()
    return dict(row) if row else None


def db_get_all_tickets() -> list[dict]:
    with get_db() as conn:
        rows = conn.execute("SELECT * FROM tickets ORDER BY created_at DESC").fetchall()
    return [dict(r) for r in rows]


def db_get_all_refunds() -> list[dict]:
    with get_db() as conn:
        rows = conn.execute("SELECT * FROM refunds ORDER BY created_at DESC").fetchall()
    return [dict(r) for r in rows]


def db_record_metric(event_type: str, tool_name: str | None, duration_ms: float | None, success: bool) -> None:
    """Persist a metric event for the /api/metrics endpoint."""
    try:
        with get_db() as conn:
            conn.execute(
                "INSERT INTO metrics (event_type,tool_name,duration_ms,success,ts) VALUES (?,?,?,?,?)",
                (event_type, tool_name, duration_ms, int(success), datetime.now().isoformat()),
            )
    except Exception:
        pass  # metrics are non-critical
