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
- recuperación automática de puntos después de restaurar `svc-lealtad`;
- errores de validación y conflictos;
- métricas HTTP y de negocio;
- persistencia después de reiniciar PostgreSQL.

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
