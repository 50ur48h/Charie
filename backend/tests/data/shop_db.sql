-- The shop fixture database (P09.1): a tiny restaurant group in Nov-Dec 2025.
-- Hand-made rows, so every test number can be checked by hand. Times are
-- written with their business time zone; created_on/created_local mirror it.

CREATE SCHEMA IF NOT EXISTS shop;

CREATE TABLE shop.restaurants (
    id integer PRIMARY KEY,
    name text NOT NULL,
    city text NOT NULL,
    is_test boolean NOT NULL
);

CREATE TABLE shop.cuisines (
    id integer PRIMARY KEY,
    name text NOT NULL
);

CREATE TABLE shop.restaurant_cuisines (
    restaurant_id integer NOT NULL REFERENCES shop.restaurants (id),
    cuisine_id integer NOT NULL REFERENCES shop.cuisines (id)
);

CREATE TABLE shop.orders (
    id integer PRIMARY KEY,
    restaurant_id integer NOT NULL REFERENCES shop.restaurants (id),
    created_at timestamptz NOT NULL,
    created_on date NOT NULL,
    created_local timestamp NOT NULL,
    status text NOT NULL,
    total_amount numeric(10, 2) NOT NULL,
    tax_amount numeric(10, 2) NOT NULL,
    delivery_fee numeric(10, 2) NOT NULL
);

CREATE TABLE shop.order_items (
    id integer PRIMARY KEY,
    order_id integer NOT NULL REFERENCES shop.orders (id),
    name text NOT NULL,
    quantity integer NOT NULL,
    price numeric(10, 2) NOT NULL
);

CREATE TABLE shop.ingredient_usage (
    id integer PRIMARY KEY,
    order_item_id integer NOT NULL REFERENCES shop.order_items (id),
    ingredient text NOT NULL,
    grams integer NOT NULL
);

INSERT INTO shop.restaurants (id, name, city, is_test) VALUES
    (1, 'Bella Forno', 'Austin', false),
    (2, 'Forno North', 'Dallas', false),
    (3, 'Test Kitchen', 'Austin', true),
    (4, 'Lone Star Tacos', 'Chicago', false);

INSERT INTO shop.cuisines (id, name) VALUES
    (1, 'Italian'),
    (2, 'Mexican');

INSERT INTO shop.restaurant_cuisines (restaurant_id, cuisine_id) VALUES
    (1, 1),
    (2, 1),
    (4, 1),
    (4, 2);

INSERT INTO shop.orders
    (id, restaurant_id, created_at, created_on, created_local,
     status, total_amount, tax_amount, delivery_fee)
VALUES
    (1, 1, TIMESTAMPTZ '2025-11-03 12:00:00 America/Chicago', DATE '2025-11-03',
     TIMESTAMP '2025-11-03 12:00:00', 'completed', 40.00, 3.00, 2.00),
    (2, 1, TIMESTAMPTZ '2025-11-10 18:30:00 America/Chicago', DATE '2025-11-10',
     TIMESTAMP '2025-11-10 18:30:00', 'completed', 60.00, 4.50, 0.00),
    (3, 2, TIMESTAMPTZ '2025-11-15 12:15:00 America/Chicago', DATE '2025-11-15',
     TIMESTAMP '2025-11-15 12:15:00', 'completed', 25.00, 2.00, 3.00),
    (4, 2, TIMESTAMPTZ '2025-11-20 19:00:00 America/Chicago', DATE '2025-11-20',
     TIMESTAMP '2025-11-20 19:00:00', 'cancelled', 100.00, 8.00, 5.00),
    (5, 3, TIMESTAMPTZ '2025-11-25 12:00:00 America/Chicago', DATE '2025-11-25',
     TIMESTAMP '2025-11-25 12:00:00', 'completed', 10.00, 1.00, 1.00),
    (6, 4, TIMESTAMPTZ '2025-11-30 23:30:00 America/Chicago', DATE '2025-11-30',
     TIMESTAMP '2025-11-30 23:30:00', 'completed', 33.00, 2.50, 4.00),
    (7, 1, TIMESTAMPTZ '2025-12-02 12:00:00 America/Chicago', DATE '2025-12-02',
     TIMESTAMP '2025-12-02 12:00:00', 'completed', 50.00, 4.00, 2.00),
    (8, 4, TIMESTAMPTZ '2025-12-10 18:00:00 America/Chicago', DATE '2025-12-10',
     TIMESTAMP '2025-12-10 18:00:00', 'completed', 22.00, 1.75, 3.00),
    (9, 2, TIMESTAMPTZ '2025-12-20 12:30:00 America/Chicago', DATE '2025-12-20',
     TIMESTAMP '2025-12-20 12:30:00', 'completed', 35.00, 2.80, 0.00),
    (10, 1, TIMESTAMPTZ '2025-12-15 13:00:00 America/Chicago', DATE '2025-12-15',
     TIMESTAMP '2025-12-15 13:00:00', 'completed', 44.00, 3.50, 2.50),
    (11, 4, TIMESTAMPTZ '2025-12-22 19:30:00 America/Chicago', DATE '2025-12-22',
     TIMESTAMP '2025-12-22 19:30:00', 'completed', 28.00, 2.25, 3.50),
    (12, 3, TIMESTAMPTZ '2025-12-28 12:00:00 America/Chicago', DATE '2025-12-28',
     TIMESTAMP '2025-12-28 12:00:00', 'completed', 12.00, 1.00, 1.00);

INSERT INTO shop.order_items (id, order_id, name, quantity, price) VALUES
    (1, 1, 'Margherita', 2, 20.00),
    (2, 2, 'Lasagna', 1, 60.00),
    (3, 7, 'Margherita', 1, 50.00);

INSERT INTO shop.ingredient_usage (id, order_item_id, ingredient, grams) VALUES
    (1, 1, 'flour', 200),
    (2, 1, 'cheese', 100),
    (3, 2, 'cheese', 150);
