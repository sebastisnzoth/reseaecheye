# ImageTrace OSINT

A privacy-conscious, local-first image investigation application: React + TypeScript + Vite frontend; FastAPI + Pillow + imagehash + SQLite backend. **Real local analysis, no mock web results, no facial identification.**

## What works today
- Validated JPG/PNG/WEBP uploads (max 10 MB, decompression-bomb protection, 35 MP limit).
- SHA-256 exact-match detection; 64-bit perceptual pHash similarity comparison across the private uploaded index (distance ≤10; not a statistical confidence percentage).
- Safe EXIF subset, dimensions, optional OCR if Tesseract executable is installed; GPS coordinates intentionally never returned.
- Single-user API-key-protected history, JSON/PDF reports, delete on demand, automatic cleanup after 24 hours on API activity.
- Two-image comparison of SHA-256 and pHash; manual Google Lens / TinEye links that do not auto-upload user data.
- Spanish, Brazilian Portuguese and English UI.

## Important limitations
- **NOT** a whole-Internet reverse image search. Public matches are always empty until an official permitted provider is connected. Manual links are not search results.
- URL ingestion intentionally returns HTTP 501: resolving remote URLs securely needs DNS pinning, allowed schemes, streaming byte limits, verified redirects, and SSRF tests.
- No cropped-image detection guarantee; no overlay/difference heatmaps, evidence-grade tampering detection, image provenance certificates, or signed expiring download URLs yet.
- No account multi-tenancy: APP_API_KEY is a **single-operator key**. Do not offer this as a public SaaS or share it with untrusted users.
- Metadata may be absent or modified; image-derived conclusions do not prove original source or editing.
- Malware scanning not integrated. Image decoding is restricted; deploy behind additional upload screening before public exposure.
- For a continuous retention guarantee add a separate scheduled cleanup job; current cleanup runs when API endpoints are used.
- SQLite is durable only on persistent disk; ephemeral free hosting can erase files/data.
- Source provider adapters require legitimate access and separate integration; no scraping of restricted sites.

## Local startup
Requires Python 3.11+, Node 20+, Tesseract optional. From the project root:

```sh
cd backend
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
export APP_API_KEY="$(python3 -c 'import secrets; print(secrets.token_urlsafe(32))')"
uvicorn app.main:app --reload --port 8000
```
Open a second terminal:
```sh
cd frontend
npm install
npm run dev
```
Open http://localhost:5173 and paste the same APP_API_KEY into the private key field. It remains in sessionStorage until the browser session ends. For CORS change CORS_ORIGINS and for frontend API URL set VITE_API_URL before build. Don't commit secrets.

## Tests
```sh
cd backend
pip install -r requirements.txt
pytest -q
cd ../frontend
npm ci && npm run build
```

## Public deployment note
For $0, run FastAPI + SQLite locally and host the static frontend on GitHub Pages or another free static hosting provider; the frontend requires a reachable HTTPS backend. Free API hosts may have sleep policies, quotas or nonpersistent storage; none are claimed verified for production here. **Do not publish a single-key backend without robust user auth, TLS, rate limiting, scanning, retention scheduler and security review.**

## Security model
Private operator API secret, no public upload endpoint, no biometric indexing, GPS suppressed, configured exact CORS origins and no remote fetch by default. All reports are API-key protected and served with no-store. Replace shared-key auth with real per-user accounts and signed, expiring URLs before any multi-user deployment.

## Licensing
The project does not copy InfoChecker code or reuse its branding. Evaluate third-party image and search provider licenses and terms before integration.
