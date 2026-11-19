"""Mandatory functional and security tests for ImageTrace OSINT."""

from __future__ import annotations

import dataclasses
import io
import json
from pathlib import Path

from fastapi.testclient import TestClient

from app.config import Settings
from app.main import create_app
from tests.conftest import (
    HEADERS,
    OTHER_HEADERS,
    analyze,
    exif_with_gps,
    jpeg_bytes,
    pattern_image,
    png_bytes,
)


# 1. Valid and invalid image uploads -------------------------------------------------
def test_valid_and_invalid_uploads(client: TestClient) -> None:
    valid = jpeg_bytes()
    investigation_id, investigation = analyze(client, valid)
    assert investigation["id"] == investigation_id
    assert investigation["status"] == "done"
    assert len(investigation["sha256"]) == 64

    # WEBP is accepted through real decoding, not by trusting the extension.
    webp = io.BytesIO()
    pattern_image((200, 150)).save(webp, "WEBP")
    response = client.post(
        "/api/investigations", headers=HEADERS,
        files={"file": ("ok.webp", webp.getvalue(), "image/webp")},
        data={"lang": "en", "allow_external": "false"},
    )
    assert response.status_code == 201, response.text

    invalid_cases = [
        ("fake.jpg", b"this is not an image", "image/jpeg"),
        ("script.jpg", b"<svg><script>alert(1)</script></svg>", "image/jpeg"),
        ("real.png.gif", png_bytes(), "image/png"),
        ("empty.jpg", b"", "image/jpeg"),
    ]
    for filename, data, mime in invalid_cases:
        response = client.post(
            "/api/investigations", headers=HEADERS,
            files={"file": (filename, data, mime)},
        )
        assert response.status_code == 400, (filename, response.text)


# 2. Exact duplicate detection -------------------------------------------------------
def test_exact_duplicate_detection(client: TestClient) -> None:
    data = jpeg_bytes()
    first_id, _ = analyze(client, data, "original.jpg")
    second_id, second = analyze(client, data, "copy.jpg")
    assert first_id != second_id
    exact = [m for m in second["matches"] if m["evidence_level"] == "verified_exact"]
    assert exact, "Exact SHA-256 duplicate must be found in the local index"
    assert any(m["sha256_match"] for m in exact)
    assert any(m["provider"] == "local_index" for m in exact)
    assert second["report"]["verified_matches"]
    assert second["report"]["duplicates"]


# 3. Cropped / resized similarity ----------------------------------------------------
def test_cropped_photo_similarity(client: TestClient) -> None:
    base = pattern_image((400, 300), seed=7)
    base_bytes = jpeg_bytes(base, quality=90)
    crop = base.crop((40, 30, 360, 270))
    crop_bytes = jpeg_bytes(crop, quality=75)
    analyze(client, base_bytes, "base.jpg")
    _, cropped = analyze(client, crop_bytes, "cropped.jpg")
    visual = [m for m in cropped["matches"] if m["evidence_level"] == "verified_visual"]
    assert visual, "Crop-aware ORB/RANSAC alignment must detect a cropped version"
    assert all(m["metric_explanation"] for m in visual)
    assert "alineaci" in " ".join(m["metric_explanation"].lower() for m in visual)

    # The explicit comparator also verifies the crop and produces a heat-map.
    response = client.post(
        f"/api/investigations/{cropped['id']}/compare", headers=HEADERS,
        files={"file": ("base.jpg", base_bytes, "image/jpeg")},
    )
    assert response.status_code == 200, response.text
    comparison = response.json()
    assert comparison["alignment"]["status"] == "aligned"
    assert comparison["crop_aware_similarity_pct"] is not None
    assert comparison["diff_url"]
    heatmap = client.get(comparison["diff_url"])
    assert heatmap.status_code == 200
    assert heatmap.headers["content-type"].startswith("image/png")
    assert heatmap.content[:8] == b"\x89PNG\r\n\x1a\n"


# 4. EXIF extraction and GPS authorisation -------------------------------------------
def test_exif_extraction_and_gps_authorization(client: TestClient) -> None:
    data = jpeg_bytes(pattern_image((320, 240)), exif=exif_with_gps())
    _, withheld = analyze(client, data, "exif-withheld.jpg", allow_gps="false")
    assert withheld["metadata"]["available"] is True
    assert withheld["metadata"]["gps_present"] is True
    assert withheld["metadata"]["gps"]["status"] == "withheld"
    facts = {f["field"]: f["value"] for f in withheld["metadata"]["facts"]}
    assert facts["capture_date"] == "2024-05-12T10:30:00"
    assert "ACME Model X" in facts["device"]
    assert facts["software"] == "ImageTrace Test"

    _, allowed = analyze(client, data, "exif-allowed.jpg", allow_gps="true")
    gps = allowed["metadata"]["gps"]
    assert gps["status"] == "fact"
    assert abs(gps["latitude"] - 27.583333) < 0.001
    assert abs(gps["longitude"] + 48.55) < 0.001


# 5. Images without metadata ---------------------------------------------------------
def test_image_without_metadata(client: TestClient) -> None:
    _, investigation = analyze(client, png_bytes(), "no-exif.png")
    metadata = investigation["metadata"]
    assert metadata["available"] is False
    assert metadata["gps_present"] is False
    assert any("cámara" in item or "camera" in item for item in metadata["unknowns"])
    assert not any(f["field"] in {"capture_date", "device"} for f in metadata["facts"])
    assert "no contiene EXIF" in " ".join(investigation["report"]["limitations"])


# 6. External provider failures ------------------------------------------------------
def test_external_provider_failures_are_reported(external_app) -> None:
    with TestClient(external_app) as client:
        _, investigation = analyze(client, jpeg_bytes(), "offline.jpg", allow_external="true")
    runs = {r["provider"]: r for r in investigation["provider_runs"]}
    for provider in ("openverse", "wikimedia_commons", "nasa_image_library", "met_museum"):
        assert runs[provider]["status"] == "unavailable", (provider, runs[provider])
    assert "No se inventan resultados" in runs["openverse"]["message"]
    assert investigation["status"] == "done"
    assert investigation["matches"] == []
    assert investigation["manual_links"]  # manual links are offered, never counted as matches
    assert any("no pudieron consultarse" in c for c in investigation["report"]["conclusions"])


def test_new_catalog_connectors_parse_without_fabricating(catalog_app) -> None:
    """NASA + Met: real-shaped API payloads, SSRF-blocked thumbnails => unverified."""
    with TestClient(catalog_app) as client:
        _, investigation = analyze(
            client, jpeg_bytes(), "catalogs.jpg", allow_external="true", keywords="earth,cat"
        )
    runs = {r["provider"]: r for r in investigation["provider_runs"]}
    assert runs["nasa_image_library"]["status"] == "ok"
    assert runs["met_museum"]["status"] == "ok"
    nasa = [m for m in investigation["matches"] if m["provider"] == "nasa_image_library"]
    met = [m for m in investigation["matches"] if m["provider"] == "met_museum"]
    assert nasa and met
    for match in nasa + met:
        assert match["evidence_level"] == "unverified"
        assert match["similarity"] is None and match["phash_distance"] is None
        assert "SIN VERIFICAR" in (match["notes"] or "")
        assert match["published_at_note"]
    assert nasa[0]["published_at"] == "2024-01-02T03:04:05Z"
    assert "date_created" in nasa[0]["published_at_note"]
    assert met[0]["published_at"] == "664–30 BCE"
    assert "obra" in met[0]["published_at_note"]
    assert all(m["provider"] != "manual_links" for m in investigation["matches"])
    assert investigation["report"]["unverified_results"]


def test_manual_links_cover_news_archives_forums(catalog_app) -> None:
    with TestClient(catalog_app) as client:
        _, investigation = analyze(client, jpeg_bytes(), "manual.jpg", allow_external="true")
    keys = {link["key"] for link in investigation["manual_links"]}
    assert len(investigation["manual_links"]) >= 16
    for expected in (
        "manual.gdelt", "manual.internet_archive", "manual.wayback",
        "manual.flickr_commons", "manual.europeana", "manual.forums",
        "manual.nasa", "manual.met", "manual.ddg_images",
    ):
        assert expected in keys
    assert all("note_key" in link for link in investigation["manual_links"])
    manual_run = next(r for r in investigation["provider_runs"] if r["provider"] == "manual_links")
    assert manual_run["result_count"] == 0
    assert manual_run["status"] == "ok"


def test_registry_isolates_provider_crash(app, monkeypatch) -> None:
    from app.providers.local import LocalIndexProvider

    def crash(self, ctx):  # noqa: ARG001
        raise RuntimeError("simulated provider crash")

    monkeypatch.setattr(LocalIndexProvider, "run", crash)
    with TestClient(app) as client:
        _, investigation = analyze(client, jpeg_bytes(), "crash.jpg")
    local_run = next(r for r in investigation["provider_runs"] if r["provider"] == "local_index")
    assert local_run["status"] == "error"
    assert investigation["status"] == "done"
    assert investigation["report"] is not None


# 7. PDF report generation -----------------------------------------------------------
def test_pdf_and_json_report(client: TestClient) -> None:
    investigation_id, investigation = analyze(client, jpeg_bytes(), "report.jpg")
    pdf = client.get(f"/api/investigations/{investigation_id}/report/pdf", headers=HEADERS)
    assert pdf.status_code == 200
    assert pdf.headers["content-type"].startswith("application/pdf")
    assert pdf.content.startswith(b"%PDF")
    assert len(pdf.content) > 3000

    exported = client.get(f"/api/investigations/{investigation_id}/report/json", headers=HEADERS)
    assert exported.status_code == 200
    report = json.loads(exported.content)
    for key in (
        "image", "metadata", "matches", "sources_consulted", "first_known_appearance",
        "duplicates", "modification_signals", "limitations", "conclusions", "evidence_legend",
    ):
        assert key in report
    assert report["policy"]["face_recognition"] is False
    assert report["policy"]["fabricated_results"] is False
    assert investigation["report"]["schema_version"] == "1.0"


# 8. Unauthorised access / signed URLs ------------------------------------------------
def test_unauthorized_access_and_signed_urls(client: TestClient) -> None:
    investigation_id, _ = analyze(client, jpeg_bytes(), "private.jpg")
    assert client.get(f"/api/investigations/{investigation_id}").status_code == 401
    assert client.get(f"/api/investigations/{investigation_id}/report/pdf").status_code == 401
    assert client.get(f"/api/investigations/{investigation_id}", headers=OTHER_HEADERS).status_code == 404
    assert client.delete(f"/api/investigations/{investigation_id}", headers=OTHER_HEADERS).status_code == 404

    link = client.post(
        f"/api/investigations/{investigation_id}/signed-link", headers=HEADERS, json={"format": "pdf"}
    )
    assert link.status_code == 200
    url = link.json()["url"]
    assert "X-Owner-Token" not in url and "pytest-owner-token" not in url
    assert client.get(url).status_code == 200  # signature works without a header
    assert client.get(url.replace("sig=", "sig=deadbeef")).status_code == 403
    assert client.get(url.split("?")[0] + "?exp=1&sig=invalid").status_code == 403
    assert client.get(f"/api/assets/{investigation_id}/display").status_code == 403


def test_signed_json_download_and_expiry(client: TestClient) -> None:
    investigation_id, _ = analyze(client, jpeg_bytes(), "signed.jpg")
    link = client.post(
        f"/api/investigations/{investigation_id}/signed-link", headers=HEADERS, json={"format": "json"}
    ).json()["url"]
    response = client.get(link)
    assert response.status_code == 200
    assert json.loads(response.content)["investigation_id"] == investigation_id
    assert client.get(link.replace("exp=", "exp=1&old=")).status_code == 403


# 9. Empty results -------------------------------------------------------------------
def test_empty_results_are_honest(client: TestClient) -> None:
    _, investigation = analyze(client, jpeg_bytes(pattern_image((220, 160), seed=42)), "empty.jpg")
    assert investigation["matches"] == []
    assert investigation["provider_runs"][0]["provider"] == "local_index"
    assert investigation["provider_runs"][0]["status"] == "empty"
    assert investigation["report"]["first_known_appearance"]["status"] == "unknown"
    assert any("No se verificó ninguna coincidencia exacta" in c for c in investigation["report"]["conclusions"])
    assert investigation["report"]["verified_matches"] == []
    assert investigation["report"]["unverified_results"] == []


# 10. File deletion and retention ----------------------------------------------------
def test_delete_files_and_user_data(app, client: TestClient) -> None:
    data_dir: Path = app.state.runtime.settings.data_dir
    investigation_id, _ = analyze(client, jpeg_bytes(), "delete-me.jpg")
    folder = data_dir / "investigations" / investigation_id
    assert folder.is_dir()
    assert (folder / "report.pdf").is_file()
    response = client.delete(f"/api/investigations/{investigation_id}", headers=HEADERS)
    assert response.status_code == 200
    assert not folder.exists()
    assert client.get(f"/api/investigations/{investigation_id}", headers=HEADERS).status_code == 404

    second_id, _ = analyze(client, jpeg_bytes(pattern_image((180, 140), seed=5)), "purge.jpg")
    purge = client.post("/api/privacy/purge", headers=HEADERS)
    assert purge.status_code == 200
    assert (data_dir / "investigations" / second_id).exists()  # not expired yet
    wipe = client.delete("/api/privacy/all", headers=HEADERS)
    assert wipe.status_code == 200
    assert wipe.json()["deleted_investigations"] >= 1
    assert not (data_dir / "investigations" / second_id).exists()


# Additional security checks ---------------------------------------------------------
def test_ssrf_protection(client: TestClient) -> None:
    blocked = [
        "http://127.0.0.1/admin.jpg",
        "http://localhost/private.jpg",
        "http://169.254.169.254/latest/meta-data/",
        "http://metadata.google.internal/computeMetadata/v1/",
        "file:///etc/passwd",
        "ftp://example.com/image.jpg",
        "http://example.com:8080/image.jpg",
        "http://user:pass@example.com/image.jpg",
    ]
    for url in blocked:
        response = client.post(
            "/api/investigations/url", headers=HEADERS,
            json={"image_url": url, "allow_external": False, "lang": "es"},
        )
        assert response.status_code == 400, (url, response.text)


def test_rate_limiting(settings: Settings) -> None:
    limited = create_app(dataclasses.replace(settings, rate_limit_per_minute=2))
    with TestClient(limited) as client:
        for _ in range(2):
            response = client.post(
                "/api/investigations", headers=HEADERS,
                files={"file": ("bad.jpg", b"not an image", "image/jpeg")},
            )
            assert response.status_code == 400
        throttled = client.post(
            "/api/investigations", headers=HEADERS,
            files={"file": ("bad.jpg", b"not an image", "image/jpeg")},
        )
        assert throttled.status_code == 429
        assert throttled.headers.get("Retry-After") == "60"


def test_versioned_migrations_and_capabilities(app, client: TestClient) -> None:
    versions = [row["version"] for row in app.state.runtime.db.fetchall("SELECT version FROM schema_migrations")]
    assert versions == ["001_init", "002_provider_runs", "003_comparisons"]
    config = client.get("/api/config").json()
    assert config["policy"]["face_recognition"] is False
    assert config["policy"]["paid_apis"] is False
    assert "No existe búsqueda inversa automática" in config["honesty_notice"]
    assert {p["name"] for p in config["providers"]} == {
        "local_index", "openverse", "wikimedia_commons",
        "nasa_image_library", "met_museum", "manual_links",
    }


def test_local_index_add_and_delete(client: TestClient) -> None:
    data = png_bytes()
    created = client.post(
        "/api/index", headers=HEADERS,
        files={"file": ("permitted.png", data, "image/png")},
        data={"label": "imagen permitida", "retention_hours": "24"},
    )
    assert created.status_code == 201
    entries = client.get("/api/index", headers=HEADERS).json()["items"]
    assert any(entry["label"] == "imagen permitida" for entry in entries)
    _, investigation = analyze(client, data, "permitted.png")
    assert any(m["provider"] == "local_index" and m["sha256_match"] for m in investigation["matches"])
    entry_id = next(e["id"] for e in entries if e["label"] == "imagen permitida")
    assert client.delete(f"/api/index/{entry_id}", headers=HEADERS).status_code == 200


def test_results_never_contain_fake_dates(client: TestClient) -> None:
    _, investigation = analyze(client, jpeg_bytes(), "dates.jpg")
    for match in investigation["matches"]:
        if match["published_at"] is None:
            assert match["published_at_note"]
    assert investigation["report"]["first_known_appearance"]["status"] in {"unknown", "source_timestamp"}
