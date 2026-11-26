# Seguridad del frontend público

## Alcance

El frontend conserva sesiones anónimas: no hay cuentas ni pagos reales. Solo
ese servicio debe recibir tráfico público. Menú, pedidos, lealtad y PostgreSQL
son servicios internos sin autenticación pública; nunca se deben publicar sus
puertos ni reenviar sus rutas de API a Internet.

Esta implementación prepara el software. No instala certificados, modifica
Proxmox, abre puertos ni publica el servidor. El despliegue requiere coordinar
con infraestructura el proxy HTTPS, la red interna, los secretos y los límites
de tráfico.

## CSRF

La generación, firma, caducidad y validación de tokens se delegan a
`fastapi-csrf-protect==1.0.7`. La dependencia y sus transitivas están fijadas
con hashes en el lock del frontend; no hay generación ni comparación
criptográfica de tokens implementada por la app.

Cada sesión recibe un par generado por la biblioteca: un token que se conserva
en la sesión firmada y su versión firmada en una cookie CSRF independiente.
El token aparece como campo oculto `csrf_token` en todos los formularios.
HTMX lo envía en `X-CSRF-Token`, heredada del body sin JavaScript inline.

El adaptador convierte el campo urlencoded en una cabecera para llamar a la
API `validate_csrf` de la biblioteca en modo estricto de cabecera. Así ambos
flujos usan la misma validación y una cabecera incorrecta nunca puede caer
al token del formulario como alternativa. El adaptador también rechaza campos
duplicados y limita el cuerpo antes de analizarlo.

Las operaciones POST, PUT, PATCH y DELETE requieren que el token coincida con el
de la cookie CSRF firmada. La biblioteca comprueba además esa cookie contra el
token de la sesión: trasladar un par válido a otra sesión tampoco autoriza
operaciones. Si hay cabecera, se valida esa cabecera; un campo de formulario
válido no rescata una cabecera incorrecta.
La protección no se desactiva en desarrollo ni al recibir `HX-Request: true`.

También se comprueba `Origin`, o `Referer` si no hay Origin. Un origen distinto,
el origen `null` y `Sec-Fetch-Site: cross-site` se rechazan. Si ninguno de esos
encabezados está presente, el token sigue siendo obligatorio. En producción,
el destino se toma de `PUBLIC_ORIGIN`, sin confiar en encabezados forwarded
proporcionados por el cliente. Los formularios urlencoded tienen límite de 8 KiB.

Los rechazos responden 403 `CSRF_REJECTED` antes de modificar carrito o pedidos.
Una sesión o un token vencidos deben abrir de nuevo el menú para obtener un
par válido. El par se reutiliza mientras es válido para no romper formularios
abiertos ni peticiones concurrentes. La configuración de la biblioteca se aísla
por instancia de aplicación, sin cambiar secretos globales entre apps.
Sin JavaScript, los formularios HTML normales siguen funcionando.

## Política de contenido y HTMX local

HTMX 2.0.4 se distribuye en `/static/vendor/htmx-2.0.4.min.js`, con su licencia y
hash fijado. Se mantuvo la versión previamente usada; no es una actualización
automática de dependencias.

La cabecera CSP permite recursos del mismo origen y bloquea scripts externos,
scripts inline, eval, objetos, frames y cambios de base URL. HTMX usa
`allowEval=false`, `allowScriptTags=false`, `selfRequestsOnly=true` y
`includeIndicatorStyles=false`. El carrito y el polling no requieren funciones
basadas en eval. Su caché de historial HTML en localStorage está desactivada.

Las respuestas incluyen `X-Content-Type-Options: nosniff`,
`X-Frame-Options: DENY`, una política de referente y permisos que deshabilita
cámara, micrófono y geolocalización. En producción se añade HSTS por un año,
sin `includeSubDomains` ni preload. Las páginas, fragmentos y errores usan
`Cache-Control: private, no-store` para no compartir sesiones ni historiales.

Los errores inesperados devuelven un mensaje genérico y `trace_id`, con las
mismas cabeceras. Las excepciones se registran internamente. Los fragmentos de
error del carrito escapan HTML. La documentación automática del frontend se
deshabilita en producción; su uso en desarrollo puede quedar limitado por la
CSP estricta que no permite los CDN de Swagger/ReDoc.

## Configuración

| Variable | Desarrollo | Producción |
|---|---|---|
| `APP_ENV` | `development` | `production` |
| `SESSION_SECRET` | Valor local conocido | Aleatorio, al menos 32 caracteres; obligatorio. |
| `SESSION_HTTPS_ONLY` | `false` para localhost HTTP | `true`; la app rechaza false. |
| `PUBLIC_ORIGIN` | Opcional; usa origen de la petición validada | Origen HTTPS exacto, sin ruta ni credenciales. |
| `ALLOWED_HOSTS` | localhost, loopback y host de pruebas | Hosts explícitos, sin comodines; debe incluir el del origen público y localhost para salud. |
| `SESSION_MAX_AGE_SECONDS` | `86400` | `86400` por defecto; entero positivo. |

Las réplicas deben compartir el mismo secreto. No guardarlo en Git; suministrarlo
mediante el mecanismo de secretos del despliegue. Puede generarse con
`python -c "import secrets; print(secrets.token_urlsafe(48))"` en un entorno
administrativo y almacenarse directamente como secreto.

Las cookies de producción se llaman `__Host-cafeteria_session` y
`__Host-cafeteria_csrf`: ambas son host-only,
`Path=/`, `HttpOnly`, `Secure`, `SameSite=Lax`. La sesión tiene una vida deslizante
de un día por defecto. El token CSRF caduca como máximo tras ese mismo
plazo desde su generación, comprobado por la biblioteca, y su cookie tiene
el mismo `Max-Age`. Cambiar de modo de desarrollo a producción crea una sesión
nueva por el cambio de nombre. La firma impide modificar la cookie, pero no
cifra su contenido: no debe contener credenciales ni datos sensibles.

Los formularios de una sesión firmada antigua sin token necesitan recargar el
menú. No hay revocación central de sesiones individuales; cambiar el secreto
invalida todas las sesiones. El alcance es una demo de compras anónimas, no un
sistema de cuentas o control de acceso para usuarios registrados.

## Plantilla de despliegue

`compose.public.yaml` se aplica sobre el Compose local con Docker Compose
2.24.4 o posterior. Requiere valores explícitos para `SESSION_SECRET`,
`POSTGRES_PASSWORD`, `PUBLIC_ORIGIN` y `ALLOWED_HOSTS`. Retira los puertos
publicados de los backends y publica frontend únicamente en loopback para un
proxy HTTPS instalado en el mismo host.

```powershell
# Con las variables de producción ya suministradas de forma segura:
docker compose -f compose.yaml -f compose.public.yaml config --quiet
```

Es una plantilla, no se ha aplicado al servidor. Si el proxy está en otro
contenedor o máquina, adaptar la conexión privada en conjunto con el responsable
de infraestructura. No usar el Compose de desarrollo tal cual en Internet.

El proxy debe conservar Host, terminar TLS, redirigir HTTP a HTTPS y limitar
tráfico y tamaño de solicitudes. Solo se deben confiar encabezados forwarded de
ese proxy conocido; no configurar confianza global en IPs arbitrarias.
No hay redirección HTTPS en la app para evitar bucles detrás del proxy y no
romper las probes internas por HTTP. El origen CSRF se valida con la
configuración explícita, y los assets usan rutas relativas al origen.

Los endpoints operativos `/health` y `/metrics` se mantienen para probes y
monitorización; el proxy público debe excluirlos. La app no implementa un
limitador de tráfico distribuido: el proxy/Ingress debe establecerlo antes de
exponer la demo, en especial para formularios y checkout.

Si existe una base con datos, aplicar primero la
[migración de claves de lealtad](concurrency-and-idempotency.md#base-de-datos-existente).

## Referencias y validación

- [OWASP: CSRF Prevention](https://cheatsheetseries.owasp.org/cheatsheets/Cross-Site_Request_Forgery_Prevention_Cheat_Sheet.html)
- [fastapi-csrf-protect: API e integración](https://github.com/aekasitt/fastapi-csrf-protect)
- [Starlette: middleware de sesiones y hosts](https://starlette.dev/middleware/)
- [HTMX: seguridad, CSRF y CSP](https://htmx.org/docs/#security)
- [Docker: merge, reset y override](https://docs.docker.com/reference/compose-file/merge/)

Las pruebas usan tokens reales; no existe una variable para desactivar CSRF.
Se verifican formularios HTML, peticiones HTMX, rechazos entre sesiones/orígenes,
cookies de producción, configuración inválida, cabeceras, activos y regresiones
del flujo de compras y recuperación.

## Evidencia — 26 de noviembre de 2026

- **79 pruebas del frontend y contrato común aprobadas**; incluyen 40 casos
  de seguridad y configuración. La integración con la biblioteca verifica
  cookies ausentes o alteradas, pares trasladados entre sesiones, aislamiento
  de configuración entre apps y renovación del CSRF vencido sin perder el carrito.
- **31 pruebas E2E aprobadas en 146.60 segundos**, con contenedores reales,
  `fastapi-csrf-protect` activo, concurrencia, interrupciones y recuperación.
- Ruff y formato correctos; los tres contratos OpenAPI válidos.
- En la comprobación visual inicial del bloque se agregó café mediante HTMX,
  se cambió la cantidad y se
  confirmó una compra. No se registraron errores de CSP ni JavaScript.
- Después se compró con lealtad detenido: el recibo mostró puntos pendientes.
  Al restaurarlo, cambió automáticamente a **+3 puntos**, actualizó el saldo y
  retiró `hx-trigger`, sin recargar ni reenviar el checkout. La consola siguió
  sin errores ni advertencias.
- La combinación de Compose público se validó con valores sintéticos: cero
  puertos de backends publicados, frontend solo en `127.0.0.1`, modo production
  y cookies seguras. No se desplegó esa plantilla ni se configuró TLS real.

La validación HTTPS de cookies se hizo con el cliente de pruebas sobre un origen
HTTPS simulado. El certificado, la red y la configuración real del proxy deben
validarse durante la integración con infraestructura. La aplicación sigue en
revisión local; estas pruebas no equivalen a una auditoría de penetración.
