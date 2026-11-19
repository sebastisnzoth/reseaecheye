"""NASA Image and Video Library connector (official public API, no key).

NASA offers text search over a public image catalogue. It is NOT reverse image
search: candidates are retrieved by keywords/OCR terms and then verified
locally with SHA-256, pHash and ORB/RANSAC alignment. Dates are NASA's
`date_created` catalogue timestamps, never claimed as original publication.
"""

from __future__ import annotations

import httpx

from .base import Candidate, Provider, ProviderOutcome, SearchContext, verify_candidate

API_URL = "https://images-api.nasa.gov/search"
DETAILS_URL = "https://images.nasa.gov/details/{nasa_id}"


def _pick_link(links: list[dict], preferred: tuple[str, ...]) -> str | None:
    for rel in preferred:
        for link in links:
            href = link.get("href")
            if href and (link.get("rel") == rel or link.get("render") == rel):
                return str(href)
    for link in links:
        if link.get("href") and link.get("render") == "image":
            return str(link.get("href"))
    return None


class NasaImageLibraryProvider(Provider):
    name = "nasa_image_library"
    label = "NASA Image & Video Library (API pública)"
    kind = "external"

    def run(self, ctx: SearchContext) -> ProviderOutcome:
        if not ctx.allow_external or not ctx.settings.external_providers_enabled:
            return self._outcome("skipped", "Búsquedas externas desactivadas por el usuario o por configuración.")
        terms = (ctx.keywords + ctx.ocr_terms)[:8]
        if not terms:
            return self._outcome(
                "empty",
                "Sin palabras clave ni texto OCR: la API de NASA solo admite búsqueda por texto, no búsqueda inversa por imagen.",
            )
        query = " ".join(dict.fromkeys(terms))[:180]
        params = {
            "q": query,
            "media_type": "image",
            "page_size": str(min(20, max(5, ctx.max_results * 2))),
        }
        try:
            with httpx.Client(
                timeout=ctx.settings.provider_timeout_seconds,
                headers={"User-Agent": ctx.settings.user_agent},
            ) as client:
                response = client.get(API_URL, params=params)
            if response.status_code == 429:
                return self._outcome("unavailable", "NASA aplicó un límite de solicitudes (HTTP 429). Reintentar más tarde.")
            if response.status_code != 200:
                return self._outcome("error", f"NASA respondió HTTP {response.status_code}. No se reportan resultados.")
            payload = response.json()
        except (httpx.HTTPError, ValueError) as exc:
            return self._outcome(
                "unavailable",
                f"No se pudo consultar la API de NASA desde este entorno ({type(exc).__name__}). "
                "Conector implementado; sin conectividad saliente no se inventan resultados.",
            )

        items = ((payload.get("collection") or {}).get("items") or []) if isinstance(payload, dict) else []
        candidates: list[Candidate] = []
        for item in items[: ctx.max_results]:
            if not isinstance(item, dict):
                continue
            data = (item.get("data") or [{}])[0]
            links = [link for link in (item.get("links") or []) if isinstance(link, dict)]
            nasa_id = str(data.get("nasa_id") or "").strip()
            thumb = _pick_link(links, ("preview",))
            original = _pick_link(links, ("canonical",)) or _pick_link(links, ("image",))
            details = DETAILS_URL.format(nasa_id=nasa_id) if nasa_id else (item.get("href") or API_URL)
            created = data.get("date_created")
            keywords = ", ".join(str(k) for k in (data.get("keywords") or [])[:8])
            candidate = Candidate(
                provider=self.name,
                source_url=details,
                page_url=details,
                image_url=original,
                thumbnail_url=thumb,
                title=str(data.get("title") or "Imagen del catálogo NASA"),
                domain="images.nasa.gov",
                published_at=str(created) if created else None,
                published_at_note=(
                    "Fecha de creación/catalogación declarada por NASA (date_created). "
                    "NO es una fecha de publicación original verificada."
                    if created else
                    "NASA no entregó fecha; se reporta como desconocida."
                ),
                license=None,
                notes=(
                    f"Centro: {data.get('center') or 'desconocido'}. Crédito: "
                    f"{data.get('secondary_creator') or 'no declarado'}. Palabras clave: {keywords or '—'}. "
                    "La API no entrega licencia por ítem: verificar derechos de uso y atribución antes de reutilizar."
                ),
            )
            candidates.append(verify_candidate(ctx, candidate, thumb) if thumb else candidate)

        if not candidates:
            return self._outcome("empty", f"NASA devolvió 0 imágenes para «{query}».")
        verified = sum(1 for c in candidates if c.evidence_level.startswith("verified"))
        return self._outcome(
            "ok",
            f"NASA devolvió {len(candidates)} candidatos por texto para «{query}»; {verified} verificados localmente "
            "con SHA-256/pHash/alineación. Los demás son resultados NO verificados.",
            candidates,
        )

    def _outcome(
        self, status: str, message: str, candidates: list[Candidate] | None = None
    ) -> ProviderOutcome:
        return ProviderOutcome(
            provider=self.name, label=self.label, kind=self.kind,
            status=status, message=message, candidates=candidates or [],
        )
