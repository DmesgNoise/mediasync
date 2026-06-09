from typing import Any

from app.providers.request_apps.base import RequestAppProvider


class OmbiProvider(RequestAppProvider):
    def test_connection(self) -> dict[str, Any]:
        return {
            "success": False,
            "message": "Ombi support is scaffolded but not implemented yet.",
        }

    def get_status(self) -> dict[str, Any]:
        return {
            "success": False,
            "message": "Ombi support is scaffolded but not implemented yet.",
            "data": {},
        }

    def get_request_counts(self) -> dict[str, Any]:
        return {
            "success": False,
            "message": "Ombi support is scaffolded but not implemented yet.",
            "data": {},
        }

    def get_recent_requests(self, limit: int = 10) -> list[dict[str, Any]]:
        return []

    def get_pending_requests(self, limit: int = 25) -> list[dict[str, Any]]:
        return []
