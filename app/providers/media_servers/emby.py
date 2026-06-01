from datetime import datetime, timezone

import requests


class EmbyProvider:
    def __init__(self, server_url: str, api_key: str):
        self.server_url = server_url.rstrip("/")
        self.api_key = api_key

    def _headers(self) -> dict:
        return {
            "X-Emby-Token": self.api_key,
            "Accept": "application/json",
        }

    def utc_now_iso(self) -> str:
        return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")

    def test_connection(self) -> dict:
        try:
            response = requests.get(
                f"{self.server_url}/System/Info",
                headers=self._headers(),
                timeout=10,
            )

            if response.status_code == 401:
                return {
                    "success": False,
                    "message": "Authentication failed. Check your Emby API key.",
                }

            response.raise_for_status()
            data = response.json()

            return {
                "success": True,
                "message": "Emby connection successful.",
                "server_name": data.get("ServerName", "Emby Server"),
                "version": data.get("Version", "Unknown"),
            }

        except requests.exceptions.ConnectionError:
            return {
                "success": False,
                "message": "Could not connect to Emby. Check the server URL.",
            }

        except requests.exceptions.Timeout:
            return {
                "success": False,
                "message": "Connection timed out. Check the server address.",
            }

        except requests.exceptions.RequestException as error:
            return {
                "success": False,
                "message": f"Emby connection failed: {error}",
            }

    def get_libraries(self) -> list[dict]:
        response = requests.get(
            f"{self.server_url}/Library/SelectableMediaFolders",
            headers=self._headers(),
            timeout=10,
        )

        response.raise_for_status()

        libraries = []

        for item in response.json():
            item_id = item.get("Id")
            name = item.get("Name", "Unknown Library")
            library_type = item.get("CollectionType")

            if not library_type:
                library_type = self._infer_library_type(name)

            libraries.append(
                {
                    "id": item_id,
                    "name": name,
                    "type": library_type,
                    "image_url": self._library_image_url(item_id),
                }
            )

        return libraries

    def scan_library(self, library_id: str, library_name: str | None = None) -> dict:
        try:
            response = requests.post(
                f"{self.server_url}/Items/{library_id}/Refresh",
                headers=self._headers(),
                params={
                    "Recursive": "true",
                    "MetadataRefreshMode": "Default",
                    "ImageRefreshMode": "Default",
                    "ReplaceAllMetadata": "false",
                    "ReplaceAllImages": "false",
                },
                timeout=15,
            )

            if response.status_code == 401:
                return {
                    "success": False,
                    "message": "Authentication failed. Check your Emby API key.",
                }

            if response.status_code == 404:
                return {
                    "success": False,
                    "message": "Library not found in Emby.",
                }

            response.raise_for_status()

            display_name = library_name or library_id

            return {
                "success": True,
                "message": f"Emby library scan started for {display_name}.",
                "library_id": library_id,
                "library_name": library_name,
            }

        except requests.exceptions.ConnectionError:
            return {
                "success": False,
                "message": "Could not connect to Emby. Check the server URL.",
            }

        except requests.exceptions.Timeout:
            return {
                "success": False,
                "message": "Emby scan request timed out.",
            }

        except requests.exceptions.RequestException as error:
            return {
                "success": False,
                "message": f"Emby library scan failed: {error}",
            }

    def get_library_scan_status(
        self,
        library_id: str | None = None,
        library_name: str | None = None,
        scan_requested_at: str | None = None,
    ) -> dict:
        try:
            response = requests.get(
                f"{self.server_url}/ScheduledTasks",
                headers=self._headers(),
                timeout=10,
            )

            if response.status_code == 401:
                return {
                    "success": False,
                    "message": "Authentication failed. Check your Emby API key.",
                    "running": False,
                    "progress": 0,
                }

            response.raise_for_status()

            tasks = response.json()
            scan_task = self._find_library_scan_task(tasks)

            if not scan_task:
                return {
                    "success": True,
                    "message": "Waiting for Emby scan status.",
                    "running": True,
                    "progress": 1,
                    "state": "Unknown",
                    "task_name": None,
                    "library_id": library_id,
                    "library_name": library_name,
                }

            state = str(scan_task.get("State", "Unknown"))
            last_result = scan_task.get("LastExecutionResult") or {}
            status = str(last_result.get("Status", "Unknown"))
            start_time = last_result.get("StartTimeUtc")
            end_time = last_result.get("EndTimeUtc")

            progress = scan_task.get("CurrentProgressPercentage")

            if progress is None:
                progress = scan_task.get("ProgressPercentage")

            try:
                progress = float(progress)
            except (TypeError, ValueError):
                progress = 0.0

            request_dt = self._parse_emby_time(scan_requested_at)
            start_dt = self._parse_emby_time(start_time)
            end_dt = self._parse_emby_time(end_time)

            state_running = state.lower() == "running"
            status_running = status.lower() in {"running", "cancelling", "inprogress"}

            if state_running or status_running:
                return {
                    "success": True,
                    "message": f"Emby scan running: {progress:.0f}%.",
                    "running": True,
                    "progress": max(1, min(100, progress)),
                    "state": state,
                    "task_status": status,
                    "task_name": scan_task.get("Name"),
                    "library_id": library_id,
                    "library_name": library_name,
                }

            if request_dt and start_dt and start_dt >= request_dt:
                if end_dt:
                    return {
                        "success": True,
                        "message": "Emby scan complete.",
                        "running": False,
                        "progress": 100,
                        "state": state,
                        "task_status": status,
                        "task_name": scan_task.get("Name"),
                        "library_id": library_id,
                        "library_name": library_name,
                    }

                return {
                    "success": True,
                    "message": "Emby scan running.",
                    "running": True,
                    "progress": max(1, min(100, progress)),
                    "state": state,
                    "task_status": status,
                    "task_name": scan_task.get("Name"),
                    "library_id": library_id,
                    "library_name": library_name,
                }

            if request_dt:
                return {
                    "success": True,
                    "message": "Waiting for Emby to report the requested scan.",
                    "running": True,
                    "progress": 1,
                    "state": state,
                    "task_status": status,
                    "task_name": scan_task.get("Name"),
                    "library_id": library_id,
                    "library_name": library_name,
                }

            return {
                "success": True,
                "message": "Emby scan complete.",
                "running": False,
                "progress": 100,
                "state": state,
                "task_status": status,
                "task_name": scan_task.get("Name"),
                "library_id": library_id,
                "library_name": library_name,
            }

        except requests.exceptions.ConnectionError:
            return {
                "success": False,
                "message": "Could not connect to Emby. Check the server URL.",
                "running": False,
                "progress": 0,
            }

        except requests.exceptions.Timeout:
            return {
                "success": False,
                "message": "Emby scan status request timed out.",
                "running": False,
                "progress": 0,
            }

        except requests.exceptions.RequestException as error:
            return {
                "success": False,
                "message": f"Emby scan status failed: {error}",
                "running": False,
                "progress": 0,
            }

    def _find_library_scan_task(self, tasks: list[dict]) -> dict | None:
        preferred_keys = {
            "RefreshLibrary",
            "RefreshMediaLibrary",
            "ScanMediaLibrary",
        }

        for task in tasks:
            key = str(task.get("Key", ""))
            name = str(task.get("Name", ""))

            if key in preferred_keys:
                return task

            normalized_name = name.lower()

            if (
                "scan" in normalized_name
                and "library" in normalized_name
            ) or (
                "refresh" in normalized_name
                and "library" in normalized_name
            ):
                return task

        return None

    def _parse_emby_time(self, value: str | None) -> datetime | None:
        if not value:
            return None

        try:
            normalized = value.rstrip("Z")

            if "." in normalized:
                date_part, fraction = normalized.split(".", 1)
                fraction = fraction[:6]
                normalized = f"{date_part}.{fraction}"

            parsed = datetime.fromisoformat(normalized)
            return parsed.replace(tzinfo=timezone.utc)

        except ValueError:
            return None

    def _library_image_url(self, item_id: str | None) -> str | None:
        if not item_id:
            return None

        return (
            f"{self.server_url}/Items/{item_id}/Images/Primary"
            f"?api_key={self.api_key}"
        )

    def _infer_library_type(self, name: str) -> str:
        normalized = name.lower()

        if "movie" in normalized or "film" in normalized:
            return "movies"

        if "tv" in normalized or "show" in normalized or "series" in normalized:
            return "tvshows"

        if "music" in normalized:
            return "music"

        if "recording" in normalized:
            return "homevideos"

        return "unknown"
