from __future__ import annotations

import librosa
import numpy as np

from src.config import SAMPLE_RATE
from src.schemas import AudioFeatures


def extract_features(wav_path: str) -> AudioFeatures:
    """Extract audio features from a WAV file using librosa."""
    y, sr = librosa.load(wav_path, sr=SAMPLE_RATE, mono=True)
    duration = librosa.get_duration(y=y, sr=sr)

    tempo, _ = librosa.beat.beat_track(y=y, sr=sr)
    tempo_val = float(np.atleast_1d(tempo)[0])

    rms = librosa.feature.rms(y=y)[0]
    energy_mean = float(np.mean(rms))
    energy_std = float(np.std(rms))

    spectral_centroid = librosa.feature.spectral_centroid(y=y, sr=sr)[0]
    spectral_bandwidth = librosa.feature.spectral_bandwidth(y=y, sr=sr)[0]
    spectral_rolloff = librosa.feature.spectral_rolloff(y=y, sr=sr)[0]

    mfcc = librosa.feature.mfcc(y=y, sr=sr, n_mfcc=13)
    mfcc_means = [float(x) for x in np.mean(mfcc, axis=1)]

    chroma = librosa.feature.chroma_stft(y=y, sr=sr)
    chroma_means = [float(x) for x in np.mean(chroma, axis=1)]

    zcr = librosa.feature.zero_crossing_rate(y)[0]

    onset_env = librosa.onset.onset_strength(y=y, sr=sr)
    onsets = librosa.onset.onset_detect(y=y, sr=sr, onset_envelope=onset_env)
    onset_rate = float(len(onsets) / duration) if duration > 0 else 0.0

    loudness_approx = float(20 * np.log10(energy_mean + 1e-10))

    return AudioFeatures(
        tempo_bpm=tempo_val,
        energy_mean=energy_mean,
        energy_std=energy_std,
        spectral_centroid_mean=float(np.mean(spectral_centroid)),
        spectral_bandwidth_mean=float(np.mean(spectral_bandwidth)),
        spectral_rolloff_mean=float(np.mean(spectral_rolloff)),
        mfcc_means=mfcc_means,
        chroma_means=chroma_means,
        zero_crossing_rate=float(np.mean(zcr)),
        onset_rate=onset_rate,
        duration_seconds=float(duration),
        loudness_db=loudness_approx,
    )
