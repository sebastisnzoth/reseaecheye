"""Runtime configuration. All values come from environment variables.

No credentials are required to run the application. A local secret key is
generated once and stored with 0600 permissions for HMAC-signed URLs.
"""

from __future__ import annotations

import os
import secrets
from dataclasses import dataclass, field
from pathlib import Path


def _env_bool(name: str, default: bool) -> bool:
    raw = os.getenv(name)
    if raw is None:
        return default
    return raw.strip().lower() in {"1", "true", "yes", "on"}


def _env_int(name: str, default: int) -> int:
    try:
        return int(os.getenv(name, str(default)))
    except ValueError:
        return default


def _env_float(name: str, default: float) -> float:
    try:
        return float(os.getenv(name, str(default)))
    except ValueError:
        return default


def _resolve_path(raw: str) -> Path:
    return Path(raw).expanduser().resolve()


def _load_secret_key(data_dir: Path) -> bytes:
    env_value = os.getenv("IMAGETRACE_SECRET_KEY")
    if env_value:
        return env_value.encode("utf-8")
    data_dir.mkdir(parents=True, exist_ok=True)
    secret_file = data_dir / ".secret_key"
    if secret_file.exists():
        return secret_file.read_bytes().strip()
    value = secrets.token_hex(32).encode("ascii")
    secret_file.write_bytes(value)
    try:
        secret_file.chmod(0o600)
    except OSError:  # pragma: no cover - platform dependent
        pass
    return value


@dataclass(frozen=True)
class Settings:
    data_dir: Path
    database_path: Path
    secret_key: bytes
    frontend_dist: Path
    max_upload_mb: int = 15
    max_url_download_mb: int = 10
    retention_hours: int = 24
    rate_limit_per_minute: int = 30
    signed_url_ttl_seconds: int = 600
    provider_timeout_seconds: float = 6.0
    max_provider_results: int = 12
    external_providers_enabled: bool = True
    sync_processing: bool = False
    contact_email: str = ""
    cors_origins: list[str] = field(default_factory=list)
    allow_private_networks: bool = False
    tesseract_cmd: str = ""

    @classmethod
    def from_env(cls) -> "Settings":
        root = Path(__file__).resolve().parents[2]
        data_dir = _resolve_path(os.getenv("IMAGETRACE_DATA_DIR", str(root / "data")))
        db_raw = os.getenv("IMAGETRACE_DATABASE_URL", "")
        if db_raw.startswith("sqlite:///"):
            database_path = _resolve_path(db_raw[len("sqlite:///") :])
        elif db_raw.startswith("postgres"):
            # Fail loudly rather than silently ignoring a PostgreSQL URL: the
            # bundled runtime is SQLite-only. See docs/LIMITATIONS.md.
            raise RuntimeError(
                "PostgreSQL aún no está conectado: esta versión usa SQLite. "
                "Deje IMAGETRACE_DATABASE_URL vacío o sqlite:///... (ver docs/LIMITATIONS.md)."
            )
        else:
            database_path = data_dir / "imagetrace.db"
        origins = [
            o.strip()
            for o in os.getenv("IMAGETRACE_CORS_ORIGINS", "").split(",")
            if o.strip()
        ]
        return cls(
            data_dir=data_dir,
            database_path=database_path,
            secret_key=_load_secret_key(data_dir),
            frontend_dist=_resolve_path(
                os.getenv("IMAGETRACE_FRONTEND_DIST", str(root / "frontend" / "dist"))
            ),
            max_upload_mb=_env_int("IMAGETRACE_MAX_UPLOAD_MB", 15),
            max_url_download_mb=_env_int("IMAGETRACE_MAX_URL_DOWNLOAD_MB", 10),
            retention_hours=_env_int("IMAGETRACE_RETENTION_HOURS", 24),
            rate_limit_per_minute=_env_int("IMAGETRACE_RATE_LIMIT_PER_MINUTE", 30),
            signed_url_ttl_seconds=_env_int("IMAGETRACE_SIGNED_URL_TTL", 600),
            provider_timeout_seconds=_env_float("IMAGETRACE_PROVIDER_TIMEOUT", 6.0),
            max_provider_results=_env_int("IMAGETRACE_MAX_PROVIDER_RESULTS", 12),
            external_providers_enabled=_env_bool("IMAGETRACE_EXTERNAL_PROVIDERS", True),
            sync_processing=_env_bool("IMAGETRACE_SYNC_PROCESSING", False),
            contact_email=os.getenv("IMAGETRACE_CONTACT_EMAIL", ""),
            cors_origins=origins,
            allow_private_networks=_env_bool("IMAGETRACE_ALLOW_PRIVATE_NETWORKS", False),
            tesseract_cmd=os.getenv("IMAGETRACE_TESSERACT_CMD", ""),
        )

    @classmethod
    def for_tests(cls, tmp: Path) -> "Settings":
        return cls(
            data_dir=tmp / "data",
            database_path=tmp / "data" / "test.db",
            secret_key=b"test-secret-key-for-pytest-only",
            frontend_dist=tmp / "no-dist",
            rate_limit_per_minute=1000,
            external_providers_enabled=False,
            sync_processing=True,
            provider_timeout_seconds=0.5,
            max_provider_results=5,
        )

    @property
    def user_agent(self) -> str:
        contact = self.contact_email or "set IMAGETRACE_CONTACT_EMAIL in production"
        return f"ImageTrace-OSINT/1.0 (+https://github.com/sebastisnzoth/reseaecheye; {contact})"

    @property
    def max_upload_bytes(self) -> int:
        return self.max_upload_mb * 1024 * 1024

    @property
    def max_url_download_bytes(self) -> int:
        return self.max_url_download_mb * 1024 * 1024
