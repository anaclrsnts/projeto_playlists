from __future__ import annotations

import math
from urllib.parse import urlparse

import requests

BASE_URL = "https://api.reccobeats.com/v1"
TIMEOUT = 20

FEATURE_NAMES = (
    "tempo",
    "energy",
    "valence",
    "danceability",
    "acousticness",
    "instrumentalness",
)


class ReccoError(RuntimeError):
    pass


def _get(path, params=None):
    response = requests.get(
        BASE_URL + path,
        params=params,
        headers={
            "Accept": "application/json",
            "User-Agent": (
                "PlaylistEngine/2.0 "
                "(https://github.com/anaclrsnts/playlists)"
            ),
        },
        timeout=TIMEOUT,
    )

    if not response.ok:
        try:
            payload = response.json()
            message = payload.get("error") or payload.get("message")
        except Exception:
            message = None

        raise ReccoError(
            message or f"ReccoBeats error ({response.status_code})"
        )

    try:
        return response.json()
    except ValueError as exc:
        raise ReccoError("Invalid response from ReccoBeats.") from exc


def _content(payload):
    """
    ReccoBeats list endpoints use `content` in their current response shape.
    Keep a few fallbacks so the app remains resilient to small schema changes.
    """
    if isinstance(payload, list):
        return payload

    if not isinstance(payload, dict):
        return []

    for key in ("content", "tracks", "items", "data"):
        value = payload.get(key)

        if isinstance(value, list):
            return value

        if isinstance(value, dict):
            for nested_key in ("content", "items", "tracks"):
                nested = value.get(nested_key)
                if isinstance(nested, list):
                    return nested

    return []


def spotify_id_from_href(href):
    if not href:
        return None

    marker = "open.spotify.com/track/"

    if marker not in href:
        return None

    tail = href.split(marker, 1)[1]
    return tail.split("?", 1)[0].split("/", 1)[0] or None


def recommendation_ids(seed_spotify_id, size=45):
    """
    ReccoBeats recommendation accepts Spotify IDs as seeds.
    We request a healthy candidate pool and re-rank it ourselves so the UI's
    sonic feature weights actually control the final playlist.
    """
    payload = _get(
        "/track/recommendation",
        {
            "seeds": seed_spotify_id,
            "size": max(1, min(int(size), 100)),
        },
    )

    ids = []

    for row in _content(payload):
        if not isinstance(row, dict):
            continue

        spotify_id = (
            row.get("spotifyId")
            or row.get("spotify_id")
            or spotify_id_from_href(row.get("href"))
        )

        if spotify_id and spotify_id != seed_spotify_id:
            ids.append(spotify_id)

    # stable dedupe
    return list(dict.fromkeys(ids))


def audio_features(spotify_ids):
    """
    Bulk audio-features endpoint accepts Spotify IDs.
    The API currently supports CSV IDs and returns feature rows containing
    the Spotify href, which lets us map each row back to a Spotify track.
    """
    ids = [item for item in dict.fromkeys(spotify_ids) if item]

    if not ids:
        return {}

    result = {}

    # Keep batches modest to respect the public API.
    for start in range(0, len(ids), 35):
        batch = ids[start:start + 35]

        payload = _get(
            "/audio-features",
            {"ids": ",".join(batch)},
        )

        for row in _content(payload):
            if not isinstance(row, dict):
                continue

            spotify_id = (
                row.get("spotifyId")
                or row.get("spotify_id")
                or spotify_id_from_href(row.get("href"))
            )

            if spotify_id:
                result[spotify_id] = row

    return result


def _number(value):
    try:
        result = float(value)
    except (TypeError, ValueError):
        return None

    return result if math.isfinite(result) else None


def _tempo_distance(a, b):
    """
    Tempo is special because half/double-time songs can feel rhythmically close.
    Compare the direct BPM distance as well as 2x and 0.5x relationships.
    """
    a = _number(a)
    b = _number(b)

    if a is None or b is None or a <= 0 or b <= 0:
        return None

    differences = (
        abs(a - b),
        abs(a - (b * 2)),
        abs(a - (b / 2)),
    )

    # 70 BPM difference is already effectively "far" for this recommender.
    return min(1.0, min(differences) / 70.0)


def _unit_distance(a, b):
    a = _number(a)
    b = _number(b)

    if a is None or b is None:
        return None

    return min(1.0, abs(a - b))


def sound_similarity(seed_features, candidate_features, weights):
    """
    Weighted feature distance -> similarity in [0, 1].

    Missing dimensions are ignored and remaining weights are re-normalized.
    """
    distance_functions = {
        "tempo": _tempo_distance,
        "energy": _unit_distance,
        "valence": _unit_distance,
        "danceability": _unit_distance,
        "acousticness": _unit_distance,
        "instrumentalness": _unit_distance,
    }

    weighted_distance = 0.0
    active_weight = 0.0

    for feature in FEATURE_NAMES:
        try:
            weight = max(0.0, float(weights.get(feature, 0)))
        except (TypeError, ValueError):
            weight = 0.0

        if weight <= 0:
            continue

        distance = distance_functions[feature](
            seed_features.get(feature),
            candidate_features.get(feature),
        )

        if distance is None:
            continue

        weighted_distance += distance * weight
        active_weight += weight

    if active_weight == 0:
        return None

    normalized_distance = weighted_distance / active_weight

    return max(0.0, min(1.0, 1.0 - normalized_distance))


def feature_snapshot(features):
    """Small serializable subset for the explanation UI."""
    if not features:
        return {}

    output = {}

    for name in FEATURE_NAMES:
        value = _number(features.get(name))
        if value is not None:
            output[name] = round(value, 3)

    return output