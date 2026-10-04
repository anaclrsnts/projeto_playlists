from __future__ import annotations

import base64
import os
import secrets
import time
from urllib.parse import urlencode

import requests
from dotenv import load_dotenv
from flask import Flask, jsonify, redirect, render_template, request, session, url_for

from vibe_engine import build_vibe_playlist

load_dotenv()

app = Flask(__name__)
app.secret_key = os.getenv("FLASK_SECRET_KEY", secrets.token_hex(32))

CLIENT_ID = os.getenv("SPOTIFY_CLIENT_ID", "")
CLIENT_SECRET = os.getenv("SPOTIFY_CLIENT_SECRET", "")
REDIRECT_URI = os.getenv(
    "SPOTIFY_REDIRECT_URI",
    "http://127.0.0.1:5000/callback",
)
LASTFM_API_KEY = os.getenv("LASTFM_API_KEY", "")

API = "https://api.spotify.com/v1"
ACC = "https://accounts.spotify.com"
TIMEOUT = 20
SCOPES = "playlist-modify-public playlist-modify-private"


class SpotifyError(RuntimeError):
    def __init__(self, message, status_code=None):
        super().__init__(message)
        self.status_code = status_code


class SpotifyAuthError(SpotifyError):
    pass


def configured():
    return bool(CLIENT_ID and CLIENT_SECRET)


def basic():
    raw = f"{CLIENT_ID}:{CLIENT_SECRET}".encode()
    return "Basic " + base64.b64encode(raw).decode()


def err(resp):
    try:
        payload = resp.json()
        error = payload.get("error", {}) if isinstance(payload, dict) else {}

        if isinstance(error, dict):
            return error.get("message") or str(error)

        return (
            payload.get("error_description")
            if isinstance(payload, dict)
            else str(error)
        )
    except Exception:
        return f"Spotify error ({resp.status_code})"


def app_token():
    if not configured():
        raise SpotifyError(
            "Configure the Spotify credentials in your environment variables."
        )

    response = requests.post(
        ACC + "/api/token",
        headers={"Authorization": basic()},
        data={"grant_type": "client_credentials"},
        timeout=TIMEOUT,
    )

    if not response.ok:
        raise SpotifyError(
            err(response),
            status_code=response.status_code,
        )

    return response.json()["access_token"]


def call(method, path, token, params=None, body=None):
    response = requests.request(
        method,
        API + path,
        headers={
            "Authorization": f"Bearer {token}",
            "Content-Type": "application/json",
        },
        params=params,
        json=body,
        timeout=TIMEOUT,
    )

    if not response.ok:
        raise SpotifyError(
            err(response),
            status_code=response.status_code,
        )

    return {} if response.status_code == 204 else response.json()


def store_user_token(token_data):
    """
    Save Spotify OAuth credentials and an absolute expiry timestamp.

    Spotify may omit a new refresh_token during refresh. In that case we keep
    the refresh token that is already in the session.
    """
    access_token = token_data.get("access_token")

    if not access_token:
        raise SpotifyAuthError(
            "Spotify did not return an access token."
        )

    session["access_token"] = access_token

    refresh_token = token_data.get("refresh_token")

    if refresh_token:
        session["refresh_token"] = refresh_token

    try:
        expires_in = int(token_data.get("expires_in", 3600))
    except (TypeError, ValueError):
        expires_in = 3600

    # Refresh a little early so a token does not expire halfway through saving.
    session["token_expires_at"] = (
        int(time.time()) + max(60, expires_in - 60)
    )


def refresh_user_token():
    refresh_token = session.get("refresh_token")

    if not refresh_token:
        session.pop("access_token", None)
        session.pop("token_expires_at", None)

        raise SpotifyAuthError(
            "Your Spotify session expired. Please connect again.",
            status_code=401,
        )

    response = requests.post(
        ACC + "/api/token",
        headers={
            "Authorization": basic(),
            "Content-Type": "application/x-www-form-urlencoded",
        },
        data={
            "grant_type": "refresh_token",
            "refresh_token": refresh_token,
        },
        timeout=TIMEOUT,
    )

    if not response.ok:
        session.pop("access_token", None)
        session.pop("refresh_token", None)
        session.pop("token_expires_at", None)

        raise SpotifyAuthError(
            "Your Spotify session expired. Please connect again.",
            status_code=response.status_code,
        )

    token_data = response.json()
    store_user_token(token_data)

    return session["access_token"]


def get_user_token():
    token = session.get("access_token")

    if not token:
        raise SpotifyAuthError(
            "Connect your Spotify account to save the playlist.",
            status_code=401,
        )

    expires_at = session.get("token_expires_at")

    try:
        expired = (
            expires_at is not None
            and time.time() >= float(expires_at)
        )
    except (TypeError, ValueError):
        expired = False

    if expired:
        return refresh_user_token()

    return token


def user_call(method, path, params=None, body=None):
    """
    Call Spotify with the user's OAuth token.

    If Spotify returns 401, refresh once automatically and retry the exact
    request. This also repairs older browser sessions whose access token was
    saved before automatic refresh support existed.
    """
    token = get_user_token()

    try:
        return call(
            method,
            path,
            token,
            params=params,
            body=body,
        )
    except SpotifyError as exc:
        if exc.status_code != 401:
            raise

    token = refresh_user_token()

    return call(
        method,
        path,
        token,
        params=params,
        body=body,
    )


def pack(track):
    album = track.get("album") or {}
    images = album.get("images") or []
    artists = track.get("artists") or []

    result = {
        "id": track.get("id"),
        "uri": track.get("uri"),
        "name": track.get("name", ""),
        "artists": ", ".join(a.get("name", "") for a in artists),
        "image": images[0]["url"] if images else "",
        "url": (track.get("external_urls") or {}).get("spotify", ""),
    }

    if "_vibe_match" in track:
        result["match"] = round(float(track["_vibe_match"]), 3)

    if track.get("_vibe_reason"):
        result["reason"] = track["_vibe_reason"]

    return result


@app.get("/")
def index():
    return render_template(
        "index.html",
        connected=bool(session.get("access_token")),
        vibe_enabled=bool(LASTFM_API_KEY),
    )


@app.get("/api/search")
def search():
    query = request.args.get("q", "").strip()

    if len(query) < 2:
        return jsonify(error="Type a song or artist."), 400

    try:
        payload = call(
            "GET",
            "/search",
            app_token(),
            {
                "q": query,
                "type": "track",
                "market": "BR",
                "limit": 8,
            },
        )

        tracks = (payload.get("tracks") or {}).get("items", [])

        return jsonify(tracks=[pack(track) for track in tracks])

    except SpotifyError as exc:
        return jsonify(error=str(exc)), 502


@app.post("/api/generate")
def generate():
    data = request.get_json(silent=True) or {}
    seed_id = data.get("seed_track_id")

    if not seed_id:
        return jsonify(error="Choose a song first."), 400

    try:
        diversity = float(data.get("diversity", 0.75))
    except (TypeError, ValueError):
        diversity = 0.75

    try:
        listening_weight = float(
            data.get("listening_weight", 0.5)
        )
    except (TypeError, ValueError):
        listening_weight = 0.5

    mode = str(data.get("mode") or "hybrid").lower()

    if mode not in {"listening", "sound", "hybrid"}:
        mode = "hybrid"

    sound_weights = data.get("sound_weights") or {}

    try:
        token = app_token()

        seed = call(
            "GET",
            f"/tracks/{seed_id}",
            token,
            {"market": "BR"},
        )

        tracks, engine_info = build_vibe_playlist(
            spotify_call=call,
            spotify_token=token,
            seed=seed,
            lastfm_api_key=LASTFM_API_KEY,
            mode=mode,
            diversity=max(0.0, min(1.0, diversity)),
            listening_weight=max(
                0.0,
                min(1.0, listening_weight),
            ),
            sound_weights=sound_weights,
            limit=12,
        )

        if not tracks:
            raise SpotifyError(
                "It was not possible to generate the playlist."
            )

        payload = {
            "seed": pack(seed),
            "tracks": [pack(track) for track in tracks],
            "engine": engine_info,
        }

        session["generated"] = payload

        return jsonify(payload)

    except SpotifyError as exc:
        return jsonify(error=str(exc)), 502
    except Exception as exc:
        # Keep the public error readable while Render logs contain the real exception.
        app.logger.exception("Playlist generation failed")
        return jsonify(
            error=(
                "The recommendation engine could not finish this request. "
                "Please try again."
            )
        ), 502


@app.get("/login")
def login():
    if not configured():
        return redirect(url_for("index", error="config"))

    state = secrets.token_urlsafe(24)
    session["oauth_state"] = state

    return redirect(
        ACC
        + "/authorize?"
        + urlencode(
            {
                "client_id": CLIENT_ID,
                "response_type": "code",
                "redirect_uri": REDIRECT_URI,
                "scope": SCOPES,
                "state": state,
                "show_dialog": "true",
            }
        )
    )


@app.get("/callback")
def callback():
    if request.args.get("state") != session.pop("oauth_state", None):
        return redirect(url_for("index", error="state"))

    code = request.args.get("code")

    if not code:
        return redirect(url_for("index", error="login"))

    response = requests.post(
        ACC + "/api/token",
        headers={"Authorization": basic()},
        data={
            "grant_type": "authorization_code",
            "code": code,
            "redirect_uri": REDIRECT_URI,
        },
        timeout=TIMEOUT,
    )

    if not response.ok:
        return redirect(url_for("index", error="token"))

    try:
        store_user_token(response.json())
    except SpotifyAuthError:
        return redirect(url_for("index", error="token"))

    return redirect(url_for("index", connected="1"))


@app.post("/logout")
def logout():
    session.clear()
    return jsonify(message="Disconnected.")


@app.post("/api/save")
def save():
    data = request.get_json(silent=True) or {}

    tracks = (
        data.get("tracks")
        or (session.get("generated") or {}).get("tracks", [])
    )

    uris = [
        track.get("uri")
        for track in tracks
        if track.get("uri")
    ]

    if not uris:
        return jsonify(
            error="There are no tracks available to save."
        ), 400

    try:
        # 1. Create the playlist.
        playlist = user_call(
            "POST",
            "/me/playlists",
            body={
                "name": (
                    data.get("name")
                    or "Playlist Engine"
                )[:100],
                "public": bool(data.get("public")),
                "description": (
                    "Created with Playlist Engine — "
                    "music discovery by listening patterns and sound profile."
                ),
            },
        )

        playlist_id = playlist.get("id")

        if not playlist_id:
            raise SpotifyError(
                "Spotify created the request but did not return a playlist ID."
            )

        # 2. Add the generated tracks.
        add_result = user_call(
            "POST",
            f"/playlists/{playlist_id}/items",
            body={"uris": uris},
        )

        # 3. Verify that the playlist exists after insertion.
        verified = user_call(
            "GET",
            f"/playlists/{playlist_id}",
        )

        external_url = (
            verified.get("external_urls")
            or playlist.get("external_urls")
            or {}
        ).get("spotify", "")

        # Some Spotify responses expose item counts differently over time,
        # so this is intentionally optional metadata, not the success condition.
        tracks_info = (
            verified.get("tracks")
            or verified.get("items")
            or {}
        )

        item_count = None

        if isinstance(tracks_info, dict):
            item_count = (
                tracks_info.get("total")
                or tracks_info.get("count")
            )

        return jsonify(
            message="Playlist saved successfully!",
            playlist_id=playlist_id,
            snapshot_id=add_result.get("snapshot_id"),
            item_count=item_count,
            url=external_url,
            verified=True,
        )

    except SpotifyAuthError as exc:
        app.logger.info("Spotify user authentication needs reconnect")

        return jsonify(
            error=str(exc),
            verified=False,
            login_required=True,
        ), 401

    except SpotifyError as exc:
        app.logger.exception("Spotify playlist save failed")

        return jsonify(
            error=str(exc),
            verified=False,
        ), 502


if __name__ == "__main__":
    app.run(debug=True)