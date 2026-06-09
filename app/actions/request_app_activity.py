import json
from pathlib import Path
from typing import Any

from app.database import add_activity_event
from app.providers.request_apps.base import build_request_app_provider

STATE_PATH = Path("/config/request_activity_state.json")
DEFAULT_SYNC_LIMIT = 25


def sync_request_app_activity(request_apps: list[dict[str, Any]], limit: int = DEFAULT_SYNC_LIMIT) -> None:
    state = _load_state()
    changed = False

    for request_app in request_apps:
        if str(request_app.get("app_type", "")).strip().lower() != "seerr":
            continue

        provider = build_request_app_provider(
            app_type=request_app.get("app_type"),
            server_url=request_app.get("app_url"),
            api_key=request_app.get("api_key"),
        )

        if not provider:
            continue

        try:
            requests = provider.get_recent_requests(limit=limit)
        except Exception:
            continue

        app_state_key = f"request_app:{request_app.get('id')}"
        app_state = state.setdefault(app_state_key, {})

        for request_item in reversed(requests):
            if _sync_single_request(
                request_app=request_app,
                provider=provider,
                request_item=request_item,
                app_state=app_state,
            ):
                changed = True

    if changed:
        _save_state(state)


def _sync_single_request(
    request_app: dict[str, Any],
    provider: Any,
    request_item: dict[str, Any],
    app_state: dict[str, Any],
) -> bool:
    request_id = request_item.get("id")

    if request_id is None:
        return False

    request_key = str(request_id)
    previous_state = app_state.get(request_key, {})
    new_state = _build_request_state(provider, request_item)

    changed = False

    if not previous_state.get("requested"):
        _add_requested_event(request_app, new_state)
        previous_state["requested"] = True
        changed = True

    if new_state["request_status"] == "approved" and previous_state.get("request_status") != "approved":
        _add_simple_event(request_app, new_state, "approved", "success")
        changed = True

    if new_state["request_status"] == "declined" and previous_state.get("request_status") != "declined":
        _add_simple_event(request_app, new_state, "denied", "error")
        changed = True

    if new_state["pipeline_status"] == "processing" and previous_state.get("pipeline_status") != "processing":
        _add_simple_event(request_app, new_state, "processing", "active")
        changed = True

    if new_state["pipeline_status"] == "available" and previous_state.get("pipeline_status") != "available":
        _add_simple_event(request_app, new_state, "available", "success")
        changed = True

    previous_state.update(
        {
            "request_status": new_state["request_status"],
            "pipeline_status": new_state["pipeline_status"],
            "title": new_state["title"],
            "media_type": new_state["media_type"],
            "quality_profile": new_state["quality_profile"],
            "tmdb_id": new_state["tmdb_id"],
            "imdb_id": new_state["imdb_id"],
            "tvdb_id": new_state["tvdb_id"],
            "updated_at": new_state["updated_at"],
        }
    )

    app_state[request_key] = previous_state

    return changed


def _build_request_state(provider: Any, request_item: dict[str, Any]) -> dict[str, Any]:
    raw = request_item.get("raw") or {}
    media = raw.get("media") or {}
    requested_by = request_item.get("requested_by") or {}

    media_type = _normalize_media_type(
        request_item.get("media_type")
        or raw.get("type")
        or media.get("mediaType")
    )

    tmdb_id = request_item.get("tmdb_id") or media.get("tmdbId") or raw.get("tmdbId")
    imdb_id = media.get("imdbId") or media.get("imdb_id") or raw.get("imdbId")
    tvdb_id = request_item.get("tvdb_id") or media.get("tvdbId") or raw.get("tvdbId")

    title = request_item.get("title")

    if not title or title == "Unknown Title":
        title = _fetch_title(provider, media_type, tmdb_id) or f"TMDB {tmdb_id or 'Unknown'}"

    return {
        "request_id": request_item.get("id"),
        "request_status": _normalize_request_status(raw.get("status") or request_item.get("status")),
        "pipeline_status": _normalize_pipeline_status(raw, media, request_item),
        "media_type": media_type,
        "media_label": _media_label(media_type),
        "title": title,
        "requested_by": _display_name(requested_by),
        "quality_profile": _quality_profile(raw, media),
        "tmdb_id": tmdb_id,
        "imdb_id": imdb_id,
        "tvdb_id": tvdb_id,
        "created_at": request_item.get("created_at") or raw.get("createdAt"),
        "updated_at": request_item.get("updated_at") or raw.get("updatedAt"),
    }


def _fetch_title(provider: Any, media_type: str, tmdb_id: Any) -> str | None:
    if not tmdb_id or not hasattr(provider, "_get"):
        return None

    endpoint_type = "tv" if media_type == "tv" else "movie"

    try:
        result = provider._get(f"/{endpoint_type}/{tmdb_id}")
    except Exception:
        return None

    if not result.get("success"):
        return None

    data = result.get("data") or {}

    for key in ("title", "name", "originalTitle", "originalName"):
        value = data.get(key)

        if value:
            return str(value)

    return None


def _add_requested_event(request_app: dict[str, Any], state: dict[str, Any]) -> None:
    requester = state.get("requested_by") or "Someone"
    title = state.get("title") or "Unknown Title"
    media_label = state.get("media_label") or "media item"

    sentence = f"{requester} requested the {media_label} {title}"

    add_activity_event(
        event_type=sentence,
        status="success",
        source_name=request_app.get("app_name") or "Seerr",
        source_type=request_app.get("app_type") or "seerr",
        media_title=sentence,
        details=_details(state),
    )


def _add_simple_event(
    request_app: dict[str, Any],
    state: dict[str, Any],
    action: str,
    status: str,
) -> None:
    title = state.get("title") or "Unknown Title"
    sentence = f"{title} {action}"

    add_activity_event(
        event_type=sentence,
        status=status,
        source_name=request_app.get("app_name") or "Seerr",
        source_type=request_app.get("app_type") or "seerr",
        media_title=sentence,
        details=_details(state),
    )


def _details(state: dict[str, Any]) -> str:
    return state.get("quality_profile") or ""


def _quality_profile(raw: dict[str, Any], media: dict[str, Any]) -> str:
    for key in (
        "profileName",
        "profile_name",
        "qualityProfile",
        "quality_profile",
        "qualityProfileName",
        "quality_profile_name",
    ):
        value = raw.get(key) or media.get(key)

        if isinstance(value, str) and value.strip():
            return value.strip()

        if isinstance(value, dict):
            for nested_key in ("name", "label", "title"):
                nested_value = value.get(nested_key)

                if nested_value:
                    return str(nested_value).strip()

    profile = raw.get("profile") or media.get("profile")

    if isinstance(profile, dict):
        for key in ("name", "label", "title"):
            value = profile.get(key)

            if value:
                return str(value).strip()

    if raw.get("is4k") or media.get("is4k") or media.get("status4k") not in (None, 1, "1"):
        return "4K"

    return ""


def _normalize_request_status(status: Any) -> str:
    try:
        parsed_status = int(status)
    except (TypeError, ValueError):
        parsed_status = None

    if parsed_status == 1:
        return "pending"

    if parsed_status == 2:
        return "approved"

    if parsed_status == 3:
        return "declined"

    if parsed_status == 5:
        return "available"

    if isinstance(status, str):
        normalized = status.strip().lower()

        if normalized:
            return normalized

    return "unknown"


def _normalize_pipeline_status(
    raw: dict[str, Any],
    media: dict[str, Any],
    request_item: dict[str, Any],
) -> str:
    media_url = media.get("mediaUrl") or media.get("media_url")
    jellyfin_media_id = media.get("jellyfinMediaId") or media.get("jellyfin_media_id")
    plex_rating_key = media.get("ratingKey") or media.get("rating_key")
    request_status = _normalize_request_status(raw.get("status") or request_item.get("status"))

    try:
        media_status = int(media.get("status"))
    except (TypeError, ValueError):
        media_status = None

    if media_url or jellyfin_media_id or plex_rating_key or request_status == "available" or media_status == 5:
        return "available"

    if request_status == "approved" or media_status in (2, 3, 4):
        return "processing"

    if request_status == "pending":
        return "pending"

    if request_status == "declined":
        return "declined"

    return "unknown"


def _normalize_media_type(media_type: Any) -> str:
    normalized = str(media_type or "").strip().lower()

    if normalized in ("movie", "movies"):
        return "movie"

    if normalized in ("tv", "show", "series", "tvshows"):
        return "tv"

    return normalized or "unknown"


def _media_label(media_type: str) -> str:
    if media_type == "movie":
        return "movie"

    if media_type == "tv":
        return "TV series"

    return "media item"


def _display_name(user: dict[str, Any] | None) -> str | None:
    if not user:
        return None

    for key in ("display_name", "username", "email"):
        value = user.get(key)

        if value:
            return str(value)

    return None


def _load_state() -> dict[str, Any]:
    if not STATE_PATH.exists():
        return {}

    try:
        return json.loads(STATE_PATH.read_text())
    except Exception:
        return {}


def _save_state(state: dict[str, Any]) -> None:
    STATE_PATH.parent.mkdir(parents=True, exist_ok=True)
    STATE_PATH.write_text(json.dumps(state, indent=2, sort_keys=True))
