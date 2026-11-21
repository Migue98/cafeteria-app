# Validación de entradas externas inmutables

- **Fecha:** 20 de noviembre de 2026.
- **Alcance:** imágenes base, pip, runner y GitHub Actions.

## Verificación de fuentes

Las etiquetas y releases se consultaron directamente en sus fuentes oficiales.
Los digests corresponden a índices OCI multi-arquitectura y los SHAs a los tags
publicados por los repositorios de Actions.

| Entrada | Versión | Identidad verificada |
|---|---|---|
| Python oficial | `3.13.18-slim-bookworm` | `sha256:a5a7017efc5969e00ae2b91c8eb0631049a569652aa4ffc4501769049ae45c72` |
| PostgreSQL oficial | `16.16-alpine3.24` | `sha256:1d5b02d3a9941fbd52437db4107f8c52d6297dac553ca1e5c299ebb3756b4857` |
| Checkout | `v4.4.0` | `11d5960a326750d5838078e36cf38b85af677262` |
| Setup Python | `v5.6.0` | `a26af69be951a213d495a4c3e4e4022e16d87065` |

Fuentes:

- [imagen oficial de Python](https://hub.docker.com/_/python/tags?name=3.13.18-slim-bookworm);
- [imagen oficial de PostgreSQL](https://hub.docker.com/_/postgres/tags?name=16.16-alpine3.24);
- [release de Checkout v4.4.0](https://github.com/actions/checkout/releases/tag/v4.4.0);
- [release de Setup Python v5.6.0](https://github.com/actions/setup-python/releases/tag/v5.6.0).

## Validaciones estáticas

- `docker compose config --quiet` aceptó la configuración.
- Los cuatro Containerfiles usan la misma imagen Python por etiqueta y digest.
- Los cuatro Containerfiles fijan `pip==26.3` e instalan con
  `--require-hashes`.
- Ningún workflow conserva `ubuntu-latest`, `actions/checkout@v*` ni
  `actions/setup-python@v*`.
- Los cuatro workflows usan `ubuntu-24.04` y Python `3.13.18`.
- `git diff --check` no encontró errores de espacios.

## Construcción y runtime

Las cuatro imágenes se reconstruyeron sin caché. Dentro de cada una se comprobó:

```text
Python 3.13.18
pip 26.3
```

Los locks se instalaron correctamente con validación obligatoria de hashes.
Después se generaron las etiquetas aisladas de `cafeteria-e2e` desde los mismos
Containerfiles y se verificaron nuevamente ambas versiones dentro de cada imagen.

## Regresión integral

El stack aislado usó explícitamente PostgreSQL
`16.16-alpine3.24@sha256:1d5b02d3a9941fbd52437db4107f8c52d6297dac553ca1e5c299ebb3756b4857`.
Las cuatro imágenes recién reconstruidas pasaron las nueve pruebas E2E,
incluida la persistencia después de reiniciar PostgreSQL.

Resultado final: `9 passed in 6.49s`.

Al terminar se eliminaron los contenedores, la red y el volumen temporal del
proyecto `cafeteria-e2e`.

Los workflows se validaron estáticamente y sus SHAs existen en los repositorios
oficiales. Su ejecución dentro de GitHub ocurrirá cuando los cambios se integren
y publiquen; no se afirma una ejecución remota en esta evidencia local.

Decisión relacionada:
[`ADR-004 — Entradas externas inmutables`](decisions/ADR-004-immutable-build-inputs.md).
