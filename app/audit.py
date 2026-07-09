"""
Audit logging, per Business Rule 18: 'Important actions must be recorded
in the audit history.'
"""

from datetime import datetime, timezone

from app.database import get_connection


def record(actor: str, action: str, entity: str, details: str = "") -> None:
    with get_connection() as conn:
        conn.execute(
            """
            INSERT INTO audit_log (actor, action, entity, details, timestamp)
            VALUES (?, ?, ?, ?, ?)
            """,
            (actor, action, entity, details, datetime.now(timezone.utc).isoformat()),
        )


def history(limit: int = 50):
    with get_connection() as conn:
        rows = conn.execute(
            "SELECT * FROM audit_log ORDER BY id DESC LIMIT ?", (limit,)
        ).fetchall()
    return [dict(r) for r in rows]
