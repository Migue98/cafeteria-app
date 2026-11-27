# HTMX vendorizado

- Versión: **2.0.4**, la misma que utilizaba antes el CDN.
- Origen: https://raw.githubusercontent.com/bigskysoftware/htmx/v2.0.4/dist/htmx.min.js
- Licencia: `LICENSE.htmx`, Zero-Clause BSD, obtenida del mismo tag oficial.
- SHA-256 del archivo con saltos de línea LF:
  `69caefd0da92269066e725d7fe175e26b9d50c962e3056459c0c477154cdb9d3`.

Se conserva el código de la distribución sin modificaciones funcionales.
La prueba del frontend comprueba este hash normalizando CRLF a LF.
No se obtiene código de Internet durante la ejecución ni el build del frontend.
Para actualizar, revisar el release oficial, conservar la licencia, cambiar
el archivo y su hash, y verificar carrito y polling con CSP activa.

## Extensión response-targets

- Versión: **2.0.4**, compatible con HTMX 2.
- Origen: paquete oficial `htmx-ext-response-targets@2.0.4` del registro npm.
- Archivo: `response-targets-2.0.4.min.js`, sin modificaciones.
- Licencia: `LICENSE.response-targets`, Zero-Clause BSD, incluida en el paquete.
- SHA-384 (LF):
  `4f8d6882550fbd72c6055c91759b154713569ce3aa0b29da3ee6e35158f186c8c54caac524610c9b7ff428698d43e3e0`.
- Se verificó también la integridad SHA-512 del tarball del registro.

La extensión oficial permite mostrar un error HTTP en un fragmento específico
del carrito mediante `HX-Retarget`, conservando el estado HTTP 4xx/5xx. Se activa
en el menú y se sirve localmente, después de HTMX, con CSP sin scripts inline.
Referencia: https://htmx.org/extensions/response-targets/.
