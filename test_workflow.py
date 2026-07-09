"""
Quick integration test of the full workflow (not a formal pytest suite,
just a smoke test to validate the happy path and key business rules).
"""

from app import auth, purchase_service, admin_service
from app.exceptions import (
    AuthorizationError,
    InvalidWeightError,
    InvalidCategoryError,
    DuplicatePaymentConfirmationError,
    DuplicatePaymentReferenceError,
    InvalidMobileMoneyNumberError,
)


def check(label, condition):
    status = "PASS" if condition else "FAIL"
    print(f"[{status}] {label}")
    assert condition, label


def main():
    agent = auth.login("agent", "agent123")
    manager = auth.login("manager", "manager123")
    admin = auth.login("admin", "admin123")

    # Happy path: agent submits a purchase
    purchase = purchase_service.submit_purchase(
        agent, "maize", 50, "Nakato Sarah", "MTN", "0771234567", "ID-001"
    )
    check("Supplier payout calculated correctly", purchase["supplier_payout"] == 60000)
    check("Commission calculated correctly", purchase["commission_amount"] == 5000)
    check("Initial status is PAYMENT_PENDING", purchase["status"] == "PAYMENT_PENDING")

    # Rule 11/12: agent cannot confirm payments
    try:
        purchase_service.confirm_payment(agent, purchase["id"], "SUPPLIER", "TXN001")
        check("Agent blocked from confirming payment", False)
    except AuthorizationError:
        check("Agent blocked from confirming payment", True)

    # Manager confirms supplier payout
    updated = purchase_service.confirm_payment(manager, purchase["id"], "SUPPLIER", "TXN001")
    check("Status PARTIALLY_PAID after one confirmation", updated["status"] == "PARTIALLY_PAID")

    # Rule 20: duplicate confirmation of same payment blocked
    try:
        purchase_service.confirm_payment(manager, purchase["id"], "SUPPLIER", "TXN002")
        check("Duplicate supplier confirmation blocked", False)
    except DuplicatePaymentConfirmationError:
        check("Duplicate supplier confirmation blocked", True)

    # Duplicate transaction reference blocked
    try:
        purchase_service.confirm_payment(manager, purchase["id"], "AGENT", "TXN001")
        check("Duplicate transaction reference blocked", False)
    except DuplicatePaymentReferenceError:
        check("Duplicate transaction reference blocked", True)

    # Manager confirms agent commission -> should complete
    final = purchase_service.confirm_payment(manager, purchase["id"], "AGENT", "TXN002")
    check("Status COMPLETED after both confirmations", final["status"] == "COMPLETED")

    # Business Rule 2: invalid weight rejected
    try:
        purchase_service.calculate_purchase("maize", -5)
        check("Negative weight rejected", False)
    except InvalidWeightError:
        check("Negative weight rejected", True)

    # Business Rule 3: unknown category rejected
    try:
        purchase_service.calculate_purchase("sorghum", 10)
        check("Unknown category rejected", False)
    except InvalidCategoryError:
        check("Unknown category rejected", True)

    # Invalid mobile money number rejected
    try:
        purchase_service.validate_supplier_details("Jane", "MTN", "12345")
        check("Invalid MoMo number rejected", False)
    except InvalidMobileMoneyNumberError:
        check("Invalid MoMo number rejected", True)

    # Deactivating category blocks new purchases but not historical ones
    admin_service.set_category_active(admin, "beans", False)
    try:
        purchase_service.calculate_purchase("beans", 10)
        check("Inactive category blocks new purchase", False)
    except InvalidCategoryError:
        check("Inactive category blocks new purchase", True)

    check(
        "Historical purchase retains original price after config change",
        purchase_service.get_purchase(purchase["id"])["unit_price"] == 1200,
    )

    print("\nAll checks passed.")


if __name__ == "__main__":
    main()
