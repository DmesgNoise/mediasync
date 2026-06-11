import base64
from typing import Any
from urllib.parse import urlparse

import requests

from app.providers.downloaders.base import BaseDownloaderProvider


class TransmissionProvider(BaseDownloaderProvider):
    TIMEOUT_SECONDS = 10

    STATUS_STOPPED = 0
    STATUS_CHECK_WAIT = 1
    STATUS_CHECK = 2
    STATUS_DOWNLOAD_WAIT = 3
    STATUS_DOWNLOAD = 4
    STATUS_SEED_WAIT = 5
    STATUS_SEED = 6

    QUEUE_FIELDS = [
        "id",
        "name",
        "status",
        "percentDone",
        "rateDownload",
        "rateUpload",
        "eta",
        "peersConnected",
        "peersGettingFromUs",
        "peersSendingToUs",
        "uploadRatio",
        "totalSize",
        "leftUntilDone",
        "isFinished",
        "isStalled",
        "error",
        "errorString",
        "downloadDir",
    ]

    def __init__(self, server_url: str, api_key: str):
        super().__init__(server_url, api_key)
        self.username = ""
        self.password = ""
        self.session_id = ""

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

    def _rpc_url(self) -> str:
        if self.server_url.endswith("/transmission/rpc"):
            return self.server_url

        return f"{self.server_url}/transmission/rpc"

    def _auth(self) -> tuple[str, str] | None:
        if self.username or self.password:
            return (self.username, self.password)

        return None

    def _rpc(self, method: str, arguments: dict[str, Any] | None = None) -> dict[str, Any]:
        if not self.server_url:
            return {
                "success": False,
                "message": "Transmission URL is required.",
            }

        if not self.api_key and not self.username and not self.password:
            return {
                "success": False,
                "message": "Transmission credentials are required. Use username:password in the API Key field.",
            }

        payload = {
            "method": method,
            "arguments": arguments or {},
        }

        headers = {
            "Accept": "application/json",
            "Content-Type": "application/json",
        }

        if self.session_id:
            headers["X-Transmission-Session-Id"] = self.session_id

        try:
            response = requests.post(
                self._rpc_url(),
                json=payload,
                headers=headers,
                auth=self._auth(),
                timeout=self.TIMEOUT_SECONDS,
            )

            if response.status_code == 409:
                self.session_id = response.headers.get("X-Transmission-Session-Id", "")

                if not self.session_id:
                    return {
                        "success": False,
                        "message": "Transmission did not return a session id.",
                    }

                headers["X-Transmission-Session-Id"] = self.session_id
                response = requests.post(
                    self._rpc_url(),
                    json=payload,
                    headers=headers,
                    auth=self._auth(),
                    timeout=self.TIMEOUT_SECONDS,
                )

            if response.status_code in (401, 403):
                return {
                    "success": False,
                    "message": "Transmission authentication failed. Check username/password.",
                    "status_code": response.status_code,
                }

            response.raise_for_status()

            try:
                data = response.json()
            except ValueError:
                return {
                    "success": False,
                    "message": "Transmission returned invalid JSON.",
                }

        except requests.exceptions.ConnectionError:
            return {
                "success": False,
                "message": "Could not connect to Transmission. Check the server URL.",
            }
        except requests.exceptions.Timeout:
            return {
                "success": False,
                "message": "Transmission connection timed out.",
            }
        except requests.RequestException as error:
            return {
                "success": False,
                "message": f"Transmission request failed: {error}",
            }

        if not isinstance(data, dict):
            return {
                "success": False,
                "message": "Transmission returned an unexpected response.",
            }

        if data.get("result") != "success":
            return {
                "success": False,
                "message": str(data.get("result") or "Transmission request failed."),
                "raw": data,
            }

        return {
            "success": True,
            "data": data,
        }

    def test_connection(self) -> dict[str, Any]:
        result = self._rpc(
            "session-get",
            {
                "fields": [
                    "version",
                    "rpc-version",
                    "download-dir",
                    "incomplete-dir",
                    "incomplete-dir-enabled",
                ]
            },
        )

        if not result.get("success"):
            return result

        arguments = (result.get("data") or {}).get("arguments") or {}
        version = str(arguments.get("version") or "Unknown")

        return {
            "success": True,
            "message": f"Connected to Transmission {version}.",
            "version": version,
            "status": "Connected",
            "connected": 1,
            "download_dir": arguments.get("download-dir") or "",
        }

    def get_status(self) -> dict[str, Any]:
        result = self._rpc("session-stats")

        if not result.get("success"):
            return result

        arguments = (result.get("data") or {}).get("arguments") or {}

        return {
            "success": True,
            "message": "Transmission status read successfully.",
            "data": arguments,
        }

    def get_queue(self) -> dict[str, Any]:
        result = self._rpc(
            "torrent-get",
            {
                "fields": self.QUEUE_FIELDS,
            },
        )

        if not result.get("success"):
            return result

        arguments = (result.get("data") or {}).get("arguments") or {}
        torrents = arguments.get("torrents") or []

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
                "seeding",
                "paused",
            }
        ]

        total_speed = sum(
            self._to_int(item.get("rateDownload"))
            for item in torrents
            if isinstance(item, dict)
        )

        return {
            "success": True,
            "message": "Transmission queue read successfully.",
            "downloads": downloads,
            "active_count": len(active_downloads),
            "total_count": len(downloads),
            "speed": self._format_bytes_per_second(total_speed),
            "timeleft": self._queue_eta(downloads),
            "size": self._queue_size(downloads),
            "raw": arguments,
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
            "message": "Transmission history read successfully.",
            "history": history[:limit],
        }

    def normalize_download_item(self, item: dict[str, Any], queue: dict[str, Any] | None = None) -> dict[str, Any]:
        status_code = self._to_int(item.get("status"))
        percent_done = self._to_float(item.get("percentDone"))
        percent = round(max(0.0, min(percent_done, 1.0)) * 100, 1)
        error_code = self._to_int(item.get("error"))
        error_string = str(item.get("errorString") or "").strip()
        left_until_done = self._to_int(item.get("leftUntilDone"), default=-1)
        total_size = self._to_int(item.get("totalSize"))

        status = self._normalize_status(
            status_code=status_code,
            percent_done=percent_done,
            error_code=error_code,
            left_until_done=left_until_done,
        )

        eta_seconds = self._to_int(item.get("eta"), default=-1)

        return {
            "id": str(item.get("id") or ""),
            "name": str(item.get("name") or "Unknown download"),
            "filename": str(item.get("name") or "Unknown download"),
            "status": status,
            "status_code": status_code,
            "percent": percent,
            "size": self._format_bytes(total_size),
            "remaining": self._format_bytes(left_until_done) if left_until_done >= 0 else "",
            "speed": self._format_bytes_per_second(self._to_int(item.get("rateDownload"))),
            "upload_speed": self._format_bytes_per_second(self._to_int(item.get("rateUpload"))),
            "eta": self._format_eta(eta_seconds),
            "peers": self._to_int(item.get("peersConnected")),
            "seeders": self._to_int(item.get("peersSendingToUs")),
            "leechers": self._to_int(item.get("peersGettingFromUs")),
            "ratio": self._to_float(item.get("uploadRatio")),
            "download_dir": str(item.get("downloadDir") or ""),
            "error": error_code,
            "errorString": error_string,
            "fail_message": error_string,
            "raw": item,
        }

    def _normalize_status(
        self,
        status_code: int,
        percent_done: float,
        error_code: int,
        left_until_done: int,
    ) -> str:
        if error_code > 0:
            return "failed"

        if left_until_done == 0 and percent_done >= 1.0 and status_code in {self.STATUS_SEED_WAIT, self.STATUS_SEED}:
            return "completed"

        if status_code == self.STATUS_DOWNLOAD:
            return "downloading"

        if status_code == self.STATUS_DOWNLOAD_WAIT:
            return "queued"

        if status_code in {self.STATUS_CHECK_WAIT, self.STATUS_CHECK}:
            return "checking"

        if status_code in {self.STATUS_SEED_WAIT, self.STATUS_SEED}:
            return "seeding"

        if status_code == self.STATUS_STOPPED:
            return "paused"

        return "unknown"

    def _queue_eta(self, downloads: list[dict[str, Any]]) -> str:
        eta_values = []

        for download in downloads:
            raw = (download.get("raw") or {}).get("eta")
            eta_seconds = self._to_int(raw, default=-1)

            if eta_seconds >= 0 and download.get("status") in {"downloading", "queued"}:
                eta_values.append(eta_seconds)

        if not eta_values:
            return ""

        return self._format_eta(min(eta_values))

    def _queue_size(self, downloads: list[dict[str, Any]]) -> str:
        total = 0

        for download in downloads:
            raw = download.get("raw") or {}
            total += self._to_int(raw.get("totalSize"))

        return self._format_bytes(total)

    def _format_eta(self, seconds: int) -> str:
        if seconds < 0:
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
