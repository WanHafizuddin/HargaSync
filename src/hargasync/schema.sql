-- HargaSync schema. Money columns are integer sen. Dates are ISO-8601 text.

CREATE TABLE IF NOT EXISTS shops (
    id INTEGER PRIMARY KEY,
    name TEXT NOT NULL,
    district TEXT NOT NULL,
    retail_level TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS users (
    id INTEGER PRIMARY KEY,
    username TEXT NOT NULL UNIQUE,
    password_hash TEXT NOT NULL,
    display_name TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS memberships (
    user_id INTEGER NOT NULL REFERENCES users(id),
    shop_id INTEGER NOT NULL REFERENCES shops(id),
    role TEXT NOT NULL CHECK (role IN ('owner', 'staff', 'auditor')),
    PRIMARY KEY (user_id, shop_id)
);

CREATE TABLE IF NOT EXISTS products (
    id INTEGER PRIMARY KEY,
    shop_id INTEGER NOT NULL REFERENCES shops(id),
    sku TEXT NOT NULL,
    name_bm TEXT NOT NULL,
    unit TEXT NOT NULL,
    cost_sen INTEGER NOT NULL CHECK (cost_sen >= 0),
    price_sen INTEGER CHECK (price_sen IS NULL OR price_sen > 0),
    target_margin TEXT NOT NULL,
    controlled_item_code TEXT,
    version INTEGER NOT NULL DEFAULT 1,
    UNIQUE (shop_id, sku)
);

CREATE TABLE IF NOT EXISTS product_aliases (
    id INTEGER PRIMARY KEY,
    shop_id INTEGER NOT NULL REFERENCES shops(id),
    product_id INTEGER NOT NULL REFERENCES products(id),
    alias_norm TEXT NOT NULL,
    unit_norm TEXT NOT NULL,
    pack_size INTEGER NOT NULL DEFAULT 1 CHECK (pack_size >= 1),
    UNIQUE (shop_id, alias_norm, unit_norm)
);

-- Reference ceilings. 'demo' rows are fictional fixtures and must be labelled as such.
CREATE TABLE IF NOT EXISTS price_limits (
    id INTEGER PRIMARY KEY,
    item_code TEXT NOT NULL,
    item_name TEXT NOT NULL,
    unit TEXT NOT NULL,
    district TEXT NOT NULL,
    retail_level TEXT NOT NULL,
    max_price_sen INTEGER NOT NULL CHECK (max_price_sen > 0),
    valid_from TEXT NOT NULL,
    valid_to TEXT NOT NULL,
    verification TEXT NOT NULL CHECK (verification IN ('verified', 'demo')),
    source_ref TEXT NOT NULL,
    notes TEXT
);

CREATE TABLE IF NOT EXISTS invoices (
    id INTEGER PRIMARY KEY,
    shop_id INTEGER NOT NULL REFERENCES shops(id),
    uploaded_by INTEGER NOT NULL REFERENCES users(id),
    supplier_name TEXT NOT NULL DEFAULT '',
    invoice_date TEXT,
    image_path TEXT,
    image_mime TEXT,
    status TEXT NOT NULL CHECK (status IN ('review', 'manual', 'proposed')),
    extraction_source TEXT NOT NULL CHECK (extraction_source IN ('runpod', 'fixture', 'manual')),
    extraction_error TEXT,
    created_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS invoice_lines (
    id INTEGER PRIMARY KEY,
    invoice_id INTEGER NOT NULL REFERENCES invoices(id),
    position INTEGER NOT NULL,
    raw_name TEXT NOT NULL,
    raw_unit TEXT NOT NULL,
    qty TEXT NOT NULL,
    unit_cost_sen INTEGER NOT NULL CHECK (unit_cost_sen >= 0),
    product_id INTEGER REFERENCES products(id),
    pack_size INTEGER NOT NULL DEFAULT 1 CHECK (pack_size >= 1),
    match_status TEXT NOT NULL CHECK (match_status IN ('matched', 'uncertain', 'unknown', 'confirmed', 'skipped')),
    match_score REAL NOT NULL DEFAULT 0
);

CREATE TABLE IF NOT EXISTS price_proposals (
    id INTEGER PRIMARY KEY,
    shop_id INTEGER NOT NULL REFERENCES shops(id),
    invoice_id INTEGER NOT NULL REFERENCES invoices(id),
    invoice_line_id INTEGER NOT NULL REFERENCES invoice_lines(id),
    product_id INTEGER NOT NULL REFERENCES products(id),
    base_version INTEGER NOT NULL,
    old_cost_sen INTEGER NOT NULL,
    new_cost_sen INTEGER NOT NULL,
    old_price_sen INTEGER,
    suggested_price_sen INTEGER NOT NULL,
    cap_sen INTEGER,
    limit_id INTEGER REFERENCES price_limits(id),
    proposed_price_sen INTEGER,
    flags TEXT NOT NULL DEFAULT '[]',
    required_role TEXT NOT NULL CHECK (required_role IN ('staff', 'owner')),
    status TEXT NOT NULL CHECK (status IN ('pending', 'blocked', 'approved', 'rejected', 'stale')),
    explanation TEXT NOT NULL DEFAULT '[]',
    decided_by INTEGER REFERENCES users(id),
    decided_at TEXT,
    final_price_sen INTEGER,
    decision_note TEXT,
    created_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS audit_events (
    id INTEGER PRIMARY KEY,
    shop_id INTEGER NOT NULL REFERENCES shops(id),
    actor_user_id INTEGER REFERENCES users(id),
    event_type TEXT NOT NULL,
    entity_type TEXT NOT NULL,
    entity_id INTEGER,
    details TEXT NOT NULL DEFAULT '{}',
    created_at TEXT NOT NULL
);

CREATE TRIGGER IF NOT EXISTS audit_events_no_update
BEFORE UPDATE ON audit_events
BEGIN
    SELECT RAISE(ABORT, 'audit_events is append-only');
END;

CREATE TRIGGER IF NOT EXISTS audit_events_no_delete
BEFORE DELETE ON audit_events
BEGIN
    SELECT RAISE(ABORT, 'audit_events is append-only');
END;
