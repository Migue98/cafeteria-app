# ADR-004 — Entradas externas inmutables

- **Estado:** aceptado.
- **Fecha:** 20 de noviembre de 2026.

## Contexto

Los locks de Python fijan las librerías de la aplicación, pero una construcción
seguía dependiendo de referencias móviles: `python:3.13-slim`,
`postgres:16-alpine`, `ubuntu-latest` y versiones mayores de GitHub Actions.
El Containerfile también actualizaba `pip` sin indicar versión. Cualquiera de
esas entradas podía cambiar sin modificar el repositorio.

## Decisión

Se fijan las siguientes entradas verificadas el 20 de noviembre de 2026:

| Entrada | Referencia legible | Identidad inmutable |
|---|---|---|
| Python | `3.13.18-slim-bookworm` | `sha256:a5a7017efc5969e00ae2b91c8eb0631049a569652aa4ffc4501769049ae45c72` |
| PostgreSQL | `16.16-alpine3.24` | `sha256:1d5b02d3a9941fbd52437db4107f8c52d6297dac553ca1e5c299ebb3756b4857` |
| pip | `26.3` | Versión exacta publicada en PyPI |
| Runner | `ubuntu-24.04` | Etiqueta fija de la imagen de runner |
| Checkout | `v4.4.0` | `11d5960a326750d5838078e36cf38b85af677262` |
| Setup Python | `v5.6.0` | `a26af69be951a213d495a4c3e4e4022e16d87065` |

Las imágenes conservan etiqueta y digest. La etiqueta explica qué versión se
eligió y el digest garantiza qué índice OCI multi-arquitectura se descargará.

Los workflows conservan comentarios con el release legible junto al SHA. Las
líneas mayores de Actions no cambian en esta decisión para evitar mezclar la
reproducibilidad con una migración a nuevas versiones mayores.

Los Containerfiles instalan los locks con `--require-hashes`. La versión raíz
de Python, CI y la imagen base queda alineada en `3.13.18`.

## Actualizaciones

Actualizar una entrada inmutable será un cambio explícito:

1. elegir una etiqueta o release publicado por la fuente oficial;
2. obtener y revisar su digest o SHA completo;
3. actualizar juntos la referencia y su comentario legible;
4. construir las cuatro imágenes y ejecutar la regresión completa;
5. documentar la nueva evidencia antes de integrar.

## Alternativas rechazadas

- Usar solamente una etiqueta exacta de contenedor: una etiqueta todavía puede
  volver a publicarse con otro contenido.
- Usar solamente el digest: impide reconocer fácilmente la versión seleccionada.
- Mantener referencias mayores de Actions: el código ejecutado puede cambiar
  cuando el proveedor mueve la etiqueta.
- Migrar de inmediato a las últimas versiones mayores de Actions: ampliaría el
  alcance y podría requerir una versión diferente del runner.

## Consecuencias

- Dos construcciones resolverán las mismas imágenes, Actions y herramienta de
  instalación mientras esas referencias sigan disponibles.
- Las correcciones de seguridad ya no entrarán automáticamente; deben pasar por
  una actualización deliberada y su regresión.
- `ubuntu-24.04` es más estable que `ubuntu-latest`, aunque GitHub todavía puede
  actualizar el software preinstalado dentro de esa familia de runner.

Decisión de locks relacionada:
[`ADR-003 — Dependencias reproducibles`](ADR-003-reproducible-dependencies.md).

Evidencia de validación:
[`docs/immutable-input-validation.md`](../immutable-input-validation.md).
