"""
Optional DSP research module for Playlist Engine.

This module intentionally analyzes audio supplied locally by the developer/user.
It does NOT download Spotify audio. That keeps the experimental signal-processing
work separate from Spotify catalog usage.

Install:
    pip install -r requirements-audio.txt
"""

from __future__ import annotations

from pathlib import Path

import numpy as np


def _mean(values):
    values = np.asarray(values, dtype=float)
    return float(np.mean(values)) if values.size else 0.0


def analyze_audio(path):
    import librosa

    path = Path(path)

    y, sr = librosa.load(
        path,
        sr=22050,
        mono=True,
        duration=45,
    )

    if y.size == 0:
        raise ValueError("Empty audio file.")

    # Rhythm / time-domain
    tempo, _ = librosa.beat.beat_track(y=y, sr=sr)
    rms = librosa.feature.rms(y=y)
    zcr = librosa.feature.zero_crossing_rate(y)

    # Spectral shape / brightness
    centroid = librosa.feature.spectral_centroid(y=y, sr=sr)
    bandwidth = librosa.feature.spectral_bandwidth(y=y, sr=sr)
    rolloff = librosa.feature.spectral_rolloff(y=y, sr=sr)

    # Tonal content
    chroma = librosa.feature.chroma_stft(y=y, sr=sr)

    # Timbre
    mfcc = librosa.feature.mfcc(
        y=y,
        sr=sr,
        n_mfcc=13,
    )

    tempo_value = float(np.asarray(tempo).reshape(-1)[0])

    features = {
        "tempo_bpm": tempo_value,
        "rms_energy": _mean(rms),
        "zero_crossing_rate": _mean(zcr),
        "spectral_centroid_hz": _mean(centroid),
        "spectral_bandwidth_hz": _mean(bandwidth),
        "spectral_rolloff_hz": _mean(rolloff),
        "chroma": [
            float(value)
            for value in np.mean(chroma, axis=1)
        ],
        "mfcc": [
            float(value)
            for value in np.mean(mfcc, axis=1)
        ],
    }

    return features


def feature_vector(features):
    """
    Compact normalized-ish research vector.

    In the next project stage, compute a dataset-wide mean/std and standardize
    these dimensions before cosine/Euclidean similarity.
    """
    return np.asarray(
        [
            features["tempo_bpm"] / 200.0,
            features["rms_energy"],
            features["zero_crossing_rate"],
            features["spectral_centroid_hz"] / 8000.0,
            features["spectral_bandwidth_hz"] / 8000.0,
            features["spectral_rolloff_hz"] / 11025.0,
            *features["chroma"],
            *features["mfcc"],
        ],
        dtype=float,
    )


def cosine_similarity(a, b):
    a = np.asarray(a, dtype=float)
    b = np.asarray(b, dtype=float)

    denominator = np.linalg.norm(a) * np.linalg.norm(b)

    if denominator == 0:
        return 0.0

    return float(np.dot(a, b) / denominator)