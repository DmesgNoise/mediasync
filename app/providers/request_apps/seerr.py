import json
from typing import Any

import requests

from app.providers.request_apps.base import RequestAppProvider


class SeerrProvider(RequestAppProvider):
    REQUEST_STATUS_PENDING = 1
    REQUEST_STATUS_APPROVED = 2
    REQUEST_STATUS_DECLINED = 3

    MEDIA_TYPE_MOVIE = "movie"
    MEDIA_TYPE_TV = "tv"

    # Includes request, approval, auto-approval, auto-request, and available-style
    # Seerr webhook notifications. This covers both manual approval users and
    # auto-approval users.
    WEBHOOK_NOTIFICATION_TYPES = 4318

    DEFAULT_WEBHOOK_JSON_PAYLOAD = """{
  "notification_type": "{{notification_type}}",
  "event": "{{event}}",
  "subject": "{{subject}}",
  "message": "{{message}}",
  "image": "{{image}}",
  "media": {
    "media_type": "{{media_type}}",
    "tmdbId": "{{media_tmdbid}}",
    "tvdbId": "{{media_tvdbid}}",
    "status": "{{media_status}}",
    "status4k": "{{media_status4k}}"
  },
  "request": {
    "request_id": "{{request_id}}",
    "requestedBy_email": "{{requestedBy_email}}",
    "requestedBy_username": "{{requestedBy_username}}",
    "requestedBy_avatar": "{{requestedBy_avatar}}",
    "requestedBy_settings_discordId": "{{requestedBy_settings_discordId}}",
    "requestedBy_settings_telegramChatId": "{{requestedBy_settings_telegramChatId}}"
  },
  "issue": {
    "issue_id": "{{issue_id}}",
    "issue_type": "{{issue_type}}",
    "issue_status": "{{issue_status}}",
    "reportedBy_email": "{{reportedBy_email}}",
    "reportedBy_username": "{{reportedBy_username}}",
    "reportedBy_avatar": "{{reportedBy_avatar}}",
    "reportedBy_settings_discordId": "{{reportedBy_settings_discordId}}",
    "reportedBy_settings_telegramChatId": "{{reportedBy_settings_telegramChatId}}"
  },
  "comment": {
    "comment_message": "{{comment_message}}",
    "commentedBy_email": "{{commentedBy_email}}",
    "commentedBy_username": "{{commentedBy_username}}",
    "commentedBy_avatar": "{{commentedBy_avatar}}",
    "commentedBy_settings_discordId": "{{commentedBy_settings_discordId}}",
    "commentedBy_settings_telegramChatId": "{{commentedBy_settings_telegramChatId}}"
  },
  "extra": []
}"""

    def _headers(self) -> dict[str, str]:
        return {
            "X-Api-Key": self.api_key,
            "Accept": "application/json",
        }

    def _json_headers(self) -> dict[str, str]:
        headers = self._headers()
        headers["Content-Type"] = "application/json"
        return headers

    def _api_url(self, path: str) -> str:
        normalized_path = str(path or "").strip()

        if not normalized_path.startswith("/"):
            normalized_path = f"/{normalized_path}"

        return f"{self.server_url}/api/v1{normalized_path}"

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
                "message": "Authentication failed. Check your Seerr API key.",
                "status_code": response.status_code,
            }

        response.raise_for_status()

        try:
            data = response.json()
        except ValueError:
            data = {}

        return {
            "success": True,
            "message": "Seerr request successful.",
            "data": data,
            "status_code": response.status_code,
        }

    def _post_with_csrf(self, path: str, json_body: dict[str, Any]) -> dict[str, Any]:
        session = requests.Session()

        get_response = session.get(
            self._api_url(path),
            headers=self._headers(),
            timeout=10,
        )

        if get_response.status_code in (401, 403):
            return {
                "success": False,
                "message": "Authentication failed. Check your Seerr API key.",
                "status_code": get_response.status_code,
            }

        get_response.raise_for_status()

        xsrf_token = session.cookies.get("XSRF-TOKEN", "")

        headers = self._json_headers()

        if xsrf_token:
            headers["X-XSRF-TOKEN"] = xsrf_token

        post_response = session.post(
            self._api_url(path),
            headers=headers,
            json=json_body,
            timeout=10,
        )

        if post_response.status_code in (401, 403):
            message = "Authentication failed. Check your Seerr API key."

            try:
                message = post_response.json().get("message", message)
            except ValueError:
                pass

            return {
                "success": False,
                "message": message,
                "status_code": post_response.status_code,
            }

        if post_response.status_code >= 400:
            message = f"Seerr returned HTTP {post_response.status_code}."

            try:
                message = post_response.json().get("message", message)
            except ValueError:
                if post_response.text:
                    message = post_response.text

            return {
                "success": False,
                "message": message,
                "status_code": post_response.status_code,
            }

        try:
            data = post_response.json()
        except ValueError:
            data = {}

        return {
            "success": True,
            "message": "Seerr request successful.",
            "data": data,
            "status_code": post_response.status_code,
        }

    def test_connection(self) -> dict[str, Any]:
        if not self.server_url:
            return {
                "success": False,
                "message": "Seerr URL is required.",
            }

        if not self.api_key:
            return {
                "success": False,
                "message": "Seerr API key is required.",
            }

        try:
            status_result = self.get_status()

            if not status_result.get("success"):
                return status_result

            status_data = status_result.get("data", {})
            version = self._extract_version(status_data)

            return {
                "success": True,
                "message": "Seerr connection successful.",
                "server_name": "Seerr",
                "version": version,
                "status": status_data,
            }

        except requests.exceptions.ConnectionError:
            return {
                "success": False,
                "message": "Could not connect to Seerr. Check the server URL.",
            }

        except requests.exceptions.Timeout:
            return {
                "success": False,
                "message": "Connection timed out. Check the Seerr address.",
            }

        except requests.exceptions.RequestException as error:
            return {
                "success": False,
                "message": f"Seerr connection failed: {error}",
            }

    def get_status(self) -> dict[str, Any]:
        return self._get("/status")

    def get_webhook_settings(self) -> dict[str, Any]:
        try:
            return self._get("/settings/notifications/webhook")
        except requests.exceptions.RequestException as error:
            return {
                "success": False,
                "message": f"Could not read Seerr webhook settings: {error}",
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
                "embedPoster": True,
                "types": 0,
                "options": {},
            }

        payload["enabled"] = True

        try:
            existing_types = int(payload.get("types", 0) or 0)
        except (TypeError, ValueError):
            existing_types = 0

        payload["types"] = existing_types | self.WEBHOOK_NOTIFICATION_TYPES

        options = payload.get("options")

        if not isinstance(options, dict):
            options = {}

        options["webhookUrl"] = normalized_webhook_url
        options["customHeaders"] = options.get("customHeaders") or []
        options["supportVariables"] = False

        # Proven Seerr rule:
        # POST validation wants jsonPayload as a string, and Seerr UI stays healthy
        # when the stored value is a JSON-escaped string.
        options["jsonPayload"] = self.DEFAULT_WEBHOOK_JSON_PAYLOAD

        payload["options"] = options

        result = self._post_with_csrf(
            "/settings/notifications/webhook",
            json_body=payload,
        )

        if not result.get("success"):
            result["attempted"] = True
            return result

        return {
            "success": True,
            "attempted": True,
            "message": "Seerr webhook registered successfully.",
            "webhook_url": normalized_webhook_url,
            "data": result.get("data"),
        }

    def get_request_counts(self) -> dict[str, Any]:
        try:
            result = self._get("/request/count")

            if result.get("success"):
                return result

            return result

        except requests.exceptions.HTTPError:
            requests_result = self._get(
                "/request",
                params={
                    "take": 100,
                    "skip": 0,
                },
            )

            if not requests_result.get("success"):
                return requests_result

            requests_list = self._extract_request_results(requests_result.get("data"))

            return {
                "success": True,
                "message": "Seerr request counts calculated from recent requests.",
                "data": self._calculate_counts(requests_list),
            }

    def get_request_by_id(self, request_id: int | str) -> dict[str, Any]:
        try:
            normalized_request_id = int(request_id)
        except (TypeError, ValueError):
            return {
                "success": False,
                "message": "Request ID is invalid.",
            }

        return self._get(f"/request/{normalized_request_id}")

    def get_recent_requests(self, limit: int = 10) -> list[dict[str, Any]]:
        result = self._get(
            "/request",
            params={
                "take": self._safe_limit(limit),
                "skip": 0,
            },
        )

        if not result.get("success"):
            return []

        return [
            self._normalize_request(item)
            for item in self._extract_request_results(result.get("data"))
        ]

    def get_pending_requests(self, limit: int = 25) -> list[dict[str, Any]]:
        result = self._get(
            "/request",
            params={
                "take": self._safe_limit(limit),
                "skip": 0,
                "filter": "pending",
            },
        )

        if not result.get("success"):
            return []

        requests_list = self._extract_request_results(result.get("data"))
        pending_requests = []

        for item in requests_list:
            normalized_request = self._normalize_request(item)

            if normalized_request.get("status") == "pending":
                pending_requests.append(normalized_request)

        return pending_requests

    def _safe_limit(self, limit: int) -> int:
        try:
            parsed_limit = int(limit)
        except (TypeError, ValueError):
            parsed_limit = 10

        return max(1, min(parsed_limit, 100))

    def _extract_version(self, status_data: dict[str, Any]) -> str:
        for key in ("version", "commitTag", "updateVersion"):
            value = status_data.get(key)

            if value:
                return str(value)

        return "Unknown"

    def _extract_request_results(self, data: Any) -> list[dict[str, Any]]:
        if isinstance(data, list):
            return data

        if not isinstance(data, dict):
            return []

        for key in ("results", "requests", "items"):
            value = data.get(key)

            if isinstance(value, list):
                return value

        return []

    def _calculate_counts(self, requests_list: list[dict[str, Any]]) -> dict[str, int]:
        counts = {
            "total": 0,
            "pending": 0,
            "approved": 0,
            "declined": 0,
            "movie": 0,
            "tv": 0,
        }

        for item in requests_list:
            normalized_request = self._normalize_request(item)
            counts["total"] += 1

            status = normalized_request.get("status")
            media_type = normalized_request.get("media_type")

            if status in counts:
                counts[status] += 1

            if media_type in counts:
                counts[media_type] += 1

        return counts

    def normalize_request_payload(self, item: dict[str, Any]) -> dict[str, Any]:
        return self._normalize_request(item)

    def _normalize_request(self, item: dict[str, Any]) -> dict[str, Any]:
        media = item.get("media") or {}
        requested_by = item.get("requestedBy") or item.get("requested_by") or {}
        modified_by = item.get("modifiedBy") or item.get("modified_by") or {}

        return {
            "id": item.get("id"),
            "status": self._normalize_status(item.get("status")),
            "media_type": self._normalize_media_type(
                item.get("type") or media.get("mediaType") or media.get("media_type")
            ),
            "media_id": media.get("id") or item.get("mediaId") or item.get("media_id"),
            "tmdb_id": media.get("tmdbId") or media.get("tmdb_id") or item.get("tmdbId"),
            "tvdb_id": media.get("tvdbId") or media.get("tvdb_id") or item.get("tvdbId"),
            "title": self._extract_title(item, media),
            "requested_by": self._normalize_user(requested_by),
            "modified_by": self._normalize_user(modified_by),
            "quality_profile": self._extract_quality_profile(item, media),
            "quality_profile_id": self._extract_quality_profile_id(item, media),
            "server_id": self._extract_server_id(item, media),
            "root_folder": self._extract_root_folder(item, media),
            "created_at": item.get("createdAt") or item.get("created_at"),
            "updated_at": item.get("updatedAt") or item.get("updated_at"),
            "raw": item,
        }

    def _extract_title(self, item: dict[str, Any], media: dict[str, Any]) -> str:
        for source in (item, media):
            for key in ("title", "name", "originalTitle", "originalName"):
                value = source.get(key)

                if value:
                    return str(value)

        movie = media.get("movie") or item.get("movie") or {}
        tv = media.get("tv") or item.get("tv") or {}

        for source in (movie, tv):
            for key in ("title", "name", "originalTitle", "originalName"):
                value = source.get(key)

                if value:
                    return str(value)

        return "Unknown Title"

    def _extract_quality_profile(self, item: dict[str, Any], media: dict[str, Any]) -> str:
        for source in (item, media):
            if not isinstance(source, dict):
                continue

            for key in (
                "profileName",
                "profile_name",
                "qualityProfileName",
                "quality_profile_name",
                "qualityProfile",
                "quality_profile",
                "profile",
            ):
                value = source.get(key)

                if isinstance(value, str) and value.strip():
                    return value.strip()

                if isinstance(value, dict):
                    for nested_key in ("name", "label", "title"):
                        nested_value = value.get(nested_key)

                        if nested_value:
                            return str(nested_value).strip()

        if item.get("is4k"):
            return "4K"

        return ""

    def _extract_quality_profile_id(self, item: dict[str, Any], media: dict[str, Any]) -> int | None:
        for source in (item, media):
            if not isinstance(source, dict):
                continue

            for key in (
                "profileId",
                "profile_id",
                "qualityProfileId",
                "quality_profile_id",
            ):
                value = source.get(key)

                if value is None or value == "":
                    continue

                try:
                    return int(value)
                except (TypeError, ValueError):
                    continue

            for key in ("qualityProfile", "quality_profile", "profile"):
                value = source.get(key)

                if isinstance(value, dict):
                    nested_value = value.get("id")

                    if nested_value is None or nested_value == "":
                        continue

                    try:
                        return int(nested_value)
                    except (TypeError, ValueError):
                        continue

        return None

    def _extract_server_id(self, item: dict[str, Any], media: dict[str, Any]) -> int | None:
        for source in (item, media):
            if not isinstance(source, dict):
                continue

            for key in ("serverId", "server_id"):
                value = source.get(key)

                if value is None or value == "":
                    continue

                try:
                    return int(value)
                except (TypeError, ValueError):
                    continue

        return None

    def _extract_root_folder(self, item: dict[str, Any], media: dict[str, Any]) -> str:
        for source in (item, media):
            if not isinstance(source, dict):
                continue

            for key in ("rootFolder", "root_folder", "rootFolderPath", "root_folder_path"):
                value = source.get(key)

                if isinstance(value, str) and value.strip():
                    return value.strip()

        return ""

    def _normalize_user(self, user: dict[str, Any]) -> dict[str, Any] | None:
        if not isinstance(user, dict) or not user:
            return None

        return {
            "id": user.get("id"),
            "username": user.get("username"),
            "display_name": user.get("displayName") or user.get("display_name"),
            "email": user.get("email"),
            "avatar": user.get("avatar"),
        }

    def _normalize_status(self, status: Any) -> str:
        try:
            parsed_status = int(status)
        except (TypeError, ValueError):
            parsed_status = None

        if parsed_status == self.REQUEST_STATUS_PENDING:
            return "pending"

        if parsed_status == self.REQUEST_STATUS_APPROVED:
            return "approved"

        if parsed_status == self.REQUEST_STATUS_DECLINED:
            return "declined"

        if parsed_status == 5:
            return "available"

        if isinstance(status, str):
            return status.lower()

        return "unknown"

    def _normalize_media_type(self, media_type: Any) -> str:
        normalized_type = str(media_type or "").strip().lower()

        if normalized_type in ("movie", "movies"):
            return self.MEDIA_TYPE_MOVIE

        if normalized_type in ("tv", "show", "series", "tvshows"):
            return self.MEDIA_TYPE_TV

        return normalized_type or "unknown"
