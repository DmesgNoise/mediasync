from fastapi import APIRouter, Form

from app.database import save_app_settings, save_media_server
from app.providers.media_servers.emby import EmbyProvider

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

    if not normalized_mediasync_url:
        return {
            "success": False,
            "message": "MediaSync URL is required so Radarr and Sonarr can send import webhooks.",
        }

    if server_type.lower() != "emby":
        return {
            "success": False,
            "message": "Only Emby is supported in this version.",
        }

    provider = EmbyProvider(
        server_url=server_url,
        api_key=api_key,
    )

    result = provider.test_connection()

    if not result["success"]:
        return result

    libraries = provider.get_libraries()

    save_media_server(
        server_type=server_type,
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

    return result
