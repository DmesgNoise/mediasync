from abc import ABC, abstractmethod
from typing import Any


class RequestAppProvider(ABC):
    def __init__(self, server_url: str, api_key: str):
        self.server_url = str(server_url or "").strip().rstrip("/")
        self.api_key = str(api_key or "").strip()

    @abstractmethod
    def test_connection(self) -> dict[str, Any]:
        raise NotImplementedError

    @abstractmethod
    def get_status(self) -> dict[str, Any]:
        raise NotImplementedError

    @abstractmethod
    def get_request_counts(self) -> dict[str, Any]:
        raise NotImplementedError

    @abstractmethod
    def get_recent_requests(self, limit: int = 10) -> list[dict[str, Any]]:
        raise NotImplementedError

    @abstractmethod
    def get_pending_requests(self, limit: int = 25) -> list[dict[str, Any]]:
        raise NotImplementedError


SUPPORTED_REQUEST_APP_TYPES = {
    "seerr",
    "overseerr",
    "ombi",
}


def get_supported_request_app_types() -> set[str]:
    return SUPPORTED_REQUEST_APP_TYPES.copy()


def build_request_app_provider(app_type: str | None, server_url: str, api_key: str):
    normalized_type = str(app_type or "").strip().lower()

    if normalized_type == "seerr":
        from app.providers.request_apps.seerr import SeerrProvider

        return SeerrProvider(server_url=server_url, api_key=api_key)

    if normalized_type == "overseerr":
        from app.providers.request_apps.overseerr import OverseerrProvider

        return OverseerrProvider(server_url=server_url, api_key=api_key)

    if normalized_type == "ombi":
        from app.providers.request_apps.ombi import OmbiProvider

        return OmbiProvider(server_url=server_url, api_key=api_key)

    return None
