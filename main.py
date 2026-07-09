"""
Grain Procurement Management System - Version 1 (Manual Payment Workflow)

Command-line interface exercising the full SOP:
  - Purchase Agent: log in, start a purchase, enter grain info, review
    calculation, enter/verify supplier mobile-money details, confirm.
  - Procurement Manager: view pending purchases, record manual payment
    confirmations for supplier payout and agent commission.
  - Administrator: manage grain categories, prices, and commission rates.

Run `python seed.py` once before first use.
"""

from app.database import init_db
from app import auth, admin_service, purchase_service, notification_service
from app.exceptions import GrainProcurementError


def prompt(label: str) -> str:
    return input(f"{label}: ").strip()


def pause():
    input("\nPress Enter to continue...")


# ---------------------------------------------------------------------------
# Agent workflow
# ---------------------------------------------------------------------------

def agent_menu(user):
    while True:
        print(f"\n--- Purchase Agent Menu ({user.username}) ---")
        print("1. Start a new purchase")
        print("2. View my notifications")
        print("3. Log out")
        choice = prompt("Choose an option")

        if choice == "1":
            start_new_purchase(user)
        elif choice == "2":
            show_notifications("AGENT", user.user_id)
        elif choice == "3":
            break
        else:
            print("Invalid option.")


def start_new_purchase(user):
    try:
        category = prompt("Grain category (e.g. maize, beans)")
        weight = prompt("Grain weight in kg")

        calc = purchase_service.calculate_purchase(category, weight)

        print("\n--- Purchase Summary (read-only) ---")
        print(f"Category:            {calc['category_name']}")
        print(f"Weight:              {calc['weight_kg']} kg")
        print(f"Unit price/kg:       {calc['unit_price']}")
        print(f"Supplier payout:     {calc['supplier_payout']}")
        print(f"Commission rate/kg:  {calc['commission_rate']}")
        print(f"Your commission:     {calc['commission_amount']}")

        while True:
            print("\nEnter supplier mobile-money details:")
            name = prompt("Supplier name")
            provider = prompt("Mobile-money provider (e.g. MTN, Airtel)")
            number = prompt("Mobile-money number (07XXXXXXXX)")
            id_info = prompt("Supplier ID info (optional)")

            print(f"\nPlease verify -> {name}, {provider}, {number}")
            verify = prompt("Correct? (y/n)").lower()
            if verify == "y":
                break
            print("Let's re-enter the supplier details.")

        confirm = prompt("\nConfirm and submit this purchase? (y/n)").lower()
        if confirm != "y":
            print("Purchase cancelled (not saved).")
            return

        purchase = purchase_service.submit_purchase(
            user, category, weight, name, provider, number, id_info
        )
        print(f"\nSaved. Purchase reference: {purchase['purchase_ref']}")
        print(f"Status: {purchase['status']}")

    except GrainProcurementError as e:
        print(f"\nError: {e}")


# ---------------------------------------------------------------------------
# Manager workflow
# ---------------------------------------------------------------------------

def manager_menu(user):
    while True:
        print(f"\n--- Procurement Manager Menu ({user.username}) ---")
        print("1. View pending purchases")
        print("2. Record a payment confirmation")
        print("3. View my notifications")
        print("4. Log out")
        choice = prompt("Choose an option")

        if choice == "1":
            view_pending(user)
        elif choice == "2":
            record_payment(user)
        elif choice == "3":
            show_notifications("MANAGER")
        elif choice == "4":
            break
        else:
            print("Invalid option.")


def view_pending(user):
    pending = purchase_service.list_pending_purchases()
    if not pending:
        print("\nNo pending purchases.")
        return

    print("\n--- Pending Purchases ---")
    for p in pending:
        print(
            f"[{p['id']}] {p['purchase_ref']} | {p['category_name']} {p['weight_kg']}kg | "
            f"Supplier: {p['supplier_name']} (payout {p['supplier_payout']}, "
            f"status {p['supplier_payment_status']}) | "
            f"Agent commission {p['commission_amount']} (status {p['agent_payment_status']}) | "
            f"Overall: {p['status']}"
        )


def record_payment(user):
    try:
        purchase_id = int(prompt("Purchase ID"))
        payment_type = prompt("Payment type (SUPPLIER/AGENT)")
        ref = prompt("Mobile Money transaction reference")

        purchase = purchase_service.confirm_payment(user, purchase_id, payment_type, ref)
        print(f"\nRecorded. Purchase {purchase['purchase_ref']} status is now: {purchase['status']}")

    except (ValueError, GrainProcurementError) as e:
        print(f"\nError: {e}")


# ---------------------------------------------------------------------------
# Admin workflow
# ---------------------------------------------------------------------------

def admin_menu(user):
    while True:
        print(f"\n--- Administrator Menu ({user.username}) ---")
        print("1. View active configuration")
        print("2. Add grain category")
        print("3. Set grain price")
        print("4. Set commission rate")
        print("5. Activate/deactivate a category")
        print("6. Log out")
        choice = prompt("Choose an option")

        try:
            if choice == "1":
                for row in admin_service.list_active_config(user):
                    print(row)
            elif choice == "2":
                name = prompt("New category name")
                admin_service.add_category(user, name)
                print("Category added.")
            elif choice == "3":
                name = prompt("Category name")
                price = float(prompt("New price per kg"))
                admin_service.set_price(user, name, price)
                print("Price updated.")
            elif choice == "4":
                name = prompt("Category name")
                rate = float(prompt("New commission rate per kg"))
                admin_service.set_commission_rate(user, name, rate)
                print("Commission rate updated.")
            elif choice == "5":
                name = prompt("Category name")
                active = prompt("Set active? (y/n)").lower() == "y"
                admin_service.set_category_active(user, name, active)
                print("Category status updated.")
            elif choice == "6":
                break
            else:
                print("Invalid option.")
        except (ValueError, GrainProcurementError) as e:
            print(f"\nError: {e}")


# ---------------------------------------------------------------------------
# Shared helpers + entry point
# ---------------------------------------------------------------------------

def show_notifications(role, recipient_id=None):
    notes = notification_service.list_for_role(role, recipient_id)
    if not notes:
        print("\nNo notifications.")
        return
    print(f"\n--- Notifications ({role}) ---")
    for n in notes:
        flag = " " if n["read_flag"] else "*"
        print(f"{flag} [{n['created_at']}] {n['message']}")


def main():
    init_db()
    print("=== Grain Procurement Management System (Version 1) ===")

    while True:
        username = prompt("\nUsername (or 'exit' to quit)")
        if username.lower() == "exit":
            break
        password = prompt("Password")

        try:
            user = auth.login(username, password)
        except GrainProcurementError as e:
            print(f"Login failed: {e}")
            continue

        print(f"Logged in as {user.username} ({user.role})")

        if user.role == "AGENT":
            agent_menu(user)
        elif user.role == "MANAGER":
            manager_menu(user)
        elif user.role == "ADMIN":
            admin_menu(user)


if __name__ == "__main__":
    main()
