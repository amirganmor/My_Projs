from __future__ import annotations

import logging

import httpx
from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware

from src.config import AIRFLOW_BASE_URL, AIRFLOW_USERNAME, AIRFLOW_PASSWORD
from src.qdrant_store import get_all_tracks, get_track
from src.schemas import (
    IngestRequest,
    RefinedSearchRequest,
    SearchResponse,
    SimilarSearchRequest,
    TextSearchRequest,
)
from src.search import search_by_text, search_similar_refined, search_similar_to_url

logger = logging.getLogger(__name__)

app = FastAPI(
    title="Electronic Track DNA Analyzer",
    description="Analyze electronic music and search by sonic characteristics",
    version="1.0.0",
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.get("/health")
async def health():
    return {"status": "healthy"}


@app.post("/ingest")
async def ingest_tracks(request: IngestRequest):
    """Trigger the Airflow DAG to ingest YouTube URLs."""
    if not request.urls:
        raise HTTPException(status_code=400, detail="No URLs provided")

    dag_run_payload = {
        "conf": {"youtube_urls": request.urls},
    }

    async with httpx.AsyncClient() as client:
        try:
            resp = await client.post(
                f"{AIRFLOW_BASE_URL}/api/v1/dags/track_dna_dag/dagRuns",
                json=dag_run_payload,
                auth=(AIRFLOW_USERNAME, AIRFLOW_PASSWORD),
                timeout=30.0,
            )
            resp.raise_for_status()
            data = resp.json()
            return {
                "status": "triggered",
                "dag_run_id": data.get("dag_run_id"),
                "urls_submitted": len(request.urls),
            }
        except httpx.HTTPStatusError as e:
            raise HTTPException(
                status_code=e.response.status_code,
                detail=f"Airflow API error: {e.response.text[:500]}",
            )
        except httpx.RequestError as e:
            raise HTTPException(
                status_code=503,
                detail=f"Cannot reach Airflow: {str(e)}",
            )


@app.get("/ingest/{dag_run_id}/status")
async def ingest_status(dag_run_id: str):
    """Check the status of a DAG run."""
    async with httpx.AsyncClient() as client:
        try:
            resp = await client.get(
                f"{AIRFLOW_BASE_URL}/api/v1/dags/track_dna_dag/dagRuns/{dag_run_id}",
                auth=(AIRFLOW_USERNAME, AIRFLOW_PASSWORD),
                timeout=10.0,
            )
            resp.raise_for_status()
            data = resp.json()
            return {
                "dag_run_id": dag_run_id,
                "state": data.get("state"),
                "start_date": data.get("start_date"),
                "end_date": data.get("end_date"),
            }
        except httpx.HTTPStatusError as e:
            raise HTTPException(
                status_code=e.response.status_code,
                detail=f"Airflow API error: {e.response.text[:500]}",
            )
        except httpx.RequestError as e:
            raise HTTPException(status_code=503, detail=str(e))


@app.post("/search/text")
async def search_text(request: TextSearchRequest):
    """Free-text semantic search."""
    try:
        response, explanation = search_by_text(request.query, limit=request.limit)
        for r in response.results:
            r.explanation = explanation
        return response
    except Exception as e:
        logger.exception("Search failed")
        raise HTTPException(status_code=500, detail=str(e))


@app.post("/search/similar")
async def search_similar(request: SimilarSearchRequest):
    """Find tracks similar to a YouTube URL."""
    try:
        response, explanation = search_similar_to_url(
            request.youtube_url, limit=request.limit,
        )
        for r in response.results:
            r.explanation = explanation
        return response
    except Exception as e:
        logger.exception("Similar search failed")
        raise HTTPException(status_code=500, detail=str(e))


@app.post("/search/similar-refined")
async def search_refined(request: RefinedSearchRequest):
    """Find tracks similar to a URL with natural language refinement."""
    try:
        response, explanation = search_similar_refined(
            request.youtube_url, request.refinement, limit=request.limit,
        )
        for r in response.results:
            r.explanation = explanation
        return response
    except Exception as e:
        logger.exception("Refined search failed")
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/tracks")
async def list_tracks(limit: int = 100, offset: int = 0):
    """List all indexed tracks."""
    try:
        tracks = get_all_tracks(limit=limit, offset=offset)
        return {
            "count": len(tracks),
            "tracks": [
                {
                    "youtube_id": t["payload"].get("youtube_id", ""),
                    "title": t["payload"].get("title", "Unknown"),
                    "artist": t["payload"].get("artist"),
                    "genre_tags": t["payload"].get("genre_tags", []),
                    "mood_tags": t["payload"].get("mood_tags", []),
                }
                for t in tracks
            ],
        }
    except Exception as e:
        logger.exception("Failed to list tracks")
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/tracks/{youtube_id}")
async def get_track_detail(youtube_id: str):
    """Get full TrackDNA for a specific track."""
    track = get_track(youtube_id)
    if not track:
        raise HTTPException(status_code=404, detail="Track not found")
    return track["payload"]
