"""Validation, SSRF protection, rate limiting, private ownership and signed URLs.

Security posture:
* Uploads are decoded by Pillow and re-encoded into a clean derivative. The
  original bytes are stored outside any static directory and never executed.
* Outbound URLs are validated before every redirect hop (DNS resolution,
  private/loopback/reserved address rejection, scheme and port allowlist).
* Private investigations are accessible only with a random bearer owner token
  held by the browser. The token is never placed in a URL.
* Short-lived HMAC signatures are used for asset/report capability URLs.
"""

from __future__ import annotations

import hashlib
import hmac
import ipaddress
import re
import secrets
import socket
import threading
import time
from dataclasses import dataclass
from io import BytesIO
from pathlib import Path
from urllib.parse import urljoin, urlparse

import httpx
from fastapi import HTTPException, Request
from PIL import Image, UnidentifiedImageError

from .config import Settings

ALLOWED_FORMATS = {"JPEG": "image/jpeg", "PNG": "image/png", "WEBP": "image/webp"}
ALLOWED_EXTENSIONS = {".jpg", ".jpeg", ".png", ".webp"}
MAX_PIXELS = 40_000_000
MAX_REDIRECTS = 3


class ValidationError(ValueError):
    """Raised when an upload or external URL does not satisfy the policy."""


@dataclass
class SanitizedImage:
    image: Image.Image
    original_bytes: bytes
    display_bytes: bytes
    fmt: str
    mime: str
    width: int
    height: int


def _looks_like_polyglot(data: bytes) -> bool:
    head = data[:2048].lower()
    markers = (b"<svg", b"<script", b"<?php", b"<%", b"<!doctype html", b"#!/")
    return any(marker in head for marker in markers)


def sanitize_image(data: bytes, filename: str = "", max_bytes: int = 15 * 1024 * 1024) -> SanitizedImage:
    """Validate an upload by real decoding, then build a clean display copy."""
    if not data:
        raise ValidationError("El archivo está vacío.")
    if len(data) > max_bytes:
        raise ValidationError(f"El archivo supera el límite de {max_bytes // (1024 * 1024)} MB.")
    if _looks_like_polyglot(data):
        raise ValidationError("El archivo contiene marcadores de script/markup; no es una imagen válida.")

    ext = Path(filename or "").suffix.lower()
    if ext and ext not in ALLOWED_EXTENSIONS:
        raise ValidationError("Formato no permitido. Se aceptan JPG, PNG y WEBP.")

    Image.MAX_IMAGE_PIXELS = MAX_PIXELS
    try:
        with Image.open(BytesIO(data)) as probe:
            fmt = (probe.format or "").upper()
            if fmt not in ALLOWED_FORMATS:
                raise ValidationError(
                    f"Formato real no permitido ({fmt or 'desconocido'}). Se aceptan JPG, PNG y WEBP."
                )
            if probe.width * probe.height > MAX_PIXELS:
                raise ValidationError("La imagen supera el límite de píxeles permitido.")
            probe.verify()
        with Image.open(BytesIO(data)) as decoded:
            decoded.load()
            width, height = decoded.size
            has_alpha = "A" in decoded.getbands() or "transparency" in decoded.info
            rgb = decoded.convert("RGBA" if has_alpha else "RGB")
            # Cap the derivative size; the original stays private for forensics.
            derivative = rgb.copy()
            derivative.thumbnail((1600, 1600), Image.Resampling.LANCZOS)
            out = BytesIO()
            if has_alpha:
                derivative.save(out, format="PNG", optimize=True)
                mime = "image/png"
            else:
                derivative.save(out, format="JPEG", quality=88, optimize=True)
                mime = "image/jpeg"
            display_bytes = out.getvalue()
            clean = rgb.convert("RGB")
    except (UnidentifiedImageError, OSError, Image.DecompressionBombError) as exc:
        raise ValidationError(f"No se pudo decodificar la imagen: {exc}") from exc

    return SanitizedImage(
        image=clean,
        original_bytes=data,
        display_bytes=display_bytes,
        fmt=fmt,
        mime=ALLOWED_FORMATS[fmt],
        width=width,
        height=height,
    )


def _is_forbidden_ip(ip: ipaddress.IPv4Address | ipaddress.IPv6Address) -> bool:
    return bool(
        ip.is_private
        or ip.is_loopback
        or ip.is_link_local
        or ip.is_reserved
        or ip.is_multicast
        or ip.is_unspecified
        or (isinstance(ip, ipaddress.IPv6Address) and ip.ipv4_mapped is not None)
    )


def validate_public_url(url: str, allow_private: bool = False) -> str:
    """Reject non-public URLs before any network request is made."""
    if not url or len(url) > 2048:
        raise ValidationError("URL vacía o demasiado larga.")
    parsed = urlparse(url.strip())
    if parsed.scheme not in {"http", "https"}:
        raise ValidationError("Solo se permiten esquemas http y https.")
    if parsed.username or parsed.password:
        raise ValidationError("Las URLs con credenciales no están permitidas.")
    hostname = parsed.hostname
    if not hostname or len(hostname) > 253:
        raise ValidationError("La URL no contiene un host válido.")
    host = hostname.lower().rstrip(".")
    if host in {"localhost", "metadata.google.internal"} or host.endswith(
        (".local", ".internal", ".localhost")
    ):
        raise ValidationError("Los hosts locales o internos están bloqueados.")
    try:
        port = parsed.port or (443 if parsed.scheme == "https" else 80)
    except ValueError as exc:
        raise ValidationError("Puerto inválido.") from exc
    if port not in {80, 443}:
        raise ValidationError("Solo se permiten los puertos 80 y 443.")

    # Block IP literals and every DNS answer, including IPv4-mapped IPv6.
    try:
        literal = ipaddress.ip_address(host.strip("[]"))
        if _is_forbidden_ip(literal):
            raise ValidationError("Las direcciones IP privadas están bloqueadas.")
    except ValueError:
        pass
    if not allow_private:
        try:
            answers = socket.getaddrinfo(host, port, proto=socket.IPPROTO_TCP)
        except socket.gaierror as exc:
            raise ValidationError(f"No se pudo resolver el host: {exc}") from exc
        if not answers:
            raise ValidationError("El host no tiene direcciones resolubles.")
        for answer in answers:
            addr = ipaddress.ip_address(answer[4][0].split("%")[0])
            if _is_forbidden_ip(addr):
                raise ValidationError("El host resuelve a una dirección privada o reservada (SSRF bloqueado).")
    return url.strip()


def fetch_public_image(
    url: str, settings: Settings, *, max_bytes: int | None = None
) -> tuple[bytes, str]:
    """Fetch an image with redirect revalidation and bounded streaming reads."""
    limit = max_bytes or settings.max_url_download_bytes
    current = validate_public_url(url, settings.allow_private_networks)
    headers = {"User-Agent": settings.user_agent, "Accept": "image/avif,image/webp,image/png,image/jpeg,*/*;q=0.8"}
    with httpx.Client(
        timeout=settings.provider_timeout_seconds,
        follow_redirects=False,
        headers=headers,
    ) as client:
        for _ in range(MAX_REDIRECTS + 1):
            with client.stream("GET", current) as response:
                if response.status_code in {301, 302, 303, 307, 308}:
                    location = response.headers.get("location")
                    if not location:
                        raise ValidationError("Redirección sin destino.")
                    current = validate_public_url(
                        urljoin(current, location), settings.allow_private_networks
                    )
                    continue
                if response.status_code != 200:
                    raise ValidationError(f"El servidor remoto respondió HTTP {response.status_code}.")
                content_type = response.headers.get("content-type", "").split(";")[0].strip().lower()
                if content_type and content_type not in set(ALLOWED_FORMATS.values()) | {
                    "application/octet-stream",
                    "binary/octet-stream",
                }:
                    raise ValidationError(f"El recurso remoto no es una imagen ({content_type}).")
                size_hint = response.headers.get("content-length")
                if size_hint and size_hint.isdigit() and int(size_hint) > limit:
                    raise ValidationError("La imagen remota supera el límite de descarga.")
                chunks: list[bytes] = []
                total = 0
                for chunk in response.iter_bytes(chunk_size=65536):
                    total += len(chunk)
                    if total > limit:
                        raise ValidationError("La imagen remota supera el límite de descarga.")
                    chunks.append(chunk)
                return b"".join(chunks), current
    raise ValidationError("Demasiadas redirecciones.")


def owner_hash(secret: bytes, token: str) -> str:
    return hmac.new(secret, token.encode("utf-8"), hashlib.sha256).hexdigest()


def require_owner(request: Request) -> tuple[str, str]:
    """Return (raw token, hashed owner id) or raise 401."""
    token = request.headers.get("X-Owner-Token", "").strip()
    if not token or len(token) < 16 or len(token) > 512:
        raise HTTPException(
            status_code=401,
            detail="Se requiere un token de propietario privado (X-Owner-Token).",
        )
    if not re.fullmatch(r"[A-Za-z0-9._\-]+", token):
        raise HTTPException(status_code=401, detail="Token de propietario con formato inválido.")
    settings: Settings = request.app.state.runtime.settings
    return token, owner_hash(settings.secret_key, token)


def verify_owner_hash(expected: str, actual: str) -> bool:
    return hmac.compare_digest(expected, actual)


def sign_resource(secret: bytes, resource: str, ttl: int) -> tuple[int, str]:
    expires = int(time.time()) + max(30, ttl)
    signature = hmac.new(
        secret, f"{resource}:{expires}".encode("utf-8"), hashlib.sha256
    ).hexdigest()
    return expires, signature


def verify_signature(secret: bytes, resource: str, expires: int, signature: str) -> bool:
    if not signature or expires < int(time.time()):
        return False
    expected = hmac.new(
        secret, f"{resource}:{expires}".encode("utf-8"), hashlib.sha256
    ).hexdigest()
    return hmac.compare_digest(expected, signature)


def new_owner_token() -> str:
    return secrets.token_urlsafe(32)


class RateLimiter:
    """Fixed-window per-IP limiter for expensive endpoints (in-process)."""

    def __init__(self, per_minute: int):
        self.per_minute = max(1, per_minute)
        self._hits: dict[str, tuple[int, int]] = {}
        self._lock = threading.Lock()

    def check(self, key: str) -> None:
        now = int(time.time())
        window = now // 60
        with self._lock:
            if len(self._hits) > 5000:
                self._hits = {k: v for k, v in self._hits.items() if v[0] >= window - 1}
            stored_window, count = self._hits.get(key, (window, 0))
            if stored_window != window:
                stored_window, count = window, 0
            if count >= self.per_minute:
                raise HTTPException(
                    status_code=429,
                    detail="Límite de solicitudes alcanzado. Intente nuevamente en un minuto.",
                    headers={"Retry-After": "60"},
                )
            self._hits[key] = (stored_window, count + 1)


def client_ip(request: Request) -> str:
    # X-Forwarded-For is only trusted when explicitly configured behind a proxy;
    # using the socket peer avoids trivially spoofable rate-limit bypasses.
    if request.client and request.client.host:
        return request.client.host
    return "unknown"
