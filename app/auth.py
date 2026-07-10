"""
Authentication for the Grain Procurement Management System.

Version 1 uses simple username/password rows in the `users` table with a
salted-hash check. This is enough to enforce Business Rules 1 and 12
(authentication required; only authorized roles may perform certain
actions) without pulling in an external auth service.
"""

import hashlib
import hmac
import os
import sqlite3

from app.database import get_connection
from app.exceptions import AuthenticationError, UsernameTakenError, WeakPasswordError


def hash_password(password: str, salt: bytes | None = None) -> str:
    salt = salt or os.urandom(16)
    digest = hashlib.pbkdf2_hmac("sha256", password.encode(), salt, 100_000)
    return salt.hex() + ":" + digest.hex()


def verify_password(password: str, stored: str) -> bool:
    salt_hex, digest_hex = stored.split(":")
    salt = bytes.fromhex(salt_hex)
    expected = hashlib.pbkdf2_hmac("sha256", password.encode(), salt, 100_000)
    return hmac.compare_digest(expected.hex(), digest_hex)


class CurrentUser:
    """Represents an authenticated session. Passed into service calls so
    every action can be checked against the acting user's role."""

    def __init__(self, user_id: int, username: str, role: str):
        self.user_id = user_id
        self.username = username
        self.role = role

    def __repr__(self):
        return f"<CurrentUser {self.username} ({self.role})>"


MIN_PASSWORD_LENGTH = 8


def create_user(username: str, password: str, role: str) -> int:
    username = (username or "").strip()
    if not username:
        raise ValueError("Username cannot be empty")
    if role not in ("AGENT", "MANAGER", "ADMIN"):
        raise ValueError(f"Invalid role: {role}")
    if len(password or "") < MIN_PASSWORD_LENGTH:
        raise WeakPasswordError(
            f"Password must be at least {MIN_PASSWORD_LENGTH} characters"
        )

    try:
        with get_connection() as conn:
            cur = conn.execute(
                "INSERT INTO users (username, password, role) VALUES (?, ?, ?)",
                (username, hash_password(password), role),
            )
            return cur.lastrowid
    except sqlite3.IntegrityError:
        raise UsernameTakenError(f"Username '{username}' is already taken")


def login(username: str, password: str) -> CurrentUser:
    with get_connection() as conn:
        row = conn.execute(
            "SELECT * FROM users WHERE username = ? AND active = 1", (username,)
        ).fetchone()

    if row is None or not verify_password(password, row["password"]):
        raise AuthenticationError("Invalid username or password")

    return CurrentUser(user_id=row["id"], username=row["username"], role=row["role"])


def require_role(user: CurrentUser, *allowed_roles: str) -> None:
    from app.exceptions import AuthorizationError

    if user.role not in allowed_roles:
        raise AuthorizationError(
            f"Action requires one of roles {allowed_roles}, but user has role '{user.role}'"
        )


def list_users():
    with get_connection() as conn:
        rows = conn.execute(
            "SELECT id, username, role, active FROM users ORDER BY role, username"
        ).fetchall()
    return [dict(r) for r in rows]


def set_user_active(user_id: int, active: bool) -> None:
    with get_connection() as conn:
        conn.execute("UPDATE users SET active = ? WHERE id = ?", (1 if active else 0, user_id))
