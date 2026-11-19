"""Shared fixtures and image factories for ImageTrace OSINT tests."""

from __future__ import annotations

import io
from dataclasses import replace
from pathlib import Path

import numpy as np
import pytest
from fastapi.testclient import TestClient
from PIL import ExifTags, Image, ImageDraw, TiffImagePlugin

from app.config import Settings
from app.main import create_app

HEADERS = {"X-Owner-Token": "pytest-owner-token-0123456789abcdef"}
OTHER_HEADERS = {"X-Owner-Token": "another-owner-token-9876543210fedcba"}


def pattern_image(size=(400, 300), seed: int = 7) -> Image.Image:
    rng = np.random.default_rng(seed)
    image = Image.fromarray(rng.integers(0, 255, (size[1], size[0], 3), dtype=np.uint8))
    draw = ImageDraw.Draw(image)
    w, h = size
    draw.rectangle([w * 0.12, h * 0.12, w * 0.88, h * 0.88], outline=(255, 30, 30), width=12)
    draw.ellipse([w * 0.3, h * 0.25, w * 0.7, h * 0.75], fill=(20, 240, 220))
    draw.line([0, h * 0.5, w, h * 0.5], fill=(255, 255, 255), width=5)
    return image


def jpeg_bytes(image: Image.Image | None = None, quality: int = 90, exif: Image.Exif | None = None) -> bytes:
    image = image or pattern_image()
    buf = io.BytesIO()
    save_kwargs = {"quality": quality}
    if exif is not None:
        save_kwargs["exif"] = exif
    image.save(buf, "JPEG", **save_kwargs)
    return buf.getvalue()


def png_bytes(image: Image.Image | None = None) -> bytes:
    image = image or pattern_image((240, 180), seed=11)
    buf = io.BytesIO()
    image.save(buf, "PNG")
    return buf.getvalue()


def exif_with_gps() -> Image.Exif:
    exif = Image.Exif()
    exif[36867] = "2024:05:12 10:30:00"  # DateTimeOriginal
    exif[271] = "ACME"
    exif[272] = "Model X"
    exif[305] = "ImageTrace Test"
    gps = exif.get_ifd(ExifTags.IFD.GPSInfo)
    gps[1] = "N"
    gps[2] = (
        TiffImagePlugin.IFDRational(27, 1),
        TiffImagePlugin.IFDRational(35, 1),
        TiffImagePlugin.IFDRational(0, 1),
    )
    gps[3] = "W"
    gps[4] = (
        TiffImagePlugin.IFDRational(48, 1),
        TiffImagePlugin.IFDRational(33, 1),
        TiffImagePlugin.IFDRational(0, 1),
    )
    return exif


def analyze(client: TestClient, data: bytes, filename: str = "sample.jpg", **form) -> tuple[str, dict]:
    response = client.post(
        "/api/investigations",
        headers=HEADERS,
        files={"file": (filename, data, "image/jpeg" if filename.endswith((".jpg", ".jpeg")) else "image/png")},
        data={"keywords": "prueba,osint", "allow_external": "false", "lang": "es", **form},
    )
    assert response.status_code == 201, response.text
    investigation_id = response.json()["id"]
    detail = client.get(f"/api/investigations/{investigation_id}", headers=HEADERS)
    assert detail.status_code == 200, detail.text
    return investigation_id, detail.json()["investigation"]


@pytest.fixture
def settings(tmp_path: Path) -> Settings:
    return Settings.for_tests(tmp_path)


@pytest.fixture
def app(settings: Settings):
    return create_app(settings)


@pytest.fixture
def client(app) -> TestClient:
    with TestClient(app) as test_client:
        yield test_client


EXTERNAL_MODULES = (
    "app.providers.openverse",
    "app.providers.wikimedia",
    "app.providers.nasa",
    "app.providers.met",
)


@pytest.fixture
def external_app(settings: Settings, monkeypatch):
    """App with all external connectors enabled but their HTTP client offline."""
    import httpx
    import importlib

    class OfflineClient(httpx.Client):
        def get(self, *_args, **_kwargs):  # noqa: D102
            raise httpx.ConnectError("network blocked in tests")

    class OfflineHTTPX:
        Client = OfflineClient
        HTTPError = httpx.HTTPError
        ConnectError = httpx.ConnectError

    fake = OfflineHTTPX()
    for module_name in EXTERNAL_MODULES:
        monkeypatch.setattr(importlib.import_module(module_name), "httpx", fake)
    return create_app(replace(settings, external_providers_enabled=True))


NASA_PAYLOAD = {
    "collection": {
        "items": [
            {
                "href": "https://images-assets.nasa.gov/image/TEST1/collection.json",
                "data": [{
                    "nasa_id": "TEST1",
                    "date_created": "2024-01-02T03:04:05Z",
                    "title": "Test NASA image",
                    "center": "JPL",
                    "secondary_creator": "NASA/JPL",
                    "keywords": ["earth", "test"],
                    "description": "Synthetic payload for tests only.",
                }],
                "links": [
                    {"href": "http://127.0.0.1/nasa-thumb.jpg", "rel": "preview", "render": "image"},
                    {"href": "http://127.0.0.1/nasa-orig.jpg", "rel": "canonical", "render": "image"},
                ],
            }
        ]
    }
}

MET_OBJECT = {
    "objectID": 552027,
    "isPublicDomain": True,
    "primaryImageSmall": "http://127.0.0.1/met-thumb.jpg",
    "primaryImage": "http://127.0.0.1/met-orig.jpg",
    "objectURL": "https://www.metmuseum.org/art/collection/search/552027",
    "title": "Cat",
    "artistDisplayName": "",
    "creditLine": "Gift, 1904",
    "objectDate": "664–30 BCE",
}


@pytest.fixture
def catalog_app(settings: Settings, monkeypatch):
    """External connectors return canned real-shaped JSON; thumbnails are SSRF-blocked.

    This verifies parsing and honest 'unverified' classification without any
    network access and without ever producing a fabricated match.
    """
    import httpx
    import importlib

    class FakeResponse:
        def __init__(self, payload, status_code: int = 200):
            self.payload = payload
            self.status_code = status_code

        def json(self):
            return self.payload

    class FakeClient(httpx.Client):
        def get(self, url, *_args, **_kwargs):  # noqa: D102
            url = str(url)
            if "images-api.nasa.gov" in url:
                return FakeResponse(NASA_PAYLOAD)
            if "collectionapi.metmuseum.org" in url and "/v1.1/search" in url:
                return FakeResponse({"total": 1, "objectIDs": [552027]})
            if "collectionapi.metmuseum.org" in url and "/objects/" in url:
                return FakeResponse(MET_OBJECT)
            if "api.openverse.org" in url:
                return FakeResponse({"result_count": 0, "results": []})
            if "commons.wikimedia.org" in url:
                return FakeResponse({"query": {"pages": []}})
            return FakeResponse({"results": []})

    class FakeHTTPX:
        Client = FakeClient
        HTTPError = httpx.HTTPError
        ConnectError = httpx.ConnectError

    fake = FakeHTTPX()
    for module_name in EXTERNAL_MODULES:
        monkeypatch.setattr(importlib.import_module(module_name), "httpx", fake)
    return create_app(replace(settings, external_providers_enabled=True))
