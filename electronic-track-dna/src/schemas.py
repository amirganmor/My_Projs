from __future__ import annotations

from datetime import datetime, timezone

from pydantic import BaseModel, Field


class AudioFeatures(BaseModel):
    tempo_bpm: float
    energy_mean: float
    energy_std: float
    spectral_centroid_mean: float
    spectral_bandwidth_mean: float
    spectral_rolloff_mean: float
    mfcc_means: list[float] = Field(description="13 MFCC coefficients")
    chroma_means: list[float] = Field(description="12 pitch-class energies")
    zero_crossing_rate: float
    onset_rate: float = Field(description="Onsets per second")
    duration_seconds: float
    loudness_db: float


class Section(BaseModel):
    label: str = Field(description="intro / buildup / drop / breakdown / outro")
    start_sec: float
    end_sec: float
    energy_level: str = Field(description="low / medium / high")
    tempo_bpm: float | None = None


class TrackDNA(BaseModel):
    youtube_url: str
    youtube_id: str
    title: str
    artist: str | None = None
    features: AudioFeatures
    sections: list[Section]
    genre_tags: list[str] = Field(default_factory=list)
    mood_tags: list[str] = Field(default_factory=list)
    search_text: str = ""
    summary: str = ""
    analyzed_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))


class IngestRequest(BaseModel):
    urls: list[str]


class TextSearchRequest(BaseModel):
    query: str
    limit: int = 5


class SimilarSearchRequest(BaseModel):
    youtube_url: str
    limit: int = 5


class RefinedSearchRequest(BaseModel):
    youtube_url: str
    refinement: str
    limit: int = 5


class SearchResult(BaseModel):
    youtube_id: str
    title: str
    artist: str | None = None
    score: float
    genre_tags: list[str] = Field(default_factory=list)
    mood_tags: list[str] = Field(default_factory=list)
    summary: str = ""
    explanation: str = ""


class SearchResponse(BaseModel):
    results: list[SearchResult]
    query_description: str = ""
