-- Solo esquema; no crea clientes ni pedidos de ejemplo.
BEGIN;

CREATE TABLE IF NOT EXISTS orders (
    id UUID PRIMARY KEY,
    customer_id UUID NOT NULL,
    status VARCHAR(20) NOT NULL CHECK (status = 'confirmed'),
    loyalty_status VARCHAR(20) NOT NULL CHECK (loyalty_status IN ('awarded', 'pending')),
    points_earned INTEGER CHECK (points_earned IS NULL OR points_earned >= 0),
    currency CHAR(3) NOT NULL CHECK (currency = 'MXN'),
    subtotal_cents INTEGER NOT NULL CHECK (subtotal_cents >= 0),
    total_cents INTEGER NOT NULL CHECK (total_cents >= 0),
    idempotency_key VARCHAR(128) NOT NULL UNIQUE,
    request_hash CHAR(64) NOT NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP
);

CREATE INDEX IF NOT EXISTS orders_customer_created_idx
    ON orders (customer_id, created_at DESC);

CREATE INDEX IF NOT EXISTS orders_loyalty_pending_idx
    ON orders (created_at, id)
    WHERE loyalty_status = 'pending';

CREATE TABLE IF NOT EXISTS order_items (
    order_id UUID NOT NULL REFERENCES orders(id) ON DELETE CASCADE,
    position SMALLINT NOT NULL CHECK (position > 0),
    product_id INTEGER NOT NULL CHECK (product_id > 0),
    sku VARCHAR(32) NOT NULL,
    product_name VARCHAR(100) NOT NULL,
    quantity INTEGER NOT NULL CHECK (quantity BETWEEN 1 AND 20),
    unit_price_cents INTEGER NOT NULL CHECK (unit_price_cents >= 0),
    line_total_cents INTEGER NOT NULL CHECK (line_total_cents >= 0),
    PRIMARY KEY (order_id, position),
    UNIQUE (order_id, product_id)
);

COMMIT;
