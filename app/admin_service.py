"""
Administrator Configuration Workflow (section 5 of the SOP).

The administrator maintains grain categories, unit prices, and commission
rates. Business Rule 16 requires that changes to prices/rates must not
alter previously saved purchases -- this is satisfied structurally because
`purchases` stores a snapshot of the unit_price/commission_rate that was
active at the time, rather than a foreign key to the live config row.
"""

from datetime import date

from app.auth import CurrentUser, require_role
from app.database import get_connection
from app import audit


def add_category(user: CurrentUser, name: str) -> int:
    require_role(user, "ADMIN")
    name = name.strip().lower()
    if not name:
        raise ValueError("Category name cannot be empty")

    with get_connection() as conn:
        cur = conn.execute(
            "INSERT INTO grain_categories (name, active) VALUES (?, 1)", (name,)
        )
        category_id = cur.lastrowid

    audit.record(user.username, "ADD_CATEGORY", "grain_categories", name)
    return category_id


def set_category_active(user: CurrentUser, category_name: str, active: bool) -> None:
    require_role(user, "ADMIN")
    with get_connection() as conn:
        conn.execute(
            "UPDATE grain_categories SET active = ? WHERE name = ?",
            (1 if active else 0, category_name.strip().lower()),
        )
    audit.record(
        user.username,
        "SET_CATEGORY_ACTIVE" if active else "SET_CATEGORY_INACTIVE",
        "grain_categories",
        category_name,
    )


def _get_category_id(conn, category_name: str) -> int:
    row = conn.execute(
        "SELECT id FROM grain_categories WHERE name = ?",
        (category_name.strip().lower(),),
    ).fetchone()
    if row is None:
        raise ValueError(f"Unknown grain category: {category_name}")
    return row["id"]


def set_price(
    user: CurrentUser,
    category_name: str,
    price_per_kg: float,
    effective_date: str | None = None,
) -> int:
    """Deactivates any currently active price for the category and inserts
    a new active price. Historical purchases already reference the old
    price by value, so they are unaffected (Business Rule 16)."""
    require_role(user, "ADMIN")
    if price_per_kg <= 0:
        raise ValueError("Price must be greater than 0")

    effective_date = effective_date or date.today().isoformat()

    with get_connection() as conn:
        category_id = _get_category_id(conn, category_name)
        conn.execute(
            "UPDATE grain_prices SET active = 0 WHERE category_id = ? AND active = 1",
            (category_id,),
        )
        cur = conn.execute(
            """
            INSERT INTO grain_prices (category_id, price_per_kg, effective_date, active)
            VALUES (?, ?, ?, 1)
            """,
            (category_id, price_per_kg, effective_date),
        )
        price_id = cur.lastrowid

    audit.record(
        user.username,
        "SET_PRICE",
        "grain_prices",
        f"{category_name} -> {price_per_kg}/kg effective {effective_date}",
    )
    return price_id


def set_commission_rate(
    user: CurrentUser,
    category_name: str,
    rate_per_kg: float,
    effective_date: str | None = None,
) -> int:
    require_role(user, "ADMIN")
    if rate_per_kg <= 0:
        raise ValueError("Commission rate must be greater than 0")

    effective_date = effective_date or date.today().isoformat()

    with get_connection() as conn:
        category_id = _get_category_id(conn, category_name)
        conn.execute(
            "UPDATE commission_rates SET active = 0 WHERE category_id = ? AND active = 1",
            (category_id,),
        )
        cur = conn.execute(
            """
            INSERT INTO commission_rates (category_id, rate_per_kg, effective_date, active)
            VALUES (?, ?, ?, 1)
            """,
            (category_id, rate_per_kg, effective_date),
        )
        rate_id = cur.lastrowid

    audit.record(
        user.username,
        "SET_COMMISSION_RATE",
        "commission_rates",
        f"{category_name} -> {rate_per_kg}/kg effective {effective_date}",
    )
    return rate_id


def list_all_categories(user: CurrentUser | None = None):
    """Returns every category (active or not) -- used by admin screens that
    need to toggle status, as opposed to purchase screens which should only
    ever see active categories."""
    with get_connection() as conn:
        rows = conn.execute(
            "SELECT name, active FROM grain_categories ORDER BY name"
        ).fetchall()
    return [dict(row) for row in rows]


def list_active_config(user: CurrentUser | None = None):
    """Returns all active categories with their current price and commission rate."""
    with get_connection() as conn:
        rows = conn.execute(
            """
            SELECT
                c.name AS category,
                c.active AS category_active,
                p.price_per_kg,
                r.rate_per_kg
            FROM grain_categories c
            LEFT JOIN grain_prices p ON p.category_id = c.id AND p.active = 1
            LEFT JOIN commission_rates r ON r.category_id = c.id AND r.active = 1
            ORDER BY c.name
            """
        ).fetchall()
    return [dict(row) for row in rows]
