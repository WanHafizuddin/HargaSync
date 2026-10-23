"""Passwords, the logged-in user, role checks and CSRF. Every check here runs on the server."""

import hashlib
import hmac
import secrets
import sqlite3
from dataclasses import dataclass

from fastapi import Depends, HTTPException, Request

from .db import connect

PBKDF2_ITERATIONS = 200_000
ROLE_LABELS = {"owner": "Owner", "staff": "Staff", "auditor": "Auditor"}


class LoginRequired(Exception):
    """No valid session; the app redirects to /login."""


@dataclass(frozen=True)
class CurrentUser:
    user_id: int
    username: str
    display_name: str
    shop_id: int
    shop_name: str
    district: str
    retail_level: str
    role: str

    @property
    def role_label(self) -> str:
        return ROLE_LABELS[self.role]


def hash_password(password: str, salt: bytes | None = None) -> str:
    salt = salt or secrets.token_bytes(16)
    digest = hashlib.pbkdf2_hmac("sha256", password.encode(), salt, PBKDF2_ITERATIONS)
    return f"pbkdf2_sha256${PBKDF2_ITERATIONS}${salt.hex()}${digest.hex()}"


def verify_password(password: str, stored: str) -> bool:
    try:
        algorithm, iterations, salt_hex, digest_hex = stored.split("$")
        if algorithm != "pbkdf2_sha256":
            return False
        digest = hashlib.pbkdf2_hmac("sha256", password.encode(), bytes.fromhex(salt_hex), int(iterations))
    except ValueError:
        return False
    return hmac.compare_digest(digest.hex(), digest_hex)


def get_db(request: Request):
    conn = connect(request.app.state.db_path)
    try:
        yield conn
    finally:
        conn.close()


def load_user(conn: sqlite3.Connection, user_id: int) -> CurrentUser | None:
    row = conn.execute(
        "SELECT u.id, u.username, u.display_name, m.role, s.id AS shop_id, s.name AS shop_name,"
        " s.district, s.retail_level"
        " FROM users u JOIN memberships m ON m.user_id = u.id JOIN shops s ON s.id = m.shop_id"
        " WHERE u.id = ? ORDER BY s.id LIMIT 1",
        (user_id,),
    ).fetchone()
    if row is None:
        return None
    return CurrentUser(
        user_id=row["id"], username=row["username"], display_name=row["display_name"],
        shop_id=row["shop_id"], shop_name=row["shop_name"], district=row["district"],
        retail_level=row["retail_level"], role=row["role"],
    )


def current_user(request: Request, conn: sqlite3.Connection = Depends(get_db)) -> CurrentUser:
    user_id = request.session.get("user_id")
    user = load_user(conn, user_id) if user_id else None
    if user is None:
        request.session.clear()
        raise LoginRequired()
    return user


def require_roles(user: CurrentUser, *roles: str) -> None:
    if user.role not in roles:
        raise HTTPException(status_code=403, detail="Your role cannot do this.")


def ensure_csrf(request: Request) -> str:
    token = request.session.get("csrf")
    if not token:
        token = secrets.token_urlsafe(32)
        request.session["csrf"] = token
    return token


def verify_csrf(request: Request, token: str) -> None:
    expected = request.session.get("csrf")
    if not expected or not token or not hmac.compare_digest(expected, token):
        raise HTTPException(status_code=403, detail="This form expired. Reload the page and try again.")


def start_session(request: Request, user_id: int) -> None:
    """Fresh session on login: drop anything from before, issue a new CSRF token."""
    request.session.clear()
    request.session["user_id"] = user_id
    request.session["csrf"] = secrets.token_urlsafe(32)
