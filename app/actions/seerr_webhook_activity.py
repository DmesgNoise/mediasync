import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import requests

from app.database import add_activity_event, get_or_create_lifecycle, get_sources, update_lifecycle_status

DEBUG_PAYLOAD_PATH = Path("/config/seerr_webhook_payloads.jsonl")
UNKNOWN_TITLE = "Unknown Title"


_PROFILE_CACHE: dict[tuple[str, str, str, int], str] = {}


def process_seerr_webhook_event(
    request_app: dict[str, Any],
    payload: dict[str, Any],
    provider: Any | None = None,
) -> dict[str, Any]:
    _write_debug_payload(request_app, payload)

    normalized = _normalize_payload(payload)

    if provider:
        enriched = _enrich_from_seerr_request(provider, normalized)

        if enriched:
            normalized.update(enriched)

    if not normalized["title"] or normalized["title"] == UNKNOWN_TITLE:
        return {
            "success": False,
            "message": "Webhook ignored. No media title was found.",
            "debug_payload": str(DEBUG_PAYLOAD_PATH),
        }

    action = _normalize_action(normalized)

    # Seerr can emit an "available" status after the media server has the item.
    # MediaSync treats the configured media server as the authoritative availability
    # source, so Seerr availability is ignored for both activity and lifecycle.
    if action == "available":
        return {
            "success": True,
            "message": "Seerr availability ignored. Media server availability is authoritative.",
            "ignored": True,
            "debug_payload": str(DEBUG_PAYLOAD_PATH),
        }

    sentence = _build_sentence(action, normalized)

    if not sentence:
        return {
            "success": True,
            "message": "Webhook ignored. Event type is not tracked.",
            "ignored": True,
            "debug_payload": str(DEBUG_PAYLOAD_PATH),
        }

    lifecycle_id = _get_or_create_lifecycle_from_request_app(request_app, normalized, action)

    if action == "denied":
        add_activity_event(
            event_type=sentence,
            status="error",
            source_name=request_app.get("app_name") or "Seerr",
            source_type=request_app.get("app_type") or "seerr",
            media_title=normalized.get("title") or sentence,
            details=normalized.get("quality_profile") or "",
            lifecycle_id=lifecycle_id,
            lifecycle_stage="Denied",
        )
        update_lifecycle_status(lifecycle_id, "denied")
    else:
        # Seerr is the request-origin authority. Record a real sync_activity row
        # for request/approval/processing notifications so the activity feed and
        # lifecycle origin do not appear to start at Radarr/Sonarr when the Arr
        # webhook arrives immediately after approval.
        add_activity_event(
            event_type=sentence,
            status=_event_status(action),
            source_name=request_app.get("app_name") or "Seerr",
            source_type=request_app.get("app_type") or "seerr",
            media_title=normalized.get("title") or sentence,
            details=normalized.get("quality_profile") or "",
            lifecycle_id=lifecycle_id,
            lifecycle_stage=_lifecycle_stage_for_action(action),
        )

        # Auto-approved/processing Seerr notifications still represent the
        # initial request in the user-facing lifecycle. Do not let them advance
        # past request ownership; later Arr/downloader/media-server events own
        # the pipeline stages.
        update_lifecycle_status(lifecycle_id, "requested")

    return {
        "success": True,
        "message": "Seerr activity event recorded.",
        "event_type": sentence,
        "action": action,
        "quality_profile": normalized.get("quality_profile") or "",
        "quality_profile_id": normalized.get("quality_profile_id"),
        "debug_payload": str(DEBUG_PAYLOAD_PATH),
    }



def _get_or_create_lifecycle_from_request_app(request_app: dict[str, Any], normalized: dict[str, Any], action: str):
    return get_or_create_lifecycle(
        media_type=normalized.get("media_type"),
        title=normalized.get("title"),
        tmdb_id=normalized.get("tmdb_id"),
        tvdb_id=normalized.get("tvdb_id"),
        imdb_id=normalized.get("imdb_id"),
        created_by=normalized.get("requested_by") or "",
        source_app=request_app.get("app_name") or "Seerr",
        source_type=request_app.get("app_type") or "seerr",
        quality_profile=normalized.get("quality_profile") or "",
        poster_url=normalized.get("poster_url") or "",
        status=action or "requested",
    )


def _lifecycle_stage_for_action(action: str) -> str:
    if action == "requested":
        return "Requested"

    if action == "approved":
        return "Approved"

    if action == "processing":
        return "Processing"

    if action == "available":
        return "Available"

    if action == "denied":
        return "Denied"

    return action or "Request Activity"

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


def _enrich_from_seerr_request(provider: Any, normalized: dict[str, Any]) -> dict[str, Any]:
    request_id = normalized.get("request_id")

    if not request_id or not hasattr(provider, "get_request_by_id"):
        return {}

    result = provider.get_request_by_id(request_id)

    if not result.get("success"):
        return {}

    request_data = result.get("data") or {}

    if not isinstance(request_data, dict):
        return {}

    if hasattr(provider, "normalize_request_payload"):
        request_item = provider.normalize_request_payload(request_data)
    else:
        request_item = {}

    requested_by = request_item.get("requested_by") or {}
    raw = request_item.get("raw") or {}
    media = raw.get("media") or {}

    media_type = _best_value(
        request_item.get("media_type"),
        normalized.get("media_type"),
    )

    enriched_title = _clean_title(request_item.get("title"))
    normalized_title = _clean_title(normalized.get("title"))

    quality_profile = (
        request_item.get("quality_profile")
        or _quality_profile(request_data, raw, media)
        or normalized.get("quality_profile")
        or ""
    )

    quality_profile_id = _first_value(
        request_item.get("quality_profile_id"),
        _quality_profile_id(request_data, raw, media),
        normalized.get("quality_profile_id"),
    )

    server_id = _first_value(
        request_item.get("server_id"),
        request_data.get("serverId"),
        raw.get("serverId"),
        media.get("serverId"),
        normalized.get("server_id"),
    )

    root_folder = _first_value(
        request_item.get("root_folder"),
        request_data.get("rootFolder"),
        raw.get("rootFolder"),
        media.get("rootFolder"),
        normalized.get("root_folder"),
    )

    if not quality_profile and quality_profile_id:
        quality_profile = _resolve_quality_profile_name(
            media_type=media_type,
            profile_id=quality_profile_id,
        )

    return {
        "title": enriched_title or normalized_title or UNKNOWN_TITLE,
        "media_type": media_type,
        "media_label": _media_label(media_type),
        "requested_by": _display_name(requested_by) or normalized.get("requested_by"),
        "quality_profile": quality_profile or "",
        "quality_profile_id": quality_profile_id,
        "server_id": server_id,
        "root_folder": root_folder,
        "tmdb_id": request_item.get("tmdb_id") or media.get("tmdbId") or request_data.get("tmdbId"),
        "tvdb_id": request_item.get("tvdb_id") or media.get("tvdbId") or request_data.get("tvdbId"),
        "imdb_id": media.get("imdbId") or request_data.get("imdbId"),
        "poster_url": normalized.get("poster_url") or _poster_url(media),
    }


def _resolve_quality_profile_name(media_type: Any, profile_id: Any) -> str:
    normalized_media_type = _normalize_media_type(media_type)
    parsed_profile_id = _safe_int(profile_id)

    if parsed_profile_id is None:
        return ""

    target_source_type = "sonarr" if normalized_media_type == "tv" else "radarr"

    try:
        sources = get_sources()
    except Exception:
        sources = []

    for source in sources:
        source_type = str(source.get("source_type") or "").strip().lower()

        if source_type != target_source_type:
            continue

        source_url = str(source.get("source_url") or "").strip().rstrip("/")
        api_key = str(source.get("api_key") or "").strip()

        if not source_url or not api_key:
            continue

        cache_key = (target_source_type, source_url, api_key, parsed_profile_id)

        if cache_key in _PROFILE_CACHE:
            return _PROFILE_CACHE[cache_key]

        resolved_name = _fetch_arr_quality_profile_name(
            source_url=source_url,
            api_key=api_key,
            profile_id=parsed_profile_id,
        )

        if resolved_name:
            _PROFILE_CACHE[cache_key] = resolved_name
            return resolved_name

    return ""


def _fetch_arr_quality_profile_name(source_url: str, api_key: str, profile_id: int) -> str:
    try:
        response = requests.get(
            f"{source_url}/api/v3/qualityprofile",
            headers={
                "X-Api-Key": api_key,
                "Accept": "application/json",
            },
            timeout=10,
        )

        response.raise_for_status()
        profiles = response.json()
    except Exception:
        return ""

    if not isinstance(profiles, list):
        return ""

    for profile in profiles:
        if not isinstance(profile, dict):
            continue

        if _safe_int(profile.get("id")) == profile_id:
            name = profile.get("name")

            if name:
                return str(name).strip()

    return ""


def _normalize_payload(payload: dict[str, Any]) -> dict[str, Any]:
    media = _first_dict(
        payload.get("media"),
        payload.get("movie"),
        payload.get("tv"),
        payload.get("series"),
    )

    request = _first_dict(
        payload.get("request"),
        payload.get("mediaRequest"),
        payload.get("media_request"),
    )

    extra = _first_dict(
        payload.get("extra"),
        payload.get("eventData"),
        payload.get("event_data"),
        payload.get("notification"),
    )

    user = _first_dict(
        payload.get("requestedBy"),
        payload.get("requested_by"),
        payload.get("user"),
        payload.get("requester"),
        request.get("requestedBy"),
        request.get("requested_by"),
        request.get("user"),
        extra.get("requestedBy"),
        extra.get("requested_by"),
    )

    title = _first_value(
        payload.get("title"),
        payload.get("mediaTitle"),
        payload.get("media_title"),
        media.get("title"),
        media.get("name"),
        media.get("originalTitle"),
        media.get("originalName"),
        request.get("title"),
        extra.get("title"),
        extra.get("mediaTitle"),
        payload.get("subject"),
    )

    media_type = _normalize_media_type(
        _first_value(
            payload.get("media_type"),
            payload.get("mediaType"),
            payload.get("type"),
            media.get("media_type"),
            media.get("mediaType"),
            media.get("type"),
            request.get("type"),
            extra.get("mediaType"),
            extra.get("media_type"),
        )
    )

    request_id = _first_value(
        payload.get("request_id"),
        payload.get("requestId"),
        request.get("request_id"),
        request.get("requestId"),
        request.get("id"),
    )

    return {
        "raw": payload,
        "request_id": request_id,
        "notification_type": _first_value(
            payload.get("notification_type"),
            payload.get("notificationType"),
            payload.get("event"),
            payload.get("eventType"),
            payload.get("type"),
            extra.get("notification_type"),
            extra.get("notificationType"),
            extra.get("event"),
            extra.get("eventType"),
        ),
        "status": _first_value(
            payload.get("status"),
            payload.get("request_status"),
            payload.get("requestStatus"),
            request.get("status"),
            media.get("status"),
            extra.get("status"),
        ),
        "title": _clean_title(title) or UNKNOWN_TITLE,
        "media_type": media_type,
        "media_label": _media_label(media_type),
        "requested_by": _display_name(user) or _string_value(
            _first_value(
                payload.get("requested_by"),
                payload.get("requestedBy"),
                payload.get("requester"),
                payload.get("username"),
                payload.get("user"),
                request.get("requestedBy_username"),
                request.get("requested_by_username"),
                extra.get("requested_by"),
                extra.get("requestedBy"),
            )
        ),
        "quality_profile": _quality_profile(payload, request, media, extra),
        "quality_profile_id": _quality_profile_id(payload, request, media, extra),
        "tmdb_id": _first_value(payload.get("tmdb_id"), payload.get("tmdbId"), media.get("tmdbId"), request.get("tmdbId")),
        "tvdb_id": _first_value(payload.get("tvdb_id"), payload.get("tvdbId"), media.get("tvdbId"), request.get("tvdbId")),
        "imdb_id": _first_value(payload.get("imdb_id"), payload.get("imdbId"), media.get("imdbId"), request.get("imdbId")),
        "poster_url": _string_value(payload.get("image")) or _poster_url(media),
        "server_id": _first_value(
            payload.get("server_id"),
            payload.get("serverId"),
            request.get("server_id"),
            request.get("serverId"),
            media.get("server_id"),
            media.get("serverId"),
        ),
        "root_folder": _first_value(
            payload.get("root_folder"),
            payload.get("rootFolder"),
            request.get("root_folder"),
            request.get("rootFolder"),
            media.get("root_folder"),
            media.get("rootFolder"),
        ),
    }



def _poster_url(media: dict[str, Any]) -> str:
    if not isinstance(media, dict):
        return ""

    for key in ("posterPath", "poster", "posterUrl", "remotePoster", "image", "imageUrl"):
        value = media.get(key)

        if value:
            return str(value)

    images = media.get("images") or []

    if isinstance(images, list):
        for image in images:
            if not isinstance(image, dict):
                continue

            if str(image.get("coverType") or "").lower() in ("poster", "cover"):
                value = image.get("remoteUrl") or image.get("url")

                if value:
                    return str(value)

        for image in images:
            if isinstance(image, dict):
                value = image.get("remoteUrl") or image.get("url")

                if value:
                    return str(value)

    return ""

def _normalize_action(normalized: dict[str, Any]) -> str:
    raw = normalized.get("raw") or {}

    notification_type = str(normalized.get("notification_type") or "").strip().upper()
    event_text = str(raw.get("event") or "").strip().lower()

    # Auto-approved requests are the only request event many Seerr installs emit
    # when users are auto-approved. Treat it as the request lifecycle entry.
    if notification_type in ("MEDIA_AUTO_APPROVED", "MEDIA_AUTO_REQUESTED"):
        return "requested"

    candidates = [
        normalized.get("notification_type"),
        normalized.get("status"),
        raw.get("action"),
        raw.get("event"),
        raw.get("eventType"),
        raw.get("notificationType"),
        raw.get("notification_type"),
        raw.get("requestStatus"),
        raw.get("request_status"),
        raw.get("subject"),
        raw.get("message"),
    ]

    joined = " ".join(
        str(value).strip().lower()
        for value in candidates
        if value is not None and str(value).strip()
    )

    if not joined:
        return ""

    if any(word in joined for word in ("available", "fulfilled")):
        return "available"

    if any(word in joined for word in ("declined", "denied", "rejected")):
        return "denied"

    if "approved" in joined:
        return "approved"

    if any(word in joined for word in ("processing", "process", "started", "added")):
        return "processing"

    if any(word in joined for word in ("request", "pending", "created", "new")):
        return "requested"

    if "automatically approved" in event_text:
        return "requested"

    return ""


def _build_sentence(action: str, normalized: dict[str, Any]) -> str:
    title = normalized.get("title") or UNKNOWN_TITLE

    if action == "requested":
        requester = normalized.get("requested_by") or "Someone"
        media_label = normalized.get("media_label") or "media item"
        return f"{requester} requested the {media_label} {title}"

    if action == "approved":
        return f"{title} approved"

    if action == "denied":
        return f"{title} denied"

    if action == "processing":
        return f"{title} processing"

    if action == "available":
        return f"{title} available"

    return ""


def _event_status(action: str) -> str:
    if action in ("requested", "approved", "available"):
        return "success"

    if action == "processing":
        return "active"

    if action == "denied":
        return "error"

    return "info"


def _quality_profile(*sources: dict[str, Any]) -> str:
    direct_keys = (
        "quality_profile",
        "qualityProfile",
        "qualityProfileName",
        "profile_name",
        "profileName",
        "profile",
        "requested_quality",
        "requestedQuality",
        "requestProfile",
        "request_profile",
        "request_profile_name",
        "requestProfileName",
        "quality",
        "quality_name",
        "qualityName",
    )

    for source in sources:
        value = _find_nested_value(source, direct_keys)

        if isinstance(value, str) and value.strip():
            return value.strip()

        if isinstance(value, dict):
            for nested_key in ("name", "label", "title"):
                nested_value = value.get(nested_key)

                if nested_value:
                    return str(nested_value).strip()

    for source in sources:
        if not isinstance(source, dict):
            continue

        if source.get("is4k") is True or source.get("is4k") == "true":
            return "4K"

    return ""


def _quality_profile_id(*sources: dict[str, Any]) -> Any:
    profile_id_keys = (
        "profileId",
        "profile_id",
        "qualityProfileId",
        "quality_profile_id",
        "qualityProfileID",
        "requestProfileId",
        "request_profile_id",
        "requestProfileID",
    )

    for source in sources:
        value = _find_nested_value(source, profile_id_keys)

        if value not in (None, ""):
            return value

    return None


def _find_nested_value(value: Any, keys: tuple[str, ...]) -> Any:
    if not isinstance(value, dict):
        return None

    for key in keys:
        if key in value and value.get(key) not in (None, ""):
            return value.get(key)

    for nested_value in value.values():
        if isinstance(nested_value, dict):
            found = _find_nested_value(nested_value, keys)

            if found not in (None, ""):
                return found

    return None


def _clean_title(value: Any) -> str:
    if not value:
        return ""

    title = str(value).strip()

    if not title or title == UNKNOWN_TITLE:
        return ""

    return title


def _best_value(*values: Any) -> str:
    for value in values:
        if value is not None and str(value).strip():
            return str(value).strip()

    return ""


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
    if not isinstance(user, dict) or not user:
        return None

    for key in ("displayName", "display_name", "username", "jellyfinUsername", "plexUsername", "email", "name"):
        value = user.get(key)

        if value:
            return str(value)

    return None


def _string_value(value: Any) -> str | None:
    if isinstance(value, str) and value.strip():
        return value.strip()

    return None


def _safe_int(value: Any) -> int | None:
    try:
        return int(value)
    except (TypeError, ValueError):
        return None


def _first_dict(*values: Any) -> dict[str, Any]:
    for value in values:
        if isinstance(value, dict):
            return value

    return {}


def _first_value(*values: Any) -> Any:
    for value in values:
        if value is not None and value != "":
            return value

    return None
