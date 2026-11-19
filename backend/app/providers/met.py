"""The Metropolitan Museum of Art Collection API connector (public, no key).

Real text search over an open-access image repository. Candidates are verified
locally; the API does not provide reverse image search. `objectDate` is the
date of the artwork/catalogue record, never an online publication date.
"""

from __future__ import annotations

import httpx

from .base import Candidate, Provider, ProviderOutcome, SearchContext, verify_candidate

SEARCH_URL = "https://collectionapi.metmuseum.org/public/collection/v1.1/search"
OBJECT_URL = "https://collectionapi.metmuseum.org/public/collection/v1/objects/{object_id}"


class MetMuseumProvider(Provider):
    name = "met_museum"
    label = "The Met Collection (Open Access, sin clave)"
    kind = "external"

    def run(self, ctx: SearchContext) -> ProviderOutcome:
        if not ctx.allow_external or not ctx.settings.external_providers_enabled:
            return self._outcome("skipped", "Búsquedas externas desactivadas por el usuario o por configuración.")
        terms = (ctx.keywords + ctx.ocr_terms)[:8]
        if not terms:
            return self._outcome(
                "empty",
                "Sin palabras clave ni texto OCR: la API del Met solo admite búsqueda por texto, no búsqueda inversa por imagen.",
            )
        query = " ".join(dict.fromkeys(terms))[:180]
        limit = min(10, max(3, ctx.max_results * 2))
        try:
            with httpx.Client(
                timeout=ctx.settings.provider_timeout_seconds,
                headers={"User-Agent": ctx.settings.user_agent},
            ) as client:
                search_response = client.get(
                    SEARCH_URL, params={"q": query, "hasImages": "true", "limit": str(limit)}
                )
                if search_response.status_code == 429:
                    return self._outcome("unavailable", "El Met aplicó un límite de solicitudes (HTTP 429).")
                if search_response.status_code != 200:
                    return self._outcome("error", f"El Met respondió HTTP {search_response.status_code} en la búsqueda.")
                object_ids = (search_response.json() or {}).get("objectIDs") or []
                objects: list[dict] = []
                for object_id in object_ids[:limit]:
                    try:
                        detail = client.get(OBJECT_URL.format(object_id=object_id))
                        if detail.status_code == 200 and isinstance(detail.json(), dict):
                            objects.append(detail.json())
                    except (httpx.HTTPError, ValueError):
                        continue  # a single failed object must not discard the rest
        except (httpx.HTTPError, ValueError) as exc:
            return self._outcome(
                "unavailable",
                f"No se pudo consultar la API del Met desde este entorno ({type(exc).__name__}). "
                "Conector implementado; sin conectividad saliente no se inventan resultados.",
            )

        candidates: list[Candidate] = []
        for obj in objects:
            thumb = obj.get("primaryImageSmall") or obj.get("primaryImage")
            if not thumb:
                continue
            object_id = obj.get("objectID")
            page = obj.get("objectURL") or f"https://www.metmuseum.org/art/collection/search/{object_id}"
            object_date = obj.get("objectDate")
            public_domain = bool(obj.get("isPublicDomain"))
            candidate = Candidate(
                provider=self.name,
                source_url=page,
                page_url=page,
                image_url=obj.get("primaryImage") or thumb,
                thumbnail_url=thumb,
                title=str(obj.get("title") or f"Objeto {object_id} del Met"),
                domain="metmuseum.org",
                published_at=str(object_date) if object_date else None,
                published_at_note=(
                    "Fecha de la obra/registro de catálogo declarada por el Met (objectDate). "
                    "NO es una fecha de publicación en Internet."
                    if object_date else
                    "El Met no entregó fecha; se reporta como desconocida."
                ),
                license="Dominio público (Open Access)" if public_domain else None,
                notes=(
                    f"Autor: {obj.get('artistDisplayName') or 'no declarado'}. "
                    f"Crédito: {obj.get('creditLine') or 'no declarado'}. "
                    "Solo se incluyen objetos con imagen; verificar derechos de uso antes de reutilizar."
                ),
            )
            candidates.append(verify_candidate(ctx, candidate, thumb))
            if len(candidates) >= ctx.max_results:
                break

        if not candidates:
            return self._outcome(
                "empty", f"El Met devolvió {len(objects)} objetos consultados pero ninguno con imagen verificable para «{query}»."
            )
        verified = sum(1 for c in candidates if c.evidence_level.startswith("verified"))
        return self._outcome(
            "ok",
            f"El Met devolvió {len(candidates)} candidatos con imagen para «{query}»; {verified} verificados localmente. "
            "Las fechas son de la obra/catálogo, no de publicación web.",
            candidates,
        )

    def _outcome(
        self, status: str, message: str, candidates: list[Candidate] | None = None
    ) -> ProviderOutcome:
        return ProviderOutcome(
            provider=self.name, label=self.label, kind=self.kind,
            status=status, message=message, candidates=candidates or [],
        )
