"""Manual research links for platforms without a compatible free/open API.

Google Lens, Bing Visual Search, TinEye and Yandex do not offer a free, open,
officially usable reverse-image API for this project. News, forum, archive and
general-web sources without a compatible image API are also exposed here.
These links are NEVER counted as matches: no scraping and no fake results.
"""

from __future__ import annotations

from urllib.parse import quote_plus

from .base import Provider, ProviderOutcome, SearchContext


class ManualSearchProvider(Provider):
    name = "manual_links"
    label = "Consultas manuales (sin API abierta)"
    kind = "manual"

    def run(self, ctx: SearchContext) -> ProviderOutcome:
        query = " ".join(dict.fromkeys(ctx.keywords + ctx.ocr_terms))[:180]
        q = quote_plus(query) if query else ""
        links = [
            {
                "key": "manual.google_lens", "note_key": "manual.google_lens_note",
                "label": "Google Lens (carga manual)",
                "note": "No existe API pública gratuita de búsqueda inversa; suba la imagen manualmente.",
                "url": "https://lens.google.com/",
            },
            {
                "key": "manual.bing_visual", "note_key": "manual.bing_visual_note",
                "label": "Bing Visual Search (carga manual)",
                "note": "La API oficial requiere clave de Azure; se ofrece solo el enlace manual.",
                "url": "https://www.bing.com/visualsearch",
            },
            {
                "key": "manual.tineye", "note_key": "manual.tineye_note",
                "label": "TinEye (carga manual)",
                "note": "Servicio comercial sin API gratuita abierta; enlace manual.",
                "url": "https://tineye.com/",
            },
            {
                "key": "manual.yandex", "note_key": "manual.yandex_note",
                "label": "Yandex Images (carga manual)",
                "note": "Sin API oficial abierta; enlace manual. Respete las condiciones del servicio.",
                "url": "https://yandex.com/images/search",
            },
            {
                "key": "manual.google_images", "note_key": "manual.google_images_note",
                "label": "Google Images por texto",
                "note": "Búsqueda por palabras clave/OCR, no búsqueda inversa.",
                "url": f"https://www.google.com/search?tbm=isch&q={q}" if q else "https://images.google.com/",
            },
            {
                "key": "manual.ddg_images", "note_key": "manual.ddg_images_note",
                "label": "DuckDuckGo Images por texto",
                "note": "Índice de imágenes por palabras clave; comprobar la fuente manualmente.",
                "url": f"https://duckduckgo.com/?q={q}&iax=images&ia=images" if q else "https://duckduckgo.com/",
            },
            {
                "key": "manual.duckduckgo", "note_key": "manual.duckduckgo_note",
                "label": "DuckDuckGo por texto",
                "note": "Búsqueda web general por palabras clave/OCR.",
                "url": f"https://duckduckgo.com/?q={q}" if q else "https://duckduckgo.com/",
            },
            {
                "key": "manual.commons", "note_key": "manual.commons_note",
                "label": "Wikipedia / Commons por texto",
                "note": "Repositorio público de imágenes; búsqueda por texto.",
                "url": f"https://commons.wikimedia.org/w/index.php?search={q}&title=Special:MediaSearch" if q else "https://commons.wikimedia.org/",
            },
            {
                "key": "manual.nasa", "note_key": "manual.nasa_note",
                "label": "NASA Image Library por texto",
                "note": "Catálogo público; consulta manual complementaria al conector automático.",
                "url": f"https://images.nasa.gov/search?q={q}" if q else "https://images.nasa.gov/",
            },
            {
                "key": "manual.met", "note_key": "manual.met_note",
                "label": "The Met Collection por texto",
                "note": "Repositorio Open Access; consulta manual complementaria al conector automático.",
                "url": f"https://www.metmuseum.org/art/collection/search?q={q}" if q else "https://www.metmuseum.org/art/collection",
            },
            {
                "key": "manual.internet_archive", "note_key": "manual.internet_archive_note",
                "label": "Internet Archive (imágenes)",
                "note": "Repositorio indexado público; filtrar por tipo de medio y verificar licencia.",
                "url": f"https://archive.org/search?query={q}&and%5B%5D=mediatype%3A%22image%22" if q else "https://archive.org/",
            },
            {
                "key": "manual.wayback", "note_key": "manual.wayback_note",
                "label": "Wayback Machine (copias históricas)",
                "note": "Pegá la URL de una fuente para comprobar versiones archivadas; no se scrapea automáticamente.",
                "url": "https://web.archive.org/",
            },
            {
                "key": "manual.flickr_commons", "note_key": "manual.flickr_commons_note",
                "label": "Flickr Commons / dominio público",
                "note": "Repositorio público sin API en esta instalación; comprobar licencia por foto.",
                "url": f"https://www.flickr.com/search/?text={q}&license=9,10" if q else "https://www.flickr.com/commons",
            },
            {
                "key": "manual.europeana", "note_key": "manual.europeana_note",
                "label": "Europeana por texto",
                "note": "Patrimonio cultural europeo; requiere clave para API, por eso enlace manual.",
                "url": f"https://www.europeana.eu/en/search?query={q}" if q else "https://www.europeana.eu/",
            },
            {
                "key": "manual.gdelt", "note_key": "manual.gdelt_note",
                "label": "Noticias / cobertura (GDELT)",
                "note": "Índice público de noticias; usar para buscar artículos por texto, nunca para perfilamiento.",
                "url": "https://www.gdeltproject.org/",
            },
            {
                "key": "manual.forums", "note_key": "manual.forums_note",
                "label": "Foros y blogs públicos por texto",
                "note": "Búsqueda general de contenido público; no se identifican personas ni se infieren identidades.",
                "url": f"https://duckduckgo.com/?q={q}+foro" if q else "https://duckduckgo.com/",
            },
        ]
        return ProviderOutcome(
            provider=self.name,
            label=self.label,
            kind=self.kind,
            status="ok",
            message=(
                "Estas plataformas no ofrecen una API gratuita/abierta compatible para imagen inversa o no se consultan "
                "automáticamente. Se proporcionan enlaces de comprobación manual; no se cuentan como coincidencias ni se scrapean."
            ),
            candidates=[],
            manual_links=links,
        )
