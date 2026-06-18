from typing import Any

import requests

from app.providers.downloaders.base import BaseDownloaderProvider


class SABnzbdProvider(BaseDownloaderProvider):
    TIMEOUT_SECONDS = 10

    def _request(self, mode: str, extra_params: dict[str, Any] | None = None) -> dict[str, Any]:
        if not self.server_url:
            return {
                "success": False,
                "message": "SABnzbd URL is required.",
            }

        if not self.api_key:
            return {
                "success": False,
                "message": "SABnzbd API key is required.",
            }

        params = {
            "mode": mode,
            "output": "json",
            "apikey": self.api_key,
        }

        if extra_params:
            params.update(extra_params)

        try:
            response = requests.get(
                f"{self.server_url}/api",
                params=params,
                timeout=self.TIMEOUT_SECONDS,
            )
            response.raise_for_status()
            data = response.json()
        except requests.RequestException as error:
            return {
                "success": False,
                "message": f"SABnzbd request failed: {error}",
            }
        except ValueError:
            return {
                "success": False,
                "message": "SABnzbd returned invalid JSON.",
            }

        if isinstance(data, dict) and data.get("error"):
            return {
                "success": False,
                "message": str(data.get("error")),
                "raw": data,
            }

        return {
            "success": True,
            "data": data,
        }

    def test_connection(self) -> dict[str, Any]:
        result = self._request("queue")

        if not result.get("success"):
            return result

        queue = (result.get("data") or {}).get("queue") or {}
        version = str(queue.get("version") or "Unknown")
        status = str(queue.get("status") or "Unknown")

        return {
            "success": True,
            "message": f"Connected to SABnzbd {version}.",
            "version": version,
            "status": status,
            "connected": 1,
        }

    def get_status(self) -> dict[str, Any]:
        result = self._request("queue")

        if not result.get("success"):
            return result

        queue = (result.get("data") or {}).get("queue") or {}

        return {
            "success": True,
            "version": str(queue.get("version") or "Unknown"),
            "status": str(queue.get("status") or "Unknown"),
            "paused": bool(queue.get("paused")),
            "paused_all": bool(queue.get("paused_all")),
            "speed": self._normalize_speed(queue.get("speed")),
            "kbpersec": self._to_float(queue.get("kbpersec")),
            "active_count": self._to_int(queue.get("noofslots")),
            "total_count": self._to_int(queue.get("noofslots_total")),
            "size": str(queue.get("size") or ""),
            "remaining": str(queue.get("sizeleft") or ""),
            "timeleft": str(queue.get("timeleft") or ""),
            "diskspace1": str(queue.get("diskspace1_norm") or queue.get("diskspace1") or ""),
            "diskspace2": str(queue.get("diskspace2_norm") or queue.get("diskspace2") or ""),
            "warnings": str(queue.get("have_warnings") or "0") not in ("0", "False", "false", ""),
        }

    def get_queue(self) -> dict[str, Any]:
        result = self._request("queue")

        if not result.get("success"):
            return result

        queue = (result.get("data") or {}).get("queue") or {}
        slots = queue.get("slots") or []

        if not isinstance(slots, list):
            slots = []

        downloads = [
            self.normalize_download_item(item, queue=queue)
            for item in slots
            if isinstance(item, dict)
        ]

        active_downloads = [
            download for download in downloads
            if download.get("status") not in {"download_completed", "failed", "cancelled"}
        ]

        return {
            "success": True,
            "version": str(queue.get("version") or "Unknown"),
            "status": str(queue.get("status") or "Unknown"),
            "paused": bool(queue.get("paused")),
            "speed": self._normalize_speed(queue.get("speed")),
            "kbpersec": self._to_float(queue.get("kbpersec")),
            "active_count": len(active_downloads),
            "total_count": self._to_int(queue.get("noofslots_total"), len(downloads)),
            "timeleft": str(queue.get("timeleft") or ""),
            "size": str(queue.get("size") or ""),
            "remaining": str(queue.get("sizeleft") or ""),
            "downloads": downloads,
        }

    def get_history(self, limit: int = 30) -> dict[str, Any]:
        result = self._request("history", {"limit": max(1, int(limit))})

        if not result.get("success"):
            return result

        history = (result.get("data") or {}).get("history") or {}
        slots = history.get("slots") or []

        if not isinstance(slots, list):
            slots = []

        return {
            "success": True,
            "history": [
                self.normalize_history_item(item)
                for item in slots
                if isinstance(item, dict)
            ],
        }

    def normalize_download_item(self, item: dict[str, Any], queue: dict[str, Any] | None = None) -> dict[str, Any]:
        raw_status = str(item.get("status") or "Unknown")
        status = self._normalize_queue_status(raw_status, item=item, queue=queue)

        return {
            "id": str(item.get("nzo_id") or item.get("id") or item.get("index") or ""),
            "name": str(item.get("filename") or item.get("name") or "Unknown Download"),
            "filename": str(item.get("filename") or item.get("name") or "Unknown Download"),
            "category": str(item.get("cat") or item.get("category") or ""),
            "status": status,
            "raw_status": raw_status,
            "percent": self._to_float(item.get("percentage")),
            "eta": str(item.get("timeleft") or ""),
            "size": str(item.get("size") or ""),
            "remaining": str(item.get("sizeleft") or ""),
            "mb": self._to_float(item.get("mb")),
            "mbleft": self._to_float(item.get("mbleft")),
            "priority": str(item.get("priority") or ""),
            "labels": item.get("labels") if isinstance(item.get("labels"), list) else [],
            "time_added": item.get("time_added"),
            "source": "SABnzbd",
        }

    def normalize_history_item(self, item: dict[str, Any]) -> dict[str, Any]:
        status = str(item.get("status") or "").strip()
        name = str(item.get("name") or item.get("nzb_name") or item.get("filename") or "Unknown Download")
        fail_message = str(item.get("fail_message") or item.get("fail_msg") or item.get("failure") or "")
        storage = str(item.get("storage") or "")
        downloaded = item.get("downloaded")

        return {
            "id": str(item.get("nzo_id") or item.get("id") or ""),
            "name": name,
            "filename": str(item.get("filename") or name),
            "status": status,
            "final_state": self._history_final_state(status, fail_message, storage, downloaded),
            "fail_message": fail_message,
            "category": str(item.get("category") or item.get("cat") or ""),
            "size": str(item.get("size") or ""),
            "completed_at": item.get("completed") or item.get("completed_at"),
            "downloaded": downloaded,
            "storage": storage,
            "raw": item,
        }

    def _normalize_queue_status(self, status: str, item: dict[str, Any] | None = None, queue: dict[str, Any] | None = None) -> str:
        status_text = str(status or "").strip().lower()
        queue_status = str((queue or {}).get("status") or "").strip().lower()
        item_text = f"{status_text} {queue_status}".strip()

        if any(word in item_text for word in ("fail", "failure", "error", "missing articles", "repair failed", "unpack failed", "crc", "password")):
            return "failed"

        if any(word in item_text for word in ("cancel", "canceled", "cancelled", "deleted", "aborted", "user abort", "user deleted")):
            return "cancelled"

        if "paused" in item_text or bool((queue or {}).get("paused")):
            return "paused"

        if any(word in item_text for word in ("repair", "verifying", "verify", "check", "checking")):
            return "repairing"

        if any(word in item_text for word in ("extract", "unpack", "unpacking")):
            return "unpacking"

        # SAB's downloader work is complete once unpacking has finished. If SAB briefly
        # reports moving or complete/completed, treat that as the downloader handoff point.
        if any(word in item_text for word in ("moving", "move", "complete", "completed")):
            return "download_completed"

        if any(word in item_text for word in ("fetch", "grabbing")):
            return "fetching"

        if any(word in item_text for word in ("queued", "queue")):
            return "queued"

        if any(word in item_text for word in ("download", "downloading")):
            return "downloading"

        return status_text or "unknown"

    def _history_final_state(self, status: str, fail_message: str, storage: str, downloaded: Any) -> str:
        status_text = str(status or "").strip().lower()
        fail_text = str(fail_message or "").strip().lower()
        storage_text = str(storage or "").strip()
        downloaded_text = str(downloaded or "").strip().lower()

        failure_text = f"{status_text} {fail_text}".strip()

        if "completed" in status_text or downloaded is True or downloaded_text in {"true", "1", "yes"}:
            return "completed"

        if any(word in failure_text for word in ("failed", "failure", "repair failed", "unpack failed", "missing articles", "password", "crc")):
            return "failed"

        if any(word in status_text for word in ("cancel", "canceled", "cancelled", "deleted", "aborted", "user abort", "user deleted")):
            return "cancelled"

        if storage_text and not fail_text:
            return "completed"

        return "unknown"

    def _normalize_speed(self, value: Any) -> str:
        raw = str(value or "0").strip()

        if not raw or raw == "0":
            return "0 B/s"

        if raw.endswith("/s"):
            return raw

        return f"{raw}/s"

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
