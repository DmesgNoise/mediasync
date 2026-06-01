import requests


class RadarrProvider:
    IMPORT_EVENT_TYPES = {
        "download",
        "moviefiledelete",
        "moviefileupgrade",
        "rename",
    }

    def __init__(self, server_url: str, api_key: str):
        self.server_url = server_url.rstrip("/")
        self.api_key = api_key

    def _headers(self) -> dict:
        return {
            "X-Api-Key": self.api_key,
            "Accept": "application/json",
        }

    def test_connection(self) -> dict:
        try:
            response = requests.get(
                f"{self.server_url}/api/v3/system/status",
                headers=self._headers(),
                timeout=10,
            )

            if response.status_code == 401:
                return {
                    "success": False,
                    "message": "Authentication failed. Check your Radarr API key.",
                }

            response.raise_for_status()
            data = response.json()

            return {
                "success": True,
                "message": "Radarr connection successful.",
                "app_name": "Radarr",
                "version": data.get("version", "Unknown"),
            }

        except requests.exceptions.ConnectionError:
            return {
                "success": False,
                "message": "Could not connect to Radarr. Check the server URL.",
            }

        except requests.exceptions.Timeout:
            return {
                "success": False,
                "message": "Connection timed out. Check the Radarr address.",
            }

        except requests.exceptions.RequestException as error:
            return {
                "success": False,
                "message": f"Radarr connection failed: {error}",
            }

    def register_mediasync_webhook(self, webhook_url: str) -> dict:
        return self._register_webhook(
            webhook_url=webhook_url,
            app_name="Radarr",
        )

    def _register_webhook(self, webhook_url: str, app_name: str) -> dict:
        try:
            existing = self._find_existing_webhook()

            payload = {
                "name": "MediaSync",
                "implementation": "Webhook",
                "implementationName": "Webhook",
                "configContract": "WebhookSettings",
                "infoLink": "https://wiki.servarr.com/radarr/supported#webhook",
                "tags": [],
                "onGrab": False,
                "onDownload": True,
                "onUpgrade": True,
                "onRename": True,
                "onMovieAdded": False,
                "onMovieDelete": False,
                "onMovieFileDelete": True,
                "onMovieFileDeleteForUpgrade": False,
                "onHealthIssue": False,
                "includeHealthWarnings": False,
                "onHealthRestored": False,
                "onApplicationUpdate": False,
                "onManualInteractionRequired": False,
                "fields": [
                    {
                        "name": "url",
                        "value": webhook_url,
                    },
                    {
                        "name": "method",
                        "value": 1,
                    },
                    {
                        "name": "headers",
                        "value": [],
                    },
                ],
            }

            if existing:
                requests.delete(
                    f"{self.server_url}/api/v3/notification/{existing['id']}",
                    headers=self._headers(),
                    timeout=30,
                )

            response = requests.post(
                f"{self.server_url}/api/v3/notification",
                headers=self._headers(),
                json=payload,
                timeout=30,
            )
            action = "created"

            if response.status_code == 401:
                return {
                    "attempted": True,
                    "success": False,
                    "message": f"{app_name} authentication failed while registering webhook.",
                }

            response.raise_for_status()

            return {
                "attempted": True,
                "success": True,
                "message": f"{app_name} MediaSync webhook {action}.",
                "webhook_url": webhook_url,
            }

        except requests.exceptions.RequestException as error:
            return {
                "attempted": True,
                "success": False,
                "message": f"{app_name} webhook registration failed: {error}",
                "webhook_url": webhook_url,
            }

    def _find_existing_webhook(self) -> dict | None:
        response = requests.get(
            f"{self.server_url}/api/v3/notification",
            headers=self._headers(),
            timeout=30,
        )
        response.raise_for_status()

        for item in response.json():
            if str(item.get("name", "")).strip().lower() == "mediasync":
                return item

        return None

    @staticmethod
    def _basename(value):
        if not value:
            return None

        normalized = str(value).strip().replace("\\", "/").rstrip("/")

        if not normalized:
            return None

        return normalized.split("/")[-1]

    @staticmethod
    def _first_present(*values):
        for value in values:
            if value:
                normalized = str(value).strip()

                if normalized:
                    return normalized

        return None

    @staticmethod
    def parse_webhook_payload(payload: dict) -> dict:
        event_type = str(payload.get("eventType", "")).strip()
        normalized_event = event_type.lower()

        movie = payload.get("movie") or {}
        movie_file = payload.get("movieFile") or {}
        release = payload.get("release") or {}

        media_title = (
            movie.get("title")
            or payload.get("movieTitle")
            or release.get("title")
            or "Unknown movie"
        )

        file_path = (
            movie_file.get("path")
            or payload.get("movieFilePath")
            or payload.get("path")
        )

        file_name = RadarrProvider._first_present(
            movie_file.get("relativePath"),
            RadarrProvider._basename(movie_file.get("path")),
            RadarrProvider._basename(payload.get("movieFilePath")),
            RadarrProvider._basename(payload.get("path")),
            release.get("title"),
        )

        should_scan = normalized_event in RadarrProvider.IMPORT_EVENT_TYPES

        if not should_scan and "download" in normalized_event:
            should_scan = True

        if not should_scan and "import" in normalized_event:
            should_scan = True

        return {
            "should_scan": should_scan,
            "event_type": event_type or "unknown",
            "media_title": media_title,
            "file_name": file_name,
            "file_path": file_path,
            "message": (
                f"Radarr {event_type} event received for {media_title}."
                if event_type
                else f"Radarr webhook received for {media_title}."
            ),
            "raw": payload,
        }
