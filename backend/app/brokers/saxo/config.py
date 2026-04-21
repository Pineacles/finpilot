"""Saxo environment configuration.

LIVE hosts are present for later, but `resolve()` refuses "live" in this
release. Flip the `_LIVE_ENABLED` flag when the LIVE rollout PR lands.
"""
from __future__ import annotations

from dataclasses import dataclass

_LIVE_ENABLED = False


@dataclass(frozen=True)
class SaxoEnvironment:
    name: str
    api_base: str
    authorize_url: str
    token_url: str


_SIM = SaxoEnvironment(
    name="sim",
    api_base="https://gateway.saxobank.com/sim/openapi",
    authorize_url="https://sim.logonvalidation.net/authorize",
    token_url="https://sim.logonvalidation.net/token",
)

_LIVE = SaxoEnvironment(
    name="live",
    api_base="https://gateway.saxobank.com/openapi",
    authorize_url="https://live.logonvalidation.net/authorize",
    token_url="https://live.logonvalidation.net/token",
)


def resolve(name: str | None) -> SaxoEnvironment:
    """Resolve an environment name. Defaults to SIM. Rejects LIVE until enabled."""
    key = (name or "sim").strip().lower()
    if key == "sim":
        return _SIM
    if key == "live":
        if not _LIVE_ENABLED:
            raise ValueError("Saxo LIVE is not enabled in this release.")
        return _LIVE
    raise ValueError(f"Unknown Saxo environment: {name!r}")


def available_environments() -> list[dict]:
    """Metadata for the Settings UI. LIVE is always listed but may be disabled."""
    return [
        {"value": "sim", "label": "SIM (Simulation)", "enabled": True},
        {"value": "live", "label": "LIVE", "enabled": _LIVE_ENABLED},
    ]
