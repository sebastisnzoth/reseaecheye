"""Openverse connector (public, keyless, Creative Commons catalog).

Openverse provides *text* search over openly licensed media. It is NOT a reverse
image search API. ImageTrace uses it only to obtain candidate images, then
verifies each candidate locally with SHA-256 and pHash. No result is assumed to
be a match without that verification.
"""

from __future__ import annotations

import httpx

from .base import Candidate, Provider, ProviderOutcome, SearchContext, verify_candidate

API_URL = "https://api.openverse.org/v1/images/"


class OpenverseProvider(Provider):
    name = "openverse"
    label = "Openverse (catálogo CC, sin clave)"
    kind = "external"

    def run(self, ctx: SearchContext) -> ProviderOutcome:
        if not ctx.allow_external or not ctx.settings.external_providers_enabled:
            return self._outcome("skipped", "Búsquedas externas desactivadas por el usuario o por configuración.")
        terms = (ctx.keywords + ctx.ocr_terms)[:8]
        if not terms:
            return self._outcome(
                "empty",
                "Sin palabras clave ni texto OCR: Openverse solo admite búsqueda por texto, no búsqueda inversa por imagen. "
                "Use los enlaces de consulta manual o añada palabras clave.",
            )
        query = " ".join(dict.fromkeys(terms))[:180]
        params = {"q": query, "page_size": min(20, max(5, ctx.max_results * 2)), "page": 1}
        try:
            with httpx.Client(
                timeout=ctx.settings.provider_timeout_seconds,
                headers={"User-Agent": ctx.settings.user_agent},
            ) as client:
                response = client.get(API_URL, params=params)
            if response.status_code == 429:
                return self._outcome("unavailable", "Openverse aplicó su límite de solicitudes anónimas (HTTP 429). Reintentar más tarde.")
            if response.status_code != 200:
                return self._outcome(
                    "error", f"Openverse respondió HTTP {response.status_code}. No se reportan resultados."
                )
            payload = response.json()
        except (httpx.HTTPError, ValueError) as exc:
            return self._outcome(
                "unavailable",
                f"No se pudo consultar Openverse desde este entorno ({type(exc).__name__}). "
                "El conector está implementado; revise la conectividad saliente. No se inventan resultados.",
            )

        results = payload.get("results", []) if isinstance(payload, dict) else []
        candidates: list[Candidate] = []
        for item in results[: ctx.max_results]:
            if not isinstance(item, dict):
                continue
            thumb = item.get("thumbnail") or item.get("url")
            source = item.get("foreign_landing_url") or item.get("url") or API_URL
            candidate = Candidate(
                provider=self.name,
                source_url=source,
                page_url=item.get("foreign_landing_url"),
                image_url=item.get("url"),
                thumbnail_url=item.get("thumbnail"),
                title=item.get("title") or "Imagen de Openverse",
                license=", ".join(
                    str(v) for v in (item.get("license"), item.get("license_version")) if v
                ) or None,
                notes=f"Autor declarado: {item.get('creator') or 'desconocido'}. Catálogo de licencias abiertas; verifique licencia y atribución.",
                published_at=item.get("indexed_on"),
                published_at_note=(
                    "Fecha de indexación en Openverse (campo indexed_on de la API). NO es la fecha de publicación original."
                    if item.get("indexed_on") else
                    "Openverse no entregó fecha; se reporta como desconocida."
                ),
            )
            if thumb:
                candidates.append(verify_candidate(ctx, candidate, thumb))
            else:
                candidate.notes = (candidate.notes or "") + " Sin miniatura descargable: resultado SIN VERIFICAR."
                candidates.append(candidate)

        if not candidates:
            return self._outcome(
                "empty", f"Openverse devolvió 0 candidatos para «{query}». No hay coincidencias que reportar."
            )
        verified = sum(1 for c in candidates if c.evidence_level.startswith("verified"))
        return self._outcome(
            "ok",
            f"Openverse devolvió {len(candidates)} candidatos por texto para «{query}»; "
            f"{verified} verificados localmente con SHA-256/pHash. Los demás son resultados NO verificados.",
            candidates,
        )

    def _outcome(
        self, status: str, message: str, candidates: list[Candidate] | None = None
    ) -> ProviderOutcome:
        return ProviderOutcome(
            provider=self.name,
            label=self.label,
            kind=self.kind,
            status=status,
            message=message,
            candidates=candidates or [],
        )
