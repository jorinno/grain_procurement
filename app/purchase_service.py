"""
Core grain purchase and payment workflow (SOP steps 4-14).

This module is the heart of the system: it validates and calculates a
purchase, saves it, sends notifications, and later records manual payment
confirmations until the purchase is COMPLETED.
"""

import re
import uuid
from datetime import datetime, timezone

from app.auth import CurrentUser, require_role
from app.database import get_connection
from app import audit, notification_service
from app.exceptions import (
    InvalidCategoryError,
    InvalidWeightError,
    NoActivePriceError,
    NoActiveCommissionRateError,
    MissingSupplierInfoError,
    InvalidMobileMoneyNumberError,
    PurchaseAlreadyConfirmedError,
    DuplicatePaymentReferenceError,
    DuplicatePaymentConfirmationError,
    PurchaseNotFoundError,
)

# East African mobile money numbers: +2567########## or 07##########
MOMO_NUMBER_PATTERN = re.compile(r"^(\+256|0)7\d{8}$")


# ---------------------------------------------------------------------------
# Step 4-6: validate category/weight, look up active price + rate, calculate
# ---------------------------------------------------------------------------

def validate_category(category_name: str) -> dict:
    """Business Rule 3: category must exist and be active."""
    category_name = category_name.strip().lower()
    if not category_name:
        raise InvalidCategoryError("Please enter a grain category")

    with get_connection() as conn:
        row = conn.execute(
            "SELECT * FROM grain_categories WHERE name = ?", (category_name,)
        ).fetchone()

    if row is None:
        raise InvalidCategoryError(f"Unknown grain category: '{category_name}'")
    if not row["active"]:
        raise InvalidCategoryError(f"Grain category '{category_name}' is not active")

    return dict(row)


def validate_weight(weight_kg) -> float:
    """Business Rule 2: weight must be a positive numerical value."""
    try:
        weight_kg = float(weight_kg)
    except (TypeError, ValueError):
        raise InvalidWeightError("Weight must be a numerical value")

    if weight_kg <= 0:
        raise InvalidWeightError("Weight must be greater than 0")

    return weight_kg


def _get_active_price(conn, category_id: int) -> float:
    row = conn.execute(
        "SELECT price_per_kg FROM grain_prices WHERE category_id = ? AND active = 1",
        (category_id,),
    ).fetchone()
    if row is None:
        raise NoActivePriceError("No active price exists for this grain category")
    return row["price_per_kg"]


def _get_active_commission_rate(conn, category_id: int) -> float:
    row = conn.execute(
        "SELECT rate_per_kg FROM commission_rates WHERE category_id = ? AND active = 1",
        (category_id,),
    ).fetchone()
    if row is None:
        raise NoActiveCommissionRateError(
            "No active commission rate exists for this grain category"
        )
    return row["rate_per_kg"]


def calculate_purchase(category_name: str, weight_kg) -> dict:
    """
    Step 5-6: validate inputs, look up active price/rate, and calculate the
    supplier payout and agent commission.

        Supplier Payout = Grain Weight x Unit Price per Kilogram
        Agent Commission = Grain Weight x Commission Rate per Kilogram
    """
    category = validate_category(category_name)
    weight_kg = validate_weight(weight_kg)

    with get_connection() as conn:
        unit_price = _get_active_price(conn, category["id"])
        commission_rate = _get_active_commission_rate(conn, category["id"])

    supplier_payout = round(weight_kg * unit_price, 2)
    commission_amount = round(weight_kg * commission_rate, 2)

    return {
        "category_id": category["id"],
        "category_name": category["name"],
        "weight_kg": weight_kg,
        "unit_price": unit_price,
        "supplier_payout": supplier_payout,
        "commission_rate": commission_rate,
        "commission_amount": commission_amount,
    }


# ---------------------------------------------------------------------------
# Step 7-8: supplier mobile-money details
# ---------------------------------------------------------------------------

def validate_supplier_details(name: str, momo_provider: str, momo_number: str) -> dict:
    """Business Rule 19 & exception conditions: required supplier info must
    be present, and the mobile-money number must look valid."""
    name = (name or "").strip()
    momo_provider = (momo_provider or "").strip()
    momo_number = (momo_number or "").strip()

    missing = [
        field
        for field, value in [
            ("name", name),
            ("mobile-money provider", momo_provider),
            ("mobile-money number", momo_number),
        ]
        if not value
    ]
    if missing:
        raise MissingSupplierInfoError(
            f"Missing required supplier information: {', '.join(missing)}"
        )

    if not MOMO_NUMBER_PATTERN.match(momo_number):
        raise InvalidMobileMoneyNumberError(
            "Supplier mobile-money number is invalid. Expected format: "
            "07XXXXXXXX or +2567XXXXXXXX"
        )

    return {"name": name, "momo_provider": momo_provider, "momo_number": momo_number}


def _generate_purchase_ref() -> str:
    return "GPR-" + datetime.now().strftime("%Y%m%d") + "-" + uuid.uuid4().hex[:6].upper()


# ---------------------------------------------------------------------------
# Step 9-10: save purchase + notify
# ---------------------------------------------------------------------------

def submit_purchase(
    user: CurrentUser,
    category_name: str,
    weight_kg,
    supplier_name: str,
    momo_provider: str,
    momo_number: str,
    id_info: str = "",
) -> dict:
    """
    Full Step 5-10 flow in one call: calculate, validate supplier details,
    save the purchase, and fire notifications to the agent and manager.
    """
    require_role(user, "AGENT")

    calc = calculate_purchase(category_name, weight_kg)
    supplier = validate_supplier_details(supplier_name, momo_provider, momo_number)

    purchase_ref = _generate_purchase_ref()
    now = datetime.now(timezone.utc).isoformat()

    with get_connection() as conn:
        cur = conn.execute(
            """
            INSERT INTO suppliers (name, momo_provider, momo_number, id_info)
            VALUES (?, ?, ?, ?)
            """,
            (supplier["name"], supplier["momo_provider"], supplier["momo_number"], id_info),
        )
        supplier_id = cur.lastrowid

        cur = conn.execute(
            """
            INSERT INTO purchases (
                purchase_ref, agent_id, supplier_id, category_id, weight_kg,
                unit_price, supplier_payout, commission_rate, commission_amount,
                purchase_datetime, status, supplier_payment_status, agent_payment_status
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 'PAYMENT_PENDING', 'PENDING', 'PENDING')
            """,
            (
                purchase_ref,
                user.user_id,
                supplier_id,
                calc["category_id"],
                calc["weight_kg"],
                calc["unit_price"],
                calc["supplier_payout"],
                calc["commission_rate"],
                calc["commission_amount"],
                now,
            ),
        )
        purchase_id = cur.lastrowid

    audit.record(
        user.username,
        "SUBMIT_PURCHASE",
        "purchases",
        f"{purchase_ref} ({calc['category_name']}, {calc['weight_kg']}kg)",
    )

    notification_service.notify_agent_purchase_saved(
        user.user_id,
        purchase_id,
        f"Purchase {purchase_ref} recorded successfully. "
        f"Supplier payout: {calc['supplier_payout']}, "
        f"your commission: {calc['commission_amount']}. Status: PAYMENT_PENDING.",
    )
    notification_service.notify_manager_new_purchase(
        purchase_id,
        f"New purchase {purchase_ref} by agent '{user.username}' is awaiting payment. "
        f"Supplier: {supplier['name']} ({supplier['momo_provider']} {supplier['momo_number']}). "
        f"Payout: {calc['supplier_payout']}, commission: {calc['commission_amount']}.",
    )

    return get_purchase(purchase_id)


# ---------------------------------------------------------------------------
# Step 11-14: manual payments + completion
# ---------------------------------------------------------------------------

def get_purchase(purchase_id: int) -> dict:
    with get_connection() as conn:
        row = conn.execute(
            """
            SELECT p.*, s.name AS supplier_name, s.momo_provider, s.momo_number,
                   c.name AS category_name, u.username AS agent_username
            FROM purchases p
            JOIN suppliers s ON s.id = p.supplier_id
            JOIN grain_categories c ON c.id = p.category_id
            JOIN users u ON u.id = p.agent_id
            WHERE p.id = ?
            """,
            (purchase_id,),
        ).fetchone()

    if row is None:
        raise PurchaseNotFoundError(f"Purchase {purchase_id} not found")
    return dict(row)


def list_pending_purchases() -> list:
    with get_connection() as conn:
        rows = conn.execute(
            """
            SELECT p.*, s.name AS supplier_name, c.name AS category_name
            FROM purchases p
            JOIN suppliers s ON s.id = p.supplier_id
            JOIN grain_categories c ON c.id = p.category_id
            WHERE p.status != 'COMPLETED' AND p.status != 'CANCELLED'
            ORDER BY p.purchase_datetime
            """
        ).fetchall()
    return [dict(r) for r in rows]


def confirm_payment(
    user: CurrentUser,
    purchase_id: int,
    payment_type: str,
    transaction_reference: str,
) -> dict:
    """
    Step 13: record a manual payment confirmation (supplier payout or agent
    commission). Only MANAGER may do this (Business Rules 11-12).
    Business Rule 20: duplicate confirmation of the same payment is prevented.
    """
    require_role(user, "MANAGER")

    payment_type = payment_type.strip().upper()
    if payment_type not in ("SUPPLIER", "AGENT"):
        raise ValueError("payment_type must be 'SUPPLIER' or 'AGENT'")

    transaction_reference = (transaction_reference or "").strip()
    if not transaction_reference:
        raise ValueError("A Mobile Money transaction reference is required")

    purchase = get_purchase(purchase_id)

    if purchase["status"] == "COMPLETED":
        raise PurchaseAlreadyConfirmedError(
            f"Purchase {purchase['purchase_ref']} is already completed"
        )

    status_field = "supplier_payment_status" if payment_type == "SUPPLIER" else "agent_payment_status"
    if purchase[status_field] == "PAID":
        raise DuplicatePaymentConfirmationError(
            f"{payment_type} payment for {purchase['purchase_ref']} was already confirmed"
        )

    with get_connection() as conn:
        existing_ref = conn.execute(
            "SELECT id FROM payment_confirmations WHERE transaction_reference = ?",
            (transaction_reference,),
        ).fetchone()
        if existing_ref is not None:
            raise DuplicatePaymentReferenceError(
                f"Transaction reference '{transaction_reference}' has already been used"
            )

        now = datetime.now(timezone.utc).isoformat()
        conn.execute(
            """
            INSERT INTO payment_confirmations
                (purchase_id, payment_type, transaction_reference, confirmed_by, confirmed_at)
            VALUES (?, ?, ?, ?, ?)
            """,
            (purchase_id, payment_type, transaction_reference, user.user_id, now),
        )
        conn.execute(
            f"UPDATE purchases SET {status_field} = 'PAID' WHERE id = ?", (purchase_id,)
        )

        refreshed = conn.execute(
            "SELECT supplier_payment_status, agent_payment_status FROM purchases WHERE id = ?",
            (purchase_id,),
        ).fetchone()

        if refreshed["supplier_payment_status"] == "PAID" and refreshed["agent_payment_status"] == "PAID":
            new_status = "COMPLETED"
        else:
            new_status = "PARTIALLY_PAID"

        conn.execute(
            "UPDATE purchases SET status = ? WHERE id = ?", (new_status, purchase_id)
        )

    audit.record(
        user.username,
        f"CONFIRM_{payment_type}_PAYMENT",
        "purchases",
        f"{purchase['purchase_ref']} ref={transaction_reference} -> {new_status}",
    )

    return get_purchase(purchase_id)
