import json

from fastapi import APIRouter, BackgroundTasks, Form, Request

from app.actions.scan_coordinator import request_scan
from app.database import (
    add_activity_event,
    delete_source,
    get_app_settings,
    get_media_server,
    get_source,
    get_sources,
    save_source,
)
from app.providers.media_servers.emby import EmbyProvider
from app.providers.sources.radarr import RadarrProvider
from app.providers.sources.sonarr import SonarrProvider

router = APIRouter(
    prefix="/api/source",
    tags=["source"],
)


@router.post("/test")
async def test_source(
    source_type: str = Form(...),
    source_url: str = Form(...),
    api_key: str = Form(...),
):
    normalized_type = source_type.lower()

    if normalized_type == "radarr":
        provider = RadarrProvider(
            server_url=source_url,
            api_key=api_key,
        )
    elif normalized_type == "sonarr":
        provider = SonarrProvider(
            server_url=source_url,
            api_key=api_key,
        )
    else:
        return {
            "success": False,
            "message": "Unsupported source type.",
        }

    result = provider.test_connection()

    if not result["success"]:
        return result

    result["compatible_libraries"] = get_compatible_libraries(normalized_type)

    return result


@router.post("/save")
async def save_source_config(
    background_tasks: BackgroundTasks,
    source_name: str = Form(...),
    source_type: str = Form(...),
    source_url: str = Form(...),
    api_key: str = Form(...),
    version: str = Form(...),
    libraries_json: str = Form(""),
    source_id: str = Form(""),
):
    libraries = _parse_libraries_json(libraries_json)

    if not libraries:
        return {
            "success": False,
            "message": "Select at least one library before saving.",
        }

    normalized_source_id = None

    if source_id.strip():
        try:
            normalized_source_id = int(source_id)
        except ValueError:
            return {
                "success": False,
                "message": "Source ID is invalid.",
            }

    saved_source_id = save_source(
        source_id=normalized_source_id,
        source_name=source_name,
        source_type=source_type,
        source_url=source_url,
        api_key=api_key,
        version=version,
        libraries=libraries,
    )

    source = get_source(saved_source_id)

    if source:
        background_tasks.add_task(_register_source_webhook, source)

    return {
        "success": True,
        "message": "Source saved successfully.",
        "source_id": saved_source_id,
    }


@router.post("/delete")
async def delete_source_config(
    source_id: int = Form(...),
):
    delete_source(source_id)

    return {
        "success": True,
        "message": "Source deleted successfully.",
    }


@router.post("/webhook/{source_id}")
async def source_webhook(source_id: int, request: Request):
    source = _get_source_with_libraries(source_id)

    if not source:
        return {
            "success": False,
            "message": "Source not found.",
        }

    media_server = get_media_server()

    if not media_server or not media_server.get("connected"):
        add_activity_event(
            event_type="Automatic scan failed",
            status="error",
            source_id=source["id"],
            source_name=source["source_name"],
            source_type=source["source_type"],
            details="No connected media server is configured.",
        )

        return {
            "success": False,
            "message": "No connected media server is configured.",
        }

    payload = await _read_json_payload(request)
    import_event = _parse_import_event(source["source_type"], payload)

    if not import_event.get("should_scan"):
        return {
            "success": True,
            "message": import_event.get("message", "Webhook ignored."),
            "scan_requested": False,
        }

    libraries = source.get("libraries", [])

    if not libraries:
        add_activity_event(
            event_type="Automatic scan failed",
            status="error",
            source_id=source["id"],
            source_name=source["source_name"],
            source_type=source["source_type"],
            media_title=import_event.get("media_title"),
            file_name=import_event.get("file_name"),
            file_path=import_event.get("file_path"),
            details="No media library is mapped to this source.",
        )

        return {
            "success": False,
            "message": "No media library is mapped to this source.",
            "scan_requested": False,
        }

    add_activity_event(
        event_type=f"{source['source_name']} import detected",
        status="success",
        source_id=source["id"],
        source_name=source["source_name"],
        source_type=source["source_type"],
        media_title=import_event.get("media_title"),
        file_name=import_event.get("file_name"),
        file_path=import_event.get("file_path"),
        details=import_event.get("message", "Import event received."),
    )

    for library in libraries:
        request_scan(
            media_server=media_server,
            source=source,
            library=library,
            import_event=import_event,
        )

    return {
        "success": True,
        "message": "Scan coordinator notified.",
        "scan_requested": True,
        "source_id": source["id"],
        "source_name": source["source_name"],
        "source_type": source["source_type"],
        "media_title": import_event.get("media_title"),
    }


def _parse_libraries_json(libraries_json: str) -> list[dict]:
    if not libraries_json:
        return []

    try:
        raw_libraries = json.loads(libraries_json)
    except json.JSONDecodeError:
        return []

    libraries = []

    for library in raw_libraries:
        library_id = str(library.get("id", "")).strip()
        library_name = str(library.get("name", "")).strip()

        if not library_id or not library_name:
            continue

        libraries.append(
            {
                "id": library_id,
                "name": library_name,
                "type": str(library.get("type", "unknown")).strip() or "unknown",
                "image_url": library.get("image_url"),
            }
        )

    return libraries


def get_compatible_libraries(source_type: str) -> list[dict]:
    media_server = get_media_server()

    if not media_server or not media_server["connected"]:
        return []

    emby = EmbyProvider(
        server_url=media_server["server_url"],
        api_key=media_server["api_key"],
    )

    libraries = emby.get_libraries()

    if source_type == "radarr":
        return [
            library
            for library in libraries
            if library["type"] == "movies"
        ]

    if source_type == "sonarr":
        return [
            library
            for library in libraries
            if library["type"] == "tvshows"
        ]

    return []


async def _read_json_payload(request: Request) -> dict:
    try:
        return await request.json()
    except Exception:
        return {}


def _parse_import_event(source_type: str, payload: dict) -> dict:
    normalized_type = source_type.lower()

    if normalized_type == "radarr":
        return RadarrProvider.parse_webhook_payload(payload)

    if normalized_type == "sonarr":
        return SonarrProvider.parse_webhook_payload(payload)

    return {
        "should_scan": False,
        "event_type": "unsupported",
        "message": "Unsupported source type.",
    }


def _register_source_webhook(source: dict | None) -> dict:
    if not source:
        return {
            "attempted": False,
            "success": False,
            "message": "Source not found after save.",
        }

    settings = get_app_settings()
    mediasync_url = str(settings.get("mediasync_url", "")).strip().rstrip("/")

    if not mediasync_url:
        return {
            "attempted": False,
            "success": False,
            "message": "MediaSync URL is not configured.",
        }

    webhook_url = f"{mediasync_url}/api/source/webhook/{source['id']}"
    source_type = source["source_type"].lower()

    if source_type == "radarr":
        provider = RadarrProvider(
            server_url=source["source_url"],
            api_key=source["api_key"],
        )
    elif source_type == "sonarr":
        provider = SonarrProvider(
            server_url=source["source_url"],
            api_key=source["api_key"],
        )
    else:
        return {
            "attempted": False,
            "success": False,
            "message": "Unsupported source type.",
        }

    try:
        return provider.register_mediasync_webhook(webhook_url=webhook_url)
    except Exception as error:
        return {
            "attempted": True,
            "success": False,
            "message": f"Webhook registration failed: {error}",
        }


def _get_source_with_libraries(source_id: int) -> dict | None:
    base_source = get_source(source_id)

    if not base_source:
        return None

    for source in get_sources():
        if int(source["id"]) == int(source_id):
            return source

    base_source["libraries"] = []
    return base_source
