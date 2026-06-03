from datetime import datetime, timezone
import xml.etree.ElementTree as ET

import requests


class PlexProvider:
    def __init__(self, server_url: str, api_key: str):
        self.server_url = server_url.rstrip("/")
        self.api_key = api_key

    def _params(self) -> dict:
        return {
            "X-Plex-Token": self.api_key,
        }

    def _headers(self) -> dict:
        return {
            "Accept": "application/xml",
        }

    def utc_now_iso(self) -> str:
        return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")

    def test_connection(self) -> dict:
        try:
            response = requests.get(
                f"{self.server_url}/identity",
                headers=self._headers(),
                params=self._params(),
                timeout=10,
            )

            if response.status_code in {401, 403}:
                return {
                    "success": False,
                    "message": "Authentication failed. Check your Plex token.",
                }

            response.raise_for_status()

            root = ET.fromstring(response.text)

            server_name = (
                root.attrib.get("friendlyName")
                or root.attrib.get("machineIdentifier")
                or "Plex Media Server"
            )

            version = root.attrib.get("version", "Unknown")

            return {
                "success": True,
                "message": "Plex connection successful.",
                "server_name": server_name,
                "version": version,
            }

        except ET.ParseError:
            return {
                "success": False,
                "message": "Plex responded, but MediaSync could not parse the response.",
            }

        except requests.exceptions.ConnectionError:
            return {
                "success": False,
                "message": "Could not connect to Plex. Check the server URL.",
            }

        except requests.exceptions.Timeout:
            return {
                "success": False,
                "message": "Connection timed out. Check the Plex address.",
            }

        except requests.exceptions.RequestException as error:
            return {
                "success": False,
                "message": f"Plex connection failed: {error}",
            }

    def get_libraries(self) -> list[dict]:
        response = requests.get(
            f"{self.server_url}/library/sections",
            headers=self._headers(),
            params=self._params(),
            timeout=10,
        )

        response.raise_for_status()

        root = ET.fromstring(response.text)
        libraries = []

        for directory in root.findall("Directory"):
            library_id = directory.attrib.get("key")
            name = directory.attrib.get("title", "Unknown Library")
            library_type = self._normalize_library_type(
                directory.attrib.get("type", "")
            )

            if not library_id:
                continue

            libraries.append(
                {
                    "id": library_id,
                    "name": name,
                    "type": library_type,
                    "image_url": None,
                }
            )

        return libraries

    def scan_library(self, library_id: str, library_name: str | None = None) -> dict:
        try:
            response = requests.get(
                f"{self.server_url}/library/sections/{library_id}/refresh",
                headers=self._headers(),
                params=self._params(),
                timeout=15,
            )

            if response.status_code in {401, 403}:
                return {
                    "success": False,
                    "message": "Authentication failed. Check your Plex token.",
                }

            if response.status_code == 404:
                return {
                    "success": False,
                    "message": "Library not found in Plex.",
                }

            response.raise_for_status()

            display_name = library_name or library_id

            return {
                "success": True,
                "message": f"Plex library scan started for {display_name}.",
                "library_id": library_id,
                "library_name": library_name,
            }

        except requests.exceptions.ConnectionError:
            return {
                "success": False,
                "message": "Could not connect to Plex. Check the server URL.",
            }

        except requests.exceptions.Timeout:
            return {
                "success": False,
                "message": "Plex scan request timed out.",
            }

        except requests.exceptions.RequestException as error:
            return {
                "success": False,
                "message": f"Plex library scan failed: {error}",
            }

    def get_library_scan_status(
        self,
        library_id: str | None = None,
        library_name: str | None = None,
        scan_requested_at: str | None = None,
    ) -> dict:
        try:
            libraries = self.get_libraries()

            matching_library = None

            for library in libraries:
                if str(library.get("id")) == str(library_id):
                    matching_library = library
                    break

            if library_id and not matching_library:
                return {
                    "success": False,
                    "message": "Library not found in Plex.",
                    "running": False,
                    "progress": 0,
                    "library_id": library_id,
                    "library_name": library_name,
                }

            return {
                "success": True,
                "message": "Plex scan request accepted.",
                "running": False,
                "progress": 100,
                "state": "Complete",
                "task_status": "Complete",
                "task_name": "Library Scan",
                "library_id": library_id,
                "library_name": library_name,
            }

        except requests.exceptions.ConnectionError:
            return {
                "success": False,
                "message": "Could not connect to Plex. Check the server URL.",
                "running": False,
                "progress": 0,
            }

        except requests.exceptions.Timeout:
            return {
                "success": False,
                "message": "Plex scan status request timed out.",
                "running": False,
                "progress": 0,
            }

        except requests.exceptions.RequestException as error:
            return {
                "success": False,
                "message": f"Plex scan status failed: {error}",
                "running": False,
                "progress": 0,
            }

        except ET.ParseError:
            return {
                "success": False,
                "message": "Plex responded, but MediaSync could not parse the scan status response.",
                "running": False,
                "progress": 0,
            }

    def _normalize_library_type(self, plex_type: str) -> str:
        normalized_type = str(plex_type or "").strip().lower()

        if normalized_type == "movie":
            return "movies"

        if normalized_type == "show":
            return "tvshows"

        if normalized_type == "artist":
            return "music"

        if normalized_type == "photo":
            return "photos"

        return normalized_type or "unknown"
