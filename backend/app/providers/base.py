"""Provider contract and shared candidate verification.

A provider may only return data it actually obtained. Candidate images are
downloaded (with SSRF protection) and compared locally with SHA-256/pHash
before anything is labelled as a match. Items that cannot be verified are
reported explicitly as such; no provider invents dates, thumbnails or matches.
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable
from urllib.parse import urlparse

from PIL import Image

from ..config import Settings
from ..db import Database
from ..imaging import EXACT_DISTANCE, VISUAL_DISTANCE, candidate_verification
from ..security import ValidationError, fetch_public_image


@dataclass
class Candidate:
    provider: str
    source_url: str
    page_url: str | None = None
    image_url: str | None = None
    thumbnail_url: str | None = None
    title: str | None = None
    domain: str | None = None
    published_at: str | None = None
    published_at_note: str | None = "Fecha no proporcionada por la fuente; se reporta como desconocida."
    license: str | None = None
    notes: str | None = None
    match_type: str = "unverified"
    evidence_level: str = "unverified"
    similarity_pct: float | None = None
    phash_distance: int | None = None
    sha256_match: bool = False
    metric_explanation: str | None = None
    local_thumbnail: str | None = None
    extra: dict[str, Any] = field(default_factory=dict)

    def to_row(self, investigation_id: str) -> dict[str, Any]:
        return {
            "id": uuid.uuid4().hex,
            "investigation_id": investigation_id,
            "provider": self.provider,
            "source_url": self.source_url,
            "page_url": self.page_url,
            "domain": self.domain or (urlparse(self.source_url).hostname if self.source_url else None),
            "title": self.title,
            "published_at": self.published_at,
            "published_at_note": self.published_at_note,
            "thumbnail_url": self.thumbnail_url,
            "local_thumbnail": self.local_thumbnail,
            "image_url": self.image_url,
            "match_type": self.match_type,
            "evidence_level": self.evidence_level,
            "similarity": self.similarity_pct,
            "phash_distance": self.phash_distance,
            "sha256_match": int(self.sha256_match),
            "metric_explanation": self.metric_explanation,
            "license": self.license,
            "notes": self.notes,
            "raw_json": None,
            "created_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        }


@dataclass
class ProviderOutcome:
    provider: str
    label: str
    kind: str
    status: str  # ok | empty | skipped | unavailable | error
    message: str
    candidates: list[Candidate] = field(default_factory=list)
    manual_links: list[dict[str, str]] = field(default_factory=list)
    duration_ms: int = 0

    @property
    def result_count(self) -> int:
        return len(self.candidates)


@dataclass
class SearchContext:
    settings: Settings
    db: Database
    owner_hash: str
    investigation_id: str
    investigation_dir: Path
    query_image: Image.Image
    sha256: str
    phash: str
    keywords: list[str]
    ocr_terms: list[str]
    allow_external: bool
    max_results: int
    lang: str = "es"
    fetch: Callable[..., tuple[bytes, str]] = fetch_public_image


def verify_candidate(ctx: SearchContext, candidate: Candidate, image_url: str) -> Candidate:
    """Download a candidate image and classify it with local hashes."""
    metric = (
        "SHA-256 compara los bytes completos (idéntico = mismo archivo). "
        "pHash DCT 16×16 produce 256 bits; similitud = 100 × (1 − distancia Hamming / 256). "
        f"Umbral de similitud visual: distancia ≤ {VISUAL_DISTANCE}."
    )
    try:
        data, final_url = ctx.fetch(image_url, ctx.settings, max_bytes=6 * 1024 * 1024)
    except Exception as exc:  # noqa: BLE001 - provider failure must not abort analysis
        candidate.notes = (
            f"No se pudo verificar la imagen candidata ({type(exc).__name__}). "
            "El resultado permanece SIN VERIFICAR."
        )
        candidate.metric_explanation = metric
        return candidate

    verification = candidate_verification(ctx.query_image, ctx.sha256, ctx.phash, data)
    if verification is None:
        candidate.notes = "La imagen candidata no es decodificable; resultado SIN VERIFICAR."
        candidate.metric_explanation = metric
        return candidate
    candidate.phash_distance = verification["phash_distance"]
    candidate.similarity_pct = verification["similarity_pct"]
    candidate.sha256_match = verification["sha256_equal"]
    candidate.metric_explanation = metric
    candidate.match_type = verification["classification"]
    alignment = verification.get("alignment") or {}
    if verification.get("alignment_verified"):
        candidate.evidence_level = "verified_visual"
        candidate.match_type = "visual_similarity"
        candidate.metric_explanation = (
            metric + f" Alineación adicional: {alignment.get('method')} con cobertura {alignment.get('coverage')}; "
            f"pHash alineado {alignment.get('aligned_phash_distance')}/256 y error medio {alignment.get('mean_absolute_error')}/255."
        )
        candidate.notes = (
            "Versión recortada/reescalada verificada localmente tras alineación geométrica. "
            "El pHash directo no era concluyente; comprobar la fuente manualmente."
        )
    elif verification["sha256_equal"]:
        candidate.evidence_level = "verified_exact"
        candidate.notes = "Coincidencia exacta de bytes SHA-256 verificada localmente contra la imagen descargada de la fuente."
    elif (verification["phash_distance"] or 999) <= EXACT_DISTANCE:
        candidate.evidence_level = "verified_visual"
        candidate.notes = (
            f"Duplicado perceptual: distancia pHash {verification['phash_distance']}/256. "
            "Mismo contenido visual probable (recodificación o cambio de tamaño). Verificar la fuente manualmente."
        )
    elif (verification["phash_distance"] or 999) <= VISUAL_DISTANCE:
        candidate.evidence_level = "verified_visual"
        candidate.notes = (
            f"Similitud visual calculada localmente: distancia pHash {verification['phash_distance']}/256. "
            "Puede ser una versión recortada o modificada; requiere comprobación manual."
        )
    else:
        candidate.evidence_level = "unverified"
        candidate.notes = (
            f"El candidato NO supera el umbral de similitud (distancia pHash "
            f"{verification['phash_distance']}/256). Se muestra solo como resultado no verificado."
        )
    # Persist a sanitized local thumbnail so the UI never hotlinks third parties.
    try:
        from ..security import sanitize_image

        clean = sanitize_image(data, max_bytes=6 * 1024 * 1024)
        thumbs = ctx.investigation_dir / "thumbs"
        thumbs.mkdir(parents=True, exist_ok=True)
        name = f"{uuid.uuid4().hex}.jpg"
        (thumbs / name).write_bytes(clean.display_bytes)
        candidate.local_thumbnail = f"thumbs/{name}"
    except (ValidationError, OSError):
        pass
    candidate.image_url = final_url
    return candidate


class Provider:
    name = "base"
    label = "Base"
    kind = "local"

    def run(self, ctx: SearchContext) -> ProviderOutcome:
        raise NotImplementedError
