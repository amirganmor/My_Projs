from __future__ import annotations

import logging
from functools import lru_cache

import librosa
import numpy as np
import torch
from sentence_transformers import SentenceTransformer
from transformers import ClapModel, ClapProcessor

from src.config import AUDIO_VECTOR_SIZE, CLAP_MODEL, TEXT_EMBED_MODEL

logger = logging.getLogger(__name__)

_DEVICE = "cuda" if torch.cuda.is_available() else "cpu"


@lru_cache(maxsize=1)
def _clap_model_and_processor() -> tuple[ClapModel, ClapProcessor]:
    logger.info("Loading CLAP model %s on %s", CLAP_MODEL, _DEVICE)
    processor = ClapProcessor.from_pretrained(CLAP_MODEL)
    model = ClapModel.from_pretrained(CLAP_MODEL).to(_DEVICE)
    model.eval()
    return model, processor


@lru_cache(maxsize=1)
def _text_model() -> SentenceTransformer:
    logger.info("Loading text embedder %s on %s", TEXT_EMBED_MODEL, _DEVICE)
    return SentenceTransformer(TEXT_EMBED_MODEL, device=_DEVICE)


def _extract_tensor(output) -> torch.Tensor:
    """Normalize model output (tensor or ModelOutput) to a torch.Tensor."""
    if isinstance(output, torch.Tensor):
        return output
    if hasattr(output, "pooler_output") and output.pooler_output is not None:
        return output.pooler_output
    if hasattr(output, "last_hidden_state") and output.last_hidden_state is not None:
        return output.last_hidden_state.mean(dim=1)
    if hasattr(output, "embeddings") and output.embeddings is not None:
        return output.embeddings
    # Some versions return a tuple (tensor, ...)
    if isinstance(output, (tuple, list)) and output and isinstance(output[0], torch.Tensor):
        return output[0]
    raise TypeError(f"Unsupported embedding output type: {type(output)}")


def _to_1d_vector(tensor: torch.Tensor) -> np.ndarray:
    """Squeeze embedding output to a flat float32 vector."""
    arr = tensor.detach().cpu().float().numpy()
    arr = np.asarray(arr).squeeze()
    if arr.ndim > 1:
        arr = arr.mean(axis=0)
    return arr.astype(np.float32).reshape(-1)


def embed_audio(wav_path: str) -> list[float]:
    """Embed a WAV file with CLAP into an AUDIO_VECTOR_SIZE-dim vector."""
    model, processor = _clap_model_and_processor()

    y, _ = librosa.load(wav_path, sr=48000, mono=True)

    max_samples = 48000 * 30
    if len(y) > max_samples:
        start = (len(y) - max_samples) // 2
        y = y[start:start + max_samples]

    inputs = processor(
        audio=y,
        sampling_rate=48000,
        return_tensors="pt",
    )
    inputs = {k: v.to(_DEVICE) for k, v in inputs.items()}

    with torch.no_grad():
        raw = model.get_audio_features(**inputs)

    vec = _to_1d_vector(_extract_tensor(raw))
    norm = float(np.linalg.norm(vec))
    if norm > 0:
        vec = vec / norm

    if len(vec) != AUDIO_VECTOR_SIZE:
        logger.warning(
            "CLAP returned dim %d, expected %d — update AUDIO_VECTOR_SIZE / Qdrant",
            len(vec),
            AUDIO_VECTOR_SIZE,
        )

    return vec.tolist()


def embed_text(text: str) -> list[float]:
    """Embed text with MiniLM into a TEXT_VECTOR_SIZE-dim vector."""
    model = _text_model()
    encoded = model.encode(text, normalize_embeddings=True)
    vec = _to_1d_vector(torch.as_tensor(np.asarray(encoded)))
    return vec.tolist()
