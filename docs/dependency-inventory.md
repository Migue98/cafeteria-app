# Inventario de dependencias y herramientas

Fecha de captura: **2026-11-20**.

Este documento es la línea base del paso 1 de la fase de construcción
reproducible. Registra lo declarado en Git y lo realmente instalado al momento
de la captura. **Todavía no define las versiones que se fijarán**; esa decisión
corresponde a los siguientes pasos.

## Alcance revisado

- `frontend`
- `svc-menu`
- `svc-pedidos`
- `svc-lealtad`
- pruebas E2E de la raíz
- Containerfiles e imágenes base
- Compose y PostgreSQL
- workflows de GitHub Actions
- herramientas locales de construcción

## Restricciones declaradas en Git

| Dependencia | Restricción actual | Servicios que la declaran |
|---|---|---|
| FastAPI | `>=0.115,<1.0` | Los cuatro servicios |
| HTTPX | `>=0.28,<1.0` | Frontend y pedidos en runtime; menú y lealtad para pruebas |
| ItsDangerous | `>=2.2,<3.0` | Frontend |
| Jinja2 | `>=3.1,<4.0` | Frontend |
| Prometheus Client | `>=0.21,<1.0` | Los cuatro servicios |
| Psycopg con binario | `>=3.2,<4.0` | Menú, pedidos y lealtad |
| Uvicorn Standard | `>=0.34,<1.0` | Los cuatro servicios |
| Pytest | `>=8.3,<10.0` | Los cuatro servicios y E2E |
| Ruff | `>=0.9,<1.0` | Los cuatro servicios |

Los archivos `requirements-dev.txt` incluyen el archivo de runtime mediante
`-r requirements.txt`. Actualmente no existen archivos lock ni hashes.

## Versiones realmente instaladas

### Frontend

| Componente | Entorno local | Imagen construida |
|---|---:|---:|
| Python | 3.14.3 | 3.13.18 |
| FastAPI | 0.165.0 | 0.165.0 |
| HTTPX | 0.28.1 | 0.28.1 |
| ItsDangerous | 2.2.0 | 2.2.0 |
| Jinja2 | 3.1.6 | 3.1.6 |
| Prometheus Client | 0.26.0 | 0.26.0 |
| Uvicorn | 0.54.0 | 0.54.0 |
| Pytest | 9.2.0 | No se instala en producción |
| Ruff | 0.17.6 | No se instala en producción |

### Backends

Los tres backends tienen actualmente el mismo conjunto principal de versiones
en sus entornos locales y en las imágenes construidas.

| Componente | Local | Imagen construida | Observación |
|---|---:|---:|---|
| Python | 3.13.1 | 3.13.18 | La imagen resuelve el parche más reciente de la etiqueta |
| FastAPI | 0.163.1 | 0.163.1 | Distinto del frontend |
| HTTPX | 0.28.1 | 0.28.1 en pedidos | En menú y lealtad solo se usa para pruebas |
| Prometheus Client | 0.26.0 | 0.26.0 | Compartido |
| Psycopg | 3.3.9 | 3.3.9 | Menú, pedidos y lealtad |
| Psycopg Binary | 3.3.9 | 3.3.9 | Instalado por el extra `[binary]` |
| Uvicorn | 0.54.0 | 0.54.0 | Compartido |
| Pytest | 9.2.0 | No se instala en producción | Dependencia de desarrollo |
| Ruff | 0.17.5 | No se instala en producción | El frontend local tiene 0.17.6 |

Dependencias transitivas relevantes observadas:

| Servicio | Pydantic | Pydantic Core | Starlette |
|---|---:|---:|---:|
| Frontend local | 2.14.4 | 2.50.5 | 1.10.0 |
| Backends locales | 2.14.3 | 2.50.4 | 1.10.0 |

El entorno Python global de la máquina usa 3.14.3. Las pruebas y comandos deben
seguir ejecutándose desde los entornos virtuales de cada componente.

## Imágenes y runtime de contenedores

| Elemento | Declaración actual | Versión o digest observado |
|---|---|---|
| Base de los cuatro servicios | `python:3.13-slim` | Python 3.13.18; digest remoto `sha256:e48f59cdba69a3cbd9ed2cf0f348d90d45a8d350d98134cf1070bc106ee9ed90` |
| Base de datos | `postgres:16-alpine` | PostgreSQL 16.16 |
| PostgreSQL descargado localmente | `postgres:16-alpine` | `sha256:81e77a4833487b8132fe4b00bedd39dc3f74b8641e387f19312a48f7de218c2e` |
| PostgreSQL remoto al capturar | `postgres:16-alpine` | `sha256:1d5b02d3a9941fbd52437db4107f8c52d6297dac553ca1e5c299ebb3756b4857` |
| Docker Engine y CLI | Instalación local | 28.4.0 |
| Docker Compose | Instalación local | 2.39.2-desktop.1 |

La diferencia entre el digest local y el remoto de PostgreSQL demuestra que la
misma etiqueta puede producir una imagen distinta después de un nuevo pull.

### Imágenes de aplicación construidas localmente

| Imagen | Digest local |
|---|---|
| `cafeteria-app-frontend:latest` | `sha256:99e5bdef49934bda2092dee85a341dc7d03f6fd3ffc6faad79eec0c7c8788b6c` |
| `cafeteria-app-svc-menu:latest` | `sha256:f9fc71aa90328c747351fda2b1e9240db8d3f0ce18ac48504f2ef47ca7bb7c56` |
| `cafeteria-app-svc-pedidos:latest` | `sha256:68e81a7590c3b793aa622b1cfc8eb2ce2cf62b65d148311d9f7801661ef64f73` |
| `cafeteria-app-svc-lealtad:latest` | `sha256:4d192c4454df493ad7ff87fbf3f77dfe8c553bedb8b6e2f69b3d70b04c13178e` |

Estos digests pertenecen a imágenes locales no publicadas y sirven únicamente
como evidencia de la captura. Se sustituirán por referencias del registro
cuando exista el pipeline de construcción.

## Integración continua

Los cuatro workflows declaran:

| Componente | Referencia actual |
|---|---|
| Runner | `ubuntu-latest` |
| Python | `3.13` |
| Checkout | `actions/checkout@v4` |
| Setup Python | `actions/setup-python@v5` |

Las Actions están fijadas a una versión mayor, pero no a un SHA inmutable. El
runner y Python también pueden cambiar de parche sin modificar el repositorio.

## Diferencias detectadas

1. El frontend local usa Python 3.14.3, mientras CI y contenedores usan 3.13.
2. El frontend resolvió FastAPI 0.165.0; los backends conservan 0.163.1.
3. El frontend resolvió Ruff 0.17.6; los backends conservan 0.17.5.
4. Pydantic y Pydantic Core también difieren entre frontend y backends.
5. La etiqueta remota `postgres:16-alpine` cambió después de la descarga local.
6. `python:3.13-slim`, `postgres:16-alpine` y `ubuntu-latest` son referencias móviles.
7. Las imágenes de la aplicación solo contienen etiquetas generadas por Compose;
   todavía no incluyen versión, revisión Git ni URL de origen en formato OCI.
8. Los requisitos expresan rangos amplios y permiten una resolución diferente
   en una instalación limpia.

## Comandos de captura

```powershell
python --version
.\.venv\Scripts\python.exe -m pip list --format=freeze
docker version
docker compose version
docker run --rm --entrypoint python <imagen> --version
docker run --rm --entrypoint python <imagen> -m pip list --format=freeze
docker run --rm --entrypoint postgres postgres:16-alpine --version
docker buildx imagetools inspect <imagen>
```

## Decisiones derivadas

El paso 2 resolvió este inventario en
[`ADR-003 — Dependencias reproducibles`](decisions/ADR-003-reproducible-dependencies.md):

- todo el desarrollo se estandariza en Python 3.13;
- FastAPI 0.165.0 y Ruff 0.17.6 forman la línea base común;
- cada componente declara sus dependencias directas exactas en archivos `.in`;
- los `.txt` serán locks generados con versiones transitivas y hashes;
- imágenes y Actions se fijarán por digest o SHA en sus pasos respectivos.

Los `.txt` existentes se mantuvieron intactos durante el paso 2. En el paso 3
fueron reemplazados por los locks generados y validados; su evidencia se encuentra en
[`Validación de locks`](dependency-lock-validation.md).
