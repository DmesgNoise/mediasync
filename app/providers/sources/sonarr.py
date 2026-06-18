import requests


class SonarrProvider:
    IMPORT_EVENT_TYPES = {
        "download",
        "episodefiledelete",
        "episodefileupgrade",
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
                    "message": "Authentication failed. Check your Sonarr API key.",
                }

            response.raise_for_status()
            data = response.json()

            return {
                "success": True,
                "message": "Sonarr connection successful.",
                "app_name": "Sonarr",
                "version": data.get("version", "Unknown"),
            }

        except requests.exceptions.ConnectionError:
            return {
                "success": False,
                "message": "Could not connect to Sonarr. Check the server URL.",
            }

        except requests.exceptions.Timeout:
            return {
                "success": False,
                "message": "Connection timed out. Check the Sonarr address.",
            }

        except requests.exceptions.RequestException as error:
            return {
                "success": False,
                "message": f"Sonarr connection failed: {error}",
            }

    def get_quality_profile_name(self, profile_id) -> str:
        try:
            normalized_profile_id = int(profile_id)
        except (TypeError, ValueError):
            return ""

        try:
            response = requests.get(
                f"{self.server_url}/api/v3/qualityprofile",
                headers=self._headers(),
                timeout=15,
            )

            if response.status_code == 401:
                return ""

            response.raise_for_status()
            profiles = response.json()

            if not isinstance(profiles, list):
                return ""

            for profile in profiles:
                try:
                    current_id = int(profile.get("id"))
                except (TypeError, ValueError):
                    continue

                if current_id == normalized_profile_id:
                    return str(profile.get("name") or "").strip()

        except requests.exceptions.RequestException:
            return ""

        return ""

    def get_queue_status(self) -> dict:
        try:
            response = requests.get(
                f"{self.server_url}/api/v3/queue",
                headers=self._headers(),
                params={
                    "page": 1,
                    "pageSize": 500,
                },
                timeout=30,
            )

            if response.status_code == 401:
                return {
                    "success": False,
                    "active": True,
                    "count": 0,
                    "message": "Authentication failed while checking Sonarr queue.",
                }

            response.raise_for_status()
            data = response.json()

            records = data.get("records") or []
            total_records = data.get("totalRecords")

            try:
                count = int(total_records)
            except (TypeError, ValueError):
                count = len(records)

            return {
                "success": True,
                "active": count > 0,
                "count": count,
                "records": records,
                "message": (
                    f"Sonarr queue active with {count} item(s)."
                    if count > 0
                    else "Sonarr queue is empty."
                ),
            }

        except requests.exceptions.ConnectionError:
            return {
                "success": False,
                "active": True,
                "count": 0,
                "message": "Could not connect to Sonarr while checking queue.",
            }

        except requests.exceptions.Timeout:
            return {
                "success": False,
                "active": True,
                "count": 0,
                "message": "Timed out while checking Sonarr queue.",
            }

        except requests.exceptions.RequestException as error:
            return {
                "success": False,
                "active": True,
                "count": 0,
                "message": f"Sonarr queue check failed: {error}",
            }

    def register_mediasync_webhook(self, webhook_url: str) -> dict:
        return self._register_webhook(
            webhook_url=webhook_url,
            app_name="Sonarr",
        )

    def _register_webhook(self, webhook_url: str, app_name: str) -> dict:
        try:
            existing = self._find_existing_webhook()

            payload = {
                "name": "MediaSync",
                "implementation": "Webhook",
                "implementationName": "Webhook",
                "configContract": "WebhookSettings",
                "infoLink": "https://wiki.servarr.com/sonarr/supported#webhook",
                "tags": [],
                "onGrab": True,
                "onDownload": True,
                "onUpgrade": True,
                "onRename": True,
                "onSeriesAdd": False,
                "onSeriesDelete": True,
                "onEpisodeFileDelete": True,
                "onEpisodeFileDeleteForUpgrade": False,
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
        is_grab = normalized_event == "grab"
        is_delete = normalized_event in {"seriesdelete", "episodefiledelete"}

        series = payload.get("series") or {}
        episodes = payload.get("episodes") or []
        episode_file = payload.get("episodeFile") or {}
        release = payload.get("release") or {}

        series_title = (
            series.get("title")
            or payload.get("seriesTitle")
            or "Unknown series"
        )

        episode_label = ""

        if episodes:
            first_episode = episodes[0]
            season_number = first_episode.get("seasonNumber")
            episode_number = first_episode.get("episodeNumber")

            if season_number is not None and episode_number is not None:
                episode_label = f" S{int(season_number):02d}E{int(episode_number):02d}"

        media_title = f"{series_title}{episode_label}"

        file_path = (
            episode_file.get("path")
            or payload.get("episodeFilePath")
            or payload.get("path")
        )

        file_name = SonarrProvider._first_present(
            episode_file.get("relativePath"),
            SonarrProvider._basename(episode_file.get("path")),
            SonarrProvider._basename(payload.get("episodeFilePath")),
            SonarrProvider._basename(payload.get("path")),
            release.get("title"),
        )

        should_scan = normalized_event in SonarrProvider.IMPORT_EVENT_TYPES

        if not should_scan and "download" in normalized_event:
            should_scan = True

        if not should_scan and "import" in normalized_event:
            should_scan = True

        return {
            "should_scan": should_scan,
            "is_grab": is_grab,
            "is_delete": is_delete,
            "event_type": event_type or "unknown",
            "media_type": "tv",
            "media_title": series_title,
            "tmdb_id": series.get("tmdbId") or series.get("tmdb_id"),
            "tvdb_id": series.get("tvdbId") or series.get("tvdb_id"),
            "imdb_id": series.get("imdbId") or series.get("imdb_id"),
            "file_name": file_name,
            "file_path": file_path,
            "message": (
                f"Sonarr {event_type} event received for {media_title}."
                if event_type
                else f"Sonarr webhook received for {media_title}."
            ),
            "raw": payload,
        }
