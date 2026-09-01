"""Track DNA Ingestion DAG.

Downloads YouTube audio, extracts features, builds Track DNA records with
template text, embeds with CLAP (audio) + MiniLM (text), stores in Qdrant,
then deletes raw/WAV intermediates (vectors + reports remain).

Triggered via Airflow REST API with conf: {"youtube_urls": ["..."]}
"""

from __future__ import annotations

import logging
from datetime import datetime

from airflow.decorators import dag, task
from airflow.exceptions import AirflowSkipException
from airflow.models.param import Param

logger = logging.getLogger(__name__)

# Parallel YouTube downloads invite HTTP 403s; keep this small for big batches.
_DOWNLOAD_CONCURRENCY = 3


def _skip_on_error(stage: str, label: str, err: BaseException) -> None:
    """Turn a per-URL failure into a skip so sibling mapped tasks keep running."""
    msg = f"{stage} failed for {label}: {err}"
    logger.exception(msg)
    raise AirflowSkipException(msg) from err


@dag(
    dag_id="track_dna_dag",
    description="Ingest YouTube electronic tracks and build Track DNA",
    schedule=None,
    start_date=datetime(2024, 1, 1),
    catchup=False,
    max_active_runs=2,
    tags=["track-dna", "youtube", "audio-analysis"],
    params={
        "youtube_urls": Param(
            default=[],
            type="array",
            description="List of YouTube URLs to analyze",
        ),
    },
)
def track_dna_pipeline():

    @task()
    def validate_urls(**context) -> list[str]:
        """Validate URLs and filter out already-indexed tracks."""
        from src.downloader import extract_youtube_id
        from src.qdrant_store import check_exists

        conf = context["dag_run"].conf or {}
        urls = conf.get("youtube_urls") or context["params"]["youtube_urls"]
        valid = []

        for url in urls:
            yt_id = extract_youtube_id(url)
            if not yt_id:
                logger.warning("Invalid YouTube URL, skipping: %s", url)
                continue
            if check_exists(yt_id):
                logger.info("Track %s already indexed, skipping", yt_id)
                continue
            valid.append(url)

        logger.info("Valid URLs to process: %d / %d", len(valid), len(urls))
        if not valid:
            raise AirflowSkipException("No new URLs to process")
        return valid

    @task(max_active_tis_per_dagrun=_DOWNLOAD_CONCURRENCY, retries=1)
    def download_audio(youtube_url: str) -> dict:
        """Download audio from YouTube. Failures skip this URL only."""
        from src.downloader import download_audio as dl

        try:
            meta = dl(youtube_url)
        except Exception as e:
            _skip_on_error("download", youtube_url, e)

        logger.info("Downloaded: %s -> %s", meta["title"], meta["wav_path"])
        return meta

    @task()
    def extract_features(download_meta: dict) -> dict:
        """Extract audio features with librosa."""
        from src.audio_features import extract_features as ef
        from src.track_dna import save_features

        yt_id = download_meta.get("youtube_id", "?")
        try:
            features = ef(download_meta["wav_path"])
            save_features(yt_id, features)
        except Exception as e:
            _skip_on_error("extract_features", yt_id, e)

        return {
            "download_meta": download_meta,
            "features": features.model_dump(),
        }

    @task()
    def detect_sections(data: dict) -> dict:
        """Detect track sections using energy heuristics."""
        from src.section_detector import detect_sections as ds

        yt_id = data["download_meta"].get("youtube_id", "?")
        try:
            wav_path = data["download_meta"]["wav_path"]
            sections = ds(wav_path)
            data["sections"] = [s.model_dump() for s in sections]
        except Exception as e:
            _skip_on_error("detect_sections", yt_id, e)
        return data

    @task()
    def build_track_dna(data: dict) -> dict:
        """Assemble TrackDNA with template search_text / summary / tags."""
        from src.schemas import AudioFeatures, Section
        from src.track_dna import build_track_dna as btd

        yt_id = data["download_meta"].get("youtube_id", "?")
        try:
            features = AudioFeatures(**data["features"])
            sections = [Section(**s) for s in data["sections"]]
            dna = btd(data["download_meta"], features, sections)
            out = dna.model_dump(mode="json")
            out["_wav_path"] = data["download_meta"]["wav_path"]
        except Exception as e:
            _skip_on_error("build_track_dna", yt_id, e)
        return out

    @task()
    def embed_and_store(dna_dict: dict) -> dict:
        """CLAP audio + MiniLM text embeddings → Qdrant named vectors."""
        from src.embeddings import embed_audio, embed_text
        from src.qdrant_store import upsert_track

        yt_id = dna_dict.get("youtube_id", "?")
        try:
            wav_path = dna_dict.pop("_wav_path")
            audio_vector = embed_audio(wav_path)
            text_vector = embed_text(dna_dict["search_text"])

            upsert_track(
                youtube_id=dna_dict["youtube_id"],
                audio_vector=audio_vector,
                text_vector=text_vector,
                payload=dna_dict,
            )
        except Exception as e:
            _skip_on_error("embed_and_store", yt_id, e)

        logger.info("Stored %s in Qdrant (audio+text)", dna_dict["youtube_id"])
        return dna_dict

    @task()
    def save_reports(dna_dict: dict) -> str:
        """Save Track DNA as JSON and Markdown reports."""
        from src.schemas import TrackDNA
        from src.track_dna import save_track_dna

        yt_id = dna_dict.get("youtube_id", "?")
        try:
            dna = TrackDNA(**dna_dict)
            paths = save_track_dna(dna)
        except Exception as e:
            _skip_on_error("save_reports", yt_id, e)

        logger.info("Reports saved: %s", paths)
        return {"youtube_id": yt_id, "paths": paths}

    @task()
    def cleanup_audio(report_meta: dict) -> str:
        """Remove raw/WAV after successful index + report (keep vectors only)."""
        from src.downloader import cleanup_audio_files

        yt_id = report_meta.get("youtube_id", "?")
        try:
            cleanup_audio_files(yt_id)
        except Exception as e:
            _skip_on_error("cleanup_audio", yt_id, e)
        return yt_id

    valid_urls = validate_urls()
    downloads = download_audio.expand(youtube_url=valid_urls)
    features_data = extract_features.expand(download_meta=downloads)
    with_sections = detect_sections.expand(data=features_data)
    dna_records = build_track_dna.expand(data=with_sections)
    stored = embed_and_store.expand(dna_dict=dna_records)
    reports = save_reports.expand(dna_dict=stored)
    cleanup_audio.expand(report_meta=reports)


track_dna_pipeline()
