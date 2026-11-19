# Opciones de despliegue gratuito verificadas

Verificado el **2026-11-19**. Ninguna opción listada exige tarjeta de crédito ni API de pago.

## 0. Local / servidor propio — US$0, recomendado

```bash
bash scripts/setup.sh
bash scripts/start.sh           # 0.0.0.0:8000
```

Sirve SPA + API desde FastAPI. SQLite persiste en `data/`. Es la única opción sin limitaciones de filesystem efímero.

## 1. Render Free (Docker) — $0/mes

**Verificación:** [Render Pricing](https://render.com/pricing) muestra Hobby `$0/mo` y «Free $0/month · 512 MB RAM»; [Render Free docs](https://render.com/docs/free) documenta web services gratuitos, 750 h/mes, spin-down a los 15 min, filesystem efímero y Postgres Free que expira a los 30 días. La comparativa oficial de Render ([platforms with a real free tier](https://render.com/articles/platforms-with-a-real-free-tier-for-developers-in-2026)) indica que el plan gratuito no requiere tarjeta de crédito.

Pasos:

1. Subí el repositorio a GitHub (rama actual).
2. En Render: **New → Web Service → Docker**, o usá el blueprint `render.yaml` incluido.
3. Variables: `IMAGETRACE_SECRET_KEY` (generada por Render), `IMAGETRACE_EXTERNAL_PROVIDERS=true`, `IMAGETRACE_RETENTION_HOURS=24`, `IMAGETRACE_CONTACT_EMAIL` (recomendado para Wikimedia).
4. Health check: `/api/health`.

**Limitaciones reales:** al reiniciarse o dormirse el servicio se pierden `data/` y la BD SQLite. Para un MVP de demostración es aceptable; para persistencia gratuita se requiere migrar la capa de datos a PostgreSQL gestionado (pendiente) o un disco persistente de pago (fuera del presupuesto). No se afirma persistencia que no existe.

## 2. Vercel Hobby (frontend) + Render Free (backend) — $0/mes

**Verificación:** [Vercel Pricing](https://vercel.com/pricing) muestra Hobby `$0/mo`, 100 GB de transferencia y despliegues ilimitados. La comparativa de Render señala que Hobby no requiere tarjeta de crédito.

El backend (FastAPI + OpenCV/ONNX + SQLite + archivos) **no** se despliega en Vercel Functions: dependencias nativas, tamaño y filesystem efímero. Por eso se separa:

```bash
# Backend en Render: permitir el origen del frontend
IMAGETRACE_CORS_ORIGINS=https://mi-frontend.vercel.app

# Frontend en Vercel (build-time)
VITE_API_BASE_URL=https://mi-backend.onrender.com
cd frontend && npm run build
```

`VITE_API_BASE_URL` hace que `api.ts` prefije todas las llamadas y URLs firmadas; sin la variable, todo es same-origin. En Vercel: Root Directory `frontend`, Framework `Vite`, Build Command `npm run build`, Output `dist`.

**Limitación:** dos servicios, cold start del backend, CORS estricto y el mismo filesystem efímero de Render.

## 3. Render Static Site para `frontend/dist` — $0

Alternativa a Vercel usando [Render Free docs](https://render.com/docs/free): publicar `frontend/dist` como Static Site y apuntar `VITE_API_BASE_URL` al backend. Aplica la misma limitación de CORS y de dos servicios.

## 4. Docker local / CI — $0

```bash
docker build -t imagetrace-osint .
docker run --rm -p 8000:8000 -e IMAGETRACE_SECRET_KEY="$(openssl rand -hex 32)" \
  -v "$PWD/data:/app/data" imagetrace-osint
```

El volumen evita la pérdida de datos. `HEALTHCHECK` consulta `/api/health`.

## 5. Opciones descartadas (honestidad presupuestaria)

| Servicio | Motivo |
|---|---|
| Bing Visual Search / Azure | API de pago con clave; se ofrece solo enlace manual |
| TinEye, Yandex, Google Lens | Sin API pública gratuita/abierta compatible; enlaces manuales |
| SerpAPI / motores «reverse image» de pago | Requieren clave y facturación |
| Fly.io | Ya no ofrece free tier para nuevos usuarios; requiere tarjeta ([comparativa 2026](https://render.com/articles/platforms-with-a-real-free-tier-for-developers-in-2026)) |
| Railway | Crédito mensual limitado, no US$0 sostenido |
| Render Free Postgres | Gratuito pero **expira a los 30 días**; además el código aún usa SQLite |

## 6. Checklist de producción responsable

- [ ] `IMAGETRACE_SECRET_KEY` aleatorio y fuera de Git.
- [ ] `IMAGETRACE_CONTACT_EMAIL` configurado (política de User-Agent de Wikimedia).
- [ ] `IMAGETRACE_ALLOW_PRIVATE_NETWORKS=false`.
- [ ] HTTPS en frontend y backend; `IMAGETRACE_CORS_ORIGINS` exacto, nunca `*`.
- [ ] Retención acorde a la política de datos de tu organización.
- [ ] Copia de seguridad externa si se usa filesystem efímero, o migración a PostgreSQL (pendiente).
- [ ] Revisar `docs/SECURITY.md` y `docs/LIMITATIONS.md` antes de publicar resultados.
