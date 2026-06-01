from fastapi import APIRouter, BackgroundTasks, Form

from app.database import (
    add_activity_event,
    clear_activity_events,
    delete_source,
    get_app_settings,
    get_media_server,
    get_source,
    get_sources,
    reorder_sources,
    reset_configuration,
    save_app_settings,
    update_media_server_config,
    update_source_config,
)
from app.providers.media_servers.emby import EmbyProvider
from app.providers.sources.radarr import RadarrProvider
from app.providers.sources.sonarr import SonarrProvider

router = APIRouter(prefix="/api/settings", tags=["settings"])


@router.post("/media-server/save")
async def save_media_server_settings(
    server_url: str = Form(...),
    api_key: str = Form(...),
    timezone: str = Form(...),
):
    updated = update_media_server_config(
        server_url=server_url,
        api_key=api_key,
        timezone=timezone,
    )

    if not updated:
        return {"success": False, "message": "No media server is configured."}

    save_app_settings({"timezone": timezone})

    return {"success": True, "message": "Media server settings saved."}


@router.post("/media-server/test")
async def test_media_server_settings(
    server_url: str = Form(...),
    api_key: str = Form(...),
):
    provider = EmbyProvider(server_url=server_url, api_key=api_key)
    result = provider.test_connection()

    add_activity_event(
        event_type=(
            "Media server connection test"
            if result.get("success")
            else "Media server connection test failed"
        ),
        status=("success" if result.get("success") else "error"),
        source_name="MediaSync",
        details=result.get("message"),
    )

    return result


@router.post("/source/save")
async def save_source_settings(
    background_tasks: BackgroundTasks,
    source_id: int = Form(...),
    source_name: str = Form(...),
    source_url: str = Form(...),
    api_key: str = Form(...),
):
    source = get_source(source_id)

    if not source:
        return {
            "success": False,
            "message": "Source not found.",
        }

    update_source_config(
        source_id=source_id,
        source_name=source_name,
        source_url=source_url,
        api_key=api_key,
    )

    updated_source = get_source(source_id)

    if updated_source:
        background_tasks.add_task(_register_source_webhook, updated_source)

    return {
        "success": True,
        "message": "Source settings saved.",
    }


@router.post("/source/test")
async def test_source_settings(
    source_id: int = Form(...),
    source_url: str = Form(...),
    api_key: str = Form(...),
):
    source = get_source(source_id)

    if not source:
        return {"success": False, "message": "Source not found."}

    provider = _build_source_provider(
        source_type=source["source_type"],
        source_url=source_url,
        api_key=api_key,
    )

    if not provider:
        return {"success": False, "message": "Unsupported source type."}

    result = provider.test_connection()

    add_activity_event(
        event_type=(
            "Source connection test"
            if result.get("success")
            else "Source connection test failed"
        ),
        status=("success" if result.get("success") else "error"),
        source_id=source["id"],
        source_name=source["source_name"],
        source_type=source["source_type"],
        details=result.get("message"),
    )

    return result


@router.post("/source/delete")
async def delete_source_settings(source_id: int = Form(...)):
    source = get_source(source_id)

    delete_source(source_id)

    if source:
        add_activity_event(
            event_type="Source deleted",
            status="info",
            source_id=source["id"],
            source_name=source["source_name"],
            source_type=source["source_type"],
            details="Source connection and library mapping removed.",
        )

    return {"success": True, "message": "Source deleted."}


@router.post("/sources/reorder")
async def reorder_source_settings(source_ids: str = Form(...)):
    ids = []

    for item in source_ids.split(","):
        item = item.strip()

        if not item:
            continue

        try:
            ids.append(int(item))
        except ValueError:
            return {"success": False, "message": "Invalid source order."}

    reorder_sources(ids)

    return {"success": True, "message": "Source order saved."}


@router.post("/sources/test-all")
async def test_all_sources():
    sources = get_sources()
    results = []

    for source in sources:
        provider = _build_source_provider(
            source_type=source["source_type"],
            source_url=source["source_url"],
            api_key=source["api_key"],
        )

        if provider:
            result = provider.test_connection()
        else:
            result = {"success": False, "message": "Unsupported source type."}

        results.append(
            {
                "source_id": source["id"],
                "source_name": source["source_name"],
                "success": result.get("success", False),
                "message": result.get("message", ""),
            }
        )

        add_activity_event(
            event_type=(
                "Source connection test"
                if result.get("success")
                else "Source connection test failed"
            ),
            status=("success" if result.get("success") else "error"),
            source_id=source["id"],
            source_name=source["source_name"],
            source_type=source["source_type"],
            details=result.get("message"),
        )

    success_count = len([result for result in results if result["success"]])

    return {
        "success": success_count == len(results),
        "message": f"{success_count}/{len(results)} sources connected.",
        "results": results,
    }


@router.post("/activity/clear")
async def clear_activity():
    clear_activity_events()

    return {"success": True, "message": "Activity log cleared."}


@router.post("/activity/settings")
async def save_activity_settings(
    activity_display_limit: str = Form(...),
    activity_retention_limit: str = Form(...),
    activity_file_detail: str = Form(...),
):
    if activity_file_detail not in ["filename", "path"]:
        activity_file_detail = "filename"

    save_app_settings(
        {
            "activity_display_limit": activity_display_limit,
            "activity_retention_limit": activity_retention_limit,
            "activity_file_detail": activity_file_detail,
        }
    )

    return {"success": True, "message": "Activity settings saved."}


@router.post("/app/save")
async def save_app_behavior_settings(
    mediasync_url: str = Form(""),
):
    normalized_url = mediasync_url.strip().rstrip("/")

    save_app_settings(
        {
            "mediasync_url": normalized_url,
        }
    )

    add_activity_event(
        event_type="MediaSync URL saved",
        status="success",
        source_name="MediaSync",
        details=(
            f"Webhook base URL set to {normalized_url}."
            if normalized_url
            else "Webhook base URL cleared."
        ),
    )

    return {
        "success": True,
        "message": "MediaSync URL saved.",
    }


@router.post("/tv-sync/save")
async def save_tv_sync_settings(
    tv_poll_interval_seconds: str = Form(...),
    tv_interim_scan_minutes: str = Form(...),
    tv_final_scan_enabled: str = Form(...),
):
    save_app_settings(
        {
            "tv_poll_interval_seconds": tv_poll_interval_seconds,
            "tv_interim_scan_minutes": tv_interim_scan_minutes,
            "tv_final_scan_enabled": tv_final_scan_enabled,
        }
    )

    return {"success": True, "message": "TV sync settings saved."}


@router.post("/manual-scan")
async def manual_library_scan(
    source_id: int = Form(...),
    library_id: str = Form(...),
    library_name: str = Form(...),
):
    source = get_source(source_id)
    media_server = get_media_server()

    if not media_server:
        return {
            "success": False,
            "message": "No media server configured.",
        }

    provider = EmbyProvider(
        server_url=media_server["server_url"],
        api_key=media_server["api_key"],
    )

    scan_requested_at = provider.utc_now_iso()

    result = provider.scan_library(
        library_id=library_id,
        library_name=library_name,
    )

    if result.get("success"):
        result["scan_requested_at"] = scan_requested_at

    add_activity_event(
        event_type=(
            "Manual library scan started"
            if result.get("success")
            else "Manual library scan failed"
        ),
        status=("active" if result.get("success") else "error"),
        source_id=source["id"] if source else None,
        source_name=source["source_name"] if source else "MediaSync",
        source_type=source["source_type"] if source else None,
        library_id=library_id,
        library_name=library_name,
        details=result.get("message"),
    )

    return result


@router.post("/manual-scan/status")
async def manual_library_scan_status(
    source_id: int = Form(...),
    library_id: str = Form(...),
    library_name: str = Form(...),
    scan_requested_at: str = Form(""),
):
    media_server = get_media_server()

    if not media_server:
        return {
            "success": False,
            "message": "No media server configured.",
            "running": False,
            "progress": 0,
        }

    provider = EmbyProvider(
        server_url=media_server["server_url"],
        api_key=media_server["api_key"],
    )

    return provider.get_library_scan_status(
        library_id=library_id,
        library_name=library_name,
        scan_requested_at=scan_requested_at,
    )


@router.post("/reset")
async def reset_settings():
    reset_configuration()

    return {"success": True, "message": "MediaSync configuration reset."}



def _register_source_webhook(source):
    if not source:
        return {
            "attempted": False,
            "success": False,
            "message": "Source not found.",
        }

    app_settings = get_app_settings()
    mediasync_url = str(app_settings.get("mediasync_url", "")).strip().rstrip("/")

    if not mediasync_url:
        return {
            "attempted": False,
            "success": False,
            "message": "MediaSync URL is not configured.",
        }

    webhook_url = f"{mediasync_url}/api/source/webhook/{source['id']}"
    provider = _build_source_provider(
        source_type=source["source_type"],
        source_url=source["source_url"],
        api_key=source["api_key"],
    )

    if not provider:
        return {
            "attempted": False,
            "success": False,
            "message": "Unsupported source type.",
        }

    if not hasattr(provider, "register_mediasync_webhook"):
        return {
            "attempted": False,
            "success": False,
            "message": "Provider does not support webhook registration.",
        }

    try:
        return provider.register_mediasync_webhook(webhook_url=webhook_url)
    except Exception as error:
        return {
            "attempted": True,
            "success": False,
            "message": f"Webhook registration failed: {error}",
        }

def _build_source_provider(source_type, source_url, api_key):
    normalized_type = source_type.lower()

    if normalized_type == "radarr":
        return RadarrProvider(server_url=source_url, api_key=api_key)

    if normalized_type == "sonarr":
        return SonarrProvider(server_url=source_url, api_key=api_key)

    return None
