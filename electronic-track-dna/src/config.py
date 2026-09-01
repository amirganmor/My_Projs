from __future__ import annotations

import os
from pathlib import Path


QDRANT_HOST: str = os.getenv("QDRANT_HOST", "localhost")
QDRANT_PORT: int = int(os.getenv("QDRANT_PORT", "6333"))
QDRANT_COLLECTION: str = "track_dna"

CLAP_MODEL: str = os.getenv("CLAP_MODEL", "laion/larger_clap_music_and_speech")
TEXT_EMBED_MODEL: str = os.getenv(
    "TEXT_EMBED_MODEL", "sentence-transformers/all-MiniLM-L6-v2"
)
AUDIO_VECTOR_SIZE: int = int(os.getenv("AUDIO_VECTOR_SIZE", "512"))
TEXT_VECTOR_SIZE: int = int(os.getenv("TEXT_VECTOR_SIZE", "384"))

DATA_DIR: Path = Path(os.getenv("DATA_DIR", "/opt/airflow/data"))
RAW_AUDIO_DIR: Path = DATA_DIR / "raw_audio"
WAV_DIR: Path = DATA_DIR / "wav"
FEATURES_DIR: Path = DATA_DIR / "features"
REPORTS_DIR: Path = DATA_DIR / "reports"

AIRFLOW_BASE_URL: str = os.getenv("AIRFLOW_BASE_URL", "http://airflow-webserver:8080")
AIRFLOW_USERNAME: str = os.getenv("AIRFLOW_USERNAME", "admin")
AIRFLOW_PASSWORD: str = os.getenv("AIRFLOW_PASSWORD", "admin")

SAMPLE_RATE: int = 22050


def ensure_data_dirs() -> None:
    for d in (RAW_AUDIO_DIR, WAV_DIR, FEATURES_DIR, REPORTS_DIR):
        d.mkdir(parents=True, exist_ok=True)
