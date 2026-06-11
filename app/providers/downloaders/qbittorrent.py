from typing import Any
from urllib.parse import urlparse

import requests

from app.providers.downloaders.base import BaseDownloaderProvider


class QBittorrentProvider(BaseDownloaderProvider):
    TIMEOUT_SECONDS = 10

    def __init__(self, server_url: str, api_key: str):
        super().__init__(server_url, api_key)
        self.username = ""
        self.password = ""
        self.session = requests.Session()

        parsed_url = urlparse(self.server_url)

        if parsed_url.username or parsed_url.password:
            self.username = parsed_url.username or ""
            self.password = parsed_url.password or ""
            host = parsed_url.hostname or ""
            port = f":{parsed_url.port}" if parsed_url.port else ""
            path = parsed_url.path or ""
            scheme = parsed_url.scheme or "http"
            self.server_url = f"{scheme}://{host}{port}{path}".rstrip("/")

        if self.api_key:
            if ":" in self.api_key:
                self.username, self.password = self.api_key.split(":", 1)
            elif not self.password:
                self.password = self.api_key

    def _api_url(self, path: str) -> str:
        return f"{self.server_url}/api/v2/{path.lstrip('/')}"

    def _login(self) -> dict[str, Any]:
        if not self.server_url:
            return {"success": False, "message": "qBittorrent URL is required."}

        if not self.username or not self.password:
            return {"success": False, "message": "qBittorrent username and password are required."}

        try:
            response = self.session.post(
                self._api_url("auth/login"),
                data={"username": self.username, "password": self.password},
                timeout=self.TIMEOUT_SECONDS,
            )

            if response.status_code in (200, 204):
                return {"success": True}

            return {
                "success": False,
                "message": "qBittorrent authentication failed. Check username/password.",
                "status_code": response.status_code,
            }

        except requests.exceptions.ConnectionError:
            return {"success": False, "message": "Could not connect to qBittorrent. Check the server URL."}
        except requests.exceptions.Timeout:
            return {"success": False, "message": "qBittorrent connection timed out."}
        except requests.RequestException as error:
            return {"success": False, "message": f"qBittorrent login failed: {error}"}

    def _get(self, path: str, params: dict[str, Any] | None = None, expect_json: bool = True) -> dict[str, Any]:
        login_result = self._login()

        if not login_result.get("success"):
            return login_result

        try:
            response = self.session.get(
                self._api_url(path),
                params=params or {},
                timeout=self.TIMEOUT_SECONDS,
            )

            if response.status_code in (401, 403):
                return {
                    "success": False,
                    "message": "qBittorrent authentication failed. Check username/password.",
                    "status_code": response.status_code,
                }

            response.raise_for_status()

            if expect_json:
                data = response.json()
            else:
                data = response.text

            return {"success": True, "data": data}

        except requests.exceptions.ConnectionError:
            return {"success": False, "message": "Could not connect to qBittorrent. Check the server URL."}
        except requests.exceptions.Timeout:
            return {"success": False, "message": "qBittorrent connection timed out."}
        except ValueError:
            return {"success": False, "message": "qBittorrent returned invalid JSON."}
        except requests.RequestException as error:
            return {"success": False, "message": f"qBittorrent request failed: {error}"}

    def test_connection(self) -> dict[str, Any]:
        result = self._get("app/version", expect_json=False)

        if not result.get("success"):
            return result

        version = str(result.get("data") or "Unknown").strip()
        version = version.lstrip("v") if version.lower().startswith("v") else version

        return {
            "success": True,
            "message": f"Connected to qBittorrent {version}.",
            "version": version,
            "status": "Connected",
            "connected": 1,
        }

    def get_status(self) -> dict[str, Any]:
        result = self._get("transfer/info")

        if not result.get("success"):
            return result

        data = result.get("data") or {}

        return {
            "success": True,
            "message": "qBittorrent status read successfully.",
            "data": data,
            "speed": self._format_bytes_per_second(self._to_int(data.get("dl_info_speed"))),
        }

    def get_queue(self) -> dict[str, Any]:
        result = self._get("torrents/info")

        if not result.get("success"):
            return result

        torrents = result.get("data") or []

        if not isinstance(torrents, list):
            torrents = []

        downloads = [
            self.normalize_download_item(item)
            for item in torrents
            if isinstance(item, dict)
        ]

        active_downloads = [
            item for item in downloads
            if item.get("status") in {
                "downloading",
                "queued",
                "checking",
                "verifying",
                "stalled",
                "paused",
                "seeding",
            }
        ]

        total_speed = sum(
            self._to_int(item.get("dlspeed"))
            for item in torrents
            if isinstance(item, dict)
        )

        return {
            "success": True,
            "message": "qBittorrent queue read successfully.",
            "downloads": downloads,
            "active_count": len(active_downloads),
            "total_count": len(downloads),
            "speed": self._format_bytes_per_second(total_speed),
            "timeleft": self._queue_eta(downloads),
            "size": self._queue_size(downloads),
            "raw": torrents,
        }

    def get_history(self, limit: int = 80) -> dict[str, Any]:
        result = self.get_queue()

        if not result.get("success"):
            return result

        history = []

        for item in result.get("downloads") or []:
            final_state = "unknown"
            status = str(item.get("status") or "").strip().lower()

            if status == "completed":
                final_state = "completed"
            elif status == "failed":
                final_state = "failed"
            elif status in {"cancelled", "canceled"}:
                final_state = "cancelled"

            history_item = dict(item)
            history_item["final_state"] = final_state
            history.append(history_item)

        return {
            "success": True,
            "message": "qBittorrent history read successfully.",
            "history": history[:limit],
        }

    def normalize_download_item(self, item: dict[str, Any], queue: dict[str, Any] | None = None) -> dict[str, Any]:
        progress = self._to_float(item.get("progress"))
        percent = round(max(0.0, min(progress, 1.0)) * 100, 1)
        state = str(item.get("state") or "").strip()
        status = self._normalize_status(state, progress)

        return {
            "id": str(item.get("hash") or item.get("name") or ""),
            "hash": str(item.get("hash") or ""),
            "name": str(item.get("name") or "Unknown download"),
            "filename": str(item.get("name") or "Unknown download"),
            "category": str(item.get("category") or ""),
            "status": status,
            "status_code": state,
            "percent": percent,
            "size": self._format_bytes(self._to_int(item.get("size"))),
            "remaining": self._format_bytes(self._to_int(item.get("amount_left"))),
            "speed": self._format_bytes_per_second(self._to_int(item.get("dlspeed"))),
            "upload_speed": self._format_bytes_per_second(self._to_int(item.get("upspeed"))),
            "eta": self._format_eta(self._to_int(item.get("eta"), default=-1)),
            "peers": self._to_int(item.get("num_leechs")),
            "seeders": self._to_int(item.get("num_seeds")),
            "leechers": self._to_int(item.get("num_leechs")),
            "ratio": self._to_float(item.get("ratio")),
            "download_dir": str(item.get("save_path") or ""),
            "save_path": str(item.get("save_path") or ""),
            "content_path": str(item.get("content_path") or ""),
            "error": 1 if status == "failed" else 0,
            "errorString": "",
            "fail_message": "",
            "raw": item,
        }

    def _normalize_status(self, state: str, progress: float) -> str:
        normalized = str(state or "").strip().lower()

        if normalized in {"error", "missingfiles"}:
            return "failed"

        if progress >= 1.0 and normalized in {"uploading", "stalledup", "queuedup", "pausedup", "forcedup"}:
            return "completed"

        if normalized in {"downloading", "forceddl", "metadl"}:
            return "downloading"

        if normalized in {"queueddown", "queuedup"}:
            return "queued"

        if normalized in {"checkingdown", "checkingup", "checkingresume", "allocating", "checking"}:
            return "checking"

        if normalized in {"stalleddl", "stalledup"}:
            return "stalled"

        if normalized in {"pauseddl", "pausedup"}:
            return "paused"

        if normalized in {"uploading", "forcedup"}:
            return "seeding"

        return "unknown"

    def _queue_eta(self, downloads: list[dict[str, Any]]) -> str:
        eta_values = []

        for download in downloads:
            raw = download.get("raw") or {}
            eta_seconds = self._to_int(raw.get("eta"), default=-1)

            if eta_seconds >= 0 and download.get("status") in {"downloading", "queued", "stalled"}:
                eta_values.append(eta_seconds)

        if not eta_values:
            return ""

        return self._format_eta(min(eta_values))

    def _queue_size(self, downloads: list[dict[str, Any]]) -> str:
        total = 0

        for download in downloads:
            raw = download.get("raw") or {}
            total += self._to_int(raw.get("size"))

        return self._format_bytes(total)

    def _format_eta(self, seconds: int) -> str:
        if seconds < 0 or seconds >= 8640000:
            return ""

        if seconds < 60:
            return f"{seconds}s"

        minutes, remaining_seconds = divmod(seconds, 60)

        if minutes < 60:
            return f"{minutes}m {remaining_seconds}s"

        hours, remaining_minutes = divmod(minutes, 60)

        if hours < 24:
            return f"{hours}h {remaining_minutes}m"

        days, remaining_hours = divmod(hours, 24)
        return f"{days}d {remaining_hours}h"

    def _format_bytes_per_second(self, value: int) -> str:
        return f"{self._format_bytes(value)}/s"

    def _format_bytes(self, value: int) -> str:
        size = max(0, self._to_float(value))
        units = ["B", "KB", "MB", "GB", "TB", "PB"]

        for unit in units:
            if size < 1024 or unit == units[-1]:
                if unit == "B":
                    return f"{int(size)} {unit}"

                return f"{size:.1f} {unit}"

            size = size / 1024

        return f"{size:.1f} PB"

    def _to_float(self, value: Any, default: float = 0.0) -> float:
        try:
            return float(value)
        except (TypeError, ValueError):
            return default

    def _to_int(self, value: Any, default: int = 0) -> int:
        try:
            return int(value)
        except (TypeError, ValueError):
            return default
