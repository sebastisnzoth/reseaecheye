# Seguridad, privacidad y uso responsable

## 1. Modelo de acceso

No existen cuentas, contraseñas ni login. El navegador genera un token aleatorio de 256 bits (`crypto.getRandomValues`) y lo envía en la cabecera `X-Owner-Token`. El servidor guarda únicamente `HMAC(secret_key, token)` como `owner_hash`. Sin el token:

- `GET/DELETE /api/investigations/*`, informes, historial, índice y privacidad → **401**.
- Con otro token → **404** (no se revela existencia de recursos ajenos).
- El token **nunca** se incluye en URLs, logs ni en el informe.

`IMAGETRACE_SECRET_KEY` se genera automáticamente en `data/.secret_key` con permisos `0600` si no se define. En producción debe fijarse como variable de entorno y rotarse si se filtra (rotar invalida firmas y tokens previos).

## 2. Carga de archivos

| Control | Implementación |
|---|---|
| Tamaño | `IMAGETRACE_MAX_UPLOAD_MB` (15 MB por defecto), también en descargas por URL |
| Extensión | `.jpg/.jpeg/.png/.webp` |
| Tipo real | `PIL.Image.open().format`, no el `Content-Type` declarado |
| Decodificación | `verify()` + `load()` con `Image.MAX_IMAGE_PIXELS` (40 MP) |
| Políglotas/malware | rechazo de marcadores `<svg`, `<script`, `<?php`, `<%`, `<!doctype html`, `#!/` en los primeros 2 KB; **re-codificación** del derivado; el original nunca se sirve ni se ejecuta; ningún archivo se pasa a un shell |
| Servido | solo derivados con `Content-Type` forzado, `X-Content-Type-Options: nosniff`, CSP restrictiva, `Cache-Control: private, no-store` |

Limitación honesta: **no hay escaneo antivirus con firmas ni sandbox de ejecución** (pendiente, ver `docs/LIMITATIONS.md`). La defensa se basa en decodificación estricta, re-codificación y no exposición del original.

## 3. SSRF en URLs externas

`validate_public_url()` se aplica **antes de cada petición y en cada redirección** (máximo 3):

- solo `http`/`https`, puertos 80/443;
- sin `user:pass@`, sin `file://`, `ftp://`, `gopher://`;
- bloqueo de `localhost`, `metadata.google.internal`, `*.local`, `*.internal`, `*.localhost`;
- bloqueo de literales IP privados/loopback/link-local/reservados/multicast/no especificados e IPv4-mapeadas;
- resolución DNS con `getaddrinfo` y rechazo si **cualquier** respuesta es privada/reservada;
- `User-Agent` identificable, `timeout`, `Content-Type` de imagen y límite de bytes en streaming.

Riesgo residual: DNS rebinding entre la validación y la conexión de `httpx` (la librería vuelve a resolver). No se permite `IMAGETRACE_ALLOW_PRIVATE_NETWORKS=true` en producción; existe solo para entornos controlados. Para mitigación total se requiere un transporte con IP fija/proxy de salida (pendiente).

## 4. URLs firmadas

- `sign_resource()` genera `exp` + `sig = HMAC-SHA256(secret, "recurso:exp")`.
- `verify_signature()` compara en tiempo constante y rechaza firmas vencidas.
- Recursos: `asset:<id>:display|thumb|diff:<nombre>` y `report:<id>:pdf|json`.
- TTL por defecto 600 s (`IMAGETRACE_SIGNED_URL_TTL`).
- La firma **no es un token de acceso**: no contiene el `X-Owner-Token`. Los endpoints de datos siguen exigiendo el token; las capacidades firmadas son de corta duración para miniaturas/informes.
- `thumb` valida el nombre con `^thumbs/[a-f0-9]{32}\.(jpg|png)$` y comprueba que la ruta resuelta esté dentro del directorio de la investigación (anti path-traversal).

## 5. Limitación de solicitudes

`RateLimiter` por IP, ventana fija de 60 s, aplicado a creación de investigaciones, comparación e índice. Responde `429` con `Retry-After: 60`. Es **en proceso**: con múltiples workers se necesita un store compartido (Redis) — pendiente. No sustituye a un WAF.

## 6. Privacidad de datos

- GPS EXIF: si existe y el usuario **no** autoriza, se informa «presente pero no mostrado»; si autoriza, se muestran coordenadas con la advertencia de que son declaraciones del archivo no verificadas externamente.
- Sin analítica de terceros, sin cookies de seguimiento, sin fuentes externas cargadas por el navegador, sin hotlinking de miniaturas de resultados.
- Retención automática y borrado inmediato a solicitud del usuario (`DELETE /api/investigations/{id}`, `/api/privacy/all`, `/api/privacy/purge`).
- `audit_log` guarda acción, hash del propietario y timestamp; no guarda el token ni contenido de imágenes.

## 7. Política de uso responsable (obligatoria)

ImageTrace OSINT está diseñada para **imágenes públicas** y verificación periodística/documental. Está **prohibido** utilizarla para:

1. Reconocimiento facial, identificación de desconocidos, búsqueda de otras fotos de una persona por su rostro o perfilamiento biométrico. El código no contiene detectores de rostros ni de personas.
2. Acoso, vigilancia, doxxing, exposición de información privada o inferencia de ubicación de personas sin autorización.
3. Violar derechos de autor, licencias, `robots.txt` o condiciones de acceso de plataformas. Las imágenes de resultados se usan solo como miniaturas de verificación con su licencia/autor declarados y un enlace a la fuente.
4. Presentar señales forenses (ELA, ruido, compresión) como prueba concluyente o peritaje judicial.
5. Interpretar la ausencia de coincidencias como prueba de originalidad o de inexistencia de copias.

Los conectores externos respetan las condiciones de las APIs públicas: sin clave, con `User-Agent` de contacto, timeout corto, límite de resultados y sin scraping de plataformas que no ofrecen API.

## 8. Reporte de vulnerabilidades

Abrí un issue en el repositorio sin incluir datos sensibles ni imágenes privadas. Para un problema con impacto en seguridad, describí reproducción mínima y versión; no publiques tokens reales.
