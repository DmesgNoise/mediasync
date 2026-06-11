import re
import threading
import time
from typing import Any

from app.database import add_activity_event, get_downloaders, update_lifecycle_status
from app.providers.downloaders.base import build_downloader_provider

ACTIVE_WATCHERS: dict[str, dict[str, Any]] = {}
WATCHER_LOCK = threading.Lock()

POLL_INTERVAL_SECONDS = 1
START_GRACE_SECONDS = 60
HISTORY_RESOLVE_GRACE_SECONDS = 3
MAX_WATCH_SECONDS = 60 * 60 * 6

FAILED_STATES = {"failed", "failure", "error"}
ACTIVE_STATES = {
    "downloading",
    "queued",
    "fetching",
    "grabbing",
    "paused",
    "propagating",
    "checking",
    "repairing",
    "verifying",
    "extracting",
    "unpacking",
    "moving",
}
CANCELLED_STATES = {"cancelled", "canceled", "deleted", "removed", "aborted"}


def _downloader_auth_value(downloader: dict[str, Any] | None) -> str:
    if not downloader:
        return ""

    api_key = str(downloader.get("api_key") or "").strip()

    if api_key:
        return api_key

    username = str(downloader.get("username") or "").strip()
    password = str(downloader.get("password") or "").strip()

    if username or password:
        return f"{username}:{password}"

    return ""


def start_downloader_watcher(source: dict[str, Any], import_event: dict[str, Any]) -> None:
    media_title = str(import_event.get("media_title") or "Unknown media").strip()
    watcher_key = f"{source.get('id')}:{media_title.lower()}"

    with WATCHER_LOCK:
        existing = ACTIVE_WATCHERS.get(watcher_key)

        if existing:
            existing["source"] = source
            existing["import_event"] = import_event
            existing["last_seen_at"] = time.time()
            return

        ACTIVE_WATCHERS[watcher_key] = {
            "source": source,
            "import_event": import_event,
            "started_at": time.time(),
            "last_seen_at": time.time(),
            "download_started": False,
            "seen_active": False,
            "queue_disappeared_at": None,
            "seen_download_ids": set(),
            "seen_download_names": set(),
        }

    thread = threading.Thread(
        target=_watch_downloaders,
        args=(watcher_key,),
        daemon=True,
    )
    thread.start()


def _watch_downloaders(watcher_key: str) -> None:
    while True:
        with WATCHER_LOCK:
            watcher = ACTIVE_WATCHERS.get(watcher_key)

            if not watcher:
                return

            source = watcher["source"]
            import_event = watcher["import_event"]
            started_at = watcher["started_at"]
            seen_active = watcher["seen_active"]
            download_started = watcher["download_started"]
            queue_disappeared_at = watcher.get("queue_disappeared_at")
            seen_download_ids = set(watcher.get("seen_download_ids") or set())
            seen_download_names = set(watcher.get("seen_download_names") or set())

        elapsed = time.time() - started_at

        if elapsed > MAX_WATCH_SECONDS:
            _stop_watcher(watcher_key)
            return

        queue_state = _get_combined_downloader_state(import_event, seen_download_ids, seen_download_names)

        if not queue_state.get("success"):
            time.sleep(POLL_INTERVAL_SECONDS)
            continue

        failed_downloads = queue_state.get("failed_downloads", [])
        cancelled_downloads = queue_state.get("cancelled_downloads", [])
        matched_active_downloads = queue_state.get("matched_active_downloads", [])
        downloader_name = queue_state.get("downloader_name") or "Downloader"

        if failed_downloads:
            _record_download_failed(
                source=source,
                import_event=import_event,
                downloader_name=downloader_name,
                details=_download_details(failed_downloads[0], queue_state),
            )
            _stop_watcher(watcher_key)
            return

        # Do not treat downloader queue cancelled/deleted/removed states as terminal.
        # SAB can briefly expose transitional queue states during repair, unpack,
        # cleanup, retry, or handoff to history. Final download state must come
        # from downloader history only.
        if matched_active_downloads:
            active_item = matched_active_downloads[0]
            downloader_name = active_item.get("_downloader_name") or downloader_name

            with WATCHER_LOCK:
                watcher = ACTIVE_WATCHERS.get(watcher_key)

                if watcher:
                    watcher["seen_active"] = True
                    watcher["last_seen_at"] = time.time()
                    watcher["queue_disappeared_at"] = None

                    if active_item.get("id"):
                        watcher["seen_download_ids"].add(str(active_item.get("id")))

                    if active_item.get("name"):
                        watcher["seen_download_names"].add(_normalize_text(active_item.get("name")))

                    if active_item.get("filename"):
                        watcher["seen_download_names"].add(_normalize_text(active_item.get("filename")))

            if not download_started:
                _record_download_started(
                    source=source,
                    import_event=import_event,
                    downloader_name=downloader_name,
                    details=_download_details(active_item, queue_state),
                )

                with WATCHER_LOCK:
                    watcher = ACTIVE_WATCHERS.get(watcher_key)

                    if watcher:
                        watcher["download_started"] = True

            time.sleep(POLL_INTERVAL_SECONDS)
            continue

        if seen_active:
            now = time.time()

            if queue_disappeared_at is None:
                with WATCHER_LOCK:
                    watcher = ACTIVE_WATCHERS.get(watcher_key)

                    if watcher:
                        watcher["queue_disappeared_at"] = now

            history_result = _resolve_from_downloader_history(import_event, seen_download_ids, seen_download_names)

            if history_result.get("resolved"):
                final_state = history_result.get("final_state")
                history_item = history_result.get("item") or {}
                downloader_name = history_result.get("downloader_name") or downloader_name
                details = _history_details(history_item)

                if final_state == "completed":
                    _record_download_completed(source, import_event, downloader_name, details)
                    _stop_watcher(watcher_key)
                    return

                if final_state == "cancelled":
                    _record_download_cancelled(source, import_event, downloader_name, details)
                    _stop_watcher(watcher_key)
                    return

                if final_state == "failed":
                    _record_download_failed(source, import_event, downloader_name, details)
                    _stop_watcher(watcher_key)
                    return

            # Important: do not infer cancellation only because the item disappeared
            # from the queue. SAB can temporarily remove queue records while repairing,
            # verifying, unpacking, or moving files. Keep watching history instead and
            # only record cancelled if SAB explicitly reports a cancelled/deleted state.
            time.sleep(POLL_INTERVAL_SECONDS)
            continue

        if elapsed > START_GRACE_SECONDS:
            _stop_watcher(watcher_key)
            return

        time.sleep(POLL_INTERVAL_SECONDS)


def _get_combined_downloader_state(
    import_event: dict[str, Any],
    seen_download_ids: set[str],
    seen_download_names: set[str],
) -> dict[str, Any]:
    active_downloads = []
    failed_downloads = []
    cancelled_downloads = []
    matched_active_downloads = []
    first_downloader_name = ""
    first_speed = ""
    first_timeleft = ""
    first_size = ""

    try:
        downloaders = get_downloaders()
    except Exception as error:
        return {
            "success": False,
            "message": f"Downloader list unavailable: {error}",
        }

    for downloader in downloaders:
        if not downloader.get("connected"):
            continue

        provider = build_downloader_provider(
            downloader_type=downloader.get("downloader_type"),
            server_url=downloader.get("downloader_url"),
            api_key=_downloader_auth_value(downloader),
        )

        if not provider:
            continue

        result = provider.get_queue()

        if not result.get("success"):
            continue

        if not first_downloader_name:
            first_downloader_name = downloader.get("downloader_name") or "Downloader"
            first_speed = result.get("speed") or ""
            first_timeleft = result.get("timeleft") or ""
            first_size = result.get("size") or ""

        for item in result.get("downloads") or []:
            status = str(item.get("status") or "").strip().lower()

            if status in FAILED_STATES:
                if _download_matches_import(item, import_event, seen_download_ids, seen_download_names):
                    failed_downloads.append(item)
                continue

            if status in CANCELLED_STATES:
                if _download_matches_import(item, import_event, seen_download_ids, seen_download_names):
                    cancelled_downloads.append(item)
                continue

            if status in ACTIVE_STATES or result.get("active_count", 0) > 0:
                active_downloads.append(item)

                if _download_matches_import(item, import_event, seen_download_ids, seen_download_names):
                    matched_item = dict(item)
                    matched_item["_downloader_name"] = downloader.get("downloader_name") or "Downloader"
                    matched_item["_downloader_type"] = downloader.get("downloader_type") or "downloader"
                    matched_active_downloads.append(matched_item)

                    if not matched_downloader_name:
                        matched_downloader_name = downloader.get("downloader_name") or "Downloader"
                        matched_speed = result.get("speed") or ""
                        matched_timeleft = result.get("timeleft") or ""
                        matched_size = result.get("size") or ""

    if not matched_active_downloads and len(active_downloads) == 1 and not seen_download_ids and not seen_download_names:
        matched_active_downloads = active_downloads[:]

        first_match = matched_active_downloads[0] if matched_active_downloads else {}
        matched_downloader_name = first_match.get("_downloader_name") or first_downloader_name
        matched_speed = matched_speed or first_speed
        matched_timeleft = matched_timeleft or first_timeleft
        matched_size = matched_size or first_size

    return {
        "success": True,
        "downloader_name": matched_downloader_name or first_downloader_name,
        "speed": matched_speed or first_speed,
        "timeleft": matched_timeleft or first_timeleft,
        "size": matched_size or first_size,
        "active_downloads": active_downloads,
        "failed_downloads": failed_downloads,
        "cancelled_downloads": cancelled_downloads,
        "matched_active_downloads": matched_active_downloads,
    }


def _resolve_from_downloader_history(
    import_event: dict[str, Any],
    seen_download_ids: set[str],
    seen_download_names: set[str],
) -> dict[str, Any]:
    try:
        downloaders = get_downloaders()
    except Exception:
        return {"resolved": False}

    for downloader in downloaders:
        if not downloader.get("connected"):
            continue

        provider = build_downloader_provider(
            downloader_type=downloader.get("downloader_type"),
            server_url=downloader.get("downloader_url"),
            api_key=_downloader_auth_value(downloader),
        )

        if not provider or not hasattr(provider, "get_history"):
            continue

        result = provider.get_history(limit=80)

        if not result.get("success"):
            continue

        for item in result.get("history") or []:
            if not _download_matches_import(item, import_event, seen_download_ids, seen_download_names):
                continue

            final_state = str(item.get("final_state") or "unknown").strip().lower()

            if final_state in {"completed", "failed", "cancelled"}:
                return {
                    "resolved": True,
                    "final_state": final_state,
                    "item": item,
                    "downloader_name": downloader.get("downloader_name") or "Downloader",
                }

    return {"resolved": False}


def _download_matches_import(
    item: dict[str, Any],
    import_event: dict[str, Any],
    seen_download_ids: set[str],
    seen_download_names: set[str],
) -> bool:
    item_id = str(item.get("id") or "").strip()

    if item_id and item_id in seen_download_ids:
        return True

    item_names = {
        _normalize_text(item.get("name")),
        _normalize_text(item.get("filename")),
    }
    item_names = {name for name in item_names if name}

    if item_names.intersection(seen_download_names):
        return True

    title = _normalize_text(import_event.get("media_title"))

    if not title:
        return False

    for item_name in item_names:
        if title in item_name or item_name in title:
            return True

    return False


def _record_download_started(source: dict[str, Any], import_event: dict[str, Any], downloader_name: str, details: str) -> None:
    title = import_event.get("media_title") or "Unknown media"
    sentence = f"Download started for {title}"

    add_activity_event(
        event_type=sentence,
        status="active",
        source_id=source.get("id"),
        source_name=downloader_name,
        source_type="downloader",
        media_title=title,
        file_name=import_event.get("file_name"),
        file_path=import_event.get("file_path"),
        details="",
        lifecycle_id=import_event.get("lifecycle_id"),
        lifecycle_stage="Download Started",
    )
    update_lifecycle_status(import_event.get("lifecycle_id"), "downloading")


def _record_download_completed(source: dict[str, Any], import_event: dict[str, Any], downloader_name: str, details: str) -> None:
    title = import_event.get("media_title") or "Unknown media"
    sentence = f"Download completed for {title}"

    add_activity_event(
        event_type=sentence,
        status="success",
        source_id=source.get("id"),
        source_name=downloader_name,
        source_type="downloader",
        media_title=title,
        file_name=import_event.get("file_name"),
        file_path=import_event.get("file_path"),
        details="",
        lifecycle_id=import_event.get("lifecycle_id"),
        lifecycle_stage="Download Completed",
    )
    update_lifecycle_status(import_event.get("lifecycle_id"), "download_completed")


def _record_download_cancelled(source: dict[str, Any], import_event: dict[str, Any], downloader_name: str, details: str) -> None:
    title = import_event.get("media_title") or "Unknown media"
    sentence = f"Download cancelled for {title}"

    add_activity_event(
        event_type=sentence,
        status="error",
        source_id=source.get("id"),
        source_name=downloader_name,
        source_type="downloader",
        media_title=title,
        file_name=import_event.get("file_name"),
        file_path=import_event.get("file_path"),
        details="",
        lifecycle_id=import_event.get("lifecycle_id"),
        lifecycle_stage="Download Cancelled",
    )
    update_lifecycle_status(import_event.get("lifecycle_id"), "download_cancelled")


def _record_download_failed(source: dict[str, Any], import_event: dict[str, Any], downloader_name: str, details: str) -> None:
    title = import_event.get("media_title") or "Unknown media"
    sentence = f"Download failed for {title}"

    add_activity_event(
        event_type=sentence,
        status="error",
        source_id=source.get("id"),
        source_name=downloader_name,
        source_type="downloader",
        media_title=title,
        file_name=import_event.get("file_name"),
        file_path=import_event.get("file_path"),
        details="",
        lifecycle_id=import_event.get("lifecycle_id"),
        lifecycle_stage="Download Failed",
    )
    update_lifecycle_status(import_event.get("lifecycle_id"), "download_failed")


def _download_details(download: dict[str, Any], queue_state: dict[str, Any]) -> str:
    parts = []

    if download.get("percent") not in (None, ""):
        parts.append(f"{download.get('percent')}%")

    if download.get("size"):
        parts.append(str(download.get("size")))
    elif queue_state.get("size"):
        parts.append(str(queue_state.get("size")))

    if queue_state.get("speed") and queue_state.get("speed") != "0 B/s":
        parts.append(str(queue_state.get("speed")))

    if download.get("eta"):
        parts.append(f"{download.get('eta')} remaining")
    elif queue_state.get("timeleft"):
        parts.append(f"{queue_state.get('timeleft')} remaining")

    return " â¢ ".join(parts)


def _history_details(item: dict[str, Any]) -> str:
    parts = []

    if item.get("status"):
        parts.append(f"SAB history status: {item.get('status')}")

    if item.get("fail_message"):
        parts.append(str(item.get("fail_message")))

    if item.get("size"):
        parts.append(str(item.get("size")))

    return " â¢ ".join(parts)


def _normalize_text(value: Any) -> str:
    text = str(value or "").lower()
    text = re.sub(r"[^a-z0-9]+", " ", text)
    return re.sub(r"\s+", " ", text).strip()


def _stop_watcher(watcher_key: str) -> None:
    with WATCHER_LOCK:
        ACTIVE_WATCHERS.pop(watcher_key, None)
