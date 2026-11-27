-- Solo esquema; no crea saldos ni movimientos de ejemplo.
BEGIN;

CREATE TABLE IF NOT EXISTS loyalty_accounts (
    customer_id UUID PRIMARY KEY,
    balance INTEGER NOT NULL DEFAULT 0 CHECK (balance >= 0),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS loyalty_movements (
    movement_id UUID PRIMARY KEY,
    order_id UUID NOT NULL UNIQUE,
    customer_id UUID NOT NULL REFERENCES loyalty_accounts(customer_id),
    amount_cents INTEGER NOT NULL CHECK (amount_cents >= 1),
    points_earned INTEGER NOT NULL CHECK (points_earned >= 0),
    balance_after INTEGER NOT NULL CHECK (balance_after >= 0),
    rule VARCHAR(40) NOT NULL CHECK (rule = '1-point-per-10-mxn-v1'),
    idempotency_key VARCHAR(128) NOT NULL UNIQUE,
    request_hash CHAR(64) NOT NULL,
    occurred_at TIMESTAMPTZ,
    awarded_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP
);

CREATE INDEX IF NOT EXISTS loyalty_movements_customer_awarded_idx
    ON loyalty_movements (customer_id, awarded_at DESC);

-- Una acreditación puede repetirse con claves distintas; todas quedan reservadas.
CREATE TABLE IF NOT EXISTS loyalty_request_keys (
    idempotency_key VARCHAR(128) PRIMARY KEY,
    movement_id UUID NOT NULL REFERENCES loyalty_movements(movement_id)
);

COMMIT;
