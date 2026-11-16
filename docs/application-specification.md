# Especificación de la aplicación

## Flujo funcional obligatorio

1. Consultar un menú con al menos 20 productos.
2. Agregar productos a un carrito.
3. Generar y consultar un pedido.
4. Persistir el pedido en PostgreSQL.
5. Sumar puntos al cliente mediante el servicio de lealtad.

## Microservicios

| Servicio | Responsabilidad | Datos principales |
|---|---|---|
| `frontend` | Interfaz de menú, carrito, compra y puntos | Sesión o identificador de cliente; no es dueño de datos de negocio. |
| `svc-menu` | Productos, precios y disponibilidad | Productos del menú. |
| `svc-pedidos` | Carrito confirmado, pedidos y totales | Pedidos y partidas. |
| `svc-lealtad` | Puntos ganados y saldo por cliente | Clientes y movimientos de puntos. |

Cada servicio tendrá su propio Containerfile, imagen de Docker Hub, Deployment y Service. PostgreSQL no cuenta como uno de los cuatro microservicios.

## Contrato operativo común

Todos los backends expondrán:

```text
GET /health   # liveness y readiness
GET /metrics  # formato Prometheus
```

También tendrán logs JSON en stdout con `timestamp`, `level`, `service`, `message`, `trace_id` y `span_id`. Los errores HTTP no incluirán trazas internas ni credenciales.

## Métricas

Todos los servicios expondrán peticiones por código HTTP y un histograma de latencia. Los servicios de pedidos y lealtad serán dueños de sus respectivas métricas de negocio:

```text
http_requests_total
http_request_duration_seconds
cafe_orders_total
cafe_order_value_cents_total
cafe_loyalty_points_total
```

Los pedidos por minuto se calcularán en Prometheus a partir de `cafe_orders_total`.

## Réplicas y recursos

- `frontend`: mínimo dos réplicas.
- `svc-pedidos`: mínimo dos réplicas.
- `svc-menu` y `svc-lealtad`: una réplica inicial, escalables.
- Todos los contenedores tendrán `requests` y `limits`.
- Configuración no sensible en ConfigMap y credenciales en Secret.

## Persistencia

PostgreSQL se desplegará como StatefulSet con `volumeClaimTemplates`. Un Job o script idempotente creará los esquemas y cargará al menos 20 productos. La prueba de aceptación consiste en crear un pedido, eliminar el pod de PostgreSQL y comprobar que el pedido continúa disponible.

## Fuera del alcance inicial

- Pagos reales.
- Registro público de usuarios y recuperación de contraseñas.
- Aplicación móvil.
- Procesamiento asíncrono o un broker de mensajes.
- Bases de datos separadas físicamente por servicio.

Estos elementos solo se añadirán si el núcleo evaluable está completo.

## Contratos versionados

Los contratos fuente están en [`docs/openapi/`](openapi/README.md). Las rutas de negocio usan el prefijo `/api/v1`; `/health` y `/metrics` permanecen sin versión por ser endpoints operativos.
