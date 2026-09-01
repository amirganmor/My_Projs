from __future__ import annotations

import logging
from datetime import datetime, timezone

from src.config import FEATURES_DIR, REPORTS_DIR, ensure_data_dirs
from src.schemas import AudioFeatures, Section, TrackDNA

logger = logging.getLogger(__name__)

TEMPO_GENRE_MAP = [
    (90, 110, "downtempo"),
    (110, 125, "deep house"),
    (120, 130, "house"),
    (125, 135, "tech house"),
    (130, 145, "techno"),
    (140, 155, "trance"),
    (150, 180, "drum and bass"),
]


def build_track_dna(
    download_meta: dict,
    features: AudioFeatures,
    sections: list[Section],
) -> TrackDNA:
    """Assemble a TrackDNA record from components and template text."""
    from src.text_generator import enrich_track_dna

    genre_tags = _heuristic_genre_tags(features)

    dna = TrackDNA(
        youtube_url=download_meta["youtube_url"],
        youtube_id=download_meta["youtube_id"],
        title=download_meta["title"],
        artist=download_meta.get("artist"),
        features=features,
        sections=sections,
        genre_tags=genre_tags,
        mood_tags=[],
        search_text="",
        summary="",
        analyzed_at=datetime.now(timezone.utc),
    )
    return enrich_track_dna(dna)


def _heuristic_genre_tags(features: AudioFeatures) -> list[str]:
    tags: list[str] = []
    bpm = features.tempo_bpm

    for low, high, genre in TEMPO_GENRE_MAP:
        if low <= bpm < high:
            tags.append(genre)

    if features.spectral_centroid_mean < 1500:
        tags.append("dark")
    elif features.spectral_centroid_mean > 3000:
        tags.append("bright")

    if features.energy_std > 0.05:
        tags.append("dynamic")
    else:
        tags.append("hypnotic")

    if features.onset_rate > 6:
        tags.append("percussive")
    elif features.onset_rate < 2:
        tags.append("minimal")

    return list(dict.fromkeys(tags)) if tags else ["electronic"]


def save_track_dna(dna: TrackDNA) -> dict[str, str]:
    """Save TrackDNA as JSON and Markdown report. Returns file paths."""
    ensure_data_dirs()

    json_path = REPORTS_DIR / f"{dna.youtube_id}.json"
    md_path = REPORTS_DIR / f"{dna.youtube_id}.md"

    json_path.write_text(dna.model_dump_json(indent=2))
    md_path.write_text(_render_markdown(dna))

    logger.info("Saved reports: %s, %s", json_path, md_path)
    return {"json_path": str(json_path), "md_path": str(md_path)}


def save_features(youtube_id: str, features: AudioFeatures) -> str:
    ensure_data_dirs()
    path = FEATURES_DIR / f"{youtube_id}.json"
    path.write_text(features.model_dump_json(indent=2))
    return str(path)


def _render_markdown(dna: TrackDNA) -> str:
    lines = [
        f"# Track DNA: {dna.title}",
        "",
        f"**Artist:** {dna.artist or 'Unknown'}",
        f"**YouTube:** [{dna.youtube_id}]({dna.youtube_url})",
        f"**Analyzed:** {dna.analyzed_at.isoformat()}",
        "",
        "## Summary",
        "",
        dna.summary or "_Not yet generated._",
        "",
        "## Audio Features",
        "",
        f"| Feature | Value |",
        f"|---------|-------|",
        f"| Tempo | {dna.features.tempo_bpm:.1f} BPM |",
        f"| Duration | {dna.features.duration_seconds:.1f}s |",
        f"| Energy (mean) | {dna.features.energy_mean:.4f} |",
        f"| Spectral Centroid | {dna.features.spectral_centroid_mean:.1f} Hz |",
        f"| Spectral Bandwidth | {dna.features.spectral_bandwidth_mean:.1f} Hz |",
        f"| Onset Rate | {dna.features.onset_rate:.2f} /sec |",
        f"| Zero Crossing Rate | {dna.features.zero_crossing_rate:.4f} |",
        f"| Loudness | {dna.features.loudness_db:.1f} dB |",
        "",
        "## Sections",
        "",
        "| # | Label | Start | End | Energy |",
        "|---|-------|-------|-----|--------|",
    ]
    for i, s in enumerate(dna.sections, 1):
        lines.append(
            f"| {i} | {s.label} | {s.start_sec:.1f}s | {s.end_sec:.1f}s | {s.energy_level} |"
        )

    lines.extend([
        "",
        "## Tags",
        "",
        f"**Genre:** {', '.join(dna.genre_tags) or 'None'}",
        f"**Mood:** {', '.join(dna.mood_tags) or 'None'}",
        "",
        "## Search Text",
        "",
        dna.search_text or "_Not yet generated._",
    ])

    return "\n".join(lines) + "\n"
