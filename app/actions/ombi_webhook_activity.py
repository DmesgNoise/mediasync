import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from app.database import add_activity_event, get_or_create_lifecycle, update_lifecycle_status

DEBUG_PAYLOAD_PATH = Path("/config/ombi_webhook_payloads.jsonl")
UNKNOWN_TITLE = "Unknown Title"


def process_ombi_webhook_event(
    request_app: dict[str, Any],
    payload: dict[str, Any],
    provider: Any | None = None,
) -> dict[str, Any]:
    _write_debug_payload(request_app, payload)
    normalized = _normalize_payload(payload)

    if not normalized.get("title") or normalized.get("title") == UNKNOWN_TITLE:
        return {
            "success": False,
            "message": "Ombi webhook ignored. No media title was found.",
            "debug_payload": str(DEBUG_PAYLOAD_PATH),
        }

    action = _normalize_action(normalized)

    if action == "ignored":
        return {
            "success": True,
            "message": "Ombi webhook ignored. Event type is not tracked.",
            "ignored": True,
            "action": action,
            "debug_payload": str(DEBUG_PAYLOAD_PATH),
        }

    # Ombi availability is not authoritative for MediaSync. The configured media
    # server remains the source of truth for available/completed states.
    if action == "available":
        return {
            "success": True,
            "message": "Ombi availability ignored. Media server availability is authoritative.",
            "ignored": True,
            "debug_payload": str(DEBUG_PAYLOAD_PATH),
        }

    lifecycle_id = _get_or_create_lifecycle_from_ombi(request_app, normalized, action)
    title = normalized.get("title") or UNKNOWN_TITLE
    source_name = request_app.get("app_name") or "Ombi"
    source_type = request_app.get("app_type") or "ombi"

    if action == "denied":
        add_activity_event(
            event_type=f"{title} denied",
            status="error",
            source_name=source_name,
            source_type=source_type,
            media_title=title,
            details=_details(normalized),
            lifecycle_id=lifecycle_id,
            lifecycle_stage="Denied",
        )
        update_lifecycle_status(lifecycle_id, "denied")
    else:
        add_activity_event(
            event_type=f"{title} requested",
            status="success",
            source_name=source_name,
            source_type=source_type,
            media_title=title,
            details=_details(normalized),
            lifecycle_id=lifecycle_id,
            lifecycle_stage="Requested",
        )
        update_lifecycle_status(lifecycle_id, "requested")

    return {
        "success": True,
        "message": "Ombi activity event recorded.",
        "action": action,
        "lifecycle_id": lifecycle_id,
        "title": title,
        "media_type": normalized.get("media_type"),
        "debug_payload": str(DEBUG_PAYLOAD_PATH),
    }


def _get_or_create_lifecycle_from_ombi(
    request_app: dict[str, Any],
    normalized: dict[str, Any],
    action: str,
):
    return get_or_create_lifecycle(
        media_type=normalized.get("media_type"),
        title=normalized.get("title"),
        tmdb_id=normalized.get("tmdb_id"),
        tvdb_id=normalized.get("tvdb_id"),
        imdb_id=normalized.get("imdb_id"),
        created_by=normalized.get("requested_by") or "",
        source_app=request_app.get("app_name") or "Ombi",
        source_type=request_app.get("app_type") or "ombi",
        quality_profile=normalized.get("quality_profile") or "",
        poster_url=normalized.get("poster_url") or "",
        status=action or "requested",
    )


def _normalize_payload(payload: dict[str, Any]) -> dict[str, Any]:
    raw = payload if isinstance(payload, dict) else {}

    media = _first_dict(
        raw.get("media"),
        raw.get("movie"),
        raw.get("tv"),
        raw.get("series"),
        raw.get("request"),
        raw.get("requestedItem"),
        raw.get("item"),
    )

    user = _first_dict(
        raw.get("requestedBy"),
        raw.get("requestedUser"),
        raw.get("user"),
        raw.get("requester"),
    )

    title = _first_text(
        raw.get("title"),
        raw.get("movieTitle"),
        raw.get("seriesTitle"),
        raw.get("tvTitle"),
        raw.get("mediaTitle"),
        raw.get("requestedTitle"),
        raw.get("subject"),
        raw.get("notificationSubject"),
        media.get("title"),
        media.get("name"),
        media.get("movieTitle"),
        media.get("seriesTitle"),
        media.get("tvTitle"),
        media.get("mediaTitle"),
    )

    media_type = _normalize_media_type(
        _first_text(
            raw.get("mediaType"),
            raw.get("type"),
            raw.get("requestType"),
            raw.get("request_type"),
            media.get("mediaType"),
            media.get("type"),
            media.get("requestType"),
        )
    )

    requested_by = _first_text(
        raw.get("requestedBy"),
        raw.get("requestedUser"),
        raw.get("userName"),
        raw.get("username"),
        raw.get("email"),
        user.get("displayName"),
        user.get("display_name"),
        user.get("userName"),
        user.get("username"),
        user.get("email"),
        user.get("emailAddress"),
    )

    return {
        "title": _clean_title(title) or UNKNOWN_TITLE,
        "media_type": media_type,
        "requested_by": requested_by,
        "quality_profile": _first_text(
            raw.get("qualityProfile"),
            raw.get("qualityProfileName"),
            raw.get("profileName"),
            media.get("qualityProfile"),
            media.get("qualityProfileName"),
            media.get("profileName"),
        ),
        "tmdb_id": _first_text(raw.get("tmdbId"), raw.get("theMovieDbId"), media.get("tmdbId"), media.get("theMovieDbId")),
        "tvdb_id": _first_text(raw.get("tvdbId"), raw.get("theTvDbId"), media.get("tvdbId"), media.get("theTvDbId")),
        "imdb_id": _first_text(raw.get("imdbId"), raw.get("imdbID"), media.get("imdbId"), media.get("imdbID")),
        "poster_url": _first_text(raw.get("poster"), raw.get("posterUrl"), raw.get("image"), media.get("poster"), media.get("posterUrl"), media.get("image")),
        "event": _first_text(raw.get("event"), raw.get("notificationType"), raw.get("notification_type"), raw.get("type"), raw.get("status"), media.get("status")),
        "raw": raw,
    }


def _normalize_action(normalized: dict[str, Any]) -> str:
    haystack = " ".join(
        str(value or "")
        for value in (
            normalized.get("event"),
            normalized.get("raw", {}).get("event"),
            normalized.get("raw", {}).get("notificationType"),
            normalized.get("raw", {}).get("subject"),
            normalized.get("raw", {}).get("message"),
            normalized.get("raw", {}).get("status"),
        )
    ).lower()

    if any(token in haystack for token in ("deleted", "removed", "cancelled", "canceled")):
        return "ignored"

    if any(token in haystack for token in ("denied", "declined", "rejected")):
        return "denied"

    if any(token in haystack for token in ("available", "completed", "fulfilled")):
        return "available"

    if any(token in haystack for token in ("approved", "processing")):
        return "approved"

    return "requested"


def _details(normalized: dict[str, Any]) -> str:
    parts = []

    if normalized.get("media_type") and normalized.get("media_type") != "unknown":
        parts.append(str(normalized.get("media_type")))

    if normalized.get("quality_profile"):
        parts.append(str(normalized.get("quality_profile")))

    if normalized.get("requested_by"):
        parts.append(f"Requested by {normalized.get('requested_by')}")

    return " • ".join(parts)


def _normalize_media_type(media_type: Any) -> str:
    normalized = str(media_type or "").strip().lower()

    if normalized in ("movie", "movies", "film"):
        return "movie"

    if normalized in ("tv", "show", "shows", "series", "tvshow", "tvshows", "episode"):
        return "tv"

    if "movie" in normalized:
        return "movie"

    if any(token in normalized for token in ("tv", "show", "series", "episode")):
        return "tv"

    return normalized or "unknown"


def _first_dict(*values: Any) -> dict[str, Any]:
    for value in values:
        if isinstance(value, dict):
            return value

    return {}


def _first_text(*values: Any) -> str:
    for value in values:
        if value is None:
            continue

        if isinstance(value, dict):
            for key in ("name", "title", "label", "username", "userName", "email", "emailAddress"):
                nested_value = value.get(key)

                if nested_value:
                    return str(nested_value).strip()

            continue

        if isinstance(value, list):
            continue

        text = str(value).strip()

        if text:
            return text

    return ""


def _clean_title(value: Any) -> str:
    text = str(value or "").strip()

    if not text:
        return ""

    for prefix in ("new request:", "request:", "requested:", "ombi request:"):
        if text.lower().startswith(prefix):
            return text[len(prefix):].strip()

    return text


def _write_debug_payload(request_app: dict[str, Any], payload: dict[str, Any]) -> None:
    try:
        DEBUG_PAYLOAD_PATH.parent.mkdir(parents=True, exist_ok=True)
        record = {
            "received_at": datetime.now(timezone.utc).isoformat(),
            "request_app_id": request_app.get("id"),
            "request_app_name": request_app.get("app_name"),
            "payload": payload,
        }

        with DEBUG_PAYLOAD_PATH.open("a", encoding="utf-8") as handle:
            handle.write(json.dumps(record, sort_keys=True) + "\n")
    except Exception:
        pass
