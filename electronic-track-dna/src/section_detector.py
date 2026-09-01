from __future__ import annotations

import librosa
import numpy as np

from src.config import SAMPLE_RATE
from src.schemas import Section

FRAME_DURATION_SEC = 4.0
SMOOTHING_WINDOW = 3


def detect_sections(wav_path: str) -> list[Section]:
    """Detect track sections using energy-envelope heuristics.

    Splits the track into segments based on RMS energy transitions,
    labels each as intro / buildup / drop / breakdown / outro.
    """
    y, sr = librosa.load(wav_path, sr=SAMPLE_RATE, mono=True)
    duration = librosa.get_duration(y=y, sr=sr)

    frame_samples = int(FRAME_DURATION_SEC * sr)
    n_frames = max(1, -(-len(y) // frame_samples))

    energies = np.array([
        float(np.sqrt(np.mean(y[i * frame_samples:(i + 1) * frame_samples] ** 2)))
        for i in range(n_frames)
    ])

    if len(energies) >= SMOOTHING_WINDOW:
        kernel = np.ones(SMOOTHING_WINDOW) / SMOOTHING_WINDOW
        energies = np.convolve(energies, kernel, mode="same")

    if len(energies) == 0:
        return [Section(
            label="unknown", start_sec=0, end_sec=duration,
            energy_level="medium", tempo_bpm=None,
        )]

    e_max = energies.max()
    if e_max < 1e-10:
        return [Section(
            label="silence", start_sec=0, end_sec=duration,
            energy_level="low", tempo_bpm=None,
        )]

    normed = energies / e_max

    boundaries = [0]
    derivative = np.diff(normed)
    threshold = 0.15

    for i in range(1, len(derivative)):
        if abs(derivative[i]) > threshold and (i - boundaries[-1]) >= 2:
            boundaries.append(i)
    boundaries.append(n_frames)

    sections: list[Section] = []
    for idx in range(len(boundaries) - 1):
        start_frame = boundaries[idx]
        end_frame = boundaries[idx + 1]

        seg_energy = float(np.mean(normed[start_frame:end_frame]))
        start_sec = start_frame * FRAME_DURATION_SEC
        end_sec = min(end_frame * FRAME_DURATION_SEC, duration)

        if seg_energy < 0.3:
            energy_level = "low"
        elif seg_energy < 0.65:
            energy_level = "medium"
        else:
            energy_level = "high"

        label = _classify_section(idx, len(boundaries) - 1, seg_energy, normed, start_frame, end_frame)

        sections.append(Section(
            label=label,
            start_sec=round(start_sec, 1),
            end_sec=round(end_sec, 1),
            energy_level=energy_level,
            tempo_bpm=None,
        ))

    return sections if sections else [Section(
        label="unknown", start_sec=0, end_sec=duration,
        energy_level="medium", tempo_bpm=None,
    )]


def _classify_section(
    idx: int,
    total_sections: int,
    seg_energy: float,
    normed: np.ndarray,
    start_frame: int,
    end_frame: int,
) -> str:
    position_ratio = idx / max(total_sections - 1, 1)

    if position_ratio < 0.15 and seg_energy < 0.4:
        return "intro"

    if position_ratio > 0.85 and seg_energy < 0.4:
        return "outro"

    if seg_energy >= 0.65:
        return "drop"

    segment = normed[start_frame:end_frame]
    if len(segment) >= 2:
        trend = segment[-1] - segment[0]
        if trend > 0.1:
            return "buildup"

    if seg_energy < 0.4 and 0.2 < position_ratio < 0.8:
        return "breakdown"

    return "buildup" if seg_energy >= 0.4 else "breakdown"
