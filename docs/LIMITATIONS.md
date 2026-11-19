# Informe de funcionalidades disponibles y limitaciones pendientes

**Proyecto:** ImageTrace OSINT · **Fecha:** 2026-11-19 · **Presupuesto de infraestructura:** US$0 · **Estado:** aplicación real, no maqueta.

Este documento es la respuesta explícita a la regla final: qué funciona de verdad, qué funciona parcialmente y qué no se implementa aún. Ninguna limitación se disfraza de resultado.

---

## 1. Funcionalidades disponibles y verificadas

| # | Requisito | Estado | Dónde |
|---|---|---|---|
| A1 | Subida JPG/PNG/WEBP, drag & drop, URL pública | ✅ | `UploadPanel.tsx`, `POST /api/investigations`, `/url` |
| A2 | SHA-256 + pHash DCT 16×16 (256 bits) | ✅ | `imaging.py` |
| A3 | Duplicados exactos y versiones similares (incluido **recorte/escala** con ORB/RANSAC) | ✅ | `alignment_assessment()`, `providers/local.py`, tests |
| A4 | Coincidencias en fuentes públicas mediante APIs autorizadas | ✅ parcial | Openverse + Wikimedia Commons + NASA Image Library + The Met (búsqueda por texto + verificación local) |
| A5 | Publicaciones que reutilizan la misma foto | ✅ acotado | Solo dentro del índice local y de los candidatos que esos cuatro catálogos devuelven |
| A6 | Organizar por fuente, fecha, similitud y confiabilidad | ✅ | Filtros/orden/agrupación en `Results.tsx` |
| A7 | Miniatura, URL, dominio, fecha, tipo, métrica explicada, enlace de comprobación | ✅ | `MatchCard.tsx`, esquema `matches` |
| B1 | EXIF, fecha de captura, cámara, software, resolución | ✅ | Pillow + ExifTool opcional |
| B2 | GPS solo con metadatos y autorización | ✅ | `exif_analysis(allow_gps=…)`, tests |
| B3 | Detección orientativa de alteraciones (ELA, ruido, compresión JPEG) | ✅ | `forensic_signals()`, con `not_conclusive: true` |
| B4 | Comparación de versiones, recorte, tamaño, compresión | ✅ | `compare_images()` + comparador UI |
| B5 | Iluminación, reflejos y «objetos» | ✅ con alcance declarado | Estadísticas de luminancia, regiones especulares candidatas, densidad de bordes, colores dominantes y contornos **sin etiquetas semánticas ni detección de personas** |
| B6 | OCR de carteles y texto visible | ✅ | Tesseract si existe; si no, RapidOCR/ONNX local; si falta todo, `unavailable` explícito |
| B7 | Diferenciar hechos / inferencias / desconocido | ✅ | `facts`, `inferences`, `unknowns`, `evidence_legend` |
| C1 | Conectores modulares de fuentes públicas | ✅ | `providers/base.py` + `registry.py` (6 proveedores: local, Openverse, Commons, NASA, Met, manual) |
| C2 | Enlace manual cuando no hay API compatible | ✅ | 16 enlaces: Lens, Bing, TinEye, Yandex, Google/DDG Images, Commons, NASA, Met, Internet Archive, Wayback, Flickr Commons, Europeana, GDELT, foros |
| C3 | Sin perfilado de personas ni búsqueda por rostro | ✅ | Prohibido en código, UI, informe y política |
| D1 | Lado a lado, deslizador, superposición, diferencias, hashes, regiones cambiadas | ✅ | `Comparator.tsx`, `diff.png` |
| E1 | Informe de 10 secciones con primera aparición conocida, duplicados, señales, limitaciones y conclusiones | ✅ | `reports.py` |
| E2 | Exportación PDF y JSON | ✅ | `reportlab`, endpoints y tests |
| E3 | Distinguir comprobado / similitud / no verificado | ✅ | `verified_matches`, `visual_similarities`, `unverified_results` |
| UI | Home, Panel, Resultados, Historial, responsive, es/pt-BR/en | ✅ | `frontend/src` |
| Seg | Validación, anti-malware básico, rate limit, SSRF, acceso privado, URLs firmadas, borrado, retención | ✅ | `security.py`, `service.py`, tests |
| Datos | SQLite + migraciones versionadas + almacenamiento temporal + retención | ✅ | `migrations/001..003` |
| Pruebas | 10 casos obligatorios + 9 adicionales (incluye NASA/Met y enlaces manuales) | ✅ 19/19 | `backend/tests/` |
| Entrega | `.env.example`, instalación, despliegue verificado, documentación | ✅ | `README.md`, `docs/` |

**Integraciones reales disponibles:** índice local (siempre), Openverse (API anónima, sin clave), Wikimedia Commons (MediaWiki API, sin clave), NASA Image & Video Library (API pública, sin clave), The Met Collection v1.1 (Open Access, sin clave), OCR local y PDF local. No hay ningún modo «demo» que produzca coincidencias ficticias en producción.

---

## 2. Limitaciones funcionales pendientes

| Limitación | Consecuencia real | Alternativa implementada hoy | Trabajo pendiente |
|---|---|---|---|
| **No existe búsqueda inversa automática de toda Internet** | Solo se consultan el índice propio y los catálogos configurados; la ausencia de coincidencias **no** prueba originalidad | Verificación local con SHA-256/pHash/ORB + enlaces manuales | Integrar un proveedor oficial de reverse-image o construir un índice propio autorizado con crawling respetando `robots.txt` |
| Openverse, Commons, NASA y The Met son búsqueda **por texto**, no por imagen | Dependen de palabras clave del usuario y del OCR; pueden no devolver la foto buscada | Cada candidato se descarga y verifica; los no verificados se etiquetan como tales | Proveedor con similitud visual real (no disponible gratis sin acuerdo) |
| Google Lens / Bing Visual Search / TinEye / Yandex sin API abierta | No se automatizan ni se scrapean | Enlaces manuales con instrucciones y descargo de responsabilidad | Solo si publican API oficial gratuita/compatible |
| Noticias, foros, blogs y archivos sin API de imagen compatible | No se consultan automáticamente | 16 enlaces manuales (GDELT, Internet Archive, Wayback, Flickr Commons, Europeana, DDG Images, foros) con su nota de alcance | Integrar APIs oficiales que devuelvan imágenes verificables, si aparecen gratuitas |
| Fechas de publicación original no verificables | `indexed_on` de Openverse y `timestamp` de Commons son indexación/subida, no publicación original | Se rotulan con su significado exacto; `first_known_appearance` dice «fecha más antigua entre fuentes consultadas» y nunca «primera publicación absoluta» | contraste con archivos/wayback y metadatos de la fuente original |
| Sin reconocimiento semántico de objetos | No se dice «hay un auto» ni «hay una persona» | Estadísticas de escena, contornos y regiones especulares sin etiquetas | Modelo de visión local con licencia abierta, **sin detección de rostros**, si se autoriza |
| Sin escaneo antivirus con firmas | Un archivo extremadamente elaborado podría no detectarse | Decodificación estricta, rechazo de políglotas, re-codificación y no exposición del original | ClamAV o sandbox aislado |
| Rate limiting en proceso | Con múltiples workers, el límite es por proceso | Límite por IP funcional en despliegue de un proceso | Redis / store compartido |
| PostgreSQL no conectado | La persistencia en plataformas con filesystem efímero se pierde | SQLite con migraciones versionadas (cumple «SQLite para desarrollo») | Adaptar `db.py` a SQLAlchemy/asyncpg + Alembic y usar Supabase/Neon/Render free Postgres |
| DNS rebinding residual en SSRF | `httpx` vuelve a resolver tras la validación | Bloqueo de DNS, IP, puertos y redirecciones | Transporte con IP fija o proxy de salida |
| OCR dependiente de modelos | Texto pequeño, rotado o en idiomas no soportados puede fallar | Dos motores y estado `unavailable` honesto | Modelos multilingües adicionales |
| Manipulación forense orientativa | ELA/ruido/compresión son sensibles a recompresión legítima | `disclaimer` y `not_conclusive` en UI, JSON y PDF | Peritaje humano; no se promete automatización concluyente |
| Sin cuentas ni recuperación | Si se pierde el token, se pierde el acceso a esas investigaciones (se borran por retención) | Token copiable y regenerable; borrado total | Login opcional con proveedor de identidad gratuito |
| Proveedores externos sujetos a límites | Openverse anónimo: 20/min y 200/día; puede responder 429 | `unavailable` explícito, sin reintento agresivo | Registro OAuth2 opcional de Openverse para mayor cuota (sigue sin costo, requiere cuenta) |

---

## 3. Restricciones éticas y legales (no son «pendientes»)

Estas funciones **no se implementarán** tal como están planteadas, por política del proyecto:

1. Reconocimiento facial, identificación de desconocidos o búsqueda de otras fotos de una persona por su rostro.
2. Perfilamiento, acoso, vigilancia o exposición de información privada.
3. Scraping de plataformas sin API o contra sus condiciones de acceso.
4. Uso de APIs de pago sin autorización expresa.
5. Presentar inferencias como pruebas concluyentes o inventar resultados/fechas/miniaturas.

---

## 4. Cómo se garantiza que no hay datos ficticios

- Los proveedores solo crean `Candidate` a partir de respuestas HTTP reales o filas reales del índice local.
- `verify_candidate()` debe descargar y decodificar una imagen antes de marcar `verified_*`; si falla, queda `unverified` con el motivo.
- `run_providers()` aísla excepciones: un proveedor caído produce `status=unavailable|error`, `result_count=0`.
- Los tests simulan **fallos de red**, nunca coincidencias: `Settings.for_tests()` desactiva proveedores externos por defecto.
- El informe incluye `policy.fabricated_results=false`, `sources_consulted`, limitaciones dinámicas por proveedor caído y conclusiones condicionadas a la evidencia.

---

## 5. Verificación de costos

| Componente | Costo |
|---|---|
| Openverse API (anónima) | US$0, sin clave |
| Wikimedia Commons API | US$0, sin clave |
| NASA Image & Video Library API | US$0, sin clave |
| The Met Collection API v1.1 | US$0, sin clave |
| RapidOCR/ONNX, Pillow, OpenCV, imagehash, reportlab | US$0, licencias open source |
| SQLite + archivos locales | US$0 |
| Render Free / Vercel Hobby | US$0/mes, sin tarjeta (ver `docs/DEPLOYMENT.md`) |
| Tesseract / ExifTool opcionales | US$0 (binarios del sistema) |

No se introdujeron claves de pago en `.env.example` ni en el código.

---

## 6. Conclusión

ImageTrace OSINT es una herramienta **operativa** para análisis local verificable, comparación de versiones, consulta de cuatro catálogos abiertos (Openverse, Commons, NASA, The Met) y generación de informes con niveles de evidencia explícitos. Su límite principal es estructural y se declara sin ambigüedad: **sin un proveedor real de búsqueda inversa o un índice propio autorizado, no puede afirmar que busca en toda Internet**. En lugar de simular esa capacidad, el sistema ofrece verificación local real, conectores gratuitos reales y 16 enlaces manuales transparentes para noticias, archivos y foros.
