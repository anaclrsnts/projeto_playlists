from __future__ import annotations

from collections import Counter
import random

import requests

from recco_engine import (
    ReccoError,
    audio_features,
    feature_snapshot,
    recommendation_ids,
    sound_similarity,
)

LASTFM_API = "https://ws.audioscrobbler.com/2.0/"
TIMEOUT = 15

DEFAULT_SOUND_WEIGHTS = {
    "tempo": 0.65,
    "energy": 1.0,
    "valence": 0.85,
    "danceability": 0.75,
    "acousticness": 0.55,
    "instrumentalness": 0.45,
}


def _artist_names(track):
    return [
        artist.get("name", "").strip()
        for artist in (track.get("artists") or [])
        if artist.get("name")
    ]


def _primary_artist(track):
    names = _artist_names(track)
    return names[0] if names else ""


def _dedupe_tracks(tracks):
    seen = set()
    result = []

    for track in tracks:
        track_id = track.get("id")

        if not track_id or track_id in seen:
            continue

        seen.add(track_id)
        result.append(track)

    return result


def _lastfm_similar(seed, api_key, limit=45):
    if not api_key:
        return []

    artist = _primary_artist(seed)
    title = seed.get("name", "").strip()

    if not artist or not title:
        return []

    try:
        response = requests.get(
            LASTFM_API,
            params={
                "method": "track.getsimilar",
                "artist": artist,
                "track": title,
                "api_key": api_key,
                "format": "json",
                "autocorrect": 1,
                "limit": limit,
            },
            headers={
                "User-Agent": (
                    "PlaylistEngine/2.0 "
                    "(https://github.com/anaclrsnts/playlists)"
                )
            },
            timeout=TIMEOUT,
        )
        response.raise_for_status()
        payload = response.json()
    except (requests.RequestException, ValueError):
        return []

    rows = (payload.get("similartracks") or {}).get("track", [])
    output = []

    for row in rows:
        artist_data = row.get("artist") or {}

        artist_name = (
            artist_data.get("name", "")
            if isinstance(artist_data, dict)
            else str(artist_data)
        ).strip()

        track_name = row.get("name", "").strip()

        try:
            match = float(row.get("match") or 0)
        except (TypeError, ValueError):
            match = 0.0

        if track_name and artist_name:
            output.append(
                {
                    "name": track_name,
                    "artist": artist_name,
                    "match": max(0.0, min(1.0, match)),
                }
            )

    return output


def _spotify_find_track(spotify_call, token, title, artist):
    payload = spotify_call(
        "GET",
        "/search",
        token,
        {
            "q": f"{title} {artist}".strip(),
            "type": "track",
            "market": "BR",
            "limit": 3,
        },
    )

    tracks = (payload.get("tracks") or {}).get("items", [])

    if not tracks:
        return None

    wanted_title = title.casefold()
    wanted_artist = artist.casefold()

    for track in tracks:
        title_ok = track.get("name", "").casefold() == wanted_title
        artist_ok = any(
            artist_item.get("name", "").casefold() == wanted_artist
            for artist_item in track.get("artists") or []
        )

        if title_ok and artist_ok:
            return track

    return tracks[0]


def _listening_candidates(
    spotify_call,
    token,
    seed,
    lastfm_api_key,
    target=24,
):
    rows = _lastfm_similar(
        seed,
        lastfm_api_key,
        limit=max(40, target * 2),
    )

    result = []

    for row in rows:
        try:
            track = _spotify_find_track(
                spotify_call,
                token,
                row["name"],
                row["artist"],
            )
        except Exception:
            continue

        if not track or track.get("id") == seed.get("id"):
            continue

        track["_listening_match"] = row["match"]
        result.append(track)

        if len(result) >= target:
            break

    return _dedupe_tracks(result)


def _spotify_tracks_by_ids(spotify_call, token, ids):
    """
    Spotify's current Development Mode changed several batch endpoints.
    Individual track fetches are slower but reliable and keep the project simple.
    """
    result = []

    for track_id in ids:
        try:
            track = spotify_call(
                "GET",
                f"/tracks/{track_id}",
                token,
                {"market": "BR"},
            )
        except Exception:
            continue

        if track and track.get("id"):
            result.append(track)

    return _dedupe_tracks(result)


def _sound_candidates(
    spotify_call,
    token,
    seed,
    target=35,
):
    try:
        ids = recommendation_ids(
            seed.get("id"),
            size=max(35, target),
        )
    except ReccoError:
        return []

    return _spotify_tracks_by_ids(
        spotify_call,
        token,
        ids[:target],
    )


def _spotify_fallback(
    spotify_call,
    token,
    seed,
    target=20,
):
    """
    Safe final fallback. It intentionally avoids making same-artist tracks the
    main recommendation strategy.
    """
    query = _primary_artist(seed) or seed.get("name", "")

    try:
        found = (
            spotify_call(
                "GET",
                "/search",
                token,
                {
                    "q": query,
                    "type": "track",
                    "market": "BR",
                    "limit": 10,
                },
            ).get("tracks")
            or {}
        ).get("items", [])
    except Exception:
        found = []

    result = []

    for index, track in enumerate(found):
        if track.get("id") == seed.get("id"):
            continue

        track["_listening_match"] = max(0.05, 0.18 - index * 0.01)
        result.append(track)

    return _dedupe_tracks(result)[:target]


def _normalize_weights(weights):
    raw = weights or {}
    output = {}

    for key, default in DEFAULT_SOUND_WEIGHTS.items():
        try:
            value = float(raw.get(key, default))
        except (TypeError, ValueError):
            value = default

        output[key] = max(0.0, min(1.0, value))

    # Never allow a completely empty sound profile.
    if not any(output.values()):
        output = DEFAULT_SOUND_WEIGHTS.copy()

    return output


def _attach_sound_scores(seed, tracks, weights):
    ids = [seed.get("id")] + [
        track.get("id")
        for track in tracks
        if track.get("id")
    ]

    try:
        features = audio_features(ids)
    except ReccoError:
        return False, {}

    seed_features = features.get(seed.get("id"))

    if not seed_features:
        return False, {}

    for track in tracks:
        candidate_features = features.get(track.get("id"))

        if not candidate_features:
            continue

        score = sound_similarity(
            seed_features,
            candidate_features,
            weights,
        )

        if score is not None:
            track["_sound_match"] = score
            track["_sound_features"] = feature_snapshot(
                candidate_features
            )

    return True, feature_snapshot(seed_features)


def _final_score(track, mode, listening_weight):
    listening = track.get("_listening_match")
    sound = track.get("_sound_match")

    if mode == "listening":
        return float(listening or 0)

    if mode == "sound":
        return float(sound or 0)

    listening_available = listening is not None
    sound_available = sound is not None

    if listening_available and sound_available:
        return (
            float(listening) * listening_weight
            + float(sound) * (1.0 - listening_weight)
        )

    if listening_available:
        return float(listening)

    if sound_available:
        return float(sound)

    return 0.0


def _diverse_selection(
    tracks,
    seed,
    diversity,
    limit,
):
    if diversity >= 0.72:
        max_per_artist = 1
    elif diversity >= 0.38:
        max_per_artist = 2
    else:
        max_per_artist = 3

    seed_artist = _primary_artist(seed).casefold()
    artist_count = Counter()
    selected = []
    deferred = []

    ranked = sorted(
        tracks,
        key=lambda track: float(track.get("_final_match", 0)),
        reverse=True,
    )

    for track in ranked:
        artist = _primary_artist(track)
        key = artist.casefold()

        if key == seed_artist and diversity >= 0.35:
            deferred.append(track)
            continue

        if artist_count[key] >= max_per_artist:
            deferred.append(track)
            continue

        selected.append(track)
        artist_count[key] += 1

        if len(selected) >= limit:
            return selected

    for track in deferred:
        artist = _primary_artist(track)
        key = artist.casefold()

        if artist_count[key] >= max_per_artist + 1:
            continue

        selected.append(track)
        artist_count[key] += 1

        if len(selected) >= limit:
            break

    return selected


def _reason(track, mode):
    listening = track.get("_listening_match")
    sound = track.get("_sound_match")

    if mode == "listening":
        return "similar listening patterns"

    if mode == "sound":
        return "similar sound profile"

    if listening is not None and sound is not None:
        return "listening + sound profile"

    if sound is not None:
        return "sound profile"

    if listening is not None:
        return "listening patterns"

    return "discovery fallback"


def build_vibe_playlist(
    spotify_call,
    spotify_token,
    seed,
    lastfm_api_key="",
    mode="hybrid",
    diversity=0.75,
    listening_weight=0.5,
    sound_weights=None,
    limit=12,
):
    """
    Vibe Engine v2

    Listening:
        Last.fm track-to-track listening similarity.

    Sound:
        ReccoBeats feature-based recommendation pool + local weighted
        audio-feature distance.

    Hybrid:
        combines both scores and then applies artist diversity.
    """
    mode = mode if mode in {"listening", "sound", "hybrid"} else "hybrid"
    diversity = max(0.0, min(1.0, float(diversity)))
    listening_weight = max(
        0.0,
        min(1.0, float(listening_weight)),
    )
    weights = _normalize_weights(sound_weights)

    candidate_map = {}

    listening_candidates = []

    if mode in {"listening", "hybrid"}:
        listening_candidates = _listening_candidates(
            spotify_call,
            spotify_token,
            seed,
            lastfm_api_key,
            target=24,
        )

        for track in listening_candidates:
            candidate_map[track["id"]] = track

    sound_candidates = []

    if mode in {"sound", "hybrid"}:
        sound_candidates = _sound_candidates(
            spotify_call,
            spotify_token,
            seed,
            target=35,
        )

        for track in sound_candidates:
            existing = candidate_map.get(track["id"])

            if existing:
                # Preserve Last.fm score while using the richer Spotify object.
                if "_listening_match" in existing:
                    track["_listening_match"] = existing[
                        "_listening_match"
                    ]

            candidate_map[track["id"]] = track

    candidates = list(candidate_map.values())

    if not candidates:
        candidates = _spotify_fallback(
            spotify_call,
            spotify_token,
            seed,
            target=20,
        )

    sound_available = False
    seed_features = {}

    if mode in {"sound", "hybrid"} and candidates:
        sound_available, seed_features = _attach_sound_scores(
            seed,
            candidates,
            weights,
        )

    # Graceful degradation: if Sound was chosen but ReccoBeats cannot score,
    # use listening similarity when available rather than returning nothing.
    effective_mode = mode

    if mode == "sound" and not sound_available:
        if listening_candidates:
            candidates = listening_candidates
            effective_mode = "listening-fallback"
        else:
            listening_candidates = _listening_candidates(
                spotify_call,
                spotify_token,
                seed,
                lastfm_api_key,
                target=24,
            )

            if listening_candidates:
                candidates = listening_candidates
                effective_mode = "listening-fallback"

    for track in candidates:
        scoring_mode = (
            "listening"
            if effective_mode == "listening-fallback"
            else mode
        )

        track["_final_match"] = _final_score(
            track,
            scoring_mode,
            listening_weight,
        )

        track["_vibe_reason"] = _reason(
            track,
            scoring_mode,
        )

    candidates = [
        track
        for track in _dedupe_tracks(candidates)
        if track.get("id") != seed.get("id")
    ]

    selected = _diverse_selection(
        candidates,
        seed,
        diversity,
        limit,
    )

    source_parts = []

    if listening_candidates:
        source_parts.append("Last.fm listening similarity")

    if sound_available:
        source_parts.append("ReccoBeats audio features")

    if not source_parts:
        source_parts.append("Spotify fallback")

    description_by_mode = {
        "listening": (
            "Recommendations prioritize songs connected by aggregate "
            "listening patterns, then apply artist diversity."
        ),
        "sound": (
            "Recommendations prioritize the weighted sound profile selected "
            "by you: tempo, energy, mood, danceability, acousticness and "
            "instrumentalness."
        ),
        "hybrid": (
            "Recommendations combine listening behavior with weighted sonic "
            "similarity, then apply artist diversity."
        ),
    }

    if effective_mode == "listening-fallback":
        description = (
            "Sound analysis was unavailable for this seed, so the engine "
            "fell back to listening-pattern similarity."
        )
    else:
        description = description_by_mode[mode]

    return selected, {
        "name": "Vibe Engine v2",
        "requested_mode": mode,
        "mode": effective_mode,
        "source": " + ".join(source_parts),
        "diversity": diversity,
        "listening_weight": listening_weight,
        "sound_weight": 1.0 - listening_weight,
        "sound_weights": weights,
        "sound_available": sound_available,
        "seed_features": seed_features,
        "candidate_count": len(candidates),
        "description": description,
    }