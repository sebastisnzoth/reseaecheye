"""Provider registry: add new connectors by registering them here."""

from __future__ import annotations

import time
import uuid
from datetime import datetime, timezone

from .base import Candidate, Provider, ProviderOutcome, SearchContext
from .local import LocalIndexProvider
from .manual import ManualSearchProvider
from .met import MetMuseumProvider
from .nasa import NasaImageLibraryProvider
from .openverse import OpenverseProvider
from .wikimedia import WikimediaCommonsProvider

PROVIDERS: list[Provider] = [
    LocalIndexProvider(),
    OpenverseProvider(),
    WikimediaCommonsProvider(),
    NasaImageLibraryProvider(),
    MetMuseumProvider(),
    ManualSearchProvider(),
]


def provider_catalog() -> list[dict[str, str]]:
    return [
        {
            "name": p.name,
            "label": p.label,
            "kind": p.kind,
            "description": (p.__doc__ or "").strip().split("\n")[0],
        }
        for p in PROVIDERS
    ]


def run_providers(ctx: SearchContext) -> tuple[list[ProviderOutcome], list[Candidate], list[dict[str, str]]]:
    outcomes: list[ProviderOutcome] = []
    candidates: list[Candidate] = []
    manual_links: list[dict[str, str]] = []
    for provider in PROVIDERS:
        started = time.monotonic()
        try:
            outcome = provider.run(ctx)
        except Exception as exc:  # noqa: BLE001 - one failing provider must not abort the investigation
            outcome = ProviderOutcome(
                provider=provider.name,
                label=provider.label,
                kind=provider.kind,
                status="error",
                message=f"Fallo del proveedor {provider.name}: {type(exc).__name__}. No se reportan resultados de esta fuente.",
            )
        outcome.duration_ms = int((time.monotonic() - started) * 1000)
        outcomes.append(outcome)
        candidates.extend(outcome.candidates)
        manual_links.extend(outcome.manual_links)
        ctx.db.execute(
            "INSERT INTO provider_runs(id, investigation_id, provider, status, message, "
            "result_count, checked_at, duration_ms) VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
            (
                uuid.uuid4().hex,
                ctx.investigation_id,
                outcome.provider,
                outcome.status,
                outcome.message[:1000],
                outcome.result_count,
                datetime.now(timezone.utc).isoformat(timespec="seconds"),
                outcome.duration_ms,
            ),
        )
    return outcomes, candidates, manual_links
