# Referencia de API

Base: `/api` (same-origin). Documentación interactiva: `/docs` (OpenAPI/Swagger).

**Autenticación privada:** casi todos los endpoints requieren la cabecera `X-Owner-Token: <token>` (generado por el frontend en `localStorage`). Sin ella → `401`; con otro token → `404`. Los endpoints públicos son `/api/health`, `/api/config`, los assets firmados y las descargas firmadas.

## Metadatos

| Método | Ruta | Auth | Descripción |
|---|---|---|---|
| GET | `/api/health` | no | Estado y versión |
| GET | `/api/config` | no | Capacidades, límites, proveedores, motores OCR/ExifTool y aviso de honestidad |

## Investigaciones

| Método | Ruta | Auth | Body | Respuesta |
|---|---|---|---|---|
| POST | `/api/investigations` | sí | `multipart`: `file`, `keywords`, `allow_gps`, `allow_external`, `retention_hours`, `lang` | `201 {id, status, progress_url, detail_url}` |
| POST | `/api/investigations/url` | sí | JSON: `image_url`, `keywords`, `allow_gps`, `allow_external`, `retention_hours`, `lang` | `201` idem |
| GET | `/api/investigations` | sí | — | Historial con contadores y miniatura firmada |
| GET | `/api/investigations/{id}/status` | sí | — | `{status, stage, progress, error}` |
| GET | `/api/investigations/{id}` | sí | — | Detalle completo: metadatos, forense, OCR, `matches`, `provider_runs`, `manual_links`, `report`, URLs firmadas |
| DELETE | `/api/investigations/{id}` | sí | — | Borra filas y archivos |
| POST | `/api/investigations/{id}/compare` | sí | `multipart: file` | Comparación + `diff_url` |

`lang` acepta `es`, `pt` o `en`. `retention_hours` entre 1 y 168. `status`: `queued | processing | done | failed`. `stage`: `validation | hashes | metadata | forensics | ocr | providers | report | done | error`.

Ejemplo:

```bash
TOKEN=$(openssl rand -hex 32)
curl -H "X-Owner-Token: $TOKEN" \
  -F "file=@foto.jpg" -F "keywords=evento,ciudad" \
  -F "allow_gps=false" -F "allow_external=true" \
  -F "retention_hours=24" -F "lang=es" \
  http://localhost:8000/api/investigations
curl -H "X-Owner-Token: $TOKEN" \
  http://localhost:8000/api/investigations/<id>/status
```

## Informes

| Método | Ruta | Auth | Descripción |
|---|---|---|---|
| GET | `/api/investigations/{id}/report/json` | sí | JSON estructurado (10 secciones) |
| GET | `/api/investigations/{id}/report/pdf` | sí | PDF (reportlab) |
| POST | `/api/investigations/{id}/signed-link` | sí | `{format: pdf\|json}` → URL HMAC con TTL |
| GET | `/api/downloads/{id}/{pdf\|json}?exp=&sig=` | firma | Descarga con vencimiento; sin token en la URL |

## Assets firmados

`GET /api/assets/{id}/{display|thumb|diff}?exp=&sig=[&name=thumbs/<hash>.jpg]`

- Firma HMAC con vencimiento; sin firma → `403`.
- Solo se sirven derivados saneados; el original nunca es accesible.
- `display`: imagen principal. `thumb`: miniatura local de un resultado. `diff`: mapa de calor PNG.

## Índice local permitido

| Método | Ruta | Auth | Descripción |
|---|---|---|---|
| POST | `/api/index` | sí | Agrega imagen (file o `image_url`) con `label` y `retention_hours` |
| GET | `/api/index` | sí | Entradas del propietario |
| DELETE | `/api/index/{entry_id}` | sí | Elimina entrada y derivado |

## Privacidad

| Método | Ruta | Auth | Descripción |
|---|---|---|---|
| POST | `/api/privacy/purge` | sí | Elimina ya vencidos según política |
| DELETE | `/api/privacy/all` | sí | Borra todas las investigaciones, informes e índice del token |

## Códigos de error

| Código | Causa típica |
|---|---|
| 400 | Archivo inválido, formato no permitido, URL bloqueada por SSRF, parámetros fuera de rango |
| 401 | Falta `X-Owner-Token` |
| 403 | Firma ausente, inválida o vencida |
| 404 | Recurso inexistente o de otro propietario |
| 429 | Rate limit por minuto excedido (`Retry-After: 60`) |
| 201 | Investigación creada (el procesamiento continúa en segundo plano) |

## Nota sobre proveedores

Proveedores registrados: `local_index`, `openverse`, `wikimedia_commons`, `nasa_image_library`, `met_museum`, `manual_links`.

`provider_runs[].status` puede ser `ok | empty | skipped | unavailable | error`. Un estado `unavailable/error` significa **«no se pudo consultar esa fuente»**; nunca se rellena con coincidencias ficticias. `manual_links` son enlaces con `key`/`note_key` traducibles y no cuentan como `matches`.
