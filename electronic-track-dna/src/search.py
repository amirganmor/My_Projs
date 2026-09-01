from __future__ import annotations

import logging

import numpy as np

from src import embeddings, explain, qdrant_store
from src.audio_features import extract_features
from src.downloader import download_audio
from src.schemas import SearchResponse, SearchResult, TrackDNA
from src.section_detector import detect_sections
from src.track_dna import build_track_dna

logger = logging.getLogger(__name__)


def search_by_text(query: str, limit: int = 5) -> tuple[SearchResponse, str]:
    """Free-text semantic search across indexed tracks (text vector)."""
    vector = embeddings.embed_text(query)
    raw_results = qdrant_store.search_by_vector(vector, using="text", limit=limit)

    results = _format_results(raw_results)
    explanation = ""
    if results:
        explanation = explain.explain_text_matches(query, raw_results)

    return SearchResponse(
        results=results,
        query_description=f"Text search: {query}",
    ), explanation


def search_similar_to_url(youtube_url: str, limit: int = 5) -> tuple[SearchResponse, str]:
    """Analyze a YouTube URL and find similar indexed tracks (audio vector)."""
    dna, audio_vector = _analyze_url(youtube_url)

    raw_results = qdrant_store.search_by_vector(
        audio_vector, using="audio", limit=limit,
    )

    results = _format_results(raw_results)
    explanation = ""
    if results:
        explanation = explain.explain_similar_matches(dna.model_dump(), raw_results)

    return SearchResponse(
        results=results,
        query_description=f"Similar to: {dna.title} ({youtube_url})",
    ), explanation


def search_similar_refined(
    youtube_url: str, refinement: str, limit: int = 5,
) -> tuple[SearchResponse, str]:
    """Similar-to-URL via audio, re-ranked by text similarity to refinement."""
    dna, audio_vector = _analyze_url(youtube_url)

    # Fetch a wider audio candidate pool, then re-rank with text
    pool_size = max(limit * 3, 15)
    audio_hits = qdrant_store.search_by_vector(
        audio_vector, using="audio", limit=pool_size, score_threshold=0.2,
    )

    refine_vec = np.array(embeddings.embed_text(refinement), dtype=np.float32)
    scored: list[tuple[float, dict]] = []

    for rank_i, hit in enumerate(audio_hits):
        payload = hit.get("payload", {})
        search_text = payload.get("search_text") or payload.get("title", "")
        text_vec = np.array(embeddings.embed_text(search_text), dtype=np.float32)
        text_sim = float(np.dot(refine_vec, text_vec))

        # Convert audio rank to a descending score in [0, 1]
        audio_rank_score = 1.0 - (rank_i / max(len(audio_hits), 1))
        audio_sim = float(hit.get("score", 0.0))
        combined = 0.7 * audio_sim + 0.3 * text_sim
        # Slight boost for better audio rank stability
        combined = 0.9 * combined + 0.1 * audio_rank_score

        scored.append((combined, {**hit, "score": combined}))

    scored.sort(key=lambda x: x[0], reverse=True)
    raw_results = [h for _, h in scored[:limit]]

    results = _format_results(raw_results)
    explanation = ""
    if results:
        explanation = explain.explain_similar_matches(
            dna.model_dump(), raw_results, refinement=refinement,
        )

    return SearchResponse(
        results=results,
        query_description=f"Similar to: {dna.title}, refined: {refinement}",
    ), explanation


def _analyze_url(youtube_url: str) -> tuple[TrackDNA, list[float]]:
    """Download, analyze, and CLAP-embed a YouTube URL; then drop audio files."""
    from src.downloader import cleanup_audio_files

    meta = download_audio(youtube_url)
    yt_id = meta["youtube_id"]
    try:
        features = extract_features(meta["wav_path"])
        sections = detect_sections(meta["wav_path"])
        dna = build_track_dna(meta, features, sections)
        audio_vector = embeddings.embed_audio(meta["wav_path"])
        return dna, audio_vector
    finally:
        cleanup_audio_files(yt_id)


def _format_results(raw_results: list[dict]) -> list[SearchResult]:
    results = []
    for hit in raw_results:
        payload = hit.get("payload", {})
        results.append(SearchResult(
            youtube_id=payload.get("youtube_id", ""),
            title=payload.get("title", "Unknown"),
            artist=payload.get("artist"),
            score=hit.get("score", 0.0),
            genre_tags=payload.get("genre_tags", []),
            mood_tags=payload.get("mood_tags", []),
            summary=payload.get("summary", ""),
        ))
    return results
