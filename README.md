# ImageTrace OSINT

A privacy-conscious, local-first image investigation application: React + TypeScript + Vite frontend; FastAPI + Pillow + imagehash + SQLite backend. **Real local analysis, no mock web results, no facial identification.**

## Reverse Image Search mode

The **Reverse Search** tab uploads a permitted image to the private, single-operator index then compares up to the 100 most recent uploaded images by SHA-256, 64-bit pHash distance and (when hashes differ) OpenCV ORB geometric verification. Results explicitly distinguish verified byte-exact copies from non-conclusive visual similarities; no public URL is attributed to a private index item. Optionally check the file's SHA-1 in Wikimedia Commons, or follow manual links to external image search engines without uploading anything automatically. This does **not** find unidentified people from their faces, nor claim whole-internet coverage. Because Render Free uses ephemeral storage, an empty index or restarted instance can legitimately return no results.

## What works today
- Validated JPG/PNG/WEBP uploads (max 10 MB, decompression-bomb protection, 35 MP limit).
- SHA-256 exact-match detection; 64-bit perceptual pHash similarity comparison across the private uploaded index (distance ≤10; not a statistical confidence percentage).
- Safe EXIF subset, dimensions, optional OCR if Tesseract executable is installed; GPS coordinates intentionally never returned.
- Single-user API-key-protected history, JSON/PDF reports, delete on demand, automatic cleanup after 24 hours on API activity.
- Two-image comparison of SHA-256, pHash, OpenCV ORB crop/scene features, pixel difference map, before/after slider and overlay transparency.
- Opt-in exact SHA-1 lookup in Wikimedia Commons' official MediaWiki API. Only the hash is transmitted; matching uploaded files are linked to their Commons description pages. Provider upload date is not necessarily original publication date.
- Manual Google Lens / TinEye links that do not auto-upload user data.
- Spanish, Brazilian Portuguese and English UI.

## Important limitations
- **NOT** a whole-Internet reverse image search. The authorized Wikimedia Commons connector finds only byte-identical current-version Commons files. Other public sources and visually transformed internet copies are not indexed. Manual links are not search results.
- URL ingestion intentionally returns HTTP 501: resolving remote URLs securely needs DNS pinning, allowed schemes, streaming byte limits, verified redirects, and SSRF tests.
- OpenCV ORB detects some crops, rotations and rescalings in side-by-side comparison, but can produce false matches or misses. Not applied to every file in the local index. No evidence-grade tampering detection, image provenance certificates, or signed expiring download URLs yet.
- No account multi-tenancy: APP_API_KEY is a **single-operator key**. Do not offer this as a public SaaS or share it with untrusted users.
- Metadata may be absent or modified; image-derived conclusions do not prove original source or editing.
- Malware scanning not integrated. Image decoding is restricted; deploy behind additional upload screening before public exposure.
- For a continuous retention guarantee add a separate scheduled cleanup job; current cleanup runs when API endpoints are used.
- SQLite is durable only on persistent disk; ephemeral free hosting can erase files/data.
- Additional source provider adapters require legitimate access and separate integration; no scraping of restricted sites.
- Wikimedia Commons API requests comply with its published User-Agent policy. Queries may fail or be limited; the app marks provider failure distinctly from zero results.

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

## Live evaluation deployment (2026-11-19)

- Frontend: https://imagetrace-osint-two.vercel.app (Vercel Hobby; may require Vercel authentication depending on deployment protection).
- Backend: https://imagetrace-osint-api.onrender.com/api/health (Render Free; cold starts possible).
- Branch for isolated deploys: `feat/imagetrace-osint-mvp`. Deployments were done without changing other apps.
- A private `APP_API_KEY` is configured in Render. Retrieve it securely from the service environment settings before using the dashboard; it is not embedded in frontend bundles. Do not publish it.
- **Render Free has ephemeral local disk**. Investigations and files are lost after a rebuild/restart; this is an evaluation instance, NOT durable production storage. Run locally with persistent disk or configure durable object storage and database before public release.
- The backend does not serve the web homepage at `/`. Its health endpoint is `/api/health` and OpenAPI documentation is `/docs`.
- This deploy is for one private operator only. The single shared API key does not isolate multiple accounts. Do not share the service or enable public registration until multi-user authentication, quotas, persistent storage, malware scanning, signed report downloads and review are complete.

## Public provider provenance

Wikimedia MediaWiki `list=allimages&aisha1` is an official query to detect exact file-byte matches. It does not perform face recognition, semantic similarity, or web-wide reverse search. Source: https://www.mediawiki.org/wiki/API:Allimages . User-Agent policy: https://www.mediawiki.org/wiki/Wikimedia_APIs/Access_policy .
