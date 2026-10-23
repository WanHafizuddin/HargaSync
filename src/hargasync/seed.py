"""Fictional demo data: two shops, four users, a small BM catalogue and demo price ceilings."""

import sqlite3
from datetime import date, timedelta

from .auth import hash_password
from .db import transaction
from .money import today_my

DEMO_CEILING_SOURCE = "Fictional demo fixture, not KPDN or gazette data"

USERS = [
    # username, display name, shop index, role
    ("owner_ali", "Ali bin Hassan", 0, "owner"),
    ("staff_mei", "Mei Ling", 0, "staff"),
    ("auditor_raj", "Raj Kumar", 0, "auditor"),
    ("owner_siti", "Siti Aminah", 1, "owner"),
]

SHOPS = [
    ("Kedai Runcit Pak Ali (DEMO)", "Petaling", "runcit"),
    ("Mini Market Seri Kembangan (DEMO)", "Petaling", "runcit"),
]

# sku, name_bm, unit, cost_sen, price_sen, target_margin, controlled_item_code
PRODUCTS_SHOP_A = [
    ("GULA-1KG", "Gula Pasir Kasar 1kg", "pek", 270, 300, "0.08", None),
    ("MINYAK-5KG", "Minyak Masak Botol 5kg", "botol", 2700, 3200, "0.15", None),
    ("SUSU-500G", "Susu Pekat Manis 500g", "tin", 310, 380, "0.15", None),
    ("TEPUNG-1KG", "Tepung Gandum 1kg", "pek", 150, 190, "0.18", None),
    ("AYAM-KG", "Ayam Standard (sekilo)", "kg", 820, 920, "0.12", "ayam_standard"),
    ("TELUR-A30", "Telur Gred A 30 biji", "papan", 1250, 1450, "0.10", "telur_gred_a"),
    ("KICAP-340", "Kicap Masin 340ml", "botol", 380, 450, "0.15", None),
    ("BERAS-5KG", "Beras Wangi 5kg", "pek", 1990, 2390, "0.15", None),
]

PRODUCTS_SHOP_B = [
    ("GULA-1KG", "Gula Pasir Kasar 1kg", "pek", 265, 300, "0.10", None),
    ("ROTI-400G", "Roti Putih 400g", "bungkus", 280, 350, "0.18", None),
]


def _limits(today: date) -> list[tuple]:
    d = lambda days: (today + timedelta(days=days)).isoformat()
    return [
        # item_code, item_name, unit, district, retail_level, max_price_sen, valid_from, valid_to, verification, source_ref
        ("ayam_standard", "Ayam standard", "kg", "Petaling", "runcit", 940, d(-14), d(45), "demo", DEMO_CEILING_SOURCE),
        ("telur_gred_a", "Telur gred A", "papan", "Petaling", "runcit", 1350, d(-300), d(-200), "demo", DEMO_CEILING_SOURCE),
        ("telur_gred_a", "Telur gred A", "papan", "Klang", "runcit", 1400, d(-14), d(45), "demo", DEMO_CEILING_SOURCE),
    ]


def is_empty(conn: sqlite3.Connection) -> bool:
    return conn.execute("SELECT COUNT(*) FROM shops").fetchone()[0] == 0


def seed_demo(conn: sqlite3.Connection, password: str, today: date | None = None) -> None:
    today = today or today_my()
    password_hash = hash_password(password)  # one hash for all demo accounts: same demo password
    with transaction(conn):
        shop_ids = [
            conn.execute("INSERT INTO shops (name, district, retail_level) VALUES (?, ?, ?)", shop).lastrowid
            for shop in SHOPS
        ]
        for username, display_name, shop_index, role in USERS:
            user_id = conn.execute(
                "INSERT INTO users (username, password_hash, display_name) VALUES (?, ?, ?)",
                (username, password_hash, display_name),
            ).lastrowid
            conn.execute(
                "INSERT INTO memberships (user_id, shop_id, role) VALUES (?, ?, ?)",
                (user_id, shop_ids[shop_index], role),
            )
        for shop_id, products in zip(shop_ids, (PRODUCTS_SHOP_A, PRODUCTS_SHOP_B)):
            conn.executemany(
                "INSERT INTO products (shop_id, sku, name_bm, unit, cost_sen, price_sen, target_margin,"
                " controlled_item_code) VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
                [(shop_id, *product) for product in products],
            )
        conn.executemany(
            "INSERT INTO price_limits (item_code, item_name, unit, district, retail_level, max_price_sen,"
            " valid_from, valid_to, verification, source_ref) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
            _limits(today),
        )
