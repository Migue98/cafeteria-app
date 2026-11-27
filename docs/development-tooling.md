# Herramientas de desarrollo comunes

Los cuatro componentes usan la misma configuración de pytest y heredan una
única política de Ruff. Las dependencias continúan en los archivos
`requirements.in` y sus locks; `pyproject.toml` configura las herramientas.

## Versiones y reglas

| Elemento | Configuración |
|---|---|
| Python | Línea 3.13; `.python-version`, CI y las imágenes fijan 3.13.18. |
| pytest | 9.2.0, fijado en cada lock de desarrollo. |
| Ruff | 0.17.6, fijado en cada lock y requerido por `ruff.toml`. |
| Objetivo de Ruff | `py313`. |
| Longitud de línea | 100 caracteres. |
| Reglas de lint | `E`, `F`, `I`, `UP`, `B`, `SIM`. |
| Imports del proyecto | El paquete `app` se considera código propio. |

La instalación de dependencias desde los locks corrige entornos locales que
conserven una versión anterior de las herramientas. El requisito de versión
de Ruff evita ejecutar accidentalmente otra versión con las mismas reglas.

## Archivos de configuración

```text
ruff.toml                         # Política común y versión requerida
frontend/pyproject.toml           # pytest y extend de Ruff
svc-menu/pyproject.toml           # Misma configuración
svc-pedidos/pyproject.toml         # Misma configuración
svc-lealtad/pyproject.toml         # Misma configuración
tests/observability/ruff.toml     # Hereda la política común
pytest.ini                        # Descubrimiento de HTTP y navegador en la raíz
```

Ruff permite heredar un archivo con `extend`, por lo que los componentes no
necesitan copiar sus reglas. Los pyproject usan `extend = "../ruff.toml"` y las
pruebas comunes usan `extend = "../../ruff.toml"`.
[Referencia de configuración de Ruff](https://docs.astral.sh/ruff/configuration/).

Cada pyproject configura pytest con `testpaths = ["tests"]`, `pythonpath = ["."]`,
`addopts = "-q"` y versión mínima 9.2.0. Esto permite ejecutar las pruebas de un
componente desde su carpeta, sin depender de la configuración de E2E de la raíz.

Cuando también se incluye `../tests/observability`, se debe usar
`-c pyproject.toml`: pytest busca inicialmente la configuración en el ancestro
común de las rutas y podría elegir el `pytest.ini` raíz. `-c` selecciona
explícitamente la configuración y el directorio del componente.
[Referencia de pytest](https://docs.pytest.org/en/stable/reference/customize.html).

## Preparar un componente en Windows

Desde `frontend/`, `svc-menu/`, `svc-pedidos/` o `svc-lealtad/`:

```powershell
py -3.13 -m venv .venv
.\.venv\Scripts\python.exe -m pip install --require-hashes -r requirements.txt -r requirements-dev.txt
.\.venv\Scripts\python.exe --version
.\.venv\Scripts\python.exe -m ruff --version
.\.venv\Scripts\python.exe -m pytest --version
```

El comando `py -3.13` elige expresamente esa línea aunque el Python
predeterminado de la máquina sea otro. Un entorno existente creado con Python
3.14 debe recrearse con 3.13 antes de instalar los locks. En Linux se puede
crear el entorno con `python3.13 -m venv .venv` y usar `.venv/bin/python`.

## Comprobaciones por componente

Desde la carpeta del componente, con su entorno de desarrollo:

```powershell
.\.venv\Scripts\python.exe -m ruff check app tests ../tests/observability
.\.venv\Scripts\python.exe -m ruff format --check app tests ../tests/observability
.\.venv\Scripts\python.exe -m pytest -c pyproject.toml tests ../tests/observability -p no:cacheprovider
```

Para aplicar el formato común se sustituye `format --check` por `format`.
Para ejecutar solo las pruebas propias se usa
`python -m pytest -c pyproject.toml -p no:cacheprovider` desde el componente.

En la raíz, las pruebas E2E conservan su configuración en `pytest.ini` y se
ejecutan con `python scripts/run_e2e.py`, que prepara los contenedores reales.
Los detalles están en la [guía de pruebas](../tests/README.md). Las pruebas de
Chromium tienen su entorno separado en `tests/.venv`, Playwright fijado en el
lock y una [guía de ejecución y diagnóstico](browser-testing.md).

## Integración continua

Los cuatro workflows de componentes ejecutan las mismas comprobaciones y
seleccionan explícitamente su pyproject para pytest. Además de sus carpetas,
vigilan `ruff.toml`: cambiar las reglas comunes dispara las cuatro validaciones.
Las referencias de Python y las versiones de los locks permanecen fijadas.

La configuración de desarrollo no añade dependencias compartidas a las imágenes
de aplicación: cada Containerfile sigue construyéndose con su contexto propio.

## Validación — 26 de noviembre de 2026

Los cuatro entornos locales quedaron en Python 3.13.1 con pytest 9.2.0 y Ruff
0.17.6, instalados desde sus locks existentes. CI y contenedores conservan el
parche fijado 3.13.18; no se cambiaron dependencias ni se regeneraron locks.

| Entorno | Pruebas propias y contrato común | Ruff y formato | Dependencias |
|---|---:|---|---|
| Frontend | 79 aprobadas | Correctos | Sin conflictos |
| Menú | 21 aprobadas | Correctos | Sin conflictos |
| Pedidos | 40 aprobadas | Correctos | Sin conflictos |
| Lealtad | 24 aprobadas | Correctos | Sin conflictos |

La comparación de los árboles sintácticos confirmó que los archivos Python
modificados solo cambiaron de formato y orden de imports. Los cuatro pyproject
tienen la misma configuración; los workflows seleccionan ese archivo y vigilan
la política compartida de Ruff. Los tres contratos OpenAPI son válidos.

Se verificó que pytest sigue descubriendo los 31 escenarios E2E desde la raíz.
No se volvió a ejecutar el stack E2E en este paso: la lógica de la aplicación y
las dependencias no cambiaron. La advertencia existente de deprecación del
TestClient de Starlette con HTTPX sigue apareciendo y no causa fallos.
