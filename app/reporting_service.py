"""
Audit & reporting for regulatory purposes (e.g. Uganda Revenue Authority
tax audits).

This module is intentionally read-only: it never writes to the database.
It pulls together the fields an auditor would actually need to see --
who was paid, how much, when, by what reference, and under what price/
commission configuration -- from across purchases, suppliers,
categories, agents, and payment confirmations.

Business Rule 16/17 (unit price and commission rate are snapshotted onto
each purchase, not looked up live) means this report is historically
accurate even after admin changes prices later -- exactly what an
auditor needs.
"""

import csv
import io

from app.auth import CurrentUser, require_role
from app.database import get_connection
from app import audit


def get_audit_report(
    start_date: str | None = None,
    end_date: str | None = None,
    status: str | None = None,
    category: str | None = None,
) -> list[dict]:
    """
    Returns one row per purchase with everything a tax audit would need:
    reference, date, category, weight, unit price, supplier payout,
    commission rate/amount, supplier identity, agent identity, purchase
    status, and both payment transaction references (if confirmed).

    Filters are all optional and combine with AND:
      start_date / end_date -- ISO date strings (YYYY-MM-DD), inclusive,
                                matched against purchase_datetime
      status                -- exact purchase status (e.g. 'COMPLETED')
      category               -- grain category name
    """
    query = """
        SELECT
            p.purchase_ref,
            p.purchase_datetime,
            c.name AS category,
            p.weight_kg,
            p.unit_price,
            p.supplier_payout,
            p.commission_rate,
            p.commission_amount,
            p.status,
            p.supplier_payment_status,
            p.agent_payment_status,
            s.name AS supplier_name,
            s.momo_provider,
            s.momo_number,
            s.id_info AS supplier_id_info,
            u.username AS agent_username,
            supplier_pay.transaction_reference AS supplier_txn_ref,
            supplier_pay.confirmed_at AS supplier_paid_at,
            agent_pay.transaction_reference AS agent_txn_ref,
            agent_pay.confirmed_at AS agent_paid_at
        FROM purchases p
        JOIN suppliers s ON s.id = p.supplier_id
        JOIN grain_categories c ON c.id = p.category_id
        JOIN users u ON u.id = p.agent_id
        LEFT JOIN payment_confirmations supplier_pay
            ON supplier_pay.purchase_id = p.id AND supplier_pay.payment_type = 'SUPPLIER'
        LEFT JOIN payment_confirmations agent_pay
            ON agent_pay.purchase_id = p.id AND agent_pay.payment_type = 'AGENT'
        WHERE 1=1
    """
    params: list = []

    if start_date:
        query += " AND date(p.purchase_datetime) >= date(?)"
        params.append(start_date)
    if end_date:
        query += " AND date(p.purchase_datetime) <= date(?)"
        params.append(end_date)
    if status:
        query += " AND p.status = ?"
        params.append(status)
    if category:
        query += " AND c.name = ?"
        params.append(category.strip().lower())

    query += " ORDER BY p.purchase_datetime"

    with get_connection() as conn:
        rows = conn.execute(query, params).fetchall()

    return [dict(r) for r in rows]


def get_audit_summary(rows: list[dict]) -> dict:
    """Aggregate totals for the currently-filtered report -- total weight
    purchased, total paid to suppliers, and total agent commission paid."""
    return {
        "purchase_count": len(rows),
        "total_weight_kg": round(sum(r["weight_kg"] for r in rows), 2),
        "total_supplier_payout": round(sum(r["supplier_payout"] for r in rows), 2),
        "total_commission_paid": round(sum(r["commission_amount"] for r in rows), 2),
    }


CSV_COLUMNS = [
    "purchase_ref", "purchase_datetime", "category", "weight_kg", "unit_price",
    "supplier_payout", "commission_rate", "commission_amount", "status",
    "supplier_payment_status", "agent_payment_status", "supplier_name",
    "momo_provider", "momo_number", "supplier_id_info", "agent_username",
    "supplier_txn_ref", "supplier_paid_at", "agent_txn_ref", "agent_paid_at",
]


def export_csv(rows: list[dict]) -> str:
    """Serializes report rows to CSV text (in-memory, no file written to disk)."""
    buffer = io.StringIO()
    writer = csv.DictWriter(buffer, fieldnames=CSV_COLUMNS, extrasaction="ignore")
    writer.writeheader()
    for row in rows:
        writer.writerow(row)
    return buffer.getvalue()


def record_export(user: CurrentUser, filters: dict, row_count: int) -> None:
    """Business Rule 18: important actions go in the audit log -- and an
    auditor pulling a full export of financial records is exactly that."""
    require_role(user, "ADMIN", "MANAGER")
    audit.record(
        user.username,
        "EXPORT_AUDIT_REPORT",
        "purchases",
        f"filters={filters} rows={row_count}",
    )
