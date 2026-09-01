from __future__ import annotations

import hashlib
import logging

from qdrant_client import QdrantClient, models

from src.config import (
    AUDIO_VECTOR_SIZE,
    QDRANT_COLLECTION,
    QDRANT_HOST,
    QDRANT_PORT,
    TEXT_VECTOR_SIZE,
)

logger = logging.getLogger(__name__)


def _client() -> QdrantClient:
    return QdrantClient(host=QDRANT_HOST, port=QDRANT_PORT)


def ensure_collection() -> None:
    """Create the track_dna collection with named audio + text vectors."""
    client = _client()
    collections = [c.name for c in client.get_collections().collections]
    if QDRANT_COLLECTION not in collections:
        client.create_collection(
            collection_name=QDRANT_COLLECTION,
            vectors_config={
                "audio": models.VectorParams(
                    size=AUDIO_VECTOR_SIZE,
                    distance=models.Distance.COSINE,
                ),
                "text": models.VectorParams(
                    size=TEXT_VECTOR_SIZE,
                    distance=models.Distance.COSINE,
                ),
            },
        )
        logger.info(
            "Created Qdrant collection '%s' (audio=%d, text=%d)",
            QDRANT_COLLECTION,
            AUDIO_VECTOR_SIZE,
            TEXT_VECTOR_SIZE,
        )
    else:
        logger.info("Qdrant collection '%s' already exists", QDRANT_COLLECTION)


def upsert_track(
    youtube_id: str,
    audio_vector: list[float],
    text_vector: list[float],
    payload: dict,
) -> None:
    """Insert or update a track with audio + text vectors."""
    client = _client()
    ensure_collection()

    point_id = _youtube_id_to_int(youtube_id)
    client.upsert(
        collection_name=QDRANT_COLLECTION,
        points=[
            models.PointStruct(
                id=point_id,
                vector={
                    "audio": audio_vector,
                    "text": text_vector,
                },
                payload={**payload, "youtube_id": youtube_id},
            )
        ],
    )
    logger.info("Upserted track %s (point_id=%d)", youtube_id, point_id)


def search_by_vector(
    vector: list[float],
    using: str = "text",
    limit: int = 5,
    score_threshold: float = 0.3,
) -> list[dict]:
    """Search named vector space (`audio` or `text`)."""
    client = _client()
    ensure_collection()

    results = client.query_points(
        collection_name=QDRANT_COLLECTION,
        query=vector,
        using=using,
        limit=limit,
        score_threshold=score_threshold,
    )

    return [
        {
            "id": hit.id,
            "score": hit.score,
            "payload": hit.payload,
        }
        for hit in results.points
    ]


def check_exists(youtube_id: str) -> bool:
    """Check if a track is already indexed."""
    client = _client()
    ensure_collection()

    point_id = _youtube_id_to_int(youtube_id)
    try:
        result = client.retrieve(
            collection_name=QDRANT_COLLECTION,
            ids=[point_id],
        )
        return len(result) > 0
    except Exception:
        return False


def get_all_tracks(limit: int = 100, offset: int = 0) -> list[dict]:
    """Retrieve all indexed tracks."""
    client = _client()
    ensure_collection()

    # Qdrant scroll offset is a cursor, not a skip count; ignore numeric skip
    # for simple listing (first page only when offset == 0).
    result = client.scroll(
        collection_name=QDRANT_COLLECTION,
        limit=limit,
        with_payload=True,
        with_vectors=False,
    )

    return [{"id": p.id, "payload": p.payload} for p in result[0]]


def get_track(youtube_id: str) -> dict | None:
    """Retrieve a single track by YouTube ID."""
    client = _client()
    point_id = _youtube_id_to_int(youtube_id)
    try:
        result = client.retrieve(
            collection_name=QDRANT_COLLECTION,
            ids=[point_id],
            with_payload=True,
        )
        if result:
            return {"id": result[0].id, "payload": result[0].payload}
    except Exception:
        pass
    return None


def _youtube_id_to_int(youtube_id: str) -> int:
    """Deterministic int ID from YouTube ID string (for Qdrant point ID)."""
    digest = hashlib.sha256(youtube_id.encode()).digest()[:8]
    return int.from_bytes(digest, "big") % (2**63)
