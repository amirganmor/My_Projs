from __future__ import annotations

import re


def explain_text_matches(query: str, raw_results: list[dict]) -> str:
    """Structured explanation for free-text search hits."""
    query_tokens = _tokens(query)
    lines: list[str] = []

    for i, hit in enumerate(raw_results[:5], 1):
        payload = hit.get("payload", {})
        title = payload.get("title", "Unknown")
        score = hit.get("score", 0.0)
        genres = payload.get("genre_tags", [])
        moods = payload.get("mood_tags", [])
        features = payload.get("features", {})
        sections = payload.get("sections", [])
        search_text = payload.get("search_text", "")

        reasons: list[str] = []
        overlap = [t for t in query_tokens if t in _tokens(" ".join(genres + moods + [search_text]))]
        if overlap:
            reasons.append(f"matches terms: {', '.join(overlap[:6])}")

        bpm = features.get("tempo_bpm")
        if bpm and any(k in query_tokens for k in ("techno", "house", "trance", "bass")):
            reasons.append(f"{bpm:.0f} BPM aligns with the genre cue")

        if "intro" in query_tokens or "long" in query_tokens:
            intro = next((s for s in sections if s.get("label") == "intro"), None)
            if intro:
                dur = intro.get("end_sec", 0) - intro.get("start_sec", 0)
                reasons.append(f"intro lasts {dur:.0f}s")

        if "dark" in query_tokens and features.get("spectral_centroid_mean", 9999) < 2000:
            reasons.append("darker spectral profile")
        if "bass" in query_tokens or "strong" in query_tokens:
            if features.get("energy_mean", 0) > 0.04:
                reasons.append("solid low-end energy")
        if "minimal" in query_tokens and "minimal" in moods + genres:
            reasons.append("tagged minimal")
        if "hypnotic" in query_tokens and "hypnotic" in moods:
            reasons.append("hypnotic energy curve")

        if not reasons:
            reasons.append(f"semantic text similarity ({score:.3f})")

        lines.append(f"{i}. **{title}** — {'; '.join(reasons)}.")

    return "\n".join(lines) if lines else "No matches to explain."


def explain_similar_matches(
    query_dna: dict,
    raw_results: list[dict],
    refinement: str | None = None,
) -> str:
    """Feature-delta explanation for similar / refined searches."""
    qf = query_dna.get("features", {})
    q_bpm = qf.get("tempo_bpm", 0)
    q_energy = qf.get("energy_mean", 0)
    q_centroid = qf.get("spectral_centroid_mean", 0)
    q_title = query_dna.get("title", "query track")

    header = f"Compared to **{q_title}**"
    if refinement:
        header += f" (refinement: _{refinement}_)"
    header += ":"

    lines = [header]
    for i, hit in enumerate(raw_results[:5], 1):
        payload = hit.get("payload", {})
        title = payload.get("title", "Unknown")
        score = hit.get("score", 0.0)
        f = payload.get("features", {})

        bpm = f.get("tempo_bpm", 0)
        energy = f.get("energy_mean", 0)
        centroid = f.get("spectral_centroid_mean", 0)

        deltas: list[str] = []
        bpm_diff = abs(bpm - q_bpm)
        if bpm_diff <= 3:
            deltas.append(f"near-identical tempo ({bpm:.0f} BPM)")
        elif bpm_diff <= 8:
            deltas.append(f"close tempo ({bpm:.0f} vs {q_bpm:.0f} BPM)")
        else:
            deltas.append(f"tempo offset {bpm - q_bpm:+.0f} BPM")

        if abs(energy - q_energy) < 0.02:
            deltas.append("similar energy")
        elif energy > q_energy:
            deltas.append("higher energy")
        else:
            deltas.append("lower energy")

        if abs(centroid - q_centroid) < 400:
            deltas.append("similar brightness")
        elif centroid < q_centroid:
            deltas.append("darker tone")
        else:
            deltas.append("brighter tone")

        genres = ", ".join(payload.get("genre_tags", [])[:3])
        if genres:
            deltas.append(f"tags: {genres}")

        if refinement:
            ref_tokens = _tokens(refinement)
            blob = _tokens(
                " ".join(payload.get("genre_tags", []) + payload.get("mood_tags", [])
                         + [payload.get("search_text", "")])
            )
            hit_terms = [t for t in ref_tokens if t in blob]
            if hit_terms:
                deltas.append(f"refinement hits: {', '.join(hit_terms[:4])}")

        lines.append(f"{i}. **{title}** (score {score:.3f}) — {'; '.join(deltas)}.")

    return "\n".join(lines)


def _tokens(text: str) -> list[str]:
    return re.findall(r"[a-z0-9]+", text.lower())
