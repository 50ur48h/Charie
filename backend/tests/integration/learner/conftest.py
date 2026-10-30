"""Fixtures for learning-step tests on real customer databases (P07.6).

`shop_db` builds a fresh `charie_test_shop` database with a small shop
schema behind a read-only login, plus its connected source row.
`practice_source` points a source row at the practice database. The
throwaway app database still comes from the root `db` fixture, and the
practice data itself is never written.
"""

from urllib.parse import urlparse

import pytest
from cryptography.fernet import Fernet
from sqlalchemy import create_engine, text

from charie.shared.config import get_settings
from charie.shared.connectors.postgres import PostgresConnector
from charie.shared.crypto import encrypt_text
from charie.shared.tables.sources import DataSource

SHOP_DB = "charie_test_shop"
SHOP_ROLE = "charie_shop_test"
SHOP_PASSWORD = "test-shop-password"


def _server_parts():
    """The Postgres server behind `DATABASE_URL`, on the `postgres` database."""
    import os

    parts = urlparse(os.environ["DATABASE_URL"])
    return {
        "host": parts.hostname or "localhost",
        "port": parts.port or 5432,
        "username": parts.username or "",
        "password": parts.password or "",
    }


def _server_engine(database: str):
    parts = _server_parts()
    url = (
        f"postgresql+psycopg://{parts['username']}:{parts['password']}"
        f"@{parts['host']}:{parts['port']}/{database}"
    )
    return create_engine(url, isolation_level="AUTOCOMMIT")


@pytest.fixture()
def shop_enc_key(monkeypatch):
    """A fresh encryption key, never the real one."""
    monkeypatch.setenv("CHARIE_ENCRYPTION_KEY", Fernet.generate_key().decode("utf-8"))
    get_settings.cache_clear()
    yield
    get_settings.cache_clear()


_SHOP_DDL = """
CREATE SCHEMA shop;
CREATE TABLE shop.stores (id integer PRIMARY KEY, name text, city text, city_id integer);
CREATE TABLE shop.cities (id integer PRIMARY KEY, name text);
CREATE TABLE shop.orders (id integer PRIMARY KEY, store_id integer REFERENCES shop.stores (id),
  created_at timestamp, status text, total numeric(10, 2), coupon_code text);
CREATE TABLE shop.order_lines (id integer PRIMARY KEY, order_id integer REFERENCES shop.orders (id),
  item text, qty integer, price numeric(10, 2));
CREATE TABLE shop.order_notes (order_id integer PRIMARY KEY REFERENCES shop.orders (id), note text);
CREATE TABLE shop.coupons (code text PRIMARY KEY, expires_on date);
COMMENT ON TABLE shop.orders IS 'One row per customer order.';
INSERT INTO shop.cities (id, name) VALUES (1, 'Austin'), (2, 'Dallas');
INSERT INTO shop.stores (id, name, city, city_id) VALUES
  (1, 'Downtown', 'Austin', 1), (2, 'Riverside', 'Austin', 7), (3, 'Hilltop', 'Dallas', 8);
INSERT INTO shop.coupons (code, expires_on) VALUES
  ('SAVE10', '2027-01-01'), ('SAVE20', '2027-01-01'), ('WELCOME', '2027-01-01'),
  ('FALL5', '2027-01-01'), ('LUNCH', '2027-01-01'), ('WEEKEND', '2027-01-01'),
  ('LOYAL', '2027-01-01'), ('FIRST', '2027-01-01'), ('HOLIDAY', '2027-01-01');
INSERT INTO shop.orders (id, store_id, created_at, status, total, coupon_code) VALUES
  (1, 1, '2025-01-05 12:30', 'delivered', 42.50, 'SAVE10'),
  (2, 1, '2025-01-12 18:05', 'delivered', 31.00, 'WELCOME'),
  (3, 2, '2025-01-25 13:15', 'delivered', 55.75, 'SAVE20'),
  (4, 2, '2025-02-02 19:45', 'delivered', 28.25, 'FALL5'),
  (5, 3, '2025-02-14 12:00', 'delivered', 63.00, 'LUNCH'),
  (6, 1, '2025-02-20 20:30', 'delivered', 47.50, 'WEEKEND'),
  (7, 3, '2025-03-03 13:45', 'delivered', 39.99, 'LOYAL'),
  (8, 2, '2025-03-11 18:20', 'delivered', 52.25, 'FIRST'),
  (9, 1, '2025-03-22 12:10', 'delivered', 44.00, 'HOLIDAY'),
  (10, 3, '2025-03-28 19:00', 'delivered', 58.40, 'OLD0124');
INSERT INTO shop.order_lines (id, order_id, item, qty, price) VALUES
  (1, 1, 'Margherita', 1, 18.00), (2, 1, 'Cola', 2, 3.50), (3, 2, 'Pepperoni', 1, 20.00),
  (4, 2, 'Garlic bread', 1, 6.00), (5, 3, 'Veggie', 2, 19.00), (6, 3, 'Cola', 1, 3.50),
  (7, 4, 'Margherita', 1, 18.00), (8, 5, 'Pepperoni', 2, 20.00), (9, 5, 'Salad', 1, 9.00),
  (10, 6, 'Veggie', 1, 19.00), (11, 6, 'Cola', 2, 3.50), (12, 7, 'Margherita', 2, 18.00),
  (13, 8, 'Pepperoni', 1, 20.00), (14, 8, 'Garlic bread', 2, 6.00), (15, 9, 'Salad', 2, 9.00),
  (16, 9, 'Cola', 1, 3.50), (17, 10, 'Veggie', 2, 19.00), (18, 10, 'Garlic bread', 1, 6.00),
  (19, 1, 'Salad', 1, 9.00), (20, 2, 'Cola', 1, 3.50), (21, 4, 'Cola', 1, 3.50),
  (22, 5, 'Cola', 1, 3.50), (23, 7, 'Cola', 1, 3.50), (24, 8, 'Cola', 1, 3.50),
  (25, 10, 'Cola', 1, 3.50);
INSERT INTO shop.order_notes (order_id, note) VALUES
  (1, 'Leave at the door.'), (5, 'Extra napkins.'), (9, 'Call on arrival.');
CREATE VIEW shop.daily_sales AS
  SELECT created_at::date AS day, store_id, sum(total) AS sales
  FROM shop.orders GROUP BY 1, 2;
"""


@pytest.fixture()
def shop_db(db_session, shop_enc_key):
    """A fresh customer database plus its connected source row.

    Yields the read-only connector info and an owner engine for setup
    tweaks (like dropping a table); everything is dropped afterwards.
    """
    server = _server_engine("postgres")
    with server.connect() as conn:
        conn.execute(text(f'DROP DATABASE IF EXISTS "{SHOP_DB}" WITH (FORCE)'))
        conn.execute(text(f'CREATE DATABASE "{SHOP_DB}"'))
    owner = _server_engine(SHOP_DB)
    with owner.begin() as conn:
        for statement in [part for part in _SHOP_DDL.split(";") if part.strip()]:
            conn.execute(text(statement))
        conn.execute(text(f'DROP ROLE IF EXISTS "{SHOP_ROLE}"'))
        conn.execute(text(f"CREATE ROLE \"{SHOP_ROLE}\" LOGIN PASSWORD '{SHOP_PASSWORD}'"))
        conn.execute(text(f'GRANT CONNECT ON DATABASE "{SHOP_DB}" TO "{SHOP_ROLE}"'))
        conn.execute(text(f'GRANT USAGE ON SCHEMA shop TO "{SHOP_ROLE}"'))
        conn.execute(text(f'GRANT SELECT ON ALL TABLES IN SCHEMA shop TO "{SHOP_ROLE}"'))
    parts = _server_parts()
    connector = PostgresConnector(parts["host"], parts["port"], SHOP_DB, SHOP_ROLE, SHOP_PASSWORD)
    row = DataSource(
        kind="postgres",
        name="shop database",
        host=parts["host"],
        port=parts["port"],
        database=SHOP_DB,
        username=SHOP_ROLE,
        password_encrypted=encrypt_text(SHOP_PASSWORD),
        status="connected",
        read_only_ok=connector.check_read_only(),
    )
    db_session.add(row)
    db_session.commit()
    yield {"connector": connector, "owner": owner, "source": row}
    owner.dispose()
    with server.connect() as conn:
        conn.execute(text(f'DROP DATABASE IF EXISTS "{SHOP_DB}" WITH (FORCE)'))
        conn.execute(text(f'DROP ROLE IF EXISTS "{SHOP_ROLE}"'))
    server.dispose()


@pytest.fixture()
def practice_source(db_session, shop_enc_key):
    """A connected source row for `PRACTICE_DB_URL` (practice-marked tests)."""
    raw = get_settings().practice_db_url
    if not raw:
        pytest.fail("PRACTICE_DB_URL isn't set. Add it to the project .env.")
    parts = urlparse(raw)
    connector = PostgresConnector(
        parts.hostname or "localhost",
        parts.port or 5432,
        parts.path.lstrip("/"),
        parts.username or "",
        parts.password or "",
    )
    row = DataSource(
        kind="postgres",
        name="practice database",
        host=parts.hostname or "localhost",
        port=parts.port or 5432,
        database=parts.path.lstrip("/"),
        username=parts.username or "",
        password_encrypted=encrypt_text(parts.password or ""),
        status="connected",
        read_only_ok=connector.check_read_only(),
    )
    db_session.add(row)
    db_session.commit()
    yield {"connector": connector, "source": row}
