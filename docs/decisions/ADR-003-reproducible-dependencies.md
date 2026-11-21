# ADR-003 — Dependencias reproducibles

- **Estado:** aceptado.
- **Fecha:** 20 de noviembre de 2026.

## Contexto

El inventario inicial encontró versiones diferentes de Python, FastAPI, Ruff y
dependencias transitivas entre los entornos locales, CI y las imágenes. Además,
los requisitos actuales expresan rangos amplios y las imágenes y Actions usan
referencias móviles. Una instalación limpia puede producir artefactos distintos
sin que cambie el repositorio.

La fijación de dependencias es independiente de publicar la aplicación como
`v1.0.0`: la primera controla exactamente con qué se construye; la segunda
identifica una versión funcional del producto.

## Decisión

### Plataforma común

- Desarrollo, CI y contenedores usarán Python 3.13.
- El archivo raíz `.python-version` declara esa línea para las herramientas
  locales que lo soporten.
- La versión de parche del intérprete se fijará junto con la imagen base en el
  paso dedicado a contenedores.

### Línea base de dependencias directas

| Ámbito | Dependencia | Versión decidida |
|---|---|---:|
| Todos los servicios | FastAPI | 0.165.0 |
| Todos los servicios | Prometheus Client | 0.26.0 |
| Todos los servicios | Uvicorn | 0.54.0 |
| Frontend y pedidos | HTTPX | 0.28.1 |
| Frontend | ItsDangerous | 2.2.0 |
| Frontend | Jinja2 | 3.1.6 |
| Backends | Psycopg con extra `binary` | 3.3.9 |
| Pruebas que realizan HTTP | HTTPX | 0.28.1 |
| Desarrollo | Pytest | 9.2.0 |
| Desarrollo | Ruff | 0.17.6 |

FastAPI 0.165.0 y Ruff 0.17.6 se adoptan como línea común porque ya funcionan
en el frontend. Su compatibilidad con los tres backends deberá confirmarse con
la regresión completa antes de sustituir los archivos utilizados por CI y las
imágenes.

### Archivos fuente y archivos lock

Cada componente tendrá dos capas:

- `requirements.in`: dependencias directas necesarias en producción, con una
  versión exacta elegida conscientemente.
- `requirements.txt`: lock generado con todas las dependencias transitivas,
  versiones exactas y hashes.
- `requirements-dev.in`: herramientas directas de prueba y calidad. Usa
  `-c requirements.txt` para ser compatible con el runtime bloqueado.
- `requirements-dev.txt`: lock generado de la capa de desarrollo.

Los locks se generarán con `pip-tools==7.5.2` en Python 3.13 y se guardarán en
Git. CI y los contenedores instalarán únicamente los `.txt`; nadie editará esos
locks a mano. Para desarrollo se instalarán juntos el lock de runtime y el de
desarrollo:

```text
pip install -r requirements.txt -r requirements-dev.txt
```

La suite E2E usa el mismo patrón, pero solo necesita su
`tests/requirements.in` y el lock correspondiente.

El generador común valida las versiones de Python y `pip-tools` y compila los
nueve locks contra el índice oficial, con hashes:

```text
python -m pip install pip-tools==7.5.2
python scripts/compile_requirements.py
```

### Actualizaciones

Una actualización de dependencias se realizará como un cambio aislado:

1. modificar la versión directa en el `.in` correspondiente;
2. regenerar todos los locks afectados con la herramienta y Python acordados;
3. ejecutar lint, pruebas unitarias, E2E y construcción de imágenes;
4. revisar el diff de dependencias antes de integrar.

No se usarán actualizaciones implícitas durante una construcción normal.

### Referencias externas

Las imágenes base, GitHub Actions, runner y versión de `pip` se fijaron por
separado en
[`ADR-004 — Entradas externas inmutables`](ADR-004-immutable-build-inputs.md).

## Alternativas rechazadas

- Conservar rangos amplios en los archivos instalados: no asegura que dos
  construcciones resuelvan el mismo entorno.
- Mantener manualmente una lista parcial de versiones transitivas: es propenso
  a errores y no registra hashes.
- Usar un único archivo para producción y desarrollo: instala herramientas
  innecesarias dentro de las imágenes finales.
- Adoptar automáticamente las versiones más recientes: el objetivo es partir
  de una línea observada y probada, no actualizar sin una regresión explícita.

## Consecuencias

- Los cambios de dependencias serán mayores en Git, pero auditables.
- Regenerar locks requerirá la versión acordada de Python y `pip-tools`.
- Los servicios compartirán versiones cuando la dependencia sea común.
- Los nueve locks fueron generados y validados mediante instalaciones limpias,
  47 pruebas unitarias, 9 pruebas E2E y la construcción de las cuatro imágenes.

Inventario de origen: [`docs/dependency-inventory.md`](../dependency-inventory.md).

Evidencia de validación:
[`docs/dependency-lock-validation.md`](../dependency-lock-validation.md).
