from fastapi import APIRouter, Form

from app.database import save_app_settings, save_media_server
from app.providers.media_servers.base import (
    build_media_server_provider,
    get_supported_media_server_types,
)

router = APIRouter(
    prefix="/api/server",
    tags=["server"],
)


@router.post("/test")
async def test_media_server(
    server_type: str = Form(...),
    server_url: str = Form(...),
    api_key: str = Form(...),
    timezone: str = Form(...),
    mediasync_url: str = Form(""),
):
    normalized_mediasync_url = mediasync_url.strip().rstrip("/")
    normalized_server_type = server_type.strip().lower()

    if not normalized_mediasync_url:
        return {
            "success": False,
            "message": "MediaSync URL is required so Radarr and Sonarr can send import webhooks.",
        }

    if normalized_server_type not in get_supported_media_server_types():
        return {
            "success": False,
            "message": "Unsupported media server type.",
        }

    provider = build_media_server_provider(
        server_type=normalized_server_type,
        server_url=server_url,
        api_key=api_key,
    )

    if not provider:
        return {
            "success": False,
            "message": "Unsupported media server type.",
        }

    result = provider.test_connection()

    if not result["success"]:
        return result

    libraries = provider.get_libraries()

    save_media_server(
        server_type=normalized_server_type,
        server_url=server_url,
        api_key=api_key,
        timezone=timezone,
        connected=1,
        server_name=result["server_name"],
        version=result["version"],
    )

    save_app_settings(
        {
            "mediasync_url": normalized_mediasync_url,
        }
    )

    result["libraries"] = libraries
    result["library_count"] = len(libraries)
    result["server_type"] = normalized_server_type

    return result
