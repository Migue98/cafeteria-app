# Pruebas integrales

La suite E2E verifica el frontend, los tres servicios y PostgreSQL reales dentro de Compose. No usa dobles ni repositorios en memoria.

## Alcance

- salud y correlación mediante `X-Request-ID`;
- correlación de una compra en los logs de los cuatro servicios, con `trace_id`,
  spans propios y enlace al span padre;
- catálogo, precios y disponibilidad reales;
- compra completa `menú → pedido → puntos`;
- compra desde la interfaz HTML y consulta posterior del historial;
- consulta posterior del pedido y saldo;
- idempotencia sin duplicar pedidos ni puntos;
- compras y acreditaciones simultáneas, doble envío del checkout, claves alternas
  reservadas, migración idempotente y saldo contrastado con PostgreSQL;
- recuperación automática de puntos después de restaurar `svc-lealtad`;
- historial accesible sin lealtad y actualización de los fragmentos de puntos,
  sin repetir pedidos ni acreditaciones;
- errores de validación y conflictos;
- métricas HTTP y de negocio;
- persistencia después de reiniciar PostgreSQL;
- fallas reales de menú, pedidos y PostgreSQL; timeouts de lectura al pausar
  menú o lealtad; recuperación conservando carrito, pedidos y saldo;
- protección CSRF activa en formularios y HTMX, rechazo de otros orígenes y
  hosts, CSP y carga de HTMX sin CDN.

## Ejecución

Desde la raíz del repositorio:

```powershell
python -m pip install -r tests/requirements.txt
python scripts/run_e2e.py
```

El ejecutor valida primero los contratos OpenAPI, levanta el proyecto aislado `cafeteria-e2e` en los puertos `18000` a `18003`, ejecuta `pytest` y finalmente elimina sus contenedores, red y volumen. No toca el Compose local normal.

Para conservar el entorno cuando falle una prueba:

```powershell
$env:KEEP_E2E_STACK = "1"
python scripts/run_e2e.py
```

Para usar Podman:

```powershell
$env:CONTAINER_ENGINE = "podman"
python scripts/run_e2e.py
```

## Contrato común de observabilidad

Los cuatro workflows ejecutan `tests/observability` con el entorno de cada
servicio. Desde el directorio del servicio, con sus dependencias instaladas:

```powershell
python -m pytest tests ../tests/observability -p no:cacheprovider
```

Esta suite comprueba trazas, logs de errores, aislamiento concurrente y paridad
de la implementación común. Consulta la
[guía de logs y correlación](../docs/application-observability.md).

## Concurrencia y ejecución continua

`tests/e2e/test_concurrency.py` sincroniza las solicitudes y comprueba pedidos,
movimientos y saldo persistidos. La [guía de concurrencia](../docs/concurrency-and-idempotency.md)
describe los casos y la migración de claves de lealtad.

El workflow `Integrated E2E` ejecuta el mismo flujo Compose en pushes a `main` y
Pull Requests que afecten a la aplicación. Las pruebas se mantienen en serie a
nivel de escenario: no uses `pytest-xdist` sobre este proyecto compartido.

## Seguridad web

El cliente de navegador HTTP abre primero el menú, conserva la cookie de sesión
y extrae el token CSRF que se incluye en los formularios. No se desactiva la
protección para ejecutar pruebas. Las peticiones crudas de los casos negativos
omiten o falsifican el token/origen deliberadamente.

`frontend/tests/test_security.py` cubre también la configuración de producción,
cookies `Secure`/`HttpOnly`, cabeceras en errores, aislamiento entre sesiones,
límite de cuerpo y el hash del HTMX vendorizado. La suite E2E comprueba el flujo
real con las mismas defensas. Consulta [Seguridad web](../docs/web-security.md).
