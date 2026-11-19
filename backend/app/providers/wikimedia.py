"""Wikimedia Commons connector (public MediaWiki API, no key required).

Commons offers text search over file descriptions, not reverse image search.
Each candidate thumbnail is downloaded and compared locally. The API timestamp
is the *upload time to Commons*, never claimed as the original publication date.
"""

from __future__ import annotations

import re

import httpx

from .base import Candidate, Provider, ProviderOutcome, SearchContext, verify_candidate

API_URL = "https://commons.wikimedia.org/w/api.php"


def _strip_html(value: str) -> str:
    return re.sub(r"<[^>]+>", " ", value or "").strip()[:400]


class WikimediaCommonsProvider(Provider):
    name = "wikimedia_commons"
    label = "Wikimedia Commons (API pública)"
    kind = "external"

    def run(self, ctx: SearchContext) -> ProviderOutcome:
        if not ctx.allow_external or not ctx.settings.external_providers_enabled:
            return self._outcome("skipped", "Búsquedas externas desactivadas por el usuario o por configuración.")
        terms = (ctx.keywords + ctx.ocr_terms)[:8]
        if not terms:
            return self._outcome(
                "empty",
                "Sin palabras clave ni texto OCR: la API de Commons solo admite búsqueda por texto, no búsqueda inversa por imagen.",
            )
        query = " ".join(dict.fromkeys(terms))[:180]
        params = {
            "action": "query",
            "generator": "search",
            "gsrsearch": query,
            "gsrnamespace": "6",
            "gsrlimit": str(min(20, max(5, ctx.max_results * 2))),
            "prop": "imageinfo",
            "iiprop": "url|timestamp|size|mime|extmetadata",
            "iiurlwidth": "500",
            "format": "json",
            "formatversion": "2",
        }
        try:
            with httpx.Client(
                timeout=ctx.settings.provider_timeout_seconds,
                headers={"User-Agent": ctx.settings.user_agent},
            ) as client:
                response = client.get(API_URL, params=params)
            if response.status_code != 200:
                return self._outcome("error", f"Commons respondió HTTP {response.status_code}. No se reportan resultados.")
            payload = response.json()
        except (httpx.HTTPError, ValueError) as exc:
            return self._outcome(
                "unavailable",
                f"No se pudo consultar Wikimedia Commons desde este entorno ({type(exc).__name__}). "
                "Conector implementado; sin conectividad saliente no se reportan resultados.",
            )

        pages = (payload.get("query") or {}).get("pages") or []
        candidates: list[Candidate] = []
        for page in pages[: ctx.max_results]:
            info_list = page.get("imageinfo") or []
            if not info_list:
                continue
            info = info_list[0]
            meta = info.get("extmetadata") or {}
            license_name = _strip_html((meta.get("LicenseShortName") or {}).get("value", ""))
            artist = _strip_html((meta.get("Artist") or {}).get("value", ""))
            description = _strip_html((meta.get("ImageDescription") or {}).get("value", ""))
            candidate = Candidate(
                provider=self.name,
                source_url=info.get("descriptionurl") or info.get("url"),
                page_url=info.get("descriptionurl"),
                image_url=info.get("url"),
                thumbnail_url=info.get("thumburl") or info.get("url"),
                title=page.get("title", "Archivo de Wikimedia Commons"),
                domain="commons.wikimedia.org",
                published_at=info.get("timestamp"),
                published_at_note="Fecha de subida del archivo a Wikimedia Commons (timestamp de la API). NO es la fecha de publicación original.",
                license=license_name or None,
                notes=f"Autor declarado: {artist or 'desconocido'}. {description}".strip(),
            )
            thumb = info.get("thumburl") or info.get("url")
            candidates.append(verify_candidate(ctx, candidate, thumb) if thumb else candidate)
        if not candidates:
            return self._outcome("empty", f"Commons devolvió 0 archivos para «{query}».")
        verified = sum(1 for c in candidates if c.evidence_level.startswith("verified"))
        return self._outcome(
            "ok",
            f"Commons devolvió {len(candidates)} candidatos por texto para «{query}»; "
            f"{verified} verificados localmente. Los timestamps son de subida a Commons, no de publicación original.",
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
