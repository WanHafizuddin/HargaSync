"""Append-only activity log. Rows cannot be updated or deleted (see schema triggers)."""

import json
import sqlite3

from .db import now_iso


def log_event(
    conn: sqlite3.Connection,
    shop_id: int,
    actor_user_id: int | None,
    event_type: str,
    entity_type: str,
    entity_id: int | None,
    details: dict,
) -> int:
    cur = conn.execute(
        "INSERT INTO audit_events (shop_id, actor_user_id, event_type, entity_type, entity_id, details, created_at)"
        " VALUES (?, ?, ?, ?, ?, ?, ?)",
        (shop_id, actor_user_id, event_type, entity_type, entity_id, json.dumps(details), now_iso()),
    )
    return cur.lastrowid


def list_events(conn: sqlite3.Connection, shop_id: int, limit: int = 200) -> list[dict]:
    rows = conn.execute(
        "SELECT e.*, u.display_name AS actor_name FROM audit_events e"
        " LEFT JOIN users u ON u.id = e.actor_user_id"
        " WHERE e.shop_id = ? ORDER BY e.id DESC LIMIT ?",
        (shop_id, limit),
    ).fetchall()
    events = []
    for row in rows:
        event = dict(row)
        event["details"] = json.loads(event["details"])
        events.append(event)
    return events
