from typing import Any


SUPPORTED_DOWNLOADER_TYPES = {
    "sabnzbd": "SABnzbd",
}


class BaseDownloaderProvider:
    def __init__(self, server_url: str, api_key: str):
        self.server_url = str(server_url or "").strip().rstrip("/")
        self.api_key = str(api_key or "").strip()

    def test_connection(self) -> dict[str, Any]:
        raise NotImplementedError

    def get_status(self) -> dict[str, Any]:
        raise NotImplementedError

    def get_queue(self) -> dict[str, Any]:
        raise NotImplementedError

    def normalize_download_item(self, item: dict[str, Any], queue: dict[str, Any] | None = None) -> dict[str, Any]:
        raise NotImplementedError


def get_supported_downloader_types() -> dict[str, str]:
    return SUPPORTED_DOWNLOADER_TYPES.copy()


def build_downloader_provider(
    downloader_type: str | None,
    server_url: str | None,
    api_key: str | None,
) -> BaseDownloaderProvider | None:
    normalized_type = str(downloader_type or "").strip().lower()

    if normalized_type == "sabnzbd":
        from app.providers.downloaders.sabnzbd import SABnzbdProvider

        return SABnzbdProvider(
            server_url=server_url or "",
            api_key=api_key or "",
        )

    return None
