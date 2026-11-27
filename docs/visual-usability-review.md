# Revisión visual y de usabilidad

El paso 3 de cierre de la web revisa la interfaz existente de Café Nube en
Chromium con anchos de 320, 390, 768, 1280 y 1440 px. Se recorrieron menú,
categorías, carrito, confirmación, historial vacío y con pedidos, puntos
pendientes, errores y recuperación. Se conserva el diseño de la cafetería.

## Hallazgos y correcciones

| Hallazgo observado | Corrección |
|---|---|
| A 320 y 390 px se ocultaba Mis pedidos; volver al historial requería completar otra compra. | Menú, Mis pedidos y Carrito permanecen visibles en todos los anchos. La cabecera móvil usa dos filas y marca la página actual. |
| A 320 px se recortaban el título y la descripción del hero; `overflow:hidden` disimulaba el problema. | El contenido puede encogerse dentro de la cuadrícula y la tipografía se adapta al ancho; se verifica el rectángulo del texto, no solo el ancho del documento. |
| La cabecera dejaba contenido detrás al navegar por anclas. | Fondo opaco y separación de scroll para menú y carrito. Todo vuelve a la sección del catálogo. |
| La cabecera no reflejaba el resultado de agregar productos con el carrito fuera de pantalla. | Contador de unidades actualizado mediante el mecanismo OOB de HTMX y anunciado con `aria-live`. |
| Los controles de cantidad medían 30 px. | Controles de 44 × 44 px y áreas de navegación, categorías y eliminación de al menos 44 px de alto. |
| Texto blanco sobre botones naranja: contraste aproximado 3.03:1. | Los botones principales y el contador usan un naranja oscuro con contraste blanco aproximado 5.47:1. El color de la ilustración permanece como acento. |
| El fallo HTTP 503 al agregar un producto solo aparecía en la consola. | Fragmento de error visible junto al producto o dentro del carrito; se conservan estado HTTP, contenido y sesión para reintentar. |
| Durante una solicitud no había indicador y al deshabilitar el botón se perdía el foco. | HTMX deshabilita el botón, muestra Agregando… y el código de interfaz restaura el foco al control o al título del carrito si se eliminó el elemento. Respeta un cambio de foco realizado durante la espera. |
| El error al confirmar quedaba debajo del hero y podía pasar inadvertido en móvil. | Aviso al inicio del contenido y enlace Volver al carrito. El reintento conserva un único pedido y una acreditación. |
| Encabezados de pedidos y etiquetas de puntos competían por el espacio móvil. | Encabezado apilado, texto y cantidades con separación suficiente y precios que conservan su espacio. |
| El recibo decía Total pagado aunque no existe procesamiento de pagos. | Se muestra Total del pedido. |
| El historial mostraba timestamps UTC sin identificar la zona. | Elementos `time` con ISO original; `Intl.DateTimeFormat` muestra la hora local del navegador y se reaplica al actualizar el historial. Sin JavaScript se conserva el valor con zona explícita. |

Se añadió un enlace Saltar al contenido y estilos de foco visibles. Se conserva
la preferencia de movimiento reducido. No se sustituyen la protección CSRF,
las cookies ni la política CSP para realizar los recorridos.

## HTMX y código de interfaz

Los errores utilizan la extensión oficial `htmx-ext-response-targets` 2.0.4,
vendorizada junto con HTMX. Se verificaron la integridad del paquete y su
SHA-384, y se conserva su licencia. Se sirve desde el propio frontend, con
`script-src 'self'` y sin scripts inline ni eval. Consulta
[`vendor/README.md`](../frontend/app/static/vendor/README.md).

`HX-Retarget` selecciona el aviso correspondiente y `HX-Reswap: innerHTML`
evita sustituir toda la tarjeta o perder el carrito. El estado 404/503 no se
convierte en 200 para mostrar el aviso. La siguiente respuesta exitosa limpia
el error del producto mediante OOB.

[`storefront.js`](../frontend/app/static/storefront.js) usa eventos de HTMX y
APIs nativas del navegador para el foco y el formato de fechas. El renderizado
de errores sigue en Jinja con escape automático. El chequeo de integridad de
la dependencia y el control de scripts locales se mantienen en las pruebas
de seguridad del frontend.

## Verificación y evidencias

La suite añade ocho casos a los cuatro recorridos anteriores:

1. Cinco anchos con navegación accesible, filtros, categoría sin productos,
   historial vacío, anclas y ausencia de desbordamiento y recorte de texto.
2. Flujo de teclado a 320 px: salto al contenido, agregar, aumentar, eliminar,
   restauración del foco, recibo e historial con hora local.
3. Menú pausado: carga y botón deshabilitado, error visible 503 y reintento
   exitoso sin navegación ni pérdida del carrito.
4. Pedidos detenido: error de checkout visible y reintento sin duplicar pedido
   ni puntos, contrastados también con PostgreSQL.

Los dos casos existentes de puntos pendientes se ejecutan ahora a 320 px y
capturan recibo e historial degradados antes de su recuperación automática.
El intervalo de polling sigue siendo de 15 segundos. Los recorridos normales
rechazan errores inesperados de consola, JavaScript, HTTP o red; las pruebas
negativas comprueban los errores HTTP provocados y que no haya excepciones de JS.

Se usan servicios y PostgreSQL reales en el Compose `cafeteria-e2e`, separado
del proyecto normal y de su grupo de Telegram. Las pruebas detienen o pausan
solo servicios de ese entorno, los restauran y eliminan sus datos al terminar.

```powershell
.\tests\.venv\Scripts\python.exe scripts/run_e2e.py
```

Las capturas previas están en `test-results/visual-before/`. Las capturas
actuales se generan en `test-results/browser/usability/`; el workflow publica
`browser-evidence` durante siete días. Esos archivos están excluidos de Git.
La [guía de Playwright](browser-testing.md) describe instalación y depuración.

### Resultado de la ejecución completa

Validación local del 26 de noviembre de 2026, con Python 3.13.1 en Windows y
Docker Desktop. El runner reconstruyó el entorno aislado y finalizó con código 0.

| Comprobación | Resultado |
|---|---|
| Contratos OpenAPI | 3 válidos. |
| Frontend y observabilidad común | 93 pruebas aprobadas en 44.08 segundos. |
| HTTP integral | 31 pruebas aprobadas en 147.58 segundos. |
| Chromium con JavaScript y HTMX | 12 pruebas aprobadas en 80.20 segundos. |
| Ruff y formato del frontend y pruebas de navegador | Correctos. |
| Workflow E2E y enlaces locales de las guías | YAML válido y destinos existentes. |

Se inspeccionaron las capturas de inicio y catálogo en escritorio y móvil,
carrito, recibo e historial, incluyendo puntos pendientes y avisos de error.
El runner eliminó sus contenedores, red y volumen al terminar. La aplicación
normal conserva sus datos; se reconstruyó únicamente su frontend para revisar
los cambios en `http://localhost:8000`.

Se mantienen las advertencias conocidas de Starlette con HTTPX y de la fixture
`base_url` de Playwright. No impidieron ejecutar los casos. El workflow está
preparado localmente; esta validación no es una ejecución remota de GitHub.

La revisión comprende Chromium con viewport móvil; no equivale a una prueba
en dispositivos físicos ni a una auditoría completa de accesibilidad.

Referencias: [response-targets](https://htmx.org/extensions/response-targets/),
[botones deshabilitados](https://htmx.org/attributes/hx-disabled-elt/),
[actualizaciones OOB](https://htmx.org/attributes/hx-swap-oob/) y
[foco de teclado](https://www.w3.org/WAI/WCAG22/Understanding/focus-visible.html).
