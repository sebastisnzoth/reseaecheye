# Arquitectura técnica — ImageTrace OSINT

## 1. Vista general

```
Navegador (React/TS/Tailwind, es/pt-BR/en)
        │  X-Owner-Token + /api/*
        ▼
FastAPI (uvicorn, mismo origen; sirve frontend/dist)
   ├── security.py      validación, SSRF, rate limit, HMAC, owner hash
   ├── service.py       orquestación por etapas, retención, comparación
   ├── imaging.py       hashes, EXIF, ELA, OCR, ORB/RANSAC, comparador
   ├── providers/       local | openverse | wikimedia | manual | registry
   ├── reports.py       informe JSON + PDF
   └── db.py            SQLite + migrations/*.sql
        │
        ├── data/investigations/<id>/  original (privado), display, thumbs, diff.png, report.*
        ├── data/index/                derivados del índice permitido
        └── data/imagetrace.db         investigaciones, matches, provider_runs, index_entries, audit_log
```

El frontend y el backend comparten origen en el despliegue recomendado, por lo que no se necesita CORS. Para despliegue separado se usan `VITE_API_BASE_URL` y `IMAGETRACE_CORS_ORIGINS`.

## 2. Modelo de evidencia

Todo resultado lleva un `evidence_level`:

| Nivel | Cómo se obtiene | Qué significa |
|---|---|---|
| `verified_exact` | SHA-256 idéntico entre la imagen consultada y la imagen descargada/indexada | Mismo archivo. No prueba autoría ni fecha |
| `verified_visual` | distancia pHash ≤ 32/256, **o** alineación ORB/RANSAC con cobertura ≥ 0.30, pHash alineado ≤ 64, MAE ≤ 70 y ≥ 8 inliers | Misma escena/versión probable. Requiere comprobación manual de la fuente |
| `unverified` | candidato devuelto por un proveedor sin imagen verificable o por debajo de umbrales | **No es una coincidencia**; se muestra para transparencia |

Métrica directa: `similitud = 100 × (1 − distancia Hamming / 256)` sobre pHash DCT 16×16.
Métrica alineada: `100 × (0.5 × (1 − pHash_alineado/256) + 0.5 × (1 − MAE/255))`, calculada solo sobre la región superpuesta tras estimación afín.

Los hechos EXIF se etiquetan como `fact` **del archivo**, las señales forenses como `inference`, y lo ausente como `unknown`. El informe nunca convierte una inferencia en prueba.

## 3. Ciclo de vida de una investigación

1. `POST /api/investigations` (multipart) o `/url` (JSON).
2. `sanitize_image()`: límite de bytes, extensión, formato real por Pillow, `verify()`, límite de píxeles, rechazo de políglotas, derivado saneado.
3. Inserción en BD (`status=queued`, `progress=5`) + entrada en el índice local del propietario.
4. `ThreadPoolExecutor` ejecuta `run_pipeline()` (o inline con `IMAGETRACE_SYNC_PROCESSING=true` en tests):
   - `validation` 10 → `hashes` 25 → `metadata` 40 → `forensics` 55 → `ocr` 68 → `providers` 80 → `report` 94 → `done` 100.
   - Cada etapa actualiza la BD; el frontend consulta `/status` cada 1,3 s mientras `queued|processing`.
5. `run_providers()` ejecuta cada conector con `try/except` aislado, registra `provider_runs` (estado, mensaje, duración, cantidad) y persiste solo candidatos reales.
6. `build_report()` + `render_pdf()` + `persist_report()`.
7. Un fallo parcial marca `failed`, conserva lo calculado y añade la limitación; no se rellenan huecos con datos falsos.

## 4. Proveedores

Contrato en `providers/base.py`:

```python
class Provider:
    name, label, kind
    def run(ctx: SearchContext) -> ProviderOutcome
```

`SearchContext` aporta imagen, SHA-256, pHash, palabras clave, términos OCR, permisos, directorio y un `fetch` con protección SSRF. `registry.PROVIDERS` es el único punto para agregar fuentes.

- **local**: compara contra `index_entries` e investigaciones previas del mismo `owner_hash`. Excluye la entrada propia. Hasta 30 comprobaciones de alineación por investigación para contener coste de CPU.
- **openverse**: `GET https://api.openverse.org/v1/images/?q=…&page_size=…`; usa `thumbnail` y `indexed_on`; sin clave.
- **wikimedia_commons**: `action=query&generator=search&gsrnamespace=6&prop=imageinfo&iiprop=url|timestamp|size|mime|extmetadata`; usa `thumburl`.
- **nasa_image_library**: `GET https://images-api.nasa.gov/search?q=…&media_type=image&page_size=…`; usa `links[rel=preview]`, `nasa_id` y `date_created`.
- **met_museum**: `GET /public/collection/v1.1/search?q=…&hasImages=true&limit=…` + `/objects/{id}`; usa `primaryImageSmall` y `objectDate`. La v1 de búsqueda fue retirada en 2026-10-01.
- **manual_links**: 16 enlaces con palabras clave/OCR (motores inversos, noticias, archivos, foros, repositorios); `candidates=[]` siempre. Llevan `key`/`note_key` para traducción en la UI.

`verify_candidate()` descarga la miniatura (SSRF + límite + Content-Type), calcula SHA-256/pHash, aplica alineación si hace falta, guarda una copia saneada en `thumbs/` y clasifica. Las miniaturas locales evitan que el navegador haga peticiones a terceros al ver resultados.

## 5. Base de datos y migraciones

`db.py` aplica `migrations/*.sql` en orden y registra versiones en `schema_migrations`:

- `001_init.sql`: `investigations`, `matches`, `index_entries`.
- `002_provider_runs.sql`: `provider_runs`, `audit_log`, `exiftool_available`.
- `003_comparisons.sql`: `comparison_json`, `scene_json`, `manual_links_json`.

WAL + `foreign_keys=ON` + una conexión por unidad de trabajo (seguro con hilos). `ON DELETE CASCADE` en `matches` y `provider_runs`.

## 6. Retención

- Cada investigación tiene `expires_at` según `retention_hours` (1–168 h).
- Hilo daemon cada 15 min + `POST /api/privacy/purge` ejecutan `purge_expired()`.
- `DELETE /api/investigations/{id}` elimina filas, índice asociado y directorio completo.
- `DELETE /api/privacy/all` borra todo lo del token actual.

## 7. Estrategia de pruebas

`backend/tests/` usa `TestClient`, `Settings.for_tests()` (SQLite temporal, procesamiento síncrono, proveedores externos apagados) e imágenes generadas con Pillow/NumPy. Los fallos de red se simulan **solo en tests** con un `httpx.Client` offline inyectado en los módulos proveedor; también existe un fixture `catalog_app` con respuestas JSON de forma real de NASA/Met y miniaturas bloqueadas por SSRF para comprobar que los candidatos quedan **sin verificar** y sin métricas inventadas. En producción no existe ningún modo de resultados simulados. Cobertura (19 pruebas): cargas válidas/inválidas, duplicado exacto, recorte, EXIF + GPS, sin metadatos, fallo de los 4 proveedores externos y aislamiento de excepciones, parseo de NASA/Met, enlaces manuales, PDF/JSON, acceso no autorizado, URLs firmadas, resultados vacíos, borrado, SSRF, rate limit, migraciones e índice local.

## 8. Decisiones deliberadas

- **SQLite antes que PostgreSQL**: presupuesto US$0 y simplicidad; la capa SQL es estándar, la adaptación a Postgres queda documentada como pendiente.
- **Un proceso**: FastAPI sirve `frontend/dist`, eliminando CORS y dos despliegues en local.
- **Sin login**: token de propietario opaco en el navegador; no se recogen correos ni datos personales.
- **Sin modelos de detección facial**: prohibición explícita en código, UI e informe.
- **Sin API de pago**: Openverse/Commons son gratuitas; el resto son enlaces manuales.
