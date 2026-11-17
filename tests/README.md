# Pruebas integrales

La suite E2E verifica los tres servicios y PostgreSQL reales dentro de Compose. No usa dobles ni repositorios en memoria.

## Alcance

- salud y correlación mediante `X-Request-ID`;
- catálogo, precios y disponibilidad reales;
- compra completa `menú → pedido → puntos`;
- consulta posterior del pedido y saldo;
- idempotencia sin duplicar pedidos ni puntos;
- errores de validación y conflictos;
- métricas HTTP y de negocio;
- persistencia después de reiniciar PostgreSQL.

## Ejecución

Desde la raíz del repositorio:

```powershell
python -m pip install -r tests/requirements.txt
python scripts/run_e2e.py
```

El ejecutor valida primero los contratos OpenAPI, levanta el proyecto aislado `cafeteria-e2e` en los puertos `18001`, `18002` y `18003`, ejecuta `pytest` y finalmente elimina sus contenedores, red y volumen. No toca el Compose local normal.

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
