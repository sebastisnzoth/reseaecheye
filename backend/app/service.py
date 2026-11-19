"""Investigation lifecycle: validation, analysis, providers, reports, retention."""

from __future__ import annotations

import json
import shutil
import uuid
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any

from PIL import Image

from .config import Settings
from .db import Database, utcnow
from .imaging import (
    bytes_sha256,
    compare_images,
    exif_analysis,
    forensic_signals,
    ocr_analysis,
    phash_hex,
    scene_signals,
)
from .providers.base import SearchContext
from .providers.registry import run_providers
from .reports import build_report, persist_report, render_pdf
from .security import RateLimiter, SanitizedImage


@dataclass
class Runtime:
    settings: Settings
    db: Database
    limiter: RateLimiter
    executor: ThreadPoolExecutor = field(default=None)  # type: ignore[assignment]


def create_runtime(settings: Settings) -> Runtime:
    settings.data_dir.mkdir(parents=True, exist_ok=True)
    (settings.data_dir / "investigations").mkdir(parents=True, exist_ok=True)
    (settings.data_dir / "index").mkdir(parents=True, exist_ok=True)
    db = Database(settings)
    return Runtime(
        settings=settings,
        db=db,
        limiter=RateLimiter(settings.rate_limit_per_minute),
        executor=ThreadPoolExecutor(max_workers=2, thread_name_prefix="imagetrace"),
    )


def investigation_dir(rt: Runtime, investigation_id: str) -> Path:
    return rt.settings.data_dir / "investigations" / investigation_id


def _json_load(value: str | None, default: Any) -> Any:
    if not value:
        return default
    try:
        return json.loads(value)
    except json.JSONDecodeError:
        return default


def row_to_dict(row: Any) -> dict[str, Any]:
    data = dict(row)
    for column, key in (
        ("metadata_json", "metadata"),
        ("forensics_json", "forensics"),
        ("ocr_json", "ocr"),
        ("scene_json", "scene"),
        ("comparison_json", "comparison"),
        ("manual_links_json", "manual_links"),
        ("report_json", "report"),
    ):
        data[key] = _json_load(data.get(column), {} if key != "manual_links" else [])
        data.pop(column, None)
    data["allow_gps"] = bool(data.get("allow_gps"))
    data["allow_external"] = bool(data.get("allow_external"))
    return data


def get_investigation(rt: Runtime, investigation_id: str, owner_hash: str) -> dict[str, Any] | None:
    row = rt.db.fetchone(
        "SELECT * FROM investigations WHERE id = ? AND owner_hash = ? AND deleted_at IS NULL",
        (investigation_id, owner_hash),
    )
    return row_to_dict(row) if row else None


def get_matches(rt: Runtime, investigation_id: str) -> list[dict[str, Any]]:
    rows = rt.db.fetchall(
        "SELECT * FROM matches WHERE investigation_id = ? ORDER BY "
        "CASE evidence_level WHEN 'verified_exact' THEN 0 WHEN 'verified_visual' THEN 1 ELSE 2 END, "
        "similarity DESC, created_at ASC",
        (investigation_id,),
    )
    result = []
    for row in rows:
        item = dict(row)
        item["sha256_match"] = bool(item.get("sha256_match"))
        result.append(item)
    return result


def get_provider_runs(rt: Runtime, investigation_id: str) -> list[dict[str, Any]]:
    return [dict(r) for r in rt.db.fetchall(
        "SELECT * FROM provider_runs WHERE investigation_id = ? ORDER BY checked_at", (investigation_id,)
    )]


def detail(rt: Runtime, investigation_id: str, owner_hash: str) -> dict[str, Any] | None:
    investigation = get_investigation(rt, investigation_id, owner_hash)
    if not investigation:
        return None
    return {
        **investigation,
        "matches": get_matches(rt, investigation_id),
        "provider_runs": get_provider_runs(rt, investigation_id),
    }


def _progress(rt: Runtime, investigation_id: str, stage: str, progress: int) -> None:
    rt.db.execute(
        "UPDATE investigations SET stage = ?, progress = ?, status = 'processing', updated_at = ? WHERE id = ?",
        (stage, progress, utcnow(), investigation_id),
    )


def create_investigation(
    rt: Runtime,
    *,
    owner_hash: str,
    clean: SanitizedImage,
    source_kind: str,
    source_url: str | None,
    original_filename: str | None,
    keywords: str,
    allow_gps: bool,
    allow_external: bool,
    retention_hours: int,
    lang: str,
) -> str:
    investigation_id = uuid.uuid4().hex
    directory = investigation_dir(rt, investigation_id)
    directory.mkdir(parents=True, exist_ok=True)
    ext = {"JPEG": "jpg", "PNG": "png", "WEBP": "webp"}.get(clean.fmt, "jpg")
    original_path = directory / f"original.{ext}"
    display_name = "display.png" if clean.display_bytes[:8] == b"\x89PNG\r\n\x1a\n" else "display.jpg"
    display_path = directory / display_name
    original_path.write_bytes(clean.original_bytes)
    display_path.write_bytes(clean.display_bytes)
    sha = bytes_sha256(clean.original_bytes)
    now = utcnow()
    expires = (datetime.now(timezone.utc) + timedelta(hours=max(1, retention_hours))).isoformat(timespec="seconds")
    rt.db.execute(
        "INSERT INTO investigations(id, owner_hash, created_at, updated_at, status, stage, progress, lang, "
        "source_kind, source_url, original_filename, mime, size_bytes, sha256, width, height, keywords, "
        "allow_gps, allow_external, retention_hours, expires_at, asset_original, asset_display) "
        "VALUES (?, ?, ?, ?, 'queued', 'validation', 5, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
        (
            investigation_id,
            owner_hash,
            now,
            now,
            lang,
            source_kind,
            source_url,
            original_filename,
            clean.mime,
            len(clean.original_bytes),
            sha,
            clean.width,
            clean.height,
            keywords[:500],
            int(allow_gps),
            int(allow_external),
            retention_hours,
            expires,
            str(original_path),
            str(display_path),
        ),
    )
    # Every analysed image is added to the owner's private local index.
    rt.db.execute(
        "INSERT INTO index_entries(id, owner_hash, sha256, phash, width, height, label, source_url, "
        "asset_path, created_at, expires_at) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
        (
            uuid.uuid4().hex,
            owner_hash,
            sha,
            None,
            clean.width,
            clean.height,
            f"investigación:{investigation_id[:12]}",
            source_url,
            str(display_path),
            now,
            expires,
        ),
    )
    rt.db.audit(owner_hash, "create_investigation", investigation_id, f"source={source_kind}")
    if rt.settings.sync_processing:
        run_pipeline(rt, investigation_id)
    else:
        rt.executor.submit(run_pipeline, rt, investigation_id)
    return investigation_id


def run_pipeline(rt: Runtime, investigation_id: str) -> None:
    """Real staged processing; each stage writes its actual progress to the DB."""
    row = rt.db.fetchone("SELECT * FROM investigations WHERE id = ?", (investigation_id,))
    if not row:
        return
    directory = investigation_dir(rt, investigation_id)
    try:
        _progress(rt, investigation_id, "validation", 10)
        with Image.open(row["asset_original"]) as opened:
            original_bytes = Path(row["asset_original"]).read_bytes()
            image = opened.convert("RGB")
            fmt = (opened.format or "").upper()

        _progress(rt, investigation_id, "hashes", 25)
        phash = phash_hex(image)
        rt.db.execute(
            "UPDATE investigations SET phash = ?, updated_at = ? WHERE id = ?",
            (phash, utcnow(), investigation_id),
        )
        rt.db.execute(
            "UPDATE index_entries SET phash = ? WHERE label = ? AND owner_hash = ?",
            (phash, f"investigación:{investigation_id[:12]}", row["owner_hash"]),
        )

        _progress(rt, investigation_id, "metadata", 40)
        metadata = exif_analysis(
            image,
            allow_gps=bool(row["allow_gps"]),
            exiftool_path=str(row["asset_original"]),
        )
        rt.db.execute(
            "UPDATE investigations SET metadata_json = ?, exiftool_available = ? WHERE id = ?",
            (json.dumps(metadata, ensure_ascii=False), int(metadata["exiftool_available"]), investigation_id),
        )

        _progress(rt, investigation_id, "forensics", 55)
        forensics = forensic_signals(image, original_bytes, fmt)
        scene = scene_signals(image)
        rt.db.execute(
            "UPDATE investigations SET forensics_json = ?, scene_json = ? WHERE id = ?",
            (json.dumps(forensics, ensure_ascii=False), json.dumps(scene, ensure_ascii=False), investigation_id),
        )

        _progress(rt, investigation_id, "ocr", 68)
        ocr = ocr_analysis(image, rt.settings)
        rt.db.execute(
            "UPDATE investigations SET ocr_json = ? WHERE id = ?",
            (json.dumps(ocr, ensure_ascii=False), investigation_id),
        )

        _progress(rt, investigation_id, "providers", 80)
        keywords = [k.strip() for k in (row["keywords"] or "").split(",") if k.strip()][:8]
        ctx = SearchContext(
            settings=rt.settings,
            db=rt.db,
            owner_hash=row["owner_hash"],
            investigation_id=investigation_id,
            investigation_dir=directory,
            query_image=image,
            sha256=row["sha256"],
            phash=phash,
            keywords=keywords,
            ocr_terms=ocr.get("terms", []),
            allow_external=bool(row["allow_external"]),
            max_results=rt.settings.max_provider_results,
            lang=row["lang"] or "es",
        )
        outcomes, candidates, manual_links = run_providers(ctx)
        for candidate in candidates:
            values = candidate.to_row(investigation_id)
            values["raw_json"] = json.dumps(candidate.extra, ensure_ascii=False)
            columns = ", ".join(values)
            placeholders = ", ".join("?" for _ in values)
            rt.db.execute(
                f"INSERT INTO matches({columns}) VALUES ({placeholders})", tuple(values.values())
            )
        rt.db.execute(
            "UPDATE investigations SET manual_links_json = ? WHERE id = ?",
            (json.dumps(manual_links, ensure_ascii=False), investigation_id),
        )

        _progress(rt, investigation_id, "report", 94)
        regenerate_report(rt, investigation_id)
        rt.db.execute(
            "UPDATE investigations SET status = 'done', stage = 'done', progress = 100, "
            "error = NULL, updated_at = ? WHERE id = ?",
            (utcnow(), investigation_id),
        )
    except Exception as exc:  # noqa: BLE001 - a failed analysis must still be explainable
        message = f"{type(exc).__name__}: {exc}"
        rt.db.execute(
            "UPDATE investigations SET status = 'failed', stage = 'error', error = ?, updated_at = ? WHERE id = ?",
            (message[:1000], utcnow(), investigation_id),
        )
        try:
            regenerate_report(rt, investigation_id, pipeline_error=message)
        except Exception:  # pragma: no cover - never hide the original failure
            pass


def regenerate_report(rt: Runtime, investigation_id: str, pipeline_error: str | None = None) -> dict[str, Any]:
    row = rt.db.fetchone("SELECT * FROM investigations WHERE id = ?", (investigation_id,))
    if not row:
        raise ValueError("Investigación inexistente")
    investigation = row_to_dict(row)
    matches = get_matches(rt, investigation_id)
    runs = get_provider_runs(rt, investigation_id)
    report = build_report(investigation, matches, runs, investigation.get("lang") or "es")
    if pipeline_error:
        report["limitations"].insert(0, f"El procesamiento falló parcialmente: {pipeline_error}. Los datos ausentes no se inventan.")
        report["conclusions"].append("El informe está incompleto por un fallo técnico; repita el análisis antes de usarlo como evidencia.")
    pdf_bytes = render_pdf(report)
    persist_report(rt.db, investigation_id, report, pdf_bytes, investigation_dir(rt, investigation_id))
    return report


def compare_with_upload(
    rt: Runtime, investigation_id: str, clean_b: SanitizedImage
) -> dict[str, Any]:
    row = rt.db.fetchone("SELECT * FROM investigations WHERE id = ?", (investigation_id,))
    if not row:
        raise ValueError("Investigación inexistente")
    with Image.open(row["asset_original"]) as opened:
        image_a = opened.convert("RGB")
        bytes_a = Path(row["asset_original"]).read_bytes()
    result, heatmap = compare_images(image_a, bytes_a, clean_b.image, clean_b.original_bytes)
    if heatmap:
        path = investigation_dir(rt, investigation_id) / "diff.png"
        path.write_bytes(heatmap)
        rt.db.execute(
            "UPDATE investigations SET asset_diff = ? WHERE id = ?", (str(path), investigation_id)
        )
        result["heatmap_url_name"] = "diff.png"
    rt.db.execute(
        "UPDATE investigations SET comparison_json = ?, updated_at = ? WHERE id = ?",
        (json.dumps(result, ensure_ascii=False), utcnow(), investigation_id),
    )
    regenerate_report(rt, investigation_id)
    return result


def delete_investigation(rt: Runtime, investigation_id: str, owner_hash: str) -> bool:
    row = rt.db.fetchone(
        "SELECT id FROM investigations WHERE id = ? AND owner_hash = ?", (investigation_id, owner_hash)
    )
    if not row:
        return False
    directory = investigation_dir(rt, investigation_id)
    rt.db.execute(
        "DELETE FROM index_entries WHERE owner_hash = ? AND label = ?",
        (owner_hash, f"investigación:{investigation_id[:12]}"),
    )
    rt.db.execute("DELETE FROM investigations WHERE id = ?", (investigation_id,))
    if directory.exists():
        shutil.rmtree(directory, ignore_errors=True)
    rt.db.audit(owner_hash, "delete_investigation", investigation_id)
    return True


def purge_expired(rt: Runtime) -> int:
    now = utcnow()
    rows = rt.db.fetchall(
        "SELECT id FROM investigations WHERE expires_at IS NOT NULL AND expires_at <= ? AND deleted_at IS NULL",
        (now,),
    )
    for row in rows:
        owner = rt.db.fetchone("SELECT owner_hash FROM investigations WHERE id = ?", (row["id"],))
        if owner:
            delete_investigation(rt, row["id"], owner["owner_hash"])
            rt.db.audit(owner["owner_hash"], "retention_purge", row["id"])
    stale_index = rt.db.fetchall(
        "SELECT id, asset_path FROM index_entries WHERE expires_at IS NOT NULL AND expires_at <= ?", (now,)
    )
    for entry in stale_index:
        rt.db.execute("DELETE FROM index_entries WHERE id = ?", (entry["id"],))
        path = Path(entry["asset_path"] or "")
        if path.is_absolute() and path.is_file() and rt.settings.data_dir in path.parents:
            try:
                path.unlink()
            except OSError:
                pass
    return len(rows) + len(stale_index)


def add_index_entry(
    rt: Runtime,
    owner_hash: str,
    clean: SanitizedImage,
    label: str,
    source_url: str | None,
    retention_hours: int,
) -> str:
    entry_id = uuid.uuid4().hex
    path = rt.settings.data_dir / "index" / f"{entry_id}.jpg"
    path.write_bytes(clean.display_bytes)
    expires = (datetime.now(timezone.utc) + timedelta(hours=max(1, retention_hours))).isoformat(timespec="seconds")
    rt.db.execute(
        "INSERT INTO index_entries(id, owner_hash, sha256, phash, width, height, label, source_url, "
        "asset_path, created_at, expires_at) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
        (
            entry_id,
            owner_hash,
            bytes_sha256(clean.original_bytes),
            phash_hex(clean.image),
            clean.width,
            clean.height,
            label[:200],
            source_url,
            str(path),
            utcnow(),
            expires,
        ),
    )
    rt.db.audit(owner_hash, "add_index_entry", entry_id)
    return entry_id
