from app.providers.media_servers.emby import EmbyProvider
from app.providers.media_servers.jellyfin import JellyfinProvider
from app.providers.media_servers.plex import PlexProvider


SUPPORTED_MEDIA_SERVER_TYPES = {
    "emby",
    "jellyfin",
    "plex",
}


def get_supported_media_server_types() -> set[str]:
    return SUPPORTED_MEDIA_SERVER_TYPES.copy()


def build_media_server_provider(server_type: str | None, server_url: str, api_key: str):
    normalized_type = str(server_type or "").strip().lower()

    if normalized_type == "emby":
        return EmbyProvider(server_url=server_url, api_key=api_key)

    if normalized_type == "jellyfin":
        return JellyfinProvider(server_url=server_url, api_key=api_key)

    if normalized_type == "plex":
        return PlexProvider(server_url=server_url, api_key=api_key)

    return None
