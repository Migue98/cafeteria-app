# Contrato de salud para Kubernetes

Fecha: **27 de noviembre de 2026**. Pasos 1 y 2 de preparación del software para
GitOps: **contrato definido y probes implementadas en los cuatro componentes**.
Los tres contratos OpenAPI incluyen las rutas. La validación descrita es local;
los healthchecks de Compose siguen usando `/health` y los
manifiestos de infraestructura quedan para el paso 4.

## Tres preguntas diferentes

| Endpoint | Pregunta | Comportamiento |
|---|---|---|
| `GET /livez` | ¿Responde el proceso de esta réplica? | HTTP 200 si terminó la inicialización local y el servidor puede responder. No consulta red, BD, disco externo ni exportadores. |
| `GET /readyz` | ¿Puede esta réplica atender su función principal? | HTTP 200 si las dependencias críticas pasan; HTTP 503 si alguna falla o vence el presupuesto de comprobación. |
| `GET /health` | ¿Cuál es el diagnóstico de dependencias? | Conserva los contratos y comportamientos actuales, incluidos `healthy`, `degraded` y los errores existentes. |

Una caída externa no causa por sí sola un fallo de `/livez`. Un proceso muerto
o bloqueado puede no devolver ninguna respuesta: Kubernetes detecta conexión
rechazada o timeout y aplica la política del contenedor. No hace falta que un
proceso muerto consiga responder HTTP 503.

Readiness fallida retira la réplica del tráfico del Service; no solicita un
reinicio. Startup utilizará `/livez` para dar tiempo al arranque local antes de
activar las otras probes. Ni startup ni liveness esperan a PostgreSQL o a otro
microservicio: esa espera corresponde a readiness.

## Dependencias y capacidad de servicio

| Componente | Dependencias críticas de readiness | Dependencias que no bloquean readiness | Motivo |
|---|---|---|---|
| `frontend` | Menú disponible. | Pedidos y lealtad. | Puede mostrar catálogo y manejar carrito durante esas fallas; checkout/historial muestran los errores controlados ya implementados. |
| `svc-menu` | PostgreSQL accesible y consulta de salud correcta. | Ningún otro backend. | La función principal es consultar el catálogo persistente. |
| `svc-pedidos` | PostgreSQL y menú disponibles. | Lealtad. | Puede confirmar pedidos con `loyalty_status=pending` y recuperar puntos después. |
| `svc-lealtad` | PostgreSQL accesible y consulta de salud correcta. | Menú y pedidos. | Debe poder consultar y persistir saldos/movimientos. |

La readiness del frontend comprueba únicamente menú; no llama al diagnóstico
agregado que hoy consulta los tres backends. La de pedidos tampoco consulta
lealtad. Así una comprobación opcional lenta no consume su presupuesto ni
bloquea capacidad de servicio que sí existe. Los detalles de degradación siguen
disponibles en `/health` y en las operaciones de negocio.

El frontend y pedidos consultan `/readyz` de menú con timeout y validación
del código y cuerpo del contrato. Menú solo comprueba su BD: no se crean ciclos
de comprobaciones. Cada backend comprueba su propia conexión a PostgreSQL.

En esta versión, la consulta de BD es `SELECT 1`, sin escrituras. Confirma
conexión/consulta, no demuestra que existan todas las tablas ni que todas las
compras puedan completarse. Inicialización/migraciones y smoke del catálogo
serán requisitos separados del arranque de la entrega. No se modifica el
catálogo, no se crea un pedido y no se acreditan puntos al ejecutar una probe.

## Respuestas de las nuevas probes

Los cuatro componentes usan los nombres `frontend`, `svc-menu`, `svc-pedidos`
y `svc-lealtad`. Las rutas no llevan `/api/v1`. Las respuestas son
`application/json`, sin redirecciones y con `Cache-Control: no-store`.

Liveness correcta, HTTP 200:

```json
{"service":"svc-pedidos","status":"alive"}
```

Readiness correcta de pedidos, HTTP 200:

```json
{"service":"svc-pedidos","status":"ready","checks":{"postgres":"up","menu":"up"}}
```

Readiness fallida de pedidos, HTTP 503:

```json
{"service":"svc-pedidos","status":"not_ready","checks":{"postgres":"up","menu":"down"}}
```

`service` y `status` son obligatorios. `/readyz` añade `checks` con exactamente
sus dependencias críticas: frontend `{menu}`, menú/lealtad `{postgres}` y
pedidos `{postgres,menu}`. Cada valor es `up` o `down`; fallo, timeout o respuesta
inválida se representan como `down`. Deben terminar de clasificarse todos los
checks o marcarse como `down` al vencer el presupuesto. Un fallo global de
comprobación se resuelve como HTTP 503, nunca como un falso `ready`.

La respuesta 503 de `/readyz` es una excepción operativa explícita a los errores
de negocio `application/problem+json`: permite el mismo esquema de checks en
200 y 503. Las excepciones de negocio y las respuestas de `/health` conservan
su formato actual. No se exponen DSN, hosts privados, SQL, excepciones o tokens.
Continúan la correlación `X-Request-ID`/`traceparent` y las validaciones comunes
de encabezados: una petición mal formada puede recibir el rechazo existente.

Las probes válidas no requieren autenticación, sesión de usuario ni token CSRF.
Las reglas de Host se conservan: los futuros httpGet del frontend enviarán un
Host permitido explícito, por ejemplo `localhost`, aunque conecten a la IP del
pod. El Ingress público mantendrá estas rutas operativas fuera de exposición.

## Tiempos y recuperación

Presupuesto de `/readyz`: **tres segundos en total**, incluyendo conexiones y
consulta, sin reintentos internos. Las comprobaciones críticas corren en
paralelo mediante `asyncio.TaskGroup`; el timeout cancela y espera su cierre.
Psycopg usa una conexión asíncrona propia con límites de conexión y sentencia
de un segundo; HTTPX limita a un segundo las operaciones de red y no sigue
redirecciones. La respuesta de menú debe cumplir su contrato JSON.

Cada proceso admite una sola comprobación de readiness en curso. Una solicitud
simultánea devuelve 503 con sus checks en `down` sin encolar más trabajo.
Liveness permanece independiente. Las pruebas cubren cancelación, concurrencia
y recuperación, además de PostgreSQL realmente detenido o pausado en Compose.

Valores iniciales para diseñar los manifiestos del paso 4, sujetos a medición:

| Probe | Ruta | timeoutSeconds | periodSeconds | failureThreshold | successThreshold |
|---|---|---:|---:|---:|---:|
| startup | `/livez` | 1 | 2 | 30 | 1 |
| liveness | `/livez` | 1 | 10 | 3 | 1 |
| readiness | `/readyz` | 5 | 5 | 2 | 1 |

El timeout de Kubernetes deja margen al presupuesto de readiness. Los umbrales
evitan reaccionar a una única falla transitoria. La siguiente comprobación
exitosa permite recuperar Ready sin reiniciar el proceso ni volver a desplegar.
Una probe prueba esta réplica y sus dependencias; no garantiza disponibilidad
total de la aplicación ni sustituye las pruebas de compra.

## Matriz de aceptación

Supuesto de la matriz: procesos iniciados y configuración local válida.

| Escenario | `/livez` | Readiness esperada |
|---|---|---|
| Todo disponible | 200 en los cuatro. | 200 en los cuatro. |
| Lealtad detenida | 200 en los procesos restantes. | Frontend, menú y pedidos: 200. El proceso detenido no responde. |
| Pedidos detenido | 200 en los procesos restantes. | Frontend, menú y lealtad: 200. Catálogo y carrito continúan disponibles. |
| Menú detenido | 200 en los procesos restantes. | Frontend y pedidos: 503; lealtad: 200. |
| PostgreSQL detenido | 200 en los cuatro procesos. | Los tres backends y frontend: 503; frontend detecta menú no listo. |
| Dependencia crítica lenta o respuesta inválida | 200 en el proceso comprobado. | 503 dentro del presupuesto; sin generar datos de negocio. |
| Dependencia recuperada | 200. | Vuelve a 200 en la siguiente comprobación satisfactoria. |
| Proceso muerto/bloqueado | No responde o vence el timeout. | No recibe tráfico; Kubernetes aplica sus umbrales de reinicio. |

Durante caída de lealtad, además se debe confirmar un pedido, verificar estado
pending y comprobar acreditación única al recuperarse. Durante caída de pedidos,
verificar catálogo/carrito y mensaje de checkout; readiness 200 del frontend no
afirma que toda operación esté disponible. Las suites de recuperación y navegador
comprueban estos comportamientos de negocio junto con las nuevas probes.

## Compatibilidad y siguiente paso

Se conserva `/health`: en el frontend devuelve HTTP 200 con `degraded` aunque
caiga un backend; los diagnósticos de los otros servicios conservan su semántica
actual. Los healthchecks de Compose y las llamadas entre servicios actuales
siguen usando esa ruta hasta una transición explícita. No se sustituye por una
redirección ni se renombra ningún campo de respuesta existente.

La implementación está en `app/probes.py` de cada componente, conectada desde
`create_app`. Cada imagen conserva un módulo autónomo; una prueba compartida
comprueba que las cuatro copias sean equivalentes. FastAPI/Pydantic declaran
las respuestas, HTTPX consulta menú y Psycopg comprueba PostgreSQL, usando las
dependencias ya fijadas del proyecto.

El **paso 3 ajustado** prepara la [inicialización de BD](database-initialization.md):
separa esquema y ejemplos y comprueba persistencia, sin migración de producción.
Los manifiestos Kubernetes se revisan en el paso 4; estas pruebas no constituyen
validación dentro del clúster.

## Validación local del paso 2

Ejecución del 27 de noviembre de 2026, con las imágenes reconstruidas en el
proyecto aislado `cafeteria-e2e` y datos desechables:

| Comprobación | Resultado |
|---|---|
| Frontend + pruebas compartidas | 109 aprobadas. |
| Menú + pruebas compartidas | 48 aprobadas. |
| Pedidos + pruebas compartidas | 71 aprobadas. |
| Lealtad + pruebas compartidas | 51 aprobadas. |
| E2E HTTP, incluyendo las seis pruebas nuevas de probes | 37 aprobadas en 194.66 s. |
| Chromium: compra, carrito, historial, recuperación y seguridad | 12 aprobadas en 84.65 s. |
| Ruff y formato en los cuatro componentes; contratos OpenAPI | Aprobados. |

Las 279 pruebas de componentes incluyen 65 casos nuevos de probes. La suite
HTTP verifica caídas de menú, pedidos y lealtad, además de PostgreSQL detenido
y pausado. Comprueba los códigos, el presupuesto de respuesta y que los procesos
sobrevivientes conserven su hora de inicio; después exige recuperación a 200.
El runner retiró contenedores, red y volumen de ensayo al terminar.

Permanecen avisos de deprecación de las dependencias de TestClient/Playwright;
no hay pruebas fallidas. No se ejecutaron probes de Kubernetes ni se cambió
el stack habitual de desarrollo. Este resultado corresponde al código local.

Fuente de semántica Kubernetes: [liveness, readiness y startup](https://kubernetes.io/docs/concepts/workloads/pods/probes/).
Las decisiones de dependencias y respuestas de este documento pertenecen a
la cafetería; Kubernetes no prescribe ese esquema JSON.
