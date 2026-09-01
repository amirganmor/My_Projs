from __future__ import annotations

import glob as globmod
import logging
import re
import subprocess
from pathlib import Path

import yt_dlp

from src.config import RAW_AUDIO_DIR, WAV_DIR, SAMPLE_RATE, ensure_data_dirs

logger = logging.getLogger(__name__)

_YT_ID_RE = re.compile(
    r"(?:youtu\.be/|youtube\.com/(?:watch\?v=|embed/|shorts/))([a-zA-Z0-9_-]{11})"
)


def extract_youtube_id(url: str) -> str | None:
    m = _YT_ID_RE.search(url)
    return m.group(1) if m else None


def download_audio(youtube_url: str) -> dict:
    """Download audio from YouTube and convert to WAV.

    Returns dict with keys: youtube_id, title, artist, duration, raw_path, wav_path.
    """
    ensure_data_dirs()

    yt_id = extract_youtube_id(youtube_url)
    if not yt_id:
        raise ValueError(f"Cannot extract YouTube ID from: {youtube_url}")

    raw_path = RAW_AUDIO_DIR / f"{yt_id}.%(ext)s"

    ydl_opts = {
        "format": "bestaudio/best",
        "outtmpl": str(raw_path),
        "quiet": True,
        "no_warnings": True,
        "extract_flat": False,
        "noplaylist": True,  # ignore &list=... — only the single video
        # Reduce YouTube HTTP 403s on media download
        "extractor_args": {
            "youtube": {
                "player_client": ["android", "web"],
            }
        },
        "retries": 3,
        "fragment_retries": 3,
    }

    try:
        with yt_dlp.YoutubeDL(ydl_opts) as ydl:
            info = ydl.extract_info(youtube_url, download=True)
    except yt_dlp.utils.DownloadError as e:
        # Fallback client set for stubborn 403s
        logger.warning("Download failed (%s); retrying with ios/tv clients", e)
        ydl_opts["extractor_args"] = {
            "youtube": {"player_client": ["ios", "tv"]}
        }
        with yt_dlp.YoutubeDL(ydl_opts) as ydl:
            info = ydl.extract_info(youtube_url, download=True)

    candidates = globmod.glob(str(RAW_AUDIO_DIR / f"{yt_id}.*"))
    if not candidates:
        downloaded_ext = info.get("ext", "webm")
        actual_raw = RAW_AUDIO_DIR / f"{yt_id}.{downloaded_ext}"
    else:
        actual_raw = Path(candidates[0])

    wav_path = WAV_DIR / f"{yt_id}.wav"
    if not wav_path.exists():
        _convert_to_wav(actual_raw, wav_path)

    return {
        "youtube_id": yt_id,
        "youtube_url": youtube_url,
        "title": info.get("title", "Unknown"),
        "artist": info.get("uploader") or info.get("artist"),
        "duration": info.get("duration", 0),
        "raw_path": str(actual_raw),
        "wav_path": str(wav_path),
    }


def cleanup_audio_files(youtube_id: str) -> list[str]:
    """Delete raw + WAV intermediates after vectors are stored.

    Keeps Qdrant payloads and reports; removes copyrighted audio from disk.
    """
    removed: list[str] = []
    wav_path = WAV_DIR / f"{youtube_id}.wav"
    if wav_path.exists():
        wav_path.unlink()
        removed.append(str(wav_path))

    for path_str in globmod.glob(str(RAW_AUDIO_DIR / f"{youtube_id}.*")):
        path = Path(path_str)
        if path.is_file():
            path.unlink()
            removed.append(str(path))

    if removed:
        logger.info("Cleaned audio for %s: %s", youtube_id, removed)
    return removed


def _convert_to_wav(input_path: Path, output_path: Path) -> None:
    cmd = [
        "ffmpeg", "-y",
        "-i", str(input_path),
        "-ac", "1",
        "-ar", str(SAMPLE_RATE),
        "-sample_fmt", "s16",
        str(output_path),
    ]
    logger.info("Converting %s -> %s", input_path.name, output_path.name)
    result = subprocess.run(cmd, capture_output=True, text=True)
    if result.returncode != 0:
        raise RuntimeError(f"ffmpeg failed: {result.stderr[:500]}")
