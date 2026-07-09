"""
Seeds the database with an initial admin, manager, and agent account, plus
starter grain categories/prices/commission rates, so the CLI is usable
immediately after cloning.

Run once:  python seed.py
"""

from app.database import init_db, get_connection
from app.auth import create_user
from app.admin_service import add_category, set_price, set_commission_rate
from app.auth import login


def already_seeded() -> bool:
    with get_connection() as conn:
        row = conn.execute("SELECT COUNT(*) AS n FROM users").fetchone()
    return row["n"] > 0


def main():
    init_db()

    if already_seeded():
        print("Database already seeded. Delete grain_procurement.db to reseed.")
        return

    create_user("admin", "admin123", "ADMIN")
    create_user("manager", "manager123", "MANAGER")
    create_user("agent", "agent123", "AGENT")

    admin = login("admin", "admin123")

    add_category(admin, "maize")
    add_category(admin, "beans")

    set_price(admin, "maize", 1200)
    set_price(admin, "beans", 2800)

    set_commission_rate(admin, "maize", 100)
    set_commission_rate(admin, "beans", 150)

    print("Seed complete.")
    print("  Admin:   admin / admin123")
    print("  Manager: manager / manager123")
    print("  Agent:   agent / agent123")
    print("Starter config: maize @1200/kg (commission 100/kg), "
          "beans @2800/kg (commission 150/kg)")


if __name__ == "__main__":
    main()
