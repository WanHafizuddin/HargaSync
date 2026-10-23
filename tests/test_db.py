import sqlite3
import unittest
from pathlib import Path

from hargasync.audit import list_events, log_event
from hargasync.db import connect, init_db, transaction

TABLES = {
    "shops", "users", "memberships", "products", "product_aliases", "price_limits",
    "invoices", "invoice_lines", "price_proposals", "audit_events",
}


class TestDatabase(unittest.TestCase):
    def setUp(self):
        self.conn = connect(Path(":memory:"))
        init_db(self.conn)
        self.conn.execute("INSERT INTO shops (name, district, retail_level) VALUES ('A', 'Petaling', 'runcit')")

    def test_init_creates_all_tables(self):
        names = {r["name"] for r in self.conn.execute("SELECT name FROM sqlite_master WHERE type='table'")}
        self.assertTrue(TABLES <= names, TABLES - names)

    def test_log_event_round_trip(self):
        event_id = log_event(self.conn, 1, None, "price_approved", "product", 7, {"new_price_sen": 1250})
        events = list_events(self.conn, 1)
        self.assertEqual(events[0]["id"], event_id)
        self.assertEqual(events[0]["details"], {"new_price_sen": 1250})
        self.assertEqual(events[0]["event_type"], "price_approved")

    def test_list_events_is_shop_scoped(self):
        self.conn.execute("INSERT INTO shops (name, district, retail_level) VALUES ('B', 'Klang', 'runcit')")
        log_event(self.conn, 2, None, "x", "product", 1, {})
        self.assertEqual(list_events(self.conn, 1), [])

    def test_audit_update_is_blocked(self):
        log_event(self.conn, 1, None, "x", "product", 1, {})
        with self.assertRaises(sqlite3.DatabaseError):
            self.conn.execute("UPDATE audit_events SET event_type = 'y'")

    def test_audit_delete_is_blocked(self):
        log_event(self.conn, 1, None, "x", "product", 1, {})
        with self.assertRaises(sqlite3.DatabaseError):
            self.conn.execute("DELETE FROM audit_events")

    def test_transaction_rolls_back_on_error(self):
        with self.assertRaises(RuntimeError):
            with transaction(self.conn):
                self.conn.execute("INSERT INTO shops (name, district, retail_level) VALUES ('C', 'X', 'runcit')")
                raise RuntimeError("boom")
        count = self.conn.execute("SELECT COUNT(*) FROM shops").fetchone()[0]
        self.assertEqual(count, 1)


if __name__ == "__main__":
    unittest.main()
