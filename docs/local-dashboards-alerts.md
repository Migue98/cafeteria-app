# Dashboards y alertas locales

El paso 4 incorpora dos dashboards y tres reglas de Grafana Alerting. Se cargan
desde archivos al iniciar Grafana junto con la vista de conexión existente.
La evaluación de alertas utiliza Prometheus; el envío a Telegram usa la
integración nativa de Grafana y se activa con una extensión independiente.

## Abrir los dashboards

```powershell
docker compose -f compose.yaml -f compose.monitoring.yaml up --build --detach
```

Entra a Grafana en http://localhost:3000 con tu cuenta local y abre la carpeta
**Cafetería local**. Puedes añadir `-f compose.telemetry.yaml` para consultar
también los [logs y trazas](local-logs-traces.md).

| Dashboard | UID | Paneles |
|---|---|---|
| Conexión de métricas | `cafeteria-metrics-connection` | Targets y lectura de métricas de los cuatro servicios. |
| Cafetería · aplicación | `cafeteria-application` | Disponibilidad, peticiones/s, errores 5xx/s, porcentaje 5xx, latencia promedio y p95, respuestas por código HTTP. |
| Cafetería · negocio | `cafeteria-business` | Pedidos confirmados, importe MXN, puntos, pendientes, tasas por minuto y reintentos por resultado. |

Los paneles técnicos excluyen `/health` y `/metrics` del tráfico de aplicación.
La disponibilidad representa el scrape de `/metrics`, no la salud de las
dependencias. La media y el p95 se calculan desde el histograma existente;
sin peticiones recientes pueden quedar vacíos. El p95 es una estimación por
buckets, no la duración exacta de una petición individual.

Los totales de pedidos, importes y puntos son **contadores del proceso** y
se reinician al recrear el servicio. No representan todo el historial de
PostgreSQL. Las tasas usan `rate()` para tolerar esos reinicios. El importe
convierte centavos a MXN y representa pedidos confirmados, no pagos cobrados.
Los reintentos usan `increase()` dentro del rango seleccionado y pueden mostrar
valores fraccionarios por la estimación de Prometheus.

Los dashboards se guardan en
[`observability/grafana/dashboards/`](../observability/grafana/dashboards/).
Los cambios se hacen en JSON; se recargan mediante el proveedor de archivos
cada 30 segundos. Los enlaces de navegación permiten cambiar de vista o abrir
las reglas.

## Reglas y estados

En **Alerting → Alert rules** están las reglas del grupo `cafeteria-local`,
evaluadas cada diez segundos. Expande el grupo o elige **List** para verlas:

| Regla | Condición | Espera predeterminada | Nivel |
|---|---|---|---|
| Servicio inaccesible | `up` igual a cero para un servicio. | 30 segundos continuos. | `critical` |
| Errores HTTP frecuentes | Más de 10% de respuestas 5xx y al menos cinco solicitudes de aplicación en el último minuto. | 30 segundos continuos. | `warning` |
| Puntos pendientes | Backlog de pedidos pendientes de acreditar mayor que cero. | 20 minutos continuos. | `warning` |

Las variables `ALERT_SERVICE_DOWN_FOR`, `ALERT_HTTP_ERRORS_FOR` y
`ALERT_LOYALTY_PENDING_FOR` permiten ajustar esas esperas. Las definiciones
están en [`rules.yaml`](../observability/grafana/alerting/rules.yaml).
Para aplicar cambios en reglas o notificaciones, recrea Grafana con los mismos
archivos Compose que utilizaste al iniciarlo.

Una condición pasa de **Normal** a **Pending** y, si persiste la espera,
a **Firing**. Al desaparecer se recupera sin mantener artificialmente la
alerta activa. Las notificaciones agrupan por regla y servicio, esperan diez
segundos al inicio y repiten los avisos cada hora mientras continúe el problema.
El estado puede tardar un scrape, una evaluación y el tiempo de agrupación en
reflejarse en un mensaje.

La regla de errores trata la ausencia de tráfico suficiente como normal.
Las otras reglas muestran **No Data** si falta su métrica. Los errores de
consulta conservan el estado **Error**; no se convierten en un falso estado
saludable. Grafana puede generar alertas adicionales de datasource cuando
Prometheus deja de responder.

El contador de pendientes es una fotografía actualizada por el worker. Su
intervalo normal es 15 minutos; por eso la espera de la alerta es de 20 minutos.
La regla señala un backlog persistente, no mide la antigüedad de cada pedido.
Si cambias el intervalo del worker, revisa también la espera. Un backlog que
rota entre pedidos puede mantener la condición activa aunque cambien sus IDs.

Estas son condiciones iniciales para la demostración local. Los umbrales
definitivos de producción se ajustarán con el tráfico observado.

## Notificaciones locales y Telegram

Sin extensión de Telegram, las reglas se evalúan y sus estados se ven en
Grafana. La política local silencia permanentemente todas las notificaciones;
no intenta mandar correo ni requiere credenciales. Su contacto de respaldo
usa una dirección reservada `example.invalid` y permanece silenciado; no
depende de que exista un contacto predeterminado en Grafana.
Silenciar avisos no pausa las reglas. El archivo de políticas administra el
árbol completo de esta instancia local de Grafana.

Para activar Telegram necesitas crear un bot con **BotFather**, añadirlo al
chat destinatario y guardar estos valores en el `.env` local, excluido de Git:

```dotenv
TELEGRAM_BOT_TOKEN=REEMPLAZA_CON_TU_TOKEN
TELEGRAM_CHAT_ID=REEMPLAZA_CON_EL_ID_DEL_CHAT
```

No guardes valores reales en `.env.example`, archivos de provisioning,
capturas ni documentación. La extensión falla antes de iniciar si falta
alguno de los dos valores:

```powershell
docker compose -f compose.yaml -f compose.monitoring.yaml -f compose.telemetry.yaml -f compose.telegram.yaml up --build --detach
```

Para obtener el ID del destinatario, abre el chat con el bot creado y envíale
`/start` y un mensaje nuevo. La API `getUpdates` devuelve el número en
`message.chat.id`. Para un grupo, añade al bot y envía `/start@nombre_del_bot`
en ese grupo. Si no aparecen actualizaciones, comprueba que el mensaje se
envió al mismo bot del token. Guarda únicamente el ID del destino elegido en
`TELEGRAM_CHAT_ID`; un mismo bot puede recibir mensajes de varios chats.

También funciona sin el archivo de telemetry. La extensión sustituye la política
silenciada por una ruta al contacto `cafeteria-telegram`; solamente enruta las
alertas de esta aplicación. Grafana lee las credenciales desde su entorno,
envía avisos de alerta y recuperación y usa texto sin formato. Los enlaces
generados siguen apuntando al Grafana local; el envío de Telegram no publica
Grafana en Internet.

Para comprobar el destino real puedes usar **Contact points → cafeteria-telegram
→ Test**. Esta operación sí envía un mensaje al chat configurado. Evita ejecutar
`docker compose config` sin `--quiet` o inspeccionar entornos en pantalla al
trabajar con esta extensión: Docker puede mostrar las credenciales resueltas.

Para desactivar Telegram conservando datos, primero baja el stack usando todos
los archivos con los que lo iniciaste y luego levántalo sin la extensión.
La política local vuelve a silenciar las notificaciones. El contacto anterior
puede seguir guardado en Grafana, pero no queda seleccionado en la política.
Si se retira definitivamente el bot, elimina el contacto mediante provisioning
con `deleteContactPoints` y UID `cafeteria-telegram`; los recursos provisionados
desde archivos se administran desde esos archivos.

## Pruebas de extremo a extremo

Usa el entorno Python y Chromium de [`tests/README.md`](../tests/README.md):

```powershell
# Métricas y dashboards.
.\tests\.venv\Scripts\python.exe scripts/run_monitoring_e2e.py
# Añade las fallas controladas y los avisos firing/resolved.
.\tests\.venv\Scripts\python.exe scripts/run_monitoring_e2e.py --alerts
# Comprueba también Alloy, Loki, Tempo y la navegación de trazas.
.\tests\.venv\Scripts\python.exe scripts/run_monitoring_e2e.py --telemetry --alerts
```

El runner siempre comprueba los dashboards mediante Prometheus real y Chromium.
Con `--alerts`, añade un receptor webhook interno de prueba y sustituye la
política de notificaciones. **No monta `compose.telegram.yaml` ni envía mensajes
a Telegram**, aunque existan credenciales locales. Prueba:

1. Reglas provisionadas y visibles en Grafana, con enlaces a sus paneles.
2. Detener menú: aviso de servicio caído y recuperación del mismo incidente.
3. Crear una ráfaga de solicitudes con menú caído: alerta de errores 5xx
   y recuperación al salir esos errores de la ventana temporal.
4. Crear un pedido con lealtad caída: alerta de pendientes, recuperación
   automática del pedido y siete puntos acreditados, con aviso de resolución.

Grafana, Prometheus, los servicios y PostgreSQL son reales. Solo se sustituye
el destino externo de las notificaciones. Las esperas de las tres reglas se
reducen a 20 segundos y el worker a dos segundos para que la prueba no dure
20 minutos. Las expresiones y umbrales son los mismos. Se comprueba el par
`firing`/`resolved` con igual `startsAt`, no solamente que la condición PromQL
pueda resultar verdadera.

El receptor escucha únicamente en el loopback del host, puerto `13080`,
configurable con `MONITORING_E2E_ALERT_RECEIVER_PORT`. Tiene datos sintéticos
en memoria, reutiliza la imagen del frontend y se elimina con el proyecto
`cafeteria-monitoring-e2e`. No es un nuevo servicio de la aplicación.
Las capturas de dashboards y reglas quedan en `test-results/monitoring/`.
Los webhooks recibidos se conservan en `alert-notifications.json` dentro de esa
misma carpeta para revisar los incidentes sintéticos después de limpiar Compose.
La matriz de CI comprueba el modo de métricas y el completo con alertas.

## Validación de Telegram sin enviar mensajes

La extensión Compose se comprobó con valores sintéticos: rechaza el inicio
cuando faltan credenciales. También se inició la misma imagen fijada de
Grafana en un contenedor temporal con red desactivada y se verificaron mediante
su API el contacto nativo, el chat de prueba, la ruta de aplicación, el respaldo
silenciado y los avisos de recuperación habilitados. El contenedor se eliminó
después. Esta comprobación valida el provisioning, no la autenticidad del bot
ni la entrega a un chat real.

Posteriormente se completó la activación y el envío real descritos abajo.

## Evidencia local — 26 de noviembre de 2026

| Comprobación | Resultado |
|---|---|
| Modo completo | Quince pruebas aprobadas en 504.21 segundos. |
| Modo básico sin Telegram | Seis pruebas aprobadas en 123.97 segundos, incluida la política de notificaciones silenciada. |
| Dashboards | Siete paneles técnicos y ocho de negocio, consultas válidas contra Prometheus y visualización real en Chromium. |
| Reglas | Tres reglas provisionadas, evaluadas cada diez segundos y enlazadas a sus paneles. |
| Notificaciones | Once webhooks sintéticos recibidos; las tres reglas enviaron avisos de activación y recuperación del mismo incidente. |
| Recuperación de puntos | Un pedido pendiente se recuperó automáticamente y su cliente terminó con siete puntos; se resolvió la alerta. |
| Logs y trazas | Los casos del paso 3 siguen pasando junto con dashboards y alertas, incluida la persistencia de Loki/Tempo/Alloy. |
| Telegram | Provisioning nativo validado sin red y envío real aprobado desde la API de Grafana con las credenciales guardadas. |
| Herramientas | Ruff, formato, YAML y enlaces locales correctos. |

Se revisaron visualmente las capturas de ambos dashboards y de las tres reglas.
El runner completo eliminó sus doce contenedores, red y seis volúmenes de
prueba; el básico eliminó sus siete contenedores, red y tres volúmenes.
La consulta final de Docker confirmó que no quedaron contenedores, volúmenes
ni redes de pruebas, ni contenedores auxiliares de validación de Telegram.
Durante esas suites la aplicación normal permaneció apagada. Los cambios y el workflow
quedan locales para revisión; no se ejecutó CI remoto en este paso.
Permanece una advertencia conocida de la fixture `base_url` de Playwright,
sin causar fallos.

## Activación real de Telegram — 26 de noviembre de 2026

Se validó el bot, se obtuvo un único chat privado mediante `getUpdates` y se
guardó su ID en `.env` usando `python-dotenv`. El token y el ID se conservan
solo en el archivo local excluido de Git.

Se levantó la plataforma normal con los cuatro archivos Compose. Grafana
provisionó `cafeteria-telegram`, mantuvo el token protegido y activó la ruta
para `project=cafeteria`. La API de prueba de contactos de Grafana 13 devolvió
HTTP 200 y `status: success` al enviar una notificación real usando los secretos
guardados. Se utilizó la configuración completa de la integración, incluidos
`uid` y `secureFields`, para reutilizar el token almacenado sin copiarlo al
código de la prueba. La evidencia sin credenciales está en
`test-results/monitoring/telegram-delivery.json`, fuera de Git.

La aplicación, Prometheus, Grafana, Loki, Tempo y Alloy quedaron disponibles;
los cuatro targets de Prometheus estaban UP. Esta activación dejó la
plataforma normal encendida y conservó sus volúmenes. La prueba de contacto
envió un único mensaje; las pruebas de fallas previas usaron el webhook
interno desechable.

Posteriormente se cambió el destino al grupo del equipo mediante
`TELEGRAM_CHAT_ID` y se recreó únicamente Grafana para aplicar el cambio.
Se verificó el grupo con `getChat` y se envió una notificación de prueba desde
el contacto guardado: HTTP 200 y `status: success`. El grupo quedó como destino
de las alertas y recuperaciones. La evidencia sin credenciales está en
`test-results/monitoring/telegram-group-delivery.json`.

Referencias:
[provisioning de alertas](https://grafana.com/docs/grafana/latest/alerting/set-up/provision-alerting-resources/file-provisioning/),
[integración Telegram](https://grafana.com/docs/grafana/latest/alerting/configure-notifications/manage-contact-points/integrations/configure-telegram/),
[silenciamiento de notificaciones](https://grafana.com/docs/grafana/latest/alerting/configure-notifications/mute-timings/) y
[estados No Data y Error](https://grafana.com/docs/grafana/latest/alerting/fundamentals/alert-rule-evaluation/nodata-and-error-states/).
Para automatizar la prueba del contacto:
[API de notificaciones de Grafana](https://grafana.com/docs/grafana/latest/developer-resources/api-reference/http-api/alert-notifications/).
