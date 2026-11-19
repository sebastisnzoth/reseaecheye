"""Structured digital report (JSON + PDF) with explicit evidence levels."""

from __future__ import annotations

import html
import json
from datetime import datetime, timezone
from io import BytesIO
from pathlib import Path
from typing import Any

from reportlab.lib import colors
from reportlab.lib.enums import TA_LEFT
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
from reportlab.lib.units import mm
from reportlab.platypus import (
    PageBreak,
    Paragraph,
    SimpleDocTemplate,
    Spacer,
    Table,
    TableStyle,
)

from .db import Database
from .imaging import VISUAL_DISTANCE

STRINGS: dict[str, dict[str, str]] = {
    "es": {
        "title": "Informe digital — ImageTrace OSINT",
        "subtitle": "Análisis verificable de imágenes públicas",
        "generated": "Fecha de análisis",
        "image": "1. Imagen analizada",
        "metadata": "3. Metadatos disponibles",
        "matches": "4. Coincidencias y niveles de evidencia",
        "sources": "5. Fuentes consultadas y estado",
        "first": "6. Primera aparición conocida entre las fuentes consultadas",
        "duplicates": "7. Versiones duplicadas",
        "signals": "8. Señales de modificación",
        "limitations": "9. Limitaciones del análisis",
        "conclusions": "10. Conclusiones fundamentadas",
        "verified": "Coincidencia comprobada",
        "visual": "Similitud visual calculada",
        "unverified": "Resultado no verificado",
        "none": "Sin resultados",
        "policy": "Política: sin reconocimiento facial, sin perfilado de personas, sin scraping de plataformas sin API. Respete derechos de autor y condiciones de acceso.",
        "facts": "Hechos verificados del archivo",
        "unknowns": "Información desconocida",
        "page": "Página",
    },
    "pt": {
        "title": "Relatório digital — ImageTrace OSINT",
        "subtitle": "Análise verificável de imagens públicas",
        "generated": "Data da análise",
        "image": "1. Imagem analisada",
        "metadata": "3. Metadados disponíveis",
        "matches": "4. Correspondências e níveis de evidência",
        "sources": "5. Fontes consultadas e estado",
        "first": "6. Primeira aparição conhecida entre as fontes consultadas",
        "duplicates": "7. Versões duplicadas",
        "signals": "8. Sinais de modificação",
        "limitations": "9. Limitações da análise",
        "conclusions": "10. Conclusões fundamentadas",
        "verified": "Correspondência comprovada",
        "visual": "Similaridade visual calculada",
        "unverified": "Resultado não verificado",
        "none": "Sem resultados",
        "policy": "Política: sem reconhecimento facial, sem perfilamento de pessoas, sem scraping de plataformas sem API. Respeite direitos autorais e termos de acesso.",
        "facts": "Fatos verificados do arquivo",
        "unknowns": "Informação desconhecida",
        "page": "Página",
    },
    "en": {
        "title": "Digital report — ImageTrace OSINT",
        "subtitle": "Verifiable analysis of public images",
        "generated": "Analysis date",
        "image": "1. Analysed image",
        "metadata": "3. Available metadata",
        "matches": "4. Matches and evidence levels",
        "sources": "5. Sources consulted and status",
        "first": "6. Earliest known appearance among consulted sources",
        "duplicates": "7. Duplicate versions",
        "signals": "8. Modification signals",
        "limitations": "9. Analysis limitations",
        "conclusions": "10. Evidence-based conclusions",
        "verified": "Verified match",
        "visual": "Computed visual similarity",
        "unverified": "Unverified result",
        "none": "No results",
        "policy": "Policy: no face recognition, no person profiling, no scraping of platforms without an API. Respect copyright and platform terms.",
        "facts": "Verified file facts",
        "unknowns": "Unknown information",
        "page": "Page",
    },
}

LIMITATIONS: dict[str, list[str]] = {
    "es": [
        "No existe un índice de toda Internet en esta instalación. Solo se consultan el índice local y los conectores configurados.",
        "Openverse y Wikimedia Commons ofrecen búsqueda por texto, no búsqueda inversa por imagen; los candidatos se verifican localmente con SHA-256 y pHash.",
        "Google Lens, Bing Visual Search, TinEye y Yandex no tienen API gratuita/abierta compatible: se ofrecen enlaces manuales, no resultados automáticos.",
        "La ausencia de coincidencias NO demuestra que la imagen sea inédita ni que no existan copias en Internet.",
        "Las fechas de fuentes externas pueden ser de subida o de indexación, no de publicación original; las fechas desconocidas se reportan como tales.",
        "EXIF es una declaración del archivo: puede eliminarse, editarse o falsificarse.",
        "ELA, ruido y compresión son señales orientativas, sensibles a recortes y recompresiones; NO son prueba concluyente de manipulación.",
        "No se realiza reconocimiento facial, identificación de personas ni perfilamiento biométrico.",
        "Los informes son privados mediante token de propietario; elimine los archivos cuando ya no los necesite.",
    ],
    "pt": [
        "Não existe um índice de toda a Internet nesta instalação. Consultam-se apenas o índice local e os conectores configurados.",
        "Openverse e Wikimedia Commons oferecem busca por texto, não busca reversa por imagem; os candidatos são verificados localmente com SHA-256 e pHash.",
        "Google Lens, Bing Visual Search, TinEye e Yandex não têm API gratuita/aberta compatível: oferecemos links manuais, não resultados automáticos.",
        "A ausência de correspondências NÃO demonstra que a imagem seja inédita ou que não existam cópias na Internet.",
        "Datas de fontes externas podem ser de envio ou indexação, não de publicação original; datas desconhecidas são reportadas como tal.",
        "EXIF é uma declaração do arquivo: pode ser removido, editado ou falsificado.",
        "ELA, ruído e compressão são sinais orientativos, sensíveis a recortes e recompressões; NÃO são prova conclusiva de manipulação.",
        "Não há reconhecimento facial, identificação de pessoas nem perfilamento biométrico.",
        "Os relatórios são privados por token de proprietário; exclua os arquivos quando não precisar mais deles.",
    ],
    "en": [
        "This installation has no index of the entire Internet. Only the local index and configured connectors are queried.",
        "Openverse and Wikimedia Commons provide text search, not reverse image search; candidates are verified locally with SHA-256 and pHash.",
        "Google Lens, Bing Visual Search, TinEye and Yandex have no compatible free/open API: manual links are provided, not automated results.",
        "The absence of matches does NOT prove the image is unpublished or that no copies exist online.",
        "External source dates may be upload or indexing timestamps, not original publication dates; unknown dates are reported as unknown.",
        "EXIF is a file declaration: it can be removed, edited or forged.",
        "ELA, noise and compression are orientative signals sensitive to crops and recompression; they are NOT conclusive proof of manipulation.",
        "No face recognition, person identification or biometric profiling is performed.",
        "Reports are private via an owner token; delete files when no longer needed.",
    ],
}


def _s(lang: str, key: str) -> str:
    return STRINGS.get(lang, STRINGS["es"])[key]


def build_report(
    investigation: dict[str, Any],
    matches: list[dict[str, Any]],
    provider_runs: list[dict[str, Any]],
    lang: str = "es",
) -> dict[str, Any]:
    lang = lang if lang in STRINGS else "es"
    meta = investigation.get("metadata") or {}
    forensics = investigation.get("forensics") or {}
    ocr = investigation.get("ocr") or {}
    scene = investigation.get("scene") or {}
    comparison = investigation.get("comparison") or None
    verified = [m for m in matches if m.get("evidence_level") in {"verified_exact", "verified_visual"}]
    exact = [m for m in verified if m.get("evidence_level") == "verified_exact"]
    visual = [m for m in verified if m.get("evidence_level") == "verified_visual"]
    unverified = [m for m in matches if m.get("evidence_level") not in {"verified_exact", "verified_visual"}]

    dated = [
        m
        for m in verified
        if m.get("published_at") and m.get("provider") not in {"local_index"}
    ]
    first = None
    if dated:
        earliest = min(dated, key=lambda m: str(m.get("published_at")))
        first = {
            "status": "source_timestamp",
            "date": earliest["published_at"],
            "source_url": earliest.get("source_url"),
            "provider": earliest.get("provider"),
            "note": (
                "Fecha más antigua entregada por una fuente consultada para una coincidencia verificada. "
                "Puede ser fecha de subida/indexación; no acredita la primera publicación absoluta. "
                + (earliest.get("published_at_note") or "")
            ),
        }
    else:
        first = {
            "status": "unknown",
            "reason": "Ninguna coincidencia verificada de una fuente externa aportó una fecha comprobable; se reporta como desconocida.",
        }

    conclusions: list[str] = []
    if exact:
        conclusions.append(
            f"Se verificaron {len(exact)} coincidencias exactas de bytes (SHA-256 idéntico) frente a imágenes descargadas o indexadas localmente."
        )
    else:
        conclusions.append("No se verificó ninguna coincidencia exacta de bytes en las fuentes consultadas.")
    if visual:
        conclusions.append(
            f"Se calcularon {len(visual)} similitudes visuales con distancia pHash ≤ {VISUAL_DISTANCE}/256; requieren comprobación manual de la fuente."
        )
    if unverified:
        conclusions.append(
            f"{len(unverified)} candidatos quedaron SIN VERIFICAR (sin descarga, sin imagen comparable o por debajo del umbral); no se cuentan como coincidencias."
        )
    failed = [r for r in provider_runs if r.get("status") in {"unavailable", "error"}]
    if failed:
        conclusions.append(
            "Los conectores "
            + ", ".join(str(r.get("provider")) for r in failed)
            + " no pudieron consultarse; la ausencia de resultados en esas fuentes no es evidencia de ausencia de publicaciones."
        )
    conclusions.append(
        f"Las señales forenses tienen un valor orientativo de {forensics.get('score', 'no disponible')}/100 y no constituyen prueba de manipulación."
    )
    if ocr.get("status") == "ok":
        conclusions.append("Se extrajo texto visible por OCR local; debe revisarse visualmente antes de usarlo como hecho.")
    elif ocr.get("status") == "unavailable":
        conclusions.append("El OCR no estuvo disponible; no se reporta texto inferido.")

    limitations = list(LIMITATIONS[lang])
    if ocr.get("status") == "unavailable":
        limitations.append("Motor OCR no disponible en este entorno; no se extrajo texto.")
    if not meta.get("exiftool_available"):
        limitations.append("ExifTool no está instalado: los metadatos se leyeron con Pillow (subconjunto EXIF estándar).")
    if not meta.get("available"):
        limitations.append("La imagen no contiene EXIF utilizable; no se infieren cámara ni fecha a partir de los píxeles.")
    for run in failed:
        limitations.append(f"Proveedor {run.get('provider')}: {run.get('message')}")

    return {
        "schema_version": "1.0",
        "report_type": "ImageTrace OSINT digital report",
        "generated_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "analysis_date": investigation.get("created_at"),
        "language": lang,
        "investigation_id": investigation.get("id"),
        "image": {
            "sha256": investigation.get("sha256"),
            "phash": investigation.get("phash"),
            "phash_bits": 256,
            "width": investigation.get("width"),
            "height": investigation.get("height"),
            "mime": investigation.get("mime"),
            "size_bytes": investigation.get("size_bytes"),
            "source_kind": investigation.get("source_kind"),
            "source_url": investigation.get("source_url"),
            "original_filename": investigation.get("original_filename"),
        },
        "metadata": meta,
        "scene_signals": scene,
        "forensics": forensics,
        "ocr": ocr,
        "comparison": comparison,
        "sources_consulted": [
            {
                "provider": r.get("provider"),
                "status": r.get("status"),
                "message": r.get("message"),
                "checked_at": r.get("checked_at"),
                "result_count": r.get("result_count"),
            }
            for r in provider_runs
        ],
        "manual_links": investigation.get("manual_links") or [],
        "matches": matches,
        "verified_matches": exact,
        "visual_similarities": visual,
        "unverified_results": unverified,
        "first_known_appearance": first,
        "duplicates": [
            {
                "source_url": m.get("source_url"),
                "provider": m.get("provider"),
                "evidence_level": m.get("evidence_level"),
                "similarity_pct": m.get("similarity"),
                "phash_distance": m.get("phash_distance"),
            }
            for m in verified
        ],
        "modification_signals": {
            "forensic_score": forensics.get("score"),
            "signals": forensics.get("signals", []),
            "disclaimer": forensics.get("disclaimer"),
            "comparison": comparison,
        },
        "limitations": limitations,
        "conclusions": conclusions,
        "evidence_legend": {
            "verified_exact": "SHA-256 idéntico verificado localmente.",
            "verified_visual": f"pHash con distancia ≤ {VISUAL_DISTANCE}/256; similitud calculada, requiere verificación manual de la fuente.",
            "unverified": "Candidato sin verificación de imagen o por debajo del umbral. No es una coincidencia.",
        },
        "policy": {
            "face_recognition": False,
            "person_profiling": False,
            "external_paid_apis": False,
            "fabricated_results": False,
            "note": _s(lang, "policy"),
        },
    }


def _pdf_styles() -> dict[str, ParagraphStyle]:
    base = getSampleStyleSheet()
    return {
        "title": ParagraphStyle(
            "ITTitle", parent=base["Title"], fontSize=19, leading=23, textColor=colors.HexColor("#0f2b3d"), spaceAfter=4
        ),
        "sub": ParagraphStyle("ITSub", parent=base["Normal"], fontSize=9, textColor=colors.HexColor("#4b6577"), spaceAfter=12),
        "h2": ParagraphStyle(
            "ITH2", parent=base["Heading2"], fontSize=12, leading=15, textColor=colors.HexColor("#0b6b73"), spaceBefore=10, spaceAfter=5
        ),
        "body": ParagraphStyle("ITBody", parent=base["Normal"], fontSize=8.6, leading=11.5, alignment=TA_LEFT),
        "small": ParagraphStyle("ITSmall", parent=base["Normal"], fontSize=7.2, leading=9, textColor=colors.HexColor("#425866")),
    }


def _p(text: str, style: ParagraphStyle) -> Paragraph:
    return Paragraph(html.escape(str(text if text is not None else "")).replace("\n", "<br/>"), style)


def _table(rows: list[list[Any]], styles: dict[str, ParagraphStyle], widths: list[float]) -> Table:
    header_style = ParagraphStyle(
        "ITHeader", parent=styles["small"], textColor=colors.white, fontName="Helvetica-Bold"
    )
    data: list[list[Any]] = []
    for index, row in enumerate(rows):
        style = header_style if index == 0 else styles["small"]
        data.append([cell if hasattr(cell, "wrap") else _p(str(cell), style) for cell in row])
    table = Table(data, colWidths=widths, repeatRows=1, hAlign="LEFT")
    table.setStyle(
        TableStyle(
            [
                ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#0f2b3d")),
                ("TEXTCOLOR", (0, 0), (-1, 0), colors.white),
                ("FONTNAME", (0, 0), (-1, 0), "Helvetica-Bold"),
                ("FONTSIZE", (0, 0), (-1, 0), 7.5),
                ("VALIGN", (0, 0), (-1, -1), "TOP"),
                ("GRID", (0, 0), (-1, -1), 0.35, colors.HexColor("#c8d6de")),
                ("ROWBACKGROUNDS", (0, 1), (-1, -1), [colors.white, colors.HexColor("#f3f7f9")]),
                ("LEFTPADDING", (0, 0), (-1, -1), 4),
                ("RIGHTPADDING", (0, 0), (-1, -1), 4),
                ("TOPPADDING", (0, 0), (-1, -1), 3),
                ("BOTTOMPADDING", (0, 0), (-1, -1), 3),
            ]
        )
    )
    return table


def render_pdf(report: dict[str, Any]) -> bytes:
    lang = report.get("language", "es")
    styles = _pdf_styles()
    buffer = BytesIO()
    doc = SimpleDocTemplate(
        buffer,
        pagesize=A4,
        leftMargin=16 * mm,
        rightMargin=16 * mm,
        topMargin=16 * mm,
        bottomMargin=16 * mm,
        title=report.get("report_type", "ImageTrace OSINT"),
        author="ImageTrace OSINT",
    )
    s = lambda key: _s(lang, key)  # noqa: E731
    story: list[Any] = []
    story.append(_p(s("title"), styles["title"]))
    story.append(_p(s("subtitle"), styles["sub"]))
    story.append(
        _table(
            [
                ["ID", report.get("investigation_id")],
                [s("generated"), report.get("generated_at")],
                ["SHA-256", report.get("image", {}).get("sha256")],
            ],
            styles,
            [40 * mm, 138 * mm],
        )
    )
    story.append(_p(s("policy"), styles["small"]))
    story.append(Spacer(1, 5))

    img = report.get("image", {})
    story.append(_p(s("image"), styles["h2"]))
    story.append(
        _table(
            [
                ["Campo", "Valor verificado"],
                ["SHA-256", img.get("sha256")],
                ["pHash (256 bits)", img.get("phash")],
                ["Dimensiones", f"{img.get('width')} × {img.get('height')} px"],
                ["Tipo MIME / tamaño", f"{img.get('mime')} / {img.get('size_bytes')} bytes"],
                ["Origen de carga", f"{img.get('source_kind')} {img.get('source_url') or img.get('original_filename') or ''}"],
            ],
            styles,
            [45 * mm, 133 * mm],
        )
    )
    story.append(_p("2. Hechos, inferencias e información desconocida", styles["h2"]))
    meta = report.get("metadata", {})
    fact_lines = [f"{f.get('field')}: {f.get('value')} — {f.get('note') or ''}" for f in meta.get("facts", [])]
    story.append(_p(s("facts") + ": " + ("; ".join(fact_lines) if fact_lines else "Sin metadatos EXIF verificables."), styles["body"]))
    story.append(
        _p(s("unknowns") + ": " + "; ".join(meta.get("unknowns", [])) if meta.get("unknowns") else s("unknowns") + ": —", styles["body"])
    )
    if meta.get("gps"):
        story.append(_p("GPS: " + json.dumps(meta["gps"], ensure_ascii=False), styles["body"]))
    story.append(_p(meta.get("disclaimer", ""), styles["small"]))

    story.append(_p(s("metadata"), styles["h2"]))
    story.append(
        _p(
            f"EXIF disponible: {bool(meta.get('available'))} · ExifTool: {bool(meta.get('exiftool_available'))} · "
            f"OCR: {report.get('ocr', {}).get('status')} ({report.get('ocr', {}).get('engine') or 'sin motor'})",
            styles["body"],
        )
    )
    ocr_text = (report.get("ocr") or {}).get("text")
    if ocr_text:
        story.append(_p("Texto OCR (inferencia): " + ocr_text[:600], styles["body"]))

    story.append(_p(s("matches"), styles["h2"]))
    rows: list[list[Any]] = [["Nivel", "Fuente / dominio", "Fecha", "Similitud", "URL"]]
    for m in report.get("matches", [])[:60]:
        level = {
            "verified_exact": s("verified"),
            "verified_visual": s("visual"),
            "unverified": s("unverified"),
        }.get(m.get("evidence_level"), m.get("evidence_level"))
        rows.append(
            [
                level,
                f"{m.get('provider')} · {m.get('domain') or ''}",
                f"{m.get('published_at') or 'desconocida'}\n{(m.get('published_at_note') or '')[:90]}",
                f"{m.get('similarity') if m.get('similarity') is not None else '—'}%\nδ={m.get('phash_distance') if m.get('phash_distance') is not None else '—'}",
                (m.get("source_url") or "")[:110],
            ]
        )
    if len(rows) == 1:
        rows.append([s("none"), "—", "—", "—", "—"])
    story.append(_table(rows, styles, [26 * mm, 36 * mm, 40 * mm, 23 * mm, 53 * mm]))
    story.append(
        _p(
            "Métrica: similitud = 100 × (1 − distancia Hamming / 256) sobre pHash DCT 16×16. "
            "SHA-256 idéntico implica el mismo archivo; la similitud visual no equivale a autenticidad.",
            styles["small"],
        )
    )

    story.append(PageBreak())
    story.append(_p(s("sources"), styles["h2"]))
    source_rows: list[list[Any]] = [["Proveedor", "Estado", "Resultados", "Mensaje"]]
    for r in report.get("sources_consulted", []):
        source_rows.append([r.get("provider"), r.get("status"), r.get("result_count"), (r.get("message") or "")[:210]])
    story.append(_table(source_rows, styles, [34 * mm, 22 * mm, 18 * mm, 104 * mm]))

    story.append(_p(s("first"), styles["h2"]))
    story.append(_p(json.dumps(report.get("first_known_appearance"), ensure_ascii=False), styles["body"]))
    story.append(_p(s("duplicates"), styles["h2"]))
    story.append(
        _p(
            f"Coincidencias exactas verificadas: {len(report.get('verified_matches', []))} · "
            f"Similitudes visuales: {len(report.get('visual_similarities', []))} · "
            f"Resultados no verificados: {len(report.get('unverified_results', []))}",
            styles["body"],
        )
    )
    for d in report.get("duplicates", [])[:20]:
        story.append(_p(f"• {d.get('provider')} · {d.get('similarity_pct')}% · {(d.get('source_url') or '')[:120]}", styles["small"]))

    story.append(_p(s("signals"), styles["h2"]))
    signals = report.get("modification_signals", {})
    story.append(_p(f"Valor orientativo: {signals.get('forensic_score')}/100 (no concluyente).", styles["body"]))
    for sig in signals.get("signals", []):
        story.append(_p(f"• {sig.get('label')}: {sig.get('value')} [{sig.get('status')}]", styles["small"]))
    story.append(_p(signals.get("disclaimer") or "", styles["small"]))
    if signals.get("comparison"):
        comp = signals["comparison"]
        story.append(
            _p(
                f"Comparador: δ pHash {comp.get('phash', {}).get('distance')}/256, píxeles cambiados "
                f"{comp.get('pixels', {}).get('changed_pct')}%, recorte: {comp.get('crop_detection', {}).get('status')}.",
                styles["body"],
            )
        )

    story.append(_p(s("limitations"), styles["h2"]))
    for item in report.get("limitations", []):
        story.append(_p("• " + item, styles["small"]))
    story.append(_p(s("conclusions"), styles["h2"]))
    for i, item in enumerate(report.get("conclusions", []), 1):
        story.append(_p(f"{i}. {item}", styles["body"]))
    story.append(Spacer(1, 8))
    story.append(_p(s("policy"), styles["small"]))

    def footer(canvas, doc_):  # type: ignore[no-untyped-def]
        canvas.saveState()
        canvas.setFont("Helvetica", 7)
        canvas.setFillColor(colors.HexColor("#5b7180"))
        canvas.drawString(16 * mm, 9 * mm, "ImageTrace OSINT · informe privado · evidencia verificable")
        canvas.drawRightString(A4[0] - 16 * mm, 9 * mm, f"{s('page')} {doc_.page}")
        canvas.restoreState()

    doc.build(story, onFirstPage=footer, onLaterPages=footer)
    return buffer.getvalue()


def persist_report(
    db: Database,
    investigation_id: str,
    report: dict[str, Any],
    pdf_bytes: bytes,
    directory: Path,
) -> tuple[str, str]:
    directory.mkdir(parents=True, exist_ok=True)
    json_path = directory / "report.json"
    pdf_path = directory / "report.pdf"
    json_path.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    pdf_path.write_bytes(pdf_bytes)
    db.execute(
        "UPDATE investigations SET report_json = ?, report_pdf = ?, updated_at = ? WHERE id = ?",
        (
            json.dumps(report, ensure_ascii=False),
            str(pdf_path),
            datetime.now(timezone.utc).isoformat(timespec="seconds"),
            investigation_id,
        ),
    )
    return str(json_path), str(pdf_path)
