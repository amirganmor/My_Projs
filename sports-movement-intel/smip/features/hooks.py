"""Sport-specific per-frame, per-team metric hooks for the shared engine."""

from __future__ import annotations


def hooks_for(sport: str) -> list:
    if sport == "basketball":
        from smip.features.basketball import spacing_hook

        return [spacing_hook]
    return []
