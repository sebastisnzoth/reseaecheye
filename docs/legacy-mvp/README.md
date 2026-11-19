# Implementación MVP previa (archivada, NO activa)

Cuando se integró `main` en esta rama, `main` contenía dos commits del propietario
(`8107224` "verified local-first MVP" y `ca80514` "Reverse Image Search mode")
que implementaban **otra versión** de ImageTrace OSINT: API con clave única
`X-API-Key`, endpoints `/api/analyze`, `/api/compare`,
`/api/investigations/{id}/search/commons` y un frontend más pequeño.

Esta rama contiene la implementación completa descrita en `README.md` y
`docs/ARCHITECTURE.md` (6 proveedores, firmas HMAC, 19 pruebas, informes de 10
secciones). Para no perder el trabajo previo ni romper la suite actual, sus
archivos incompatibles se conservan aquí **solo como referencia histórica**:

| Archivo aquí | Ubicación original | Motivo del archivado |
|---|---|---|
| `test_api.py` | `backend/tests/test_api.py` | Prueba endpoints y cabeceras de la API anterior; se excluye de `pytest.ini` (`testpaths = backend/tests`). |
| `backend.requirements.txt` | `backend/requirements.txt` | La instalación activa usa `requirements.txt` en la raíz. |
| `backend.pytest.ini` | `backend/pytest.ini` | La configuración activa es `pytest.ini` en la raíz (`pythonpath = backend`). |
| `backend.env.example` | `backend/.env.example` | La configuración activa es `.env.example` en la raíz (sin credenciales). |
| `frontend.style.css` | `frontend/src/style.css` | El frontend activo usa `frontend/src/index.css` (Tailwind). |

Se conservan **en uso** dos aportes de esos commits:

- `.github/workflows/ci.yml` (adaptado a la estructura actual: `requirements.txt`
  raíz, `pytest.ini` raíz, `npm ci`).
- `docs/GITHUB_OPEN_SOURCE_RESEARCH.md` (investigación de fuentes abiertas).

El historial completo de ambos commits queda en `main` y como padres del commit
de integración de esta rama; nada se borró de Git.
