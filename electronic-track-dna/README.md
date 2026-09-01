# Electronic Track DNA Analyzer

Fully local system that ingests YouTube electronic music URLs, analyzes the actual audio, creates "Track DNA" records, and stores dual vectors in Qdrant for search.

**No Ollama / chat LLM.** Embeddings are local ML models; DNA text and match explanations are deterministic templates.

## Quick Start

```bash
# 1. Copy and customize environment
cp .env.example .env

# 2. Start all services (first build downloads torch + HF models on first use)
docker compose up -d --build

# 3. Unpause the DAG
docker compose exec airflow-webserver airflow dags unpause track_dna_dag

# 4. Open the UI
open http://localhost:8501
```

First ingest downloads CLAP + MiniLM into the shared `hf-cache` volume (~1–2 GB). Later runs reuse the cache.

If you previously ran the Ollama-based stack, recreate Qdrant so the named-vector schema applies:

```bash
docker compose down
docker volume rm electronic-track-dna_qdrant-data 2>/dev/null || true
docker compose up -d --build
```

## Services

| Service | URL | Purpose |
|---------|-----|---------|
| Streamlit UI | http://localhost:8501 | Search and ingest interface |
| FastAPI | http://localhost:8000/docs | REST API + Swagger docs |
| Airflow | http://localhost:8080 | DAG orchestration (admin/admin) |
| Qdrant | http://localhost:6333/dashboard | Vector DB dashboard |

## Features

- **Ingest**: Paste one or many YouTube URLs for analysis
- **Free-text search**: MiniLM over template `search_text` (e.g. "dark melodic techno with long intro")
- **Similar-to-YouTube**: CLAP audio embedding similarity
- **Refined similarity**: CLAP candidates re-ranked by MiniLM vs refinement text

## Architecture

```
YouTube URL → yt-dlp → ffmpeg (WAV) → librosa (features) → section detection
  → Track DNA (template text/tags)
  → CLAP audio vector + MiniLM text vector → Qdrant (named vectors)
```

Orchestrated by Apache Airflow. Search served by FastAPI. UI by Streamlit.

## Tech Stack

- Python 3.11, Docker Compose
- Apache Airflow (LocalExecutor)
- Qdrant (named vectors: `audio` 512-dim, `text` 384-dim)
- CLAP (`laion/larger_clap_music_and_speech`) for audio embeddings
- sentence-transformers (`all-MiniLM-L6-v2`) for text embeddings
- FastAPI, Streamlit
- yt-dlp, ffmpeg, librosa

## Docs

- [Detailed design / data flow](docs/design.md) — YouTube URL → WAV → Track DNA → Qdrant → search
- [YouTube video presentation plan](docs/youtube_video_presentation.md) — chapter script, timestamps, checklist
