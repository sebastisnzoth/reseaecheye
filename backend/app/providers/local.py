"""Local, owner-scoped index: exact duplicates and perceptual/crop variants.

Real index, not a simulation: each analysed or explicitly added image is stored
with SHA-256, pHash and a sanitised derivative. Exact and perceptual matches are
computed locally; crop/scale variants are detected with ORB/RANSAC alignment
because plain pHash is not crop-invariant.
"""

from __future__ import annotations

import shutil
import uuid
from pathlib import Path

from PIL import Image

from ..imaging import (
    VISUAL_DISTANCE,
    alignment_assessment,
    classify_distance,
    phash_distance,
    similarity_from_distance,
)
from .base import Candidate, Provider, ProviderOutcome, SearchContext

MAX_ALIGNMENT_CHECKS = 30


class LocalIndexProvider(Provider):
    name = "local_index"
    label = "Índice local (imágenes permitidas)"
    kind = "local"

    def run(self, ctx: SearchContext) -> ProviderOutcome:
        own_label = f"investigación:{ctx.investigation_id[:12]}"
        rows = ctx.db.fetchall(
            "SELECT id, sha256, phash, label, source_url, asset_path, created_at "
            "FROM index_entries WHERE owner_hash = ? AND label != ? ORDER BY created_at DESC LIMIT 500",
            (ctx.owner_hash, own_label),
        )
        investigations = ctx.db.fetchall(
            "SELECT id, sha256, phash, original_filename, asset_display, created_at, source_url "
            "FROM investigations WHERE owner_hash = ? AND id != ? AND deleted_at IS NULL "
            "ORDER BY created_at DESC LIMIT 200",
            (ctx.owner_hash, ctx.investigation_id),
        )
        seen: set[str] = set()
        candidates: list[Candidate] = []
        alignment_checks = 0
        compared = 0

        for row in list(rows) + list(investigations):
            sha = row["sha256"]
            key = sha or row["id"]
            if key in seen:
                continue
            seen.add(key)
            compared += 1
            is_index = "asset_path" in row.keys()
            thumb_path = row["asset_path"] if is_index else row["asset_display"]
            distance = phash_distance(ctx.phash, row["phash"]) if row["phash"] else None
            exact = sha == ctx.sha256
            aligned = None
            if not exact and (distance is None or distance > VISUAL_DISTANCE) and alignment_checks < MAX_ALIGNMENT_CHECKS:
                alignment_checks += 1
                aligned = self._alignment(ctx, thumb_path)
            if not exact and (distance is None or distance > VISUAL_DISTANCE) and not (aligned and aligned.get("status") == "aligned"):
                continue

            source_url, page_url, domain, label = self._source_fields(row, is_index)
            local_thumb = self._copy_thumb(ctx, thumb_path)
            if aligned and aligned.get("status") == "aligned":
                candidates.append(
                    Candidate(
                        provider=self.name,
                        source_url=source_url,
                        page_url=page_url,
                        title=str(label or "Imagen en el índice local"),
                        domain=domain,
                        published_at=row["created_at"],
                        published_at_note="Fecha de ingreso al índice local (no fecha de publicación en Internet).",
                        local_thumbnail=local_thumb,
                        match_type="visual_similarity",
                        evidence_level="verified_visual",
                        similarity_pct=aligned.get("aligned_similarity_pct"),
                        phash_distance=aligned.get("aligned_phash_distance"),
                        metric_explanation=(
                            f"pHash directo {distance}/256 no concluyente por recorte. Alineación geométrica "
                            f"({aligned.get('method')}): cobertura {aligned.get('coverage')}, "
                            f"pHash alineado {aligned.get('aligned_phash_distance')}/256, "
                            f"error medio {aligned.get('mean_absolute_error')}/255. Índice local privado."
                        ),
                        notes="Versión recortada o reescalada detectada por alineación geométrica local; requiere comprobación manual.",
                        extra={"local_entry_id": row["id"], "kind": "index" if is_index else "history", "alignment": aligned},
                    )
                )
            else:
                classification = classify_distance(distance, exact)
                candidates.append(
                    Candidate(
                        provider=self.name,
                        source_url=source_url,
                        page_url=page_url,
                        title=str(label or "Imagen en el índice local"),
                        domain=domain,
                        published_at=row["created_at"],
                        published_at_note="Fecha de ingreso al índice local (no fecha de publicación en Internet).",
                        local_thumbnail=local_thumb,
                        match_type=classification,
                        evidence_level="verified_exact" if exact else "verified_visual",
                        similarity_pct=100.0 if exact else similarity_from_distance(distance),
                        phash_distance=0 if exact else distance,
                        sha256_match=exact,
                        metric_explanation=(
                            "SHA-256 idéntico = mismo archivo; en otros casos se usa pHash DCT 16×16: "
                            "similitud = 100 × (1 − distancia Hamming / 256). Índice local privado del usuario."
                        ),
                        notes=(
                            "Coincidencia exacta de bytes verificada en el índice local."
                            if exact
                            else f"Versión visualmente similar en el índice local (distancia pHash {distance}/256)."
                        ),
                        extra={"local_entry_id": row["id"], "kind": "index" if is_index else "history"},
                    )
                )
            if len(candidates) >= ctx.max_results:
                break

        return ProviderOutcome(
            provider=self.name,
            label=self.label,
            kind=self.kind,
            status="ok" if candidates else "empty",
            message=(
                f"Se compararon {compared} entradas permitidas del índice local "
                f"({alignment_checks} con alineación geométrica por posible recorte); "
                f"{len(candidates)} coincidencias verificadas con SHA-256/pHash/alineación."
            ),
            candidates=candidates,
        )

    @staticmethod
    def _source_fields(row, is_index: bool) -> tuple[str, str | None, str, str | None]:
        if is_index:
            label = row["label"]
            source_url = row["source_url"] or f"internal://local-index/{row['id']}"
            return source_url, None, "índice local (privado)", label
        label = row["original_filename"] or row["id"][:12]
        return f"/#/results/{row['id']}", f"/#/results/{row['id']}", "historial del usuario", label

    @staticmethod
    def _alignment(ctx: SearchContext, stored_path: str | None) -> dict | None:
        if not stored_path:
            return None
        path = Path(stored_path)
        if not path.is_absolute():
            path = ctx.settings.data_dir / path
        if not path.is_file():
            return None
        try:
            with Image.open(path) as opened:
                candidate = opened.convert("RGB")
            return alignment_assessment(candidate, ctx.query_image)
        except (OSError, ValueError):
            return None

    @staticmethod
    def _copy_thumb(ctx: SearchContext, stored_path: str | None) -> str | None:
        if not stored_path:
            return None
        source = Path(stored_path)
        if not source.is_absolute():
            source = ctx.settings.data_dir / stored_path
        if not source.exists() or not source.is_file():
            return None
        try:
            thumbs = ctx.investigation_dir / "thumbs"
            thumbs.mkdir(parents=True, exist_ok=True)
            name = f"{uuid.uuid4().hex}.jpg"
            shutil.copyfile(source, thumbs / name)
            return f"thumbs/{name}"
        except OSError:
            return None
