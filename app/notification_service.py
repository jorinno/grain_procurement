"""
Notification generation, per Step 10 of the SOP.
"""

from datetime import datetime, timezone

from app.database import get_connection


def notify_agent_purchase_saved(agent_id: int, purchase_id: int, message: str) -> int:
    return _create(
        recipient_role="AGENT",
        recipient_id=agent_id,
        purchase_id=purchase_id,
        message=message,
    )


def notify_manager_new_purchase(purchase_id: int, message: str) -> int:
    return _create(
        recipient_role="MANAGER",
        recipient_id=None,
        purchase_id=purchase_id,
        message=message,
    )


def _create(recipient_role: str, recipient_id, purchase_id: int, message: str) -> int:
    with get_connection() as conn:
        cur = conn.execute(
            """
            INSERT INTO notifications
                (recipient_role, recipient_id, purchase_id, message, created_at, read_flag)
            VALUES (?, ?, ?, ?, ?, 0)
            """,
            (
                recipient_role,
                recipient_id,
                purchase_id,
                message,
                datetime.now(timezone.utc).isoformat(),
            ),
        )
        return cur.lastrowid


def list_for_role(role: str, recipient_id: int | None = None, unread_only: bool = False):
    query = "SELECT * FROM notifications WHERE recipient_role = ?"
    params: list = [role]

    if recipient_id is not None:
        query += " AND (recipient_id = ? OR recipient_id IS NULL)"
        params.append(recipient_id)

    if unread_only:
        query += " AND read_flag = 0"

    query += " ORDER BY id DESC"

    with get_connection() as conn:
        rows = conn.execute(query, params).fetchall()
    return [dict(r) for r in rows]


def mark_read(notification_id: int) -> None:
    with get_connection() as conn:
        conn.execute(
            "UPDATE notifications SET read_flag = 1 WHERE id = ?", (notification_id,)
        )
