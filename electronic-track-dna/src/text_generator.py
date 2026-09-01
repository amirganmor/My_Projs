from __future__ import annotations

from src.schemas import AudioFeatures, Section, TrackDNA


def generate_mood_tags(features: AudioFeatures, sections: list[Section]) -> list[str]:
    """Heuristic mood tags from energy / spectral / structure profile."""
    tags: list[str] = []

    if features.spectral_centroid_mean < 1500:
        tags.extend(["dark", "atmospheric"])
    elif features.spectral_centroid_mean > 3000:
        tags.extend(["bright", "energetic"])
    else:
        tags.append("balanced")

    if features.energy_mean > 0.08:
        tags.append("driving")
    elif features.energy_mean < 0.03:
        tags.append("subtle")

    if features.energy_std < 0.03:
        tags.append("hypnotic")
    else:
        tags.append("dynamic")

    labels = {s.label for s in sections}
    if "intro" in labels:
        intro = next(s for s in sections if s.label == "intro")
        if (intro.end_sec - intro.start_sec) >= 45:
            tags.append("long-intro")
    if "drop" in labels:
        tags.append("peak-time")
    if "breakdown" in labels:
        tags.append("breakdowns")

    if features.onset_rate > 6:
        tags.append("percussive")
    elif features.onset_rate < 2:
        tags.append("minimal")

    return list(dict.fromkeys(tags))


def generate_search_text(dna: TrackDNA | dict) -> str:
    """Build keyword-rich searchable text from Track DNA fields."""
    if isinstance(dna, dict):
        title = dna.get("title", "Unknown")
        features = dna.get("features", {})
        sections = dna.get("sections", [])
        genre_tags = dna.get("genre_tags", [])
        mood_tags = dna.get("mood_tags", [])
    else:
        title = dna.title
        features = dna.features.model_dump()
        sections = [s.model_dump() for s in dna.sections]
        genre_tags = dna.genre_tags
        mood_tags = dna.mood_tags

    bpm = features.get("tempo_bpm", 0)
    energy = features.get("energy_mean", 0)
    centroid = features.get("spectral_centroid_mean", 0)
    duration = features.get("duration_seconds", 0)
    onset = features.get("onset_rate", 0)

    if centroid < 1500:
        tone = "dark, low spectral energy"
    elif centroid > 3000:
        tone = "bright, high spectral energy"
    else:
        tone = "mid-range spectral balance"

    if energy > 0.08:
        energy_desc = "high energy"
    elif energy < 0.03:
        energy_desc = "low energy"
    else:
        energy_desc = "moderate energy"

    if onset > 6:
        rhythm = "percussive, high onset density"
    elif onset < 2:
        rhythm = "sparse, minimal rhythm"
    else:
        rhythm = "steady rhythmic pulse"

    structure_parts = []
    for s in sections:
        dur = s.get("end_sec", 0) - s.get("start_sec", 0)
        structure_parts.append(f"{s.get('label', 'section')} ({s.get('energy_level', 'medium')}, {dur:.0f}s)")
    structure = ", ".join(structure_parts) if structure_parts else "unstructured"

    genres = ", ".join(genre_tags) if genre_tags else "electronic"
    moods = ", ".join(mood_tags) if mood_tags else "atmospheric"

    return (
        f"{title}: {genres} track at {bpm:.0f} BPM with {energy_desc} and {tone}. "
        f"Rhythm is {rhythm}. Duration {duration:.0f} seconds. "
        f"Structure: {structure}. Mood: {moods}. "
        f"Electronic dance music suitable for DJ sets."
    )


def generate_summary(dna: TrackDNA | dict) -> str:
    """Human-readable 3–4 sentence report from features and sections."""
    if isinstance(dna, dict):
        title = dna.get("title", "Unknown")
        artist = dna.get("artist") or "Unknown"
        features = dna.get("features", {})
        sections = dna.get("sections", [])
        genre_tags = dna.get("genre_tags", [])
        mood_tags = dna.get("mood_tags", [])
    else:
        title = dna.title
        artist = dna.artist or "Unknown"
        features = dna.features.model_dump()
        sections = [s.model_dump() for s in dna.sections]
        genre_tags = dna.genre_tags
        mood_tags = dna.mood_tags

    bpm = features.get("tempo_bpm", 0)
    duration = features.get("duration_seconds", 0)
    genres = ", ".join(genre_tags) or "electronic"
    moods = ", ".join(mood_tags) or "atmospheric"

    section_flow = " → ".join(s.get("label", "?") for s in sections) or "flat"

    intro_len = 0.0
    for s in sections:
        if s.get("label") == "intro":
            intro_len = s.get("end_sec", 0) - s.get("start_sec", 0)
            break

    intro_note = (
        f" It opens with a {intro_len:.0f}s intro,"
        if intro_len >= 20
        else ""
    )

    return (
        f"\"{title}\" by {artist} is a {bpm:.0f} BPM {genres} track "
        f"({duration:.0f}s) with a {moods} character.{intro_note} "
        f"Energy flow: {section_flow}. "
        f"Use it where {genres} and {moods} vibes fit the set."
    )


def enrich_track_dna(dna: TrackDNA) -> TrackDNA:
    """Fill mood tags, search_text, and summary from templates."""
    dna.mood_tags = generate_mood_tags(dna.features, dna.sections)
    # Keep genre tags from heuristics; refresh search/summary
    dna.search_text = generate_search_text(dna)
    dna.summary = generate_summary(dna)
    return dna
