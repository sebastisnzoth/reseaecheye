"""FastAPI application: private API, signed assets and SPA hosting."""

from __future__ import annotations

import importlib.util
import json
import re
import shutil
import threading
from contextlib import asynccontextmanager
from pathlib import Path
from typing import Any

from fastapi import FastAPI, File, Form, HTTPException, Request, UploadFile
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, HTMLResponse, JSONResponse, Response
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field

from . import __version__
from .config import Settings
from .db import utcnow
from .providers.registry import provider_catalog
from .reports import render_pdf
from .security import (
    ALLOWED_EXTENSIONS,
    ValidationError,
    client_ip,
    fetch_public_image,
    require_owner,
    sanitize_image,
    sign_resource,
    verify_signature,
)
from .service import (
    Runtime,
    add_index_entry,
    compare_with_upload,
    create_investigation,
    create_runtime,
    delete_investigation,
    detail,
    investigation_dir,
    purge_expired,
    regenerate_report,
)

THUMB_NAME_RE = re.compile(r"^thumbs/[a-f0-9]{32}\.(jpg|png)$")
LANGS = {"es", "pt", "en"}


class UrlRequest(BaseModel):
    image_url: str = Field(min_length=8, max_length=2048)
    keywords: str = Field(default="", max_length=500)
    allow_gps: bool = False
    allow_external: bool = True
    retention_hours: int = Field(default=24, ge=1, le=168)
    lang: str = "es"


class SignedLinkRequest(BaseModel):
    format: str = Field(default="pdf", pattern="^(pdf|json)$")


def _clean_lang(raw: str | None) -> str:
    value = (raw or "es").split("-")[0].lower()
    return value if value in LANGS else "es"


def _asset_url(rt: Runtime, investigation_id: str, kind: str, name: str = "") -> str:
    resource = f"asset:{investigation_id}:{kind}:{name}"
    exp, sig = sign_resource(rt.settings.secret_key, resource, rt.settings.signed_url_ttl_seconds)
    url = f"/api/assets/{investigation_id}/{kind}?exp={exp}&sig={sig}"
    if name:
        url += f"&name={name}"
    return url


def _report_url(rt: Runtime, investigation_id: str, fmt: str) -> str:
    resource = f"report:{investigation_id}:{fmt}"
    exp, sig = sign_resource(rt.settings.secret_key, resource, rt.settings.signed_url_ttl_seconds)
    return f"/api/downloads/{investigation_id}/{fmt}?exp={exp}&sig={sig}"


def _public_investigation(data: dict[str, Any]) -> dict[str, Any]:
    for key in ("asset_original", "asset_display", "asset_diff", "report_pdf", "owner_hash"):
        data.pop(key, None)
    return data


def _owned_or_404(rt: Runtime, investigation_id: str, owner_hash: str) -> dict[str, Any]:
    data = detail(rt, investigation_id, owner_hash)
    if not data:
        raise HTTPException(status_code=404, detail="Investigación no encontrada o no autorizada.")
    return data


def _validate_upload(filename: str | None, data: bytes, settings: Settings):
    return sanitize_image(data, filename or "", settings.max_upload_bytes)


def create_app(settings: Settings | None = None) -> FastAPI:
    cfg = settings or Settings.from_env()
    rt = create_runtime(cfg)
    stop_event = threading.Event()

    def retention_loop() -> None:
        while not stop_event.wait(900):
            try:
                purge_expired(rt)
            except Exception:  # pragma: no cover - retention must never crash the app
                pass

    @asynccontextmanager
    async def lifespan(app: FastAPI):  # noqa: ARG001
        try:
            purge_expired(rt)
        except Exception:
            pass
        worker = threading.Thread(target=retention_loop, name="imagetrace-retention", daemon=True)
        worker.start()
        yield
        stop_event.set()
        rt.executor.shutdown(wait=False, cancel_futures=True)

    app = FastAPI(
        title="ImageTrace OSINT",
        version=__version__,
        description="Análisis verificable de imágenes públicas. Sin resultados simulados.",
        lifespan=lifespan,
    )
    app.state.runtime = rt
    if cfg.cors_origins:
        app.add_middleware(
            CORSMiddleware,
            allow_origins=cfg.cors_origins,
            allow_methods=["GET", "POST", "DELETE", "OPTIONS"],
            allow_headers=["X-Owner-Token", "Content-Type"],
        )

    @app.exception_handler(ValidationError)
    async def validation_handler(_: Request, exc: ValidationError) -> JSONResponse:
        return JSONResponse(status_code=400, content={"detail": str(exc)})

    # ------------------------------------------------------------------ meta
    @app.get("/api/health")
    def health() -> dict[str, Any]:
        return {"status": "ok", "version": __version__, "time": utcnow()}

    @app.get("/api/config")
    def config() -> dict[str, Any]:
        return {
            "name": "ImageTrace OSINT",
            "version": __version__,
            "languages": ["es", "pt", "en"],
            "accepted_formats": sorted(ALLOWED_EXTENSIONS),
            "max_upload_mb": cfg.max_upload_mb,
            "max_url_download_mb": cfg.max_url_download_mb,
            "retention_hours": cfg.retention_hours,
            "rate_limit_per_minute": cfg.rate_limit_per_minute,
            "signed_url_ttl_seconds": cfg.signed_url_ttl_seconds,
            "external_providers_enabled": cfg.external_providers_enabled,
            "providers": provider_catalog(),
            "ocr": {
                "tesseract": bool(shutil.which("tesseract") or cfg.tesseract_cmd),
                "rapidocr": importlib.util.find_spec("rapidocr_onnxruntime") is not None,
            },
            "exiftool": bool(shutil.which("exiftool")),
            "database": cfg.database_path.name,
            "honesty_notice": (
                "No existe búsqueda inversa automática de toda Internet. Los conectores externos "
                "buscan candidatos por texto y los verifican localmente; el resto son enlaces manuales."
            ),
            "policy": {
                "face_recognition": False,
                "person_profiling": False,
                "paid_apis": False,
                "fabricated_results": False,
            },
        }

    # ------------------------------------------------------------ investigate
    @app.post("/api/investigations", status_code=201)
    def upload_investigation(
        request: Request,
        file: UploadFile | None = File(default=None),
        keywords: str = Form(default=""),
        allow_gps: bool = Form(default=False),
        allow_external: bool = Form(default=True),
        retention_hours: int = Form(default=24),
        lang: str = Form(default="es"),
    ) -> dict[str, Any]:
        _, owner = require_owner(request)
        rt.limiter.check(client_ip(request))
        if file is None:
            raise HTTPException(status_code=400, detail="Debe adjuntar un archivo de imagen.")
        data = file.file.read(cfg.max_upload_bytes + 1)
        try:
            clean = _validate_upload(file.filename, data, cfg)
        except ValidationError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc
        return _create(rt, owner, clean, "upload", None, file.filename, keywords, allow_gps, allow_external, retention_hours, lang)

    @app.post("/api/investigations/url", status_code=201)
    def url_investigation(body: UrlRequest, request: Request) -> dict[str, Any]:
        _, owner = require_owner(request)
        rt.limiter.check(client_ip(request))
        try:
            data, final_url = fetch_public_image(body.image_url, cfg)
            clean = _validate_upload(None, data, cfg)
        except ValidationError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc
        return _create(
            rt, owner, clean, "url", final_url, Path(final_url).name[:120], body.keywords,
            body.allow_gps, body.allow_external, body.retention_hours, body.lang,
        )

    def _create(
        runtime: Runtime,
        owner: str,
        clean: Any,
        source_kind: str,
        source_url: str | None,
        filename: str | None,
        keywords: str,
        allow_gps: bool,
        allow_external: bool,
        retention_hours: int,
        lang: str,
    ) -> dict[str, Any]:
        investigation_id = create_investigation(
            runtime,
            owner_hash=owner,
            clean=clean,
            source_kind=source_kind,
            source_url=source_url,
            original_filename=filename,
            keywords=keywords,
            allow_gps=bool(allow_gps),
            allow_external=bool(allow_external),
            retention_hours=max(1, min(168, int(retention_hours))),
            lang=_clean_lang(lang),
        )
        return {
            "id": investigation_id,
            "status": "queued",
            "progress_url": f"/api/investigations/{investigation_id}/status",
            "detail_url": f"/api/investigations/{investigation_id}",
        }

    # ------------------------------------------------------------------ reads
    @app.get("/api/investigations")
    def history(request: Request, limit: int = 50) -> dict[str, Any]:
        _, owner = require_owner(request)
        rows = rt.db.fetchall(
            "SELECT id, created_at, status, stage, progress, sha256, width, height, original_filename, "
            "source_url, lang, expires_at, error FROM investigations "
            "WHERE owner_hash = ? AND deleted_at IS NULL ORDER BY created_at DESC LIMIT ?",
            (owner, max(1, min(200, limit))),
        )
        items = []
        for row in rows:
            item = dict(row)
            counts = rt.db.fetchone(
                "SELECT SUM(CASE WHEN evidence_level IN ('verified_exact','verified_visual') THEN 1 ELSE 0 END) AS verified, "
                "COUNT(*) AS total FROM matches WHERE investigation_id = ?",
                (row["id"],),
            )
            item["verified_matches"] = int(counts["verified"] or 0)
            item["total_matches"] = int(counts["total"] or 0)
            item["thumbnail_url"] = _asset_url(rt, row["id"], "display")
            items.append(item)
        return {"items": items, "count": len(items)}

    @app.get("/api/investigations/{investigation_id}/status")
    def status(investigation_id: str, request: Request) -> dict[str, Any]:
        _, owner = require_owner(request)
        row = rt.db.fetchone(
            "SELECT id, status, stage, progress, error, updated_at FROM investigations "
            "WHERE id = ? AND owner_hash = ?",
            (investigation_id, owner),
        )
        if not row:
            raise HTTPException(status_code=404, detail="Investigación no encontrada o no autorizada.")
        return dict(row)

    @app.get("/api/investigations/{investigation_id}")
    def investigation_detail(investigation_id: str, request: Request) -> dict[str, Any]:
        _, owner = require_owner(request)
        data = _owned_or_404(rt, investigation_id, owner)
        data["display_url"] = _asset_url(rt, investigation_id, "display")
        if data.get("asset_diff"):
            data["diff_url"] = _asset_url(rt, investigation_id, "diff")
        data["report_urls"] = {
            "json": f"/api/investigations/{investigation_id}/report/json",
            "pdf": f"/api/investigations/{investigation_id}/report/pdf",
        }
        for match in data["matches"]:
            name = match.get("local_thumbnail")
            if name and THUMB_NAME_RE.match(name):
                match["thumbnail_url_signed"] = _asset_url(rt, investigation_id, "thumb", name)
        return {"investigation": _public_investigation(data)}

    @app.delete("/api/investigations/{investigation_id}")
    def remove_investigation(investigation_id: str, request: Request) -> dict[str, Any]:
        _, owner = require_owner(request)
        if not delete_investigation(rt, investigation_id, owner):
            raise HTTPException(status_code=404, detail="Investigación no encontrada o no autorizada.")
        return {"deleted": True, "id": investigation_id}

    # --------------------------------------------------------------- comparer
    @app.post("/api/investigations/{investigation_id}/compare")
    def compare(
        investigation_id: str,
        request: Request,
        file: UploadFile = File(...),
    ) -> dict[str, Any]:
        _, owner = require_owner(request)
        rt.limiter.check(client_ip(request))
        _owned_or_404(rt, investigation_id, owner)
        data = file.file.read(cfg.max_upload_bytes + 1)
        try:
            clean_b = _validate_upload(file.filename, data, cfg)
        except ValidationError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc
        result = compare_with_upload(rt, investigation_id, clean_b)
        result["diff_url"] = _asset_url(rt, investigation_id, "diff")
        return result

    # ---------------------------------------------------------------- reports
    @app.get("/api/investigations/{investigation_id}/report/json")
    def report_json(investigation_id: str, request: Request) -> Response:
        _, owner = require_owner(request)
        data = _owned_or_404(rt, investigation_id, owner)
        report = data.get("report") or regenerate_report(rt, investigation_id)
        return Response(
            content=json.dumps(report, ensure_ascii=False, indent=2),
            media_type="application/json",
            headers={"Content-Disposition": f'attachment; filename="imagetrace-{investigation_id[:12]}.json"'},
        )

    @app.get("/api/investigations/{investigation_id}/report/pdf")
    def report_pdf(investigation_id: str, request: Request) -> Response:
        _, owner = require_owner(request)
        data = _owned_or_404(rt, investigation_id, owner)
        path = Path(data.get("report_pdf") or "")
        if path.is_file():
            return FileResponse(
                path,
                media_type="application/pdf",
                filename=f"imagetrace-{investigation_id[:12]}.pdf",
            )
        report = data.get("report") or regenerate_report(rt, investigation_id)
        return Response(
            content=render_pdf(report),
            media_type="application/pdf",
            headers={"Content-Disposition": f'attachment; filename="imagetrace-{investigation_id[:12]}.pdf"'},
        )

    @app.post("/api/investigations/{investigation_id}/signed-link")
    def signed_link(investigation_id: str, body: SignedLinkRequest, request: Request) -> dict[str, Any]:
        _, owner = require_owner(request)
        _owned_or_404(rt, investigation_id, owner)
        return {
            "url": _report_url(rt, investigation_id, body.format),
            "expires_in_seconds": cfg.signed_url_ttl_seconds,
            "note": "La URL contiene solo una firma HMAC con vencimiento; el token de propietario nunca viaja en la URL.",
        }

    @app.get("/api/downloads/{investigation_id}/{fmt}")
    def signed_download(
        investigation_id: str, fmt: str, request: Request, exp: int = 0, sig: str = ""
    ) -> Response:
        if fmt not in {"pdf", "json"}:
            raise HTTPException(status_code=400, detail="Formato no soportado.")
        resource = f"report:{investigation_id}:{fmt}"
        if not verify_signature(cfg.secret_key, resource, exp, sig):
            raise HTTPException(status_code=403, detail="Firma inválida o vencida.")
        row = rt.db.fetchone("SELECT report_json, report_pdf FROM investigations WHERE id = ?", (investigation_id,))
        if not row:
            raise HTTPException(status_code=404, detail="Informe no disponible.")
        if fmt == "json":
            content = row["report_json"] or "{}"
            return Response(
                content=content.encode("utf-8"),
                media_type="application/json",
                headers={"Content-Disposition": f'attachment; filename="imagetrace-{investigation_id[:12]}.json"'},
            )
        path = Path(row["report_pdf"] or "")
        if not path.is_file():
            raise HTTPException(status_code=404, detail="PDF no generado todavía.")
        return FileResponse(path, media_type="application/pdf", filename=f"imagetrace-{investigation_id[:12]}.pdf")

    # ----------------------------------------------------------------- assets
    @app.get("/api/assets/{investigation_id}/{kind}")
    def asset(
        investigation_id: str,
        kind: str,
        request: Request,
        exp: int = 0,
        sig: str = "",
        name: str = "",
    ) -> Response:
        if kind not in {"display", "thumb", "diff"}:
            raise HTTPException(status_code=404, detail="Recurso no soportado.")
        if kind == "thumb" and not THUMB_NAME_RE.match(name):
            raise HTTPException(status_code=400, detail="Nombre de miniatura inválido.")
        resource = f"asset:{investigation_id}:{kind}:{name}"
        if not verify_signature(cfg.secret_key, resource, exp, sig):
            raise HTTPException(status_code=403, detail="Firma inválida o vencida.")
        row = rt.db.fetchone(
            "SELECT asset_display, asset_diff FROM investigations WHERE id = ?", (investigation_id,)
        )
        if not row:
            raise HTTPException(status_code=404, detail="Recurso no encontrado.")
        directory = investigation_dir(rt, investigation_id)
        if kind == "display":
            path = Path(row["asset_display"] or "")
            media = "image/png" if path.suffix == ".png" else "image/jpeg"
        elif kind == "diff":
            path = Path(row["asset_diff"] or "")
            media = "image/png"
        else:
            path = directory / name
            media = "image/png" if path.suffix == ".png" else "image/jpeg"
        try:
            resolved = path.resolve()
            if directory.resolve() not in resolved.parents or not resolved.is_file():
                raise HTTPException(status_code=404, detail="Recurso no encontrado.")
        except OSError as exc:
            raise HTTPException(status_code=404, detail="Recurso no encontrado.") from exc
        headers = {
            "Cache-Control": "private, no-store",
            "X-Content-Type-Options": "nosniff",
            "Content-Security-Policy": "default-src 'none'; img-src 'self' data:; style-src 'unsafe-inline'",
        }
        return FileResponse(resolved, media_type=media, headers=headers)

    # ------------------------------------------------------------ local index
    @app.post("/api/index", status_code=201)
    def add_index(
        request: Request,
        file: UploadFile | None = File(default=None),
        image_url: str | None = Form(default=None),
        label: str = Form(default="Imagen permitida"),
        retention_hours: int = Form(default=24),
    ) -> dict[str, Any]:
        _, owner = require_owner(request)
        rt.limiter.check(client_ip(request))
        if file is not None:
            data = file.file.read(cfg.max_upload_bytes + 1)
            clean = _validate_upload(file.filename, data, cfg)
            source = None
            filename = file.filename
        elif image_url:
            try:
                data, final_url = fetch_public_image(image_url, cfg)
                clean = _validate_upload(None, data, cfg)
                source = final_url
                filename = Path(final_url).name[:120]
            except ValidationError as exc:
                raise HTTPException(status_code=400, detail=str(exc)) from exc
        else:
            raise HTTPException(status_code=400, detail="Adjunte una imagen o una URL pública.")
        entry_id = add_index_entry(
            rt, owner, clean, label or filename or "Imagen permitida", source,
            max(1, min(168, int(retention_hours))),
        )
        return {"id": entry_id, "detail": "Imagen agregada al índice privado permitido por el usuario."}

    @app.get("/api/index")
    def list_index(request: Request) -> dict[str, Any]:
        _, owner = require_owner(request)
        rows = rt.db.fetchall(
            "SELECT id, sha256, phash, width, height, label, source_url, created_at, expires_at "
            "FROM index_entries WHERE owner_hash = ? ORDER BY created_at DESC LIMIT 200",
            (owner,),
        )
        return {"items": [dict(r) for r in rows], "count": len(rows)}

    @app.delete("/api/index/{entry_id}")
    def delete_index(entry_id: str, request: Request) -> dict[str, Any]:
        _, owner = require_owner(request)
        row = rt.db.fetchone(
            "SELECT asset_path FROM index_entries WHERE id = ? AND owner_hash = ?", (entry_id, owner)
        )
        if not row:
            raise HTTPException(status_code=404, detail="Entrada no encontrada.")
        path = Path(row["asset_path"] or "")
        rt.db.execute("DELETE FROM index_entries WHERE id = ?", (entry_id,))
        if path.is_absolute() and path.is_file() and cfg.data_dir in path.parents:
            try:
                path.unlink()
            except OSError:
                pass
        rt.db.audit(owner, "delete_index_entry", entry_id)
        return {"deleted": True, "id": entry_id}

    # ---------------------------------------------------------------- privacy
    @app.post("/api/privacy/purge")
    def purge(request: Request) -> dict[str, Any]:
        _, owner = require_owner(request)
        rt.db.audit(owner, "purge_expired")
        return {"removed": purge_expired(rt), "note": "Se eliminaron archivos e investigaciones vencidos según la política de retención."}

    @app.delete("/api/privacy/all")
    def delete_all(request: Request) -> dict[str, Any]:
        _, owner = require_owner(request)
        rows = rt.db.fetchall(
            "SELECT id FROM investigations WHERE owner_hash = ?", (owner,)
        )
        for row in rows:
            delete_investigation(rt, row["id"], owner)
        index_rows = rt.db.fetchall(
            "SELECT id, asset_path FROM index_entries WHERE owner_hash = ?", (owner,)
        )
        for entry in index_rows:
            path = Path(entry["asset_path"] or "")
            if path.is_absolute() and path.is_file() and cfg.data_dir in path.parents:
                try:
                    path.unlink()
                except OSError:
                    pass
            rt.db.execute("DELETE FROM index_entries WHERE id = ?", (entry["id"],))
        rt.db.audit(owner, "delete_all_data")
        return {"deleted_investigations": len(rows), "deleted_index_entries": len(index_rows)}

    # -------------------------------------------------------------------- SPA
    dist = cfg.frontend_dist
    if (dist / "index.html").is_file():
        assets_dir = dist / "assets"
        if assets_dir.is_dir():
            app.mount("/assets", StaticFiles(directory=str(assets_dir)), name="frontend-assets")

        @app.get("/{full_path:path}", include_in_schema=False)
        def spa(full_path: str) -> Response:  # noqa: ARG001
            if full_path.startswith("api/"):
                raise HTTPException(status_code=404, detail="Endpoint no encontrado.")
            candidate = (dist / full_path).resolve()
            if dist.resolve() in candidate.parents and candidate.is_file():
                return FileResponse(candidate)
            return FileResponse(dist / "index.html", media_type="text/html", headers={"Cache-Control": "no-cache"})
    else:
        @app.get("/", include_in_schema=False)
        def no_frontend() -> HTMLResponse:
            return HTMLResponse(
                "<h1>ImageTrace OSINT API</h1><p>Backend operativo. "
                "Construya el frontend con <code>npm run build</code> o use <code>npm run dev</code> "
                "(proxy /api). Documentación: <a href='/docs'>/docs</a>.</p>",
                status_code=200,
            )

    return app


app = create_app()
