import re
import threading
import time
from urllib.parse import urljoin

import requests

from app.database import add_activity_event, get_app_settings, update_lifecycle_status
from app.providers.media_servers.base import build_media_server_provider
from app.providers.sources.sonarr import SonarrProvider

TV_QUEUE_MONITORS = {}
TV_QUEUE_LOCK = threading.Lock()

AVAILABILITY_MONITORS = set()
AVAILABILITY_LOCK = threading.Lock()

DEFAULT_QUEUE_POLL_INTERVAL_SECONDS = 60
DEFAULT_INTERIM_SCAN_MINUTES = 10
DEFAULT_FINAL_SCAN_WHEN_QUEUE_EMPTY = True

AVAILABILITY_INITIAL_DELAY_SECONDS = 0
AVAILABILITY_POLL_INTERVAL_SECONDS = 1
AVAILABILITY_MAX_WAIT_SECONDS = 600


def request_scan(
    media_server,
    source,
    library,
    import_event,
):
    media_type = source["source_type"].lower()

    if media_type == "radarr":
        _run_movie_scan(
            media_server,
            source,
            library,
            import_event,
        )
        return

    if media_type == "sonarr":
        _start_or_update_tv_queue_monitor(
            media_server,
            source,
            library,
            import_event,
        )
        return


def _build_media_server_provider(media_server):
    if not media_server:
        return None

    return build_media_server_provider(
        server_type=media_server.get("server_type"),
        server_url=media_server.get("server_url"),
        api_key=media_server.get("api_key"),
    )


def _get_positive_int(value, default):
    try:
        parsed_value = int(value)
    except (TypeError, ValueError):
        return default

    if parsed_value <= 0:
        return default

    return parsed_value


def _get_tv_queue_settings():
    settings = get_app_settings()

    queue_poll_interval = _get_positive_int(
        settings.get("tv_poll_interval_seconds"),
        DEFAULT_QUEUE_POLL_INTERVAL_SECONDS,
    )

    interim_scan_minutes = _get_positive_int(
        settings.get("tv_interim_scan_minutes"),
        DEFAULT_INTERIM_SCAN_MINUTES,
    )

    final_scan_when_empty = str(
        settings.get(
            "tv_final_scan_enabled",
            "1" if DEFAULT_FINAL_SCAN_WHEN_QUEUE_EMPTY else "0",
        )
    ).strip() == "1"

    return {
        "queue_poll_interval": queue_poll_interval,
        "interim_scan_interval": interim_scan_minutes * 60,
        "interim_scan_minutes": interim_scan_minutes,
        "final_scan_when_empty": final_scan_when_empty,
    }


def _run_movie_scan(
    media_server,
    source,
    library,
    import_event,
):
    provider = _build_media_server_provider(media_server)

    if not provider:
        add_activity_event(
            event_type="Movie library scan failed",
            status="error",
            source_id=source["id"],
            source_name=source["source_name"],
            source_type=source["source_type"],
            library_id=library["library_id"],
            library_name=library["library_name"],
            media_title=import_event.get("media_title"),
            file_name=import_event.get("file_name"),
            file_path=import_event.get("file_path"),
            details="Unsupported media server type.",
            lifecycle_id=import_event.get("lifecycle_id"),
            lifecycle_stage="Movie Library Scan Failed",
        )
        return

    add_activity_event(
        event_type="Movie library scan started",
        status="active",
        source_id=source["id"],
        source_name=source["source_name"],
        source_type=source["source_type"],
        library_id=library["library_id"],
        library_name=library["library_name"],
        media_title=import_event.get("media_title"),
        file_name=import_event.get("file_name"),
        file_path=import_event.get("file_path"),
        details="Library scan started.",
        lifecycle_id=import_event.get("lifecycle_id"),
        lifecycle_stage="Library Sync Started",
    )
    update_lifecycle_status(import_event.get("lifecycle_id"), "library_sync")

    result = provider.scan_library(
        library_id=library["library_id"],
        library_name=library["library_name"],
    )

    if not result.get("success"):
        add_activity_event(
            event_type="Movie library scan failed",
            status="error",
            source_id=source["id"],
            source_name=source["source_name"],
            source_type=source["source_type"],
            library_id=library["library_id"],
            library_name=library["library_name"],
            media_title=import_event.get("media_title"),
            file_name=import_event.get("file_name"),
            file_path=import_event.get("file_path"),
            details=result.get("message", "Movie scan failed."),
            lifecycle_id=import_event.get("lifecycle_id"),
            lifecycle_stage="Library Sync Failed",
        )
        return

    _start_availability_monitor(
        media_server=media_server,
        library=library,
        import_event=import_event,
        media_type="movie",
    )


def _start_or_update_tv_queue_monitor(
    media_server,
    source,
    library,
    import_event,
):
    monitor_key = f"{source['id']}:{library['library_id']}"
    settings = _get_tv_queue_settings()

    with TV_QUEUE_LOCK:
        existing_monitor = TV_QUEUE_MONITORS.get(monitor_key)

        if existing_monitor:
            existing_monitor["latest_import_event"] = import_event
            existing_monitor["media_server"] = media_server
            existing_monitor["source"] = source
            existing_monitor["library"] = library
            existing_monitor["settings"] = settings

            add_activity_event(
                event_type="TV smart scan updated",
                status="active",
                source_id=source["id"],
                source_name=source["source_name"],
                source_type=source["source_type"],
                library_id=library["library_id"],
                library_name=library["library_name"],
                media_title=import_event.get("media_title"),
                file_name=import_event.get("file_name"),
                file_path=import_event.get("file_path"),
                details=(
                    "Additional TV import detected. Existing queue-aware "
                    "monitor remains active."
                ),
                lifecycle_id=import_event.get("lifecycle_id"),
                lifecycle_stage="Library Sync Updated",
            )
            return

        monitor = {
            "media_server": media_server,
            "source": source,
            "library": library,
            "latest_import_event": import_event,
            "settings": settings,
            "last_scan_at": None,
            "started_at": time.time(),
        }

        TV_QUEUE_MONITORS[monitor_key] = monitor

    add_activity_event(
        event_type="TV smart scan started",
        status="active",
        source_id=source["id"],
        source_name=source["source_name"],
        source_type=source["source_type"],
        library_id=library["library_id"],
        library_name=library["library_name"],
        media_title=import_event.get("media_title"),
        file_name=import_event.get("file_name"),
        file_path=import_event.get("file_path"),
        details=(
            "First TV import detected. Immediate scan executing, then "
            "Sonarr queue monitoring begins."
        ),
        lifecycle_id=import_event.get("lifecycle_id"),
        lifecycle_stage="Library Sync Started",
    )
    update_lifecycle_status(import_event.get("lifecycle_id"), "library_sync")

    _execute_tv_scan(
        media_server=media_server,
        source=source,
        library=library,
        import_event=import_event,
        reason="Immediate TV scan executing.",
        failure_event_type="TV library scan failed",
    )

    with TV_QUEUE_LOCK:
        active_monitor = TV_QUEUE_MONITORS.get(monitor_key)

        if active_monitor:
            active_monitor["last_scan_at"] = time.time()

    thread = threading.Thread(
        target=_monitor_sonarr_queue,
        args=(monitor_key,),
        daemon=True,
    )
    thread.start()


def _monitor_sonarr_queue(monitor_key):
    while True:
        with TV_QUEUE_LOCK:
            monitor = TV_QUEUE_MONITORS.get(monitor_key)

            if not monitor:
                return

            media_server = monitor["media_server"]
            source = monitor["source"]
            library = monitor["library"]
            import_event = monitor["latest_import_event"]
            settings = monitor["settings"]
            last_scan_at = monitor.get("last_scan_at")

        queue_poll_interval = settings["queue_poll_interval"]
        time.sleep(queue_poll_interval)

        with TV_QUEUE_LOCK:
            monitor = TV_QUEUE_MONITORS.get(monitor_key)

            if not monitor:
                return

            media_server = monitor["media_server"]
            source = monitor["source"]
            library = monitor["library"]
            import_event = monitor["latest_import_event"]
            settings = _get_tv_queue_settings()
            monitor["settings"] = settings
            last_scan_at = monitor.get("last_scan_at")

        queue_status = _get_sonarr_queue_status(source)

        if not queue_status.get("success"):
            add_activity_event(
                event_type="TV queue check failed",
                status="error",
                source_id=source["id"],
                source_name=source["source_name"],
                source_type=source["source_type"],
                library_id=library["library_id"],
                library_name=library["library_name"],
                media_title=import_event.get("media_title"),
                file_name=import_event.get("file_name"),
                file_path=import_event.get("file_path"),
                details=(
                    f"{queue_status.get('message', 'Sonarr queue check failed.')} "
                    "Queue monitor will keep retrying."
                ),
                lifecycle_id=import_event.get("lifecycle_id"),
                lifecycle_stage="Library Sync Queue Check Failed",
            )
            continue

        if queue_status.get("active"):
            now = time.time()
            queue_count = queue_status.get("count", 0)
            interim_scan_interval = settings["interim_scan_interval"]

            if last_scan_at is None or now - last_scan_at >= interim_scan_interval:
                add_activity_event(
                    event_type="TV interim scan started",
                    status="active",
                    source_id=source["id"],
                    source_name=source["source_name"],
                    source_type=source["source_type"],
                    library_id=library["library_id"],
                    library_name=library["library_name"],
                    media_title=import_event.get("media_title"),
                    file_name=import_event.get("file_name"),
                    file_path=import_event.get("file_path"),
                    details=(
                        f"Sonarr queue still active with {queue_count} item(s). "
                        f"Interim TV scan executing on {settings['interim_scan_minutes']} minute interval."
                    ),
                    lifecycle_id=import_event.get("lifecycle_id"),
                    lifecycle_stage="Library Sync Interim",
                )

                _execute_tv_scan(
                    media_server=media_server,
                    source=source,
                    library=library,
                    import_event=import_event,
                    reason="Interim TV scan executing while Sonarr queue remains active.",
                    failure_event_type="TV interim scan failed",
                )

                with TV_QUEUE_LOCK:
                    monitor = TV_QUEUE_MONITORS.get(monitor_key)

                    if monitor:
                        monitor["last_scan_at"] = time.time()

            continue

        if settings["final_scan_when_empty"]:
            add_activity_event(
                event_type="TV final scan started",
                status="active",
                source_id=source["id"],
                source_name=source["source_name"],
                source_type=source["source_type"],
                library_id=library["library_id"],
                library_name=library["library_name"],
                media_title=import_event.get("media_title"),
                file_name=import_event.get("file_name"),
                file_path=import_event.get("file_path"),
                details="Sonarr queue empty. Final authoritative TV scan executing.",
                lifecycle_id=import_event.get("lifecycle_id"),
                lifecycle_stage="Library Sync Final",
            )

            _execute_tv_scan(
                media_server=media_server,
                source=source,
                library=library,
                import_event=import_event,
                reason="Final authoritative TV scan executing after Sonarr queue emptied.",
                failure_event_type="TV final scan failed",
            )
        else:
            add_activity_event(
                event_type="TV final scan skipped",
                status="success",
                source_id=source["id"],
                source_name=source["source_name"],
                source_type=source["source_type"],
                library_id=library["library_id"],
                library_name=library["library_name"],
                media_title=import_event.get("media_title"),
                file_name=import_event.get("file_name"),
                file_path=import_event.get("file_path"),
                details="Sonarr queue empty. Final scan is disabled in settings.",
                lifecycle_id=import_event.get("lifecycle_id"),
                lifecycle_stage="Library Sync Skipped",
            )

        with TV_QUEUE_LOCK:
            TV_QUEUE_MONITORS.pop(monitor_key, None)

        return


def _get_sonarr_queue_status(source):
    server_url = source.get("source_url")
    api_key = source.get("api_key")

    if not server_url or not api_key:
        return {
            "success": False,
            "active": True,
            "count": 0,
            "message": "Sonarr source URL or API key is missing.",
        }

    sonarr = SonarrProvider(
        server_url=server_url,
        api_key=api_key,
    )

    return sonarr.get_queue_status()


def _execute_tv_scan(
    media_server,
    source,
    library,
    import_event,
    reason,
    failure_event_type,
):
    provider = _build_media_server_provider(media_server)

    if not provider:
        add_activity_event(
            event_type=failure_event_type,
            status="error",
            source_id=source["id"],
            source_name=source["source_name"],
            source_type=source["source_type"],
            library_id=library["library_id"],
            library_name=library["library_name"],
            media_title=import_event.get("media_title"),
            file_name=import_event.get("file_name"),
            file_path=import_event.get("file_path"),
            details="Unsupported media server type.",
            lifecycle_id=import_event.get("lifecycle_id"),
            lifecycle_stage=failure_event_type,
        )
        return

    result = provider.scan_library(
        library_id=library["library_id"],
        library_name=library["library_name"],
    )

    if not result.get("success"):
        add_activity_event(
            event_type=failure_event_type,
            status="error",
            source_id=source["id"],
            source_name=source["source_name"],
            source_type=source["source_type"],
            library_id=library["library_id"],
            library_name=library["library_name"],
            media_title=import_event.get("media_title"),
            file_name=import_event.get("file_name"),
            file_path=import_event.get("file_path"),
            details=result.get("message", "TV scan failed."),
            lifecycle_id=import_event.get("lifecycle_id"),
            lifecycle_stage=failure_event_type,
        )
        return

    # For TV, the configured media server is the source of truth. Do not mark
    # the scan complete here. Poll the media server and mark Smart Scan complete
    # at the same time the requested TV scope becomes available.
    _start_availability_monitor(
        media_server=media_server,
        library=library,
        import_event=import_event,
        media_type="tv",
    )


def _start_availability_monitor(media_server, library, import_event, media_type):
    lifecycle_id = import_event.get("lifecycle_id")
    title = import_event.get("media_title")

    if not lifecycle_id or not title:
        return

    monitor_key = f"{lifecycle_id}:{media_type}:{library.get('library_id') if library else ''}"

    with AVAILABILITY_LOCK:
        if monitor_key in AVAILABILITY_MONITORS:
            return

        AVAILABILITY_MONITORS.add(monitor_key)

    thread = threading.Thread(
        target=_monitor_media_availability,
        args=(monitor_key, media_server, library, dict(import_event), media_type),
        daemon=True,
    )
    thread.start()


def _monitor_media_availability(monitor_key, media_server, library, import_event, media_type):
    try:
        started_at = time.time()
        normalized_media_type = str(media_type or "").strip().lower()

        # Movie library scan requests return before Emby has finished processing.
        # Do not allow an immediate title/file match to complete the lifecycle.
        if normalized_media_type == "movie":
            time.sleep(max(AVAILABILITY_POLL_INTERVAL_SECONDS, 5))

        while time.time() - started_at <= AVAILABILITY_MAX_WAIT_SECONDS:
            if _media_item_is_available(
                media_server=media_server,
                library=library,
                import_event=import_event,
                media_type=media_type,
            ):
                _add_available_event(
                    media_server=media_server,
                    library=library,
                    import_event=import_event,
                    media_type=media_type,
                )
                return

            time.sleep(AVAILABILITY_POLL_INTERVAL_SECONDS)
    finally:
        with AVAILABILITY_LOCK:
            AVAILABILITY_MONITORS.discard(monitor_key)


def _media_item_is_available(media_server, library, import_event, media_type):
    server_type = str((media_server or {}).get("server_type") or "").strip().lower()

    if server_type in {"emby", "jellyfin"}:
        return _emby_family_item_is_available(
            media_server=media_server,
            library=library,
            import_event=import_event,
            media_type=media_type,
        )

    if server_type == "plex":
        return _plex_item_is_available(
            media_server=media_server,
            library=library,
            import_event=import_event,
            media_type=media_type,
        )

    return False


def _emby_family_item_is_available(media_server, library, import_event, media_type):
    server_url = str((media_server or {}).get("server_url") or "").rstrip("/")
    api_key = str((media_server or {}).get("api_key") or "")
    title = str(import_event.get("media_title") or "").strip()

    if not server_url or not api_key or not title:
        return False

    library_id = library.get("library_id") if library else None
    expected_file_name = _basename(import_event.get("file_name") or import_event.get("file_path"))

    if str(media_type or "").strip().lower() == "tv":
        scope = _tv_scope_from_import_event(import_event)

        return _emby_family_tv_scope_is_available(
            server_url=server_url,
            api_key=api_key,
            library_id=library_id,
            scope=scope,
            expected_file_name=expected_file_name,
        )

    params = {
        "Recursive": "true",
        "SearchTerm": title,
        "IncludeItemTypes": "Movie",
        "Limit": "20",
        "Fields": "Path,MediaSources",
    }

    if library_id:
        params["ParentId"] = library_id

    data = _emby_get_items(server_url=server_url, api_key=api_key, params=params)

    for item in data.get("Items", []):
        item_name = str(item.get("Name") or "").strip()

        if not _titles_match(item_name, title):
            continue

        if expected_file_name:
            for candidate_path in _candidate_item_paths(item):
                if _basename(candidate_path) == expected_file_name:
                    return True

            continue

        return True

    return False


def _tv_scope_from_import_event(import_event):
    raw = import_event.get("raw") or {}
    series = raw.get("series") or {}
    episodes = raw.get("episodes") or []
    first_episode = episodes[0] if episodes and isinstance(episodes[0], dict) else {}

    series_title = (
        series.get("title")
        or import_event.get("series_title")
        or _strip_episode_code(import_event.get("media_title"))
        or import_event.get("media_title")
        or ""
    )

    season_number = _safe_int_or_none(first_episode.get("seasonNumber"))
    episode_number = _safe_int_or_none(first_episode.get("episodeNumber"))

    if season_number is None or episode_number is None:
        season_number, episode_number = _season_episode_from_text(
            import_event.get("file_name")
            or import_event.get("file_path")
            or import_event.get("media_title")
        )

    return {
        "series_title": str(series_title or "").strip(),
        "season_number": season_number,
        "episode_number": episode_number,
    }


def _emby_family_tv_scope_is_available(server_url, api_key, library_id, scope, expected_file_name):
    series_title = str((scope or {}).get("series_title") or "").strip()
    season_number = (scope or {}).get("season_number")
    episode_number = (scope or {}).get("episode_number")

    if not series_title and expected_file_name:
        return _emby_family_tv_file_is_available(
            server_url=server_url,
            api_key=api_key,
            library_id=library_id,
            expected_file_name=expected_file_name,
        )

    if not series_title:
        return False

    series_items = _emby_find_series_items(
        server_url=server_url,
        api_key=api_key,
        library_id=library_id,
        series_title=series_title,
    )

    for series_item in series_items:
        series_id = series_item.get("Id") or series_item.get("id")
        if not series_id:
            continue

        episodes = _emby_get_series_episodes(
            server_url=server_url,
            api_key=api_key,
            series_id=series_id,
        )

        for item in episodes:
            if not isinstance(item, dict):
                continue

            if expected_file_name:
                for candidate_path in _candidate_item_paths(item):
                    if _basename(candidate_path) == expected_file_name:
                        return True

            if season_number is not None and episode_number is not None:
                try:
                    item_season = int(item.get("ParentIndexNumber"))
                    item_episode = int(item.get("IndexNumber"))
                except (TypeError, ValueError):
                    continue

                if item_season == season_number and item_episode == episode_number:
                    return True

        # If no episode scope exists, require at least one media-server episode.
        # This prevents a bare series shell from falsely completing the lifecycle.
        if season_number is None and episode_number is None and episodes:
            return True

    return False


def _emby_find_series_items(server_url, api_key, library_id, series_title):
    params = {
        "Recursive": "true",
        "SearchTerm": series_title,
        "IncludeItemTypes": "Series",
        "Limit": "20",
        "Fields": "ProviderIds",
    }

    if library_id:
        params["ParentId"] = library_id

    data = _emby_get_items(server_url=server_url, api_key=api_key, params=params)

    return [
        item for item in data.get("Items", [])
        if isinstance(item, dict) and _titles_match(item.get("Name"), series_title)
    ]


def _emby_get_series_episodes(server_url, api_key, series_id):
    try:
        response = requests.get(
            f"{server_url}/Shows/{series_id}/Episodes",
            headers={
                "X-Emby-Token": api_key,
                "Accept": "application/json",
            },
            params={
                "Fields": "Path,MediaSources,SeriesName,ParentIndexNumber,IndexNumber",
                "Limit": "10000",
            },
            timeout=10,
        )
        response.raise_for_status()
        data = response.json()
    except Exception:
        return []

    items = data.get("Items") if isinstance(data, dict) else []
    return items if isinstance(items, list) else []


def _emby_family_tv_file_is_available(server_url, api_key, library_id, expected_file_name):
    params = {
        "Recursive": "true",
        "IncludeItemTypes": "Episode",
        "Limit": "1000",
        "Fields": "Path,MediaSources",
    }

    if library_id:
        params["ParentId"] = library_id

    data = _emby_get_items(server_url=server_url, api_key=api_key, params=params)

    for item in data.get("Items", []):
        for candidate_path in _candidate_item_paths(item):
            if _basename(candidate_path) == expected_file_name:
                return True

    return False


def _emby_get_items(server_url, api_key, params):
    try:
        response = requests.get(
            f"{server_url}/Items",
            headers={
                "X-Emby-Token": api_key,
                "Accept": "application/json",
            },
            params=params,
            timeout=10,
        )
        response.raise_for_status()
        data = response.json()
    except Exception:
        return {"Items": []}

    if not isinstance(data, dict):
        return {"Items": []}

    items = data.get("Items")

    if not isinstance(items, list):
        data["Items"] = []

    return data


def _plex_item_is_available(media_server, library, import_event, media_type):
    server_url = str((media_server or {}).get("server_url") or "").rstrip("/")
    api_key = str((media_server or {}).get("api_key") or "")
    title = str(import_event.get("media_title") or "").strip()
    library_id = library.get("library_id") if library else None

    if not server_url or not api_key or not title or not library_id:
        return False

    try:
        response = requests.get(
            f"{server_url}/library/sections/{library_id}/all",
            params={
                "X-Plex-Token": api_key,
                "type": "2" if media_type == "movie" else "4",
                "title": title,
            },
            timeout=10,
        )
        response.raise_for_status()
        text = response.text.lower()
    except Exception:
        return False

    return _normalize_title(title) in _normalize_title(text)


def _safe_int_or_none(value):
    try:
        return int(value)
    except (TypeError, ValueError):
        return None


def _season_episode_from_text(value):
    match = re.search(r"[Ss](\d{1,2})[ ._-]*[Ee](\d{1,2})", str(value or ""))

    if not match:
        return None, None

    try:
        return int(match.group(1)), int(match.group(2))
    except (TypeError, ValueError):
        return None, None


def _strip_episode_code(value):
    text = str(value or "").strip()
    return re.sub(r"\s+[Ss]\d{1,2}[ ._-]*[Ee]\d{1,2}.*$", "", text).strip()


def _candidate_item_paths(item):
    paths = []

    if not isinstance(item, dict):
        return paths

    for key in ("Path", "PathName", "FileName"):
        value = item.get(key)

        if value:
            paths.append(str(value))

    for media_source in item.get("MediaSources") or []:
        if not isinstance(media_source, dict):
            continue

        for key in ("Path", "Name"):
            value = media_source.get(key)

            if value:
                paths.append(str(value))

    return paths


def _basename(value):
    if not value:
        return ""

    normalized = str(value).replace("\\", "/").rstrip("/").strip()

    if not normalized:
        return ""

    return normalized.split("/")[-1].lower()


def _titles_match(candidate, title):
    normalized_candidate = _normalize_title(candidate)
    normalized_title = _normalize_title(title)

    if not normalized_candidate or not normalized_title:
        return False

    return normalized_candidate == normalized_title or normalized_title in normalized_candidate


def _normalize_title(value):
    normalized = "".join(
        character.lower() if character.isalnum() else " "
        for character in str(value or "")
    )
    return " ".join(normalized.split())


def _add_available_event(media_server, library, import_event, media_type=None):
    server_type = str((media_server or {}).get("server_type") or "").strip().lower()
    server_label = _media_server_type_label(server_type)
    event_text = f"Available in {server_label}"

    normalized_media_type = str(media_type or "").strip().lower()

    if normalized_media_type in {"tv", "movie"}:
        add_activity_event(
            event_type="TV library scan completed" if normalized_media_type == "tv" else "Movie library scan completed",
            status="success",
            source_name=server_label,
            source_type=server_type or "media_server",
            library_id=library.get("library_id") if library else None,
            library_name=library.get("library_name") if library else None,
            media_title=import_event.get("media_title"),
            file_name=import_event.get("file_name"),
            file_path=import_event.get("file_path"),
            details="Media server availability confirmed.",
            lifecycle_id=import_event.get("lifecycle_id"),
            lifecycle_stage="Library Sync Completed",
        )

    add_activity_event(
        event_type=event_text,
        status="success",
        source_name=server_label,
        source_type=server_type or "media_server",
        library_id=library.get("library_id") if library else None,
        library_name=library.get("library_name") if library else None,
        media_title=import_event.get("media_title"),
        file_name=import_event.get("file_name"),
        file_path=import_event.get("file_path"),
        details="",
        lifecycle_id=import_event.get("lifecycle_id"),
        lifecycle_stage=event_text,
    )
    update_lifecycle_status(import_event.get("lifecycle_id"), "available")


def _media_server_type_label(server_type):
    labels = {
        "emby": "Emby",
        "jellyfin": "Jellyfin",
        "plex": "Plex",
    }

    return labels.get(server_type, "Media Server")
