import threading
import time

from app.database import add_activity_event, get_app_settings
from app.providers.media_servers.emby import EmbyProvider
from app.providers.sources.sonarr import SonarrProvider

TV_QUEUE_MONITORS = {}
TV_QUEUE_LOCK = threading.Lock()

DEFAULT_QUEUE_POLL_INTERVAL_SECONDS = 60
DEFAULT_INTERIM_SCAN_MINUTES = 10
DEFAULT_FINAL_SCAN_WHEN_QUEUE_EMPTY = True


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
    emby = EmbyProvider(
        server_url=media_server["server_url"],
        api_key=media_server["api_key"],
    )

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
        details="Immediate movie scan executing.",
    )

    result = emby.scan_library(
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
    )

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
    emby = EmbyProvider(
        server_url=media_server["server_url"],
        api_key=media_server["api_key"],
    )

    result = emby.scan_library(
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
        )
        return

    add_activity_event(
        event_type="TV library scan completed",
        status="success",
        source_id=source["id"],
        source_name=source["source_name"],
        source_type=source["source_type"],
        library_id=library["library_id"],
        library_name=library["library_name"],
        media_title=import_event.get("media_title"),
        file_name=import_event.get("file_name"),
        file_path=import_event.get("file_path"),
        details=reason,
    )
