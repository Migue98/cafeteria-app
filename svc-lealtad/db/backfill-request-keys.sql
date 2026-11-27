-- Operación manual para bases antiguas de desarrollo con movimientos sin claves.
-- Requiere haber aplicado init.sql; no modifica movimientos ni saldos.
BEGIN;
INSERT INTO loyalty_request_keys (idempotency_key, movement_id)
SELECT idempotency_key, movement_id FROM loyalty_movements
ON CONFLICT (idempotency_key) DO NOTHING;
COMMIT;
