# ImageTrace OSINT

**Plataforma de investigación verificable de imágenes públicas.** Analiza una fotografía, calcula huellas criptográficas y perceptuales, lee EXIF, extrae texto, compara versiones, consulta fuentes públicas gratuitas y genera un informe PDF/JSON que separa **hechos comprobados**, **similitudes calculadas** y **resultados no verificados**.

> **Regla de honestidad:** no hay resultados simulados. No se afirma buscar «en toda Internet». No se usa reconocimiento facial, no se perfilan personas, no se scrapean plataformas sin API y no se requiere tarjeta de crédito ni clave de pago. Cuando un proveedor no ofrece API abierta, se entrega un **enlace de consulta manual**, nunca un resultado inventado.

Inspirada funcionalmente en [InfoChecker](https://infochecker.com/), con arquitectura propia y código abierto.

---

## 1. Inicio rápido (US$0)

```bash
git clone https://github.com/sebastisnzoth/reseaecheye.git
cd reseaecheye
bash scripts/setup.sh       # venv + dependencias + build del frontend
bash scripts/start.sh        # http://localhost:8000  (API + SPA en un proceso)
```

Requisitos: Python 3.10+, Node 18+, npm. No se necesita PostgreSQL, Docker, cuenta cloud ni credenciales.

Para desarrollo con recarga automática:

```bash
bash scripts/dev.sh          # FastAPI :8000 + Vite :5173 con proxy /api
```

Pruebas automatizadas:

```bash
bash scripts/test.sh         # 19 pruebas: carga, duplicados, recortes, EXIF, OCR, fallos, NASA/Met, PDF, auth, SSRF, borrado…
```

Si `npm` no está disponible, el backend funciona igual en `/docs` (OpenAPI) y `/api/config`; el frontend se construye después con `cd frontend && npm install && npm run build`.

---

## 2. Qué hace realmente

| Módulo | Implementación | Estado |
|---|---|---|
| **A — Búsqueda inversa** | Carga JPG/PNG/WEBP, drag & drop, URL pública con protección SSRF, SHA-256, pHash DCT 16×16, **alineación ORB/RANSAC para recortes**, índice local privado, conectores Openverse, Wikimedia Commons, NASA Image Library y The Met, verificación local de cada candidato, orden por fuente/fecha/similitud/confiabilidad | Real. **No** es un índice de toda Internet |
| **B — Forense** | EXIF (Pillow + ExifTool opcional), fecha de captura, cámara, dimensiones, GPS **solo con autorización**, ELA, ruido, compresión/JPEG quantization, iluminación, reflejos especulares, colores dominantes, OCR Tesseract/RapidOCR | Real, señales **orientativas** |
| **C — OSINT** | Conectores modulares: índice local, Openverse, Wikimedia Commons, NASA Image Library y The Met (todas APIs públicas sin clave); enlaces manuales para Lens / Bing / TinEye / Yandex, noticias (GDELT), archivos (Internet Archive / Wayback), foros, Flickr Commons y Europeana | Real + manual explícito |
| **D — Comparador** | Lado a lado, deslizador antes/después, superposición con transparencia, mapa de calor de diferencias, regiones cambiadas resaltadas, hashes, detección de recorte/escala/recompresión | Real |
| **E — Informe** | 10 secciones, primera aparición conocida entre fuentes consultadas, duplicados, limitaciones, conclusiones fundamentadas, exportación PDF + JSON, URLs firmadas con vencimiento | Real |

**Detalle técnico importante:** el pHash directo *no* es invariante a recortes. Por eso, cuando la distancia directa es alta, el sistema alinea geométricamente ambas imágenes con ORB + RANSAC y compara solo la región superpuesta, reportando método, cobertura, pHash alineado y error medio. Un recorte del 10 % pasa de «sin relación» a una similitud verificada ~94 % con explicación del cálculo.

### Pantallas

- **Home**: carga, opciones de privacidad, capacidades reales y límites declarados.
- **Panel de análisis**: progreso real por etapas, metadatos, forense, OCR, estado de proveedores, coincidencias, enlaces manuales.
- **Resultados**: galería con filtros por dominio/fecha/evidencia, orden y agrupación, comparador, informe.
- **Historial**: investigaciones privadas, borrado, exportación, índice propio, configuración de privacidad.
- Idiomas: **español, portugués de Brasil e inglés** (UI + informe).

---

## 3. Arquitectura

```
frontend/                 React 18 + TypeScript + Vite + Tailwind (HashRouter, i18n)
backend/app/
  main.py                 FastAPI, rutas privadas, assets firmados, hosting SPA
  service.py              ciclo de vida, progreso real, retención, comparación
  imaging.py              SHA-256, pHash, EXIF, ELA, OCR, ORB/RANSAC, comparador
  security.py             validación, SSRF, rate limiting, HMAC, token de propietario
  reports.py              informe JSON + PDF (reportlab), evidencia y limitaciones
  db.py + migrations/     SQLite + migraciones SQL versionadas (001/002/003)
  providers/              contrato + local / openverse / wikimedia / manual / registry
backend/tests/             pytest (TestClient, imágenes generadas, fallos simulados de red)
docs/                      arquitectura, seguridad, despliegue, API, limitaciones
```

- **Base de datos:** SQLite en `data/` con WAL y migraciones versionadas. PostgreSQL es una opción de despliegue **pendiente** (ver `docs/LIMITATIONS.md`); el requisito «SQLite para desarrollo» está cubierto.
- **Almacenamiento:** original privado fuera de cualquier ruta estática + derivado saneado; borrado por usuario y por retención automática (hilo daemon cada 15 min + `POST /api/privacy/purge`).
- **Progreso:** cada etapa escribe su avance real en la BD; el frontend hace polling de `/status`.

Más detalle: [`docs/ARCHITECTURE.md`](docs/ARCHITECTURE.md) · [`docs/API.md`](docs/API.md) · [`docs/SECURITY.md`](docs/SECURITY.md).

---

## 4. Fuentes externas (gratuitas, verificadas el 2026-11-19)

| Fuente | Uso real | Condición |
|---|---|---|
| [Openverse API `GET /v1/images/`](https://api.openverse.org/v1/images/?q=landscape&page_size=1) | Búsqueda **por texto** de candidatos con licencia abierta; cada miniatura se descarga y verifica localmente | Sin clave. Cabeceras verificadas: `20/min` y `200/day` anónimas. `indexed_on` se reporta como **fecha de indexación**, no de publicación |
| [Wikimedia Commons MediaWiki API](https://www.mediawiki.org/wiki/API:Imageinfo) | Búsqueda **por texto** de archivos; `timestamp` se reporta como **fecha de subida a Commons** | Sin clave; se envía `User-Agent` con contacto configurable |
| [NASA Image & Video Library API](https://images-api.nasa.gov/search?q=earth&media_type=image&page_size=1) | Catálogo público de imágenes; `date_created` se reporta como **fecha de creación/catalogación** | Sin clave; endpoint verificado el 2026-11-19 |
| [The Met Collection API v1.1](https://collectionapi.metmuseum.org/public/collection/v1.1/search?q=cat&hasImages=true&limit=2) | Repositorio Open Access; `objectDate` se reporta como **fecha de la obra/registro**, nunca publicación web | Sin clave; la búsqueda v1 fue retirada el 2026-10-01, se usa v1.1 |
| Índice local | Todas las imágenes analizadas/agregadas por el usuario, con SHA-256 + pHash | Privado, sin red |
| Internet Archive, Wayback, Flickr Commons, Europeana, GDELT, foros/blogs, DuckDuckGo Images | **Enlaces manuales** para noticias, archivos, foros y sitios indexados | Sin API de imagen inversa compatible; no se scrapea |
| [Google Lens](https://lens.google.com/), [Bing Visual Search](https://www.bing.com/visualsearch), [TinEye](https://tineye.com/), [Yandex](https://yandex.com/images/search) | **Enlaces manuales** | Sin API gratuita/abierta compatible; no se scrapea ni se fingen resultados |

Openverse, Commons, NASA y The Met **no son motores de búsqueda inversa por imagen**: son catálogos con búsqueda textual. La verificación de coincidencia la hace ImageTrace localmente. Esta distinción aparece en la UI, en `/api/config` y en cada informe. Los enlaces manuales (noticias, archivos, foros, buscadores) nunca se cuentan como coincidencias.

---

## 5. Seguridad y privacidad (resumen)

- Tipos y tamaños validados por **decodificación real** con Pillow; se rechazan extensiones no permitidas, políglotas script/markup y bombas de descompresión. El original nunca se sirve; se re-codifica un derivado limpio.
- **SSRF:** solo `http/https` en puertos 80/443, sin credenciales en la URL, bloqueo de IP privadas/loopback/link-local/reservadas y de `.local/.internal`, resolución DNS previa y **revalidación de cada redirección**, límite de bytes y `Content-Type`.
- **Rate limiting** por IP, HMAC con vencimiento para assets/informes, `X-Content-Type-Options`, CSP en assets, `Cache-Control: private, no-store`.
- **Acceso privado:** token aleatorio de 256 bits en `localStorage` (`X-Owner-Token`); se guarda solo su HMAC en la BD. El token **nunca** aparece en una URL. No hay cuentas ni login.
- **GPS** solo si existe EXIF y el usuario lo autoriza; en caso contrario se indica «presente pero no mostrado».
- **Prohibido:** reconocimiento facial, identificación de personas, perfilamiento, acoso o vigilancia. Ver política en [`docs/SECURITY.md`](docs/SECURITY.md).

---

## 6. Configuración

Copiá `.env.example` a `.env` (sin credenciales). Variables principales:

| Variable | Default | Descripción |
|---|---|---|
| `IMAGETRACE_SECRET_KEY` | auto-generado | HMAC de firmas; vacío = archivo local `0600` |
| `IMAGETRACE_DATA_DIR` | `./data` | Originales, derivados, informes, BD |
| `IMAGETRACE_DATABASE_URL` | `sqlite:///./data/imagetrace.db` | SQLite |
| `IMAGETRACE_RETENTION_HOURS` | `24` | Eliminación automática |
| `IMAGETRACE_RATE_LIMIT_PER_MINUTE` | `30` | Límite por IP |
| `IMAGETRACE_EXTERNAL_PROVIDERS` | `true` | Apaga conectores externos |
| `IMAGETRACE_CONTACT_EMAIL` | vacío | Recomendado por la política de User-Agent de Wikimedia |
| `IMAGETRACE_CORS_ORIGINS` | vacío | Orígenes permitidos en despliegue separado |
| `VITE_API_BASE_URL` | vacío | URL del backend si el frontend se sirve en otro dominio |

**OCR:** si el binario `tesseract` está instalado se usa Tesseract; si no, se usa **RapidOCR + ONNX Runtime** (código abierto, sin servicio externo). Si faltan ambos, el informe dice explícitamente «OCR no disponible» y no inventa texto. **ExifTool** es opcional; sin él se usa el subconjunto EXIF de Pillow.

> Nota de dependencias: `rapidocr-onnxruntime` declara `opencv-python` (build con libGL). En servidores sin X se ejecuta `bash scripts/fix-opencv.sh` para conservar `opencv-python-headless`. El `Dockerfile` ya lo hace.

---

## 7. Despliegue gratuito verificado

| Opción | Costo | Verificación | Limitación honesta |
|---|---|---|---|
| **Local / VPS propio** | US$0 | Este repositorio | Ninguna |
| **Render Free Web Service** (Docker, `render.yaml`) | $0/mes, 512 MB | [Render Pricing](https://render.com/pricing) y [Free docs](https://render.com/docs/free) | Se apaga tras 15 min, 750 h/mes, **sistema de archivos efímero**: SQLite y uploads se pierden al reiniciar. Free Postgres expira a los 30 días |
| **Vercel Hobby** (solo frontend) | $0/mes, 100 GB | [Vercel Pricing](https://vercel.com/pricing) | El backend Python/OpenCV/SQLite **no** encaja en serverless; usar junto a Render y `VITE_API_BASE_URL` + `IMAGETRACE_CORS_ORIGINS` |
| **Render Static Site** para `frontend/dist` | $0 | [Render Free docs](https://render.com/docs/free) | Igual que Vercel: requiere backend aparte |

No se verificó ni se usa ningún servicio que exija tarjeta de crédito. Fly.io, Railway y Azure/Bing Visual Search quedan **fuera** del presupuesto US$0. Instrucciones completas: [`docs/DEPLOYMENT.md`](docs/DEPLOYMENT.md).

---

## 8. Limitaciones y entrega

Informe completo de funcionalidades disponibles y pendientes: [`docs/LIMITATIONS.md`](docs/LIMITATIONS.md).

Resumen de pendientes honestos: búsqueda inversa global real (requiere proveedor/índice con licencia), PostgreSQL gestionado, escaneo antivirus dedicado, rate limiting distribuido, detección semántica de objetos con modelo propio, y verificación externa de fechas de publicación original. Ninguno se simula.

**Entrega:** repositorio documentado, app web funcional, backend operativo, SQLite con migraciones, integraciones reales disponibles, 19 pruebas automatizadas, `.env.example` sin credenciales, instrucciones de instalación, opciones de despliegue gratuito verificadas e informe de limitaciones.

Licencia MIT. Creado con fines de investigación responsable de imágenes **públicas**; respete derechos de autor, privacidad y condiciones de acceso de cada plataforma.

---

## 9. Nota de integración con `main` (implementación previa)

`main` incorporó dos commits de un MVP local-first anterior (`8107224`, `ca80514`) mientras esta rama estaba abierta. Al integrarlos se conservó **toda la historia** y se tomaron estas decisiones explícitas:

- La implementación activa es la de esta rama (6 proveedores, URLs firmadas con vencimiento, 19 pruebas, informes PDF/JSON de 10 secciones).
- Se conservan y adaptan el workflow de CI (`.github/workflows/ci.yml`, ahora contra `requirements.txt` y `pytest.ini` de la raíz) y la investigación `docs/GITHUB_OPEN_SOURCE_RESEARCH.md`.
- Los archivos incompatibles del MVP anterior (API con `X-API-Key`, `/api/analyze`, `/api/compare`, y sus pruebas) se archivan **sin borrarlos** en `docs/legacy-mvp/`, fuera de `testpaths`, para que la suite actual siga siendo verde. Ver `docs/legacy-mvp/README.md`.
- Proveedores: la consulta exacta por SHA-1 en la API oficial de Wikimedia (`list=allimages&aisha1`) está documentada en [MediaWiki API:Allimages](https://www.mediawiki.org/wiki/API:Allimages); la política de User-Agent en [Wikimedia APIs/Access policy](https://www.mediawiki.org/wiki/Wikimedia_APIs/Access_policy). Nuestra integración usa `generator=search` + `prop=imageinfo` y verificación local de candidatos, y nunca atribuye una URL pública a un ítem del índice privado.
- Aquella evaluación desplegada en Vercel/Render era de un **único operador** con clave compartida y disco efímero; esta versión agrega aislamiento por token de propietario, firmas con vencimiento y retención. Sigue sin ser un SaaS público multiusuario.
