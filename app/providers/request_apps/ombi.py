from typing import Any

import requests

from app.providers.request_apps.base import RequestAppProvider


class OmbiProvider(RequestAppProvider):
    WEBHOOK_ENDPOINT = "/Settings/notifications/webhook"

    def test_connection(self) -> dict[str, Any]:
        try:
            identity_result = self._get("/Identity")

            if not identity_result.get("success"):
                return identity_result

            identity = identity_result.get("data") or {}
            user_name = identity.get("userName") or identity.get("username") or "Ombi API"
            status_result = self.get_status()
            version = status_result.get("version") or "Unknown"

            return {
                "success": True,
                "message": f"Connected to Ombi as {user_name}.",
                "server_name": "Ombi",
                "version": str(version),
                "data": identity,
            }

        except requests.exceptions.ConnectionError:
            return {
                "success": False,
                "message": "Could not connect to Ombi. Check the server URL.",
            }

        except requests.exceptions.Timeout:
            return {
                "success": False,
                "message": "Ombi connection timed out.",
            }

        except requests.exceptions.RequestException as error:
            return {
                "success": False,
                "message": f"Ombi connection failed: {error}",
            }

    def get_status(self) -> dict[str, Any]:
        try:
            result = self._get("/Status/info")

            if result.get("success"):
                result["version"] = str(result.get("data") or result.get("version") or "Unknown")

            return result

        except requests.exceptions.RequestException as error:
            return {
                "success": False,
                "message": f"Could not read Ombi status: {error}",
                "data": {},
            }

    def get_webhook_settings(self) -> dict[str, Any]:
        try:
            return self._get(self.WEBHOOK_ENDPOINT)
        except requests.exceptions.RequestException as error:
            return {
                "success": False,
                "message": f"Could not read Ombi webhook settings: {error}",
                "data": {},
            }

    def register_mediasync_webhook(self, webhook_url: str) -> dict[str, Any]:
        normalized_webhook_url = str(webhook_url or "").strip()

        if not normalized_webhook_url:
            return {
                "success": False,
                "attempted": False,
                "message": "MediaSync webhook URL is missing.",
            }

        current_result = self.get_webhook_settings()

        if current_result.get("success") and isinstance(current_result.get("data"), dict):
            payload = dict(current_result["data"])
        else:
            payload = {
                "enabled": False,
                "webhookUrl": None,
                "applicationToken": None,
                "id": 0,
            }

        payload["enabled"] = True
        payload["webhookUrl"] = normalized_webhook_url
        payload["applicationToken"] = payload.get("applicationToken") or "mediasync"
        payload["id"] = payload.get("id", 0) or 0

        post_result = self._post(self.WEBHOOK_ENDPOINT, payload)

        if not post_result.get("success"):
            post_result["attempted"] = True
            return post_result

        verify_result = self.get_webhook_settings()

        if verify_result.get("success"):
            saved_settings = verify_result.get("data") or {}
            saved_url = str(saved_settings.get("webhookUrl") or "").strip()

            if saved_url != normalized_webhook_url or not saved_settings.get("enabled"):
                return {
                    "success": False,
                    "attempted": True,
                    "message": "Ombi accepted the webhook save, but verification did not match the expected MediaSync URL.",
                    "webhook_url": normalized_webhook_url,
                    "data": saved_settings,
                }

            return {
                "success": True,
                "attempted": True,
                "message": "Ombi webhook registered successfully.",
                "webhook_url": normalized_webhook_url,
                "data": saved_settings,
            }

        return {
            "success": True,
            "attempted": True,
            "message": "Ombi webhook save was accepted, but MediaSync could not re-read the webhook settings for verification.",
            "webhook_url": normalized_webhook_url,
            "data": post_result.get("data"),
        }

    def get_request_counts(self) -> dict[str, Any]:
        return {
            "success": True,
            "message": "Ombi request counts are not implemented yet.",
            "data": {},
        }

    def get_recent_requests(self, limit: int = 10) -> list[dict[str, Any]]:
        return []

    def get_pending_requests(self, limit: int = 25) -> list[dict[str, Any]]:
        return []

    def _api_url(self, path: str) -> str:
        normalized_path = str(path or "").strip()

        if not normalized_path.startswith("/"):
            normalized_path = f"/{normalized_path}"

        return f"{self.server_url}/api/v1{normalized_path}"

    def _headers(self) -> dict[str, str]:
        return {
            "ApiKey": self.api_key,
            "Accept": "application/json",
        }

    def _json_headers(self) -> dict[str, str]:
        headers = self._headers()
        headers["Content-Type"] = "application/json"
        return headers

    def _get(self, path: str, params: dict[str, Any] | None = None) -> dict[str, Any]:
        response = requests.get(
            self._api_url(path),
            headers=self._headers(),
            params=params or {},
            timeout=10,
        )

        if response.status_code in (401, 403):
            return {
                "success": False,
                "message": "Authentication failed. Check your Ombi API key.",
                "status_code": response.status_code,
            }

        response.raise_for_status()

        try:
            data = response.json()
        except ValueError:
            data = response.text

        return {
            "success": True,
            "message": "Ombi request successful.",
            "data": data,
            "status_code": response.status_code,
        }

    def _post(self, path: str, json_body: dict[str, Any]) -> dict[str, Any]:
        response = requests.post(
            self._api_url(path),
            headers=self._json_headers(),
            json=json_body,
            timeout=10,
        )

        if response.status_code in (401, 403):
            return {
                "success": False,
                "message": "Authentication failed. Check your Ombi API key.",
                "status_code": response.status_code,
            }

        if response.status_code >= 400:
            message = f"Ombi returned HTTP {response.status_code}."

            try:
                data = response.json()
                if isinstance(data, dict):
                    message = data.get("message") or data.get("error") or message
                elif data:
                    message = str(data)
            except ValueError:
                if response.text:
                    message = response.text

            return {
                "success": False,
                "message": message,
                "status_code": response.status_code,
            }

        try:
            data = response.json()
        except ValueError:
            data = response.text

        if data is False:
            return {
                "success": False,
                "message": "Ombi rejected the webhook settings update.",
                "status_code": response.status_code,
                "data": data,
            }

        return {
            "success": True,
            "message": "Ombi POST successful.",
            "status_code": response.status_code,
            "data": data,
        }
