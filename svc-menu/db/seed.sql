-- Catálogo de ejemplo para desarrollo y demostración; ejecutar después del esquema.
-- No reemplaza productos existentes, aunque se repita manualmente.
BEGIN;
LOCK TABLE products IN SHARE ROW EXCLUSIVE MODE;

INSERT INTO products (id, sku, name, description, category, price_cents, available)
VALUES
    (1, 'CAFE-AMERICANO', 'Café americano', 'Espresso diluido con agua caliente.', 'bebidas-calientes', 3500, TRUE),
    (2, 'CAFE-ESPRESSO', 'Espresso', 'Extracción doble de café.', 'bebidas-calientes', 3200, TRUE),
    (3, 'CAFE-LATTE', 'Latte', 'Espresso con leche vaporizada.', 'bebidas-calientes', 5500, TRUE),
    (4, 'CAFE-CAPPUCCINO', 'Cappuccino', 'Espresso, leche y espuma.', 'bebidas-calientes', 5600, TRUE),
    (5, 'CAFE-MOCHA', 'Mocha', 'Espresso con chocolate y leche.', 'bebidas-calientes', 6200, TRUE),
    (6, 'CAFE-COLD-BREW', 'Cold brew', 'Café extraído en frío durante 16 horas.', 'bebidas-frias', 5800, TRUE),
    (7, 'TE-CHAI', 'Chai latte', 'Té especiado con leche vaporizada.', 'bebidas-calientes', 5900, TRUE),
    (8, 'TE-VERDE', 'Té verde', 'Infusión de té verde.', 'bebidas-calientes', 3800, TRUE),
    (9, 'CHOCOLATE', 'Chocolate caliente', 'Chocolate mexicano con leche.', 'bebidas-calientes', 5200, TRUE),
    (10, 'LIMONADA', 'Limonada', 'Limonada natural de la casa.', 'bebidas-frias', 4200, TRUE),
    (11, 'CROISSANT', 'Croissant', 'Croissant de mantequilla horneado diariamente.', 'panaderia', 3900, TRUE),
    (12, 'CONCHA-VANILLA', 'Concha de vainilla', 'Pan dulce tradicional.', 'panaderia', 2800, TRUE),
    (13, 'MUFFIN-CHOC', 'Muffin de chocolate', 'Muffin con chispas de chocolate.', 'panaderia', 4200, TRUE),
    (14, 'BAGEL-QUESO', 'Bagel con queso crema', 'Bagel tostado con queso crema.', 'alimentos', 6500, TRUE),
    (15, 'SANDWICH-PAVO', 'Sándwich de pavo', 'Pavo, queso, lechuga y jitomate.', 'alimentos', 8900, TRUE),
    (16, 'PANINI-CAPRESE', 'Panini caprese', 'Mozzarella, jitomate y pesto.', 'alimentos', 9200, TRUE),
    (17, 'ENSALADA-CESAR', 'Ensalada César', 'Lechuga, parmesano, crutones y aderezo.', 'alimentos', 9800, TRUE),
    (18, 'PAY-LIMON', 'Pay de limón', 'Rebanada de pay de limón.', 'postres', 5900, TRUE),
    (19, 'PASTEL-CHOC', 'Pastel de chocolate', 'Rebanada de pastel de chocolate oscuro.', 'postres', 6800, TRUE),
    (20, 'GALLETAS-AVENA', 'Galletas de avena', 'Dos galletas de avena y pasas.', 'postres', 3600, TRUE)
ON CONFLICT DO NOTHING;

-- Los IDs de demostración son explícitos. Nunca retroceder la secuencia si
-- ya hubo productos con IDs mayores, incluso si después fueron eliminados.
SELECT setval(
    pg_get_serial_sequence('products', 'id'),
    GREATEST((SELECT MAX(id) FROM products), (SELECT last_value FROM products_id_seq)),
    TRUE
);
COMMIT;
