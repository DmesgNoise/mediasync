import asyncio
import json
import os
import secrets
import time
from datetime import datetime, timezone

import requests
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI, Form, HTTPException, Request
from fastapi.responses import FileResponse, RedirectResponse, StreamingResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from starlette.middleware.sessions import SessionMiddleware

from app.api.downloaders import router as downloaders_router
from app.api.request_apps import router as request_apps_router
from app.api.server import router as server_router
from app.api.settings import router as settings_router
from app.api.source import router as source_router
from app.database import (
    admin_exists,
    authenticate_admin,
    create_admin_user,
    get_activity_events,
    get_admin_user,
    get_app_settings,
    get_downloaders,
    get_media_server,
    get_lifecycle,
    get_request_apps,
    get_sources,
    init_db,
    register_activity_loop,
    subscribe_activity_queue,
    unsubscribe_activity_queue,
)
from app.providers.downloaders.base import build_downloader_provider
from app.providers.request_apps.base import build_request_app_provider


@asynccontextmanager
async def lifespan(app: FastAPI):
    init_db()
    register_activity_loop(asyncio.get_running_loop())
    yield


app = FastAPI(
    title="MediaSync",
    lifespan=lifespan,
)

TV_MEDIA_SERVER_EPISODE_CACHE = {}
TV_MEDIA_SERVER_EPISODE_CACHE_TTL_SECONDS = 15

MEDIASYNC_VERSION = os.getenv("MEDIASYNC_VERSION", "dev")


def _get_session_secret():
    env_secret = os.environ.get("MEDIASYNC_SESSION_SECRET", "").strip()

    if env_secret:
        return env_secret

    secret_path = Path("/config/session_secret")
    secret_path.parent.mkdir(parents=True, exist_ok=True)

    if secret_path.exists():
        existing_secret = secret_path.read_text().strip()
        if existing_secret:
            return existing_secret

    new_secret = secrets.token_urlsafe(48)
    secret_path.write_text(new_secret)
    return new_secret


templates = Jinja2Templates(
    directory="app/templates",
)

templates.env.globals["mediasync_version"] = MEDIASYNC_VERSION

def compact_datetime(value):
    if not value:
        return ""

    raw_value = str(value).strip()

    for fmt in ("%Y-%m-%d %H:%M:%S", "%Y-%m-%dT%H:%M:%S"):
        try:
            parsed = datetime.strptime(raw_value[:19], fmt)
            return parsed.strftime("%b %-d, %-I:%M %p")
        except ValueError:
            continue

    return raw_value


templates.env.filters["compact_datetime"] = compact_datetime

app.mount(
    "/static",
    StaticFiles(directory="app/static"),
    name="static",
)

app.include_router(server_router)
app.include_router(source_router)
app.include_router(settings_router)
app.include_router(request_apps_router)
app.include_router(downloaders_router)


def _is_setup_complete():
    media_server = get_media_server()
    sources = get_sources()

    if not media_server:
        return False

    if not media_server.get("connected"):
        return False

    if not str(media_server.get("server_url", "")).strip():
        return False

    if not str(media_server.get("api_key", "")).strip():
        return False

    if not sources:
        return False

    for source in sources:
        if not str(source.get("source_name", "")).strip():
            return False

        if not str(source.get("source_type", "")).strip():
            return False

        if not str(source.get("source_url", "")).strip():
            return False

        if not str(source.get("api_key", "")).strip():
            return False

        if not source.get("connected"):
            return False

        if not source.get("libraries"):
            return False

    return True


def _is_logged_in(request: Request):
    user_id = request.session.get("admin_user_id")
    return get_admin_user(user_id) is not None


def _set_login_session(request: Request, user):
    request.session.clear()
    request.session["admin_user_id"] = user["id"]
    request.session["admin_username"] = user["username"]


def _get_post_login_redirect():
    if _is_setup_complete():
        return "/"

    return "/setup"


def _empty_request_counts():
    return {
        "total": 0,
        "movie": 0,
        "tv": 0,
        "pending": 0,
        "approved": 0,
        "declined": 0,
        "processing": 0,
        "available": 0,
        "completed": 0,
    }


def _safe_int(value, default=0):
    try:
        return int(value)
    except (TypeError, ValueError):
        return default


def _normalize_request_count_data(result):
    counts = _empty_request_counts()

    if not result or not result.get("success"):
        return counts

    raw_counts = result.get("data")

    if raw_counts is None:
        raw_counts = result

    if not isinstance(raw_counts, dict):
        return counts

    for key in counts:
        counts[key] = _safe_int(raw_counts.get(key), 0)

    return counts



def _downloader_auth_value(downloader: dict | None) -> str:
    if not downloader:
        return ""

    api_key = str(downloader.get("api_key") or "").strip()

    if api_key:
        return api_key

    username = str(downloader.get("username") or "").strip()
    password = str(downloader.get("password") or "").strip()

    if username or password:
        return f"{username}:{password}"

    return ""


def _empty_downloader_totals():
    return {
        "active": 0,
        "total": 0,
        "speed": "0 B/s",
        "timeleft": "",
    }


def _get_downloader_dashboard_stats(downloaders):
    downloader_stats = {}
    totals = _empty_downloader_totals()

    for downloader in downloaders:
        stats = {
            "success": False,
            "message": "",
            "queue": {},
        }

        provider = build_downloader_provider(
            downloader_type=downloader.get("downloader_type"),
            server_url=downloader.get("downloader_url"),
            api_key=_downloader_auth_value(downloader),
        )

        if not provider:
            stats["message"] = "Unsupported downloader type."
            downloader_stats[downloader["id"]] = stats
            continue

        try:
            result = provider.get_queue()
            stats["success"] = bool(result.get("success"))
            stats["message"] = result.get("message", "")
            stats["queue"] = result if result.get("success") else {}
        except Exception as error:
            stats["success"] = False
            stats["message"] = f"Downloader queue unavailable: {error}"

        queue = stats.get("queue") or {}
        totals["active"] += _safe_int(queue.get("active_count"), 0)
        totals["total"] += _safe_int(queue.get("total_count"), 0)

        if queue.get("speed") and queue.get("speed") != "0 B/s":
            totals["speed"] = queue.get("speed")

        if queue.get("timeleft") and queue.get("timeleft") != "0:00:00":
            totals["timeleft"] = queue.get("timeleft")

        downloader_stats[downloader["id"]] = stats

    return downloader_stats, totals



def _empty_source_queue_stats():
    return {
        "success": False,
        "count": 0,
        "message": "Queue unavailable.",
    }


def _get_source_queue_count(source):
    source_url = str((source or {}).get("source_url") or "").strip().rstrip("/")
    api_key = str((source or {}).get("api_key") or "").strip()
    source_type = str((source or {}).get("source_type") or "").strip().lower()

    if source_type not in {"radarr", "sonarr"}:
        return {
            "success": False,
            "count": 0,
            "message": "Unsupported source type.",
        }

    if not source_url or not api_key:
        return {
            "success": False,
            "count": 0,
            "message": "Source URL or API key is missing.",
        }

    try:
        response = requests.get(
            f"{source_url}/api/v3/queue",
            headers={
                "X-Api-Key": api_key,
                "Accept": "application/json",
            },
            params={
                "page": 1,
                "pageSize": 500,
            },
            timeout=15,
        )

        if response.status_code == 401:
            return {
                "success": False,
                "count": 0,
                "message": "Authentication failed while checking queue.",
            }

        response.raise_for_status()
        data = response.json()
    except Exception as error:
        return {
            "success": False,
            "count": 0,
            "message": f"Queue unavailable: {error}",
        }

    records = data.get("records") if isinstance(data, dict) else []
    total_records = data.get("totalRecords") if isinstance(data, dict) else None

    try:
        count = int(total_records)
    except (TypeError, ValueError):
        count = len(records) if isinstance(records, list) else 0

    return {
        "success": True,
        "count": count,
        "message": "Queue active." if count else "Queue empty.",
    }


def _get_source_queue_dashboard_stats(sources):
    source_queue_stats = {}

    for source in sources:
        source_queue_stats[source["id"]] = _get_source_queue_count(source)

    return source_queue_stats


def _logo_file_for_downloader(downloader_type):
    normalized_type = str(downloader_type or "").strip().lower()

    if normalized_type == "sabnzbd":
        return "sab-logo.png"

    return f"{normalized_type}-logo.png" if normalized_type else "default.png"


def _build_dashboard_action_items(request_apps, request_app_stats, sources, source_queue_stats, downloaders, downloader_stats):
    items = []

    for request_app in request_apps:
        if not request_app.get("connected"):
            continue

        stats = request_app_stats.get(request_app.get("id"), {})
        counts = stats.get("counts") or {}
        app_type = str(request_app.get("app_type") or "").strip().lower()

        items.append(
            {
                "kind": "request_app",
                "id": request_app.get("id"),
                "name": request_app.get("app_name") or "Request App",
                "label": f"{request_app.get('app_name') or 'Request App'} Requests",
                "value": _safe_int(counts.get("pending"), 0),
                "helper": "Pending",
                "logo": f"{app_type}-logo.png" if app_type else "default.png",
                "success": bool(stats.get("success", True)),
            }
        )

    for source in sources:
        if not source.get("connected"):
            continue

        source_type = str(source.get("source_type") or "").strip().lower()

        if source_type not in {"radarr", "sonarr"}:
            continue

        stats = source_queue_stats.get(source.get("id"), {})
        source_name = source.get("source_name") or source_type.capitalize()

        items.append(
            {
                "kind": "source",
                "id": source.get("id"),
                "name": source_name,
                "label": f"{source_name} Queue",
                "value": _safe_int(stats.get("count"), 0),
                "helper": "In queue",
                "logo": f"{source_type}-logo.png",
                "success": bool(stats.get("success", True)),
            }
        )

    for downloader in downloaders:
        if not downloader.get("connected"):
            continue

        stats = downloader_stats.get(downloader.get("id"), {})
        queue = stats.get("queue") or {}
        downloader_type = str(downloader.get("downloader_type") or "").strip().lower()
        downloader_name = downloader.get("downloader_name") or "Downloader"

        items.append(
            {
                "kind": "downloader",
                "id": downloader.get("id"),
                "name": downloader_name,
                "label": f"{downloader_name} Downloading",
                "value": _safe_int(queue.get("active_count"), 0),
                "helper": "Downloading",
                "logo": _logo_file_for_downloader(downloader_type),
                "success": bool(stats.get("success", True)),
            }
        )

    return items

def _get_request_app_dashboard_stats(request_apps):
    request_app_stats = {}
    totals = _empty_request_counts()

    for request_app in request_apps:
        stats = {
            "success": False,
            "counts": _empty_request_counts(),
            "message": "",
        }

        provider = build_request_app_provider(
            app_type=request_app.get("app_type"),
            server_url=request_app.get("app_url"),
            api_key=request_app.get("api_key"),
        )

        if not provider:
            stats["message"] = "Unsupported request app type."
            request_app_stats[request_app["id"]] = stats
            continue

        try:
            result = provider.get_request_counts()
            stats["success"] = bool(result.get("success"))
            stats["message"] = result.get("message", "")
            stats["counts"] = _normalize_request_count_data(result)
        except Exception as error:
            stats["success"] = False
            stats["message"] = f"Request counts unavailable: {error}"

        for key, value in stats["counts"].items():
            totals[key] = totals.get(key, 0) + _safe_int(value, 0)

        request_app_stats[request_app["id"]] = stats

    return request_app_stats, totals



def _service_status_healthy(details: str = "No warnings reported.") -> dict:
    return {
        "reachable": True,
        "state": "good",
        "label": "✓ Healthy",
        "details": details,
    }


def _service_status_warning(label: str, details: str) -> dict:
    return {
        "reachable": True,
        "state": "warning",
        "label": f"⚠ {label}",
        "details": details or label,
    }


def _service_status_error(label: str, details: str, reachable: bool = True) -> dict:
    return {
        "reachable": bool(reachable),
        "state": "error",
        "label": f"✕ {label}",
        "details": details or label,
    }


def _service_status_disconnected(name: str = "Service") -> dict:
    return _service_status_error(
        label="Disconnected",
        details=f"{name} is not reachable. Check the URL, API key, and container/network status.",
        reachable=False,
    )


def _first_status_value(data, keys):
    if isinstance(data, dict):
        for key in keys:
            if key in data and data.get(key) not in (None, ""):
                return data.get(key)

        for value in data.values():
            found = _first_status_value(value, keys)

            if found not in (None, ""):
                return found

    if isinstance(data, list):
        for item in data:
            found = _first_status_value(item, keys)

            if found not in (None, ""):
                return found

    return None


def _status_truthy(value) -> bool:
    if isinstance(value, bool):
        return value

    if isinstance(value, (int, float)):
        return value > 0

    normalized = str(value or "").strip().lower()
    return normalized in {"1", "true", "yes", "available", "update_available", "outdated"}


def _request_app_update_status(request_app: dict, stats: dict) -> dict:
    app_name = request_app.get("app_name") or "Request app"

    if not request_app.get("connected"):
        return _service_status_disconnected(app_name)

    if stats and not stats.get("success", True):
        return _service_status_error(
            label="API Warning",
            details=stats.get("message") or f"{app_name} responded, but MediaSync could not read request data.",
            reachable=True,
        )

    provider = build_request_app_provider(
        app_type=request_app.get("app_type"),
        server_url=request_app.get("app_url"),
        api_key=request_app.get("api_key"),
    )

    if not provider or not hasattr(provider, "get_status"):
        return _service_status_healthy()

    try:
        status_result = provider.get_status()
    except Exception as error:
        return _service_status_error(
            label="API Warning",
            details=f"{app_name} status check failed: {error}",
            reachable=True,
        )

    if not status_result.get("success"):
        return _service_status_error(
            label="API Warning",
            details=status_result.get("message") or f"{app_name} status check failed.",
            reachable=True,
        )

    data = status_result.get("data") or {}

    update_available = _first_status_value(
        data,
        (
            "updateAvailable",
            "update_available",
            "hasUpdate",
            "has_update",
            "isUpdateAvailable",
            "updateAvailableRestartRequired",
        ),
    )

    latest_version = _first_status_value(
        data,
        (
            "latestVersion",
            "latest_version",
            "newVersion",
            "new_version",
            "availableVersion",
            "available_version",
            "currentVersion",
            "current_version",
        ),
    )

    current_version = (
        request_app.get("version")
        or _first_status_value(data, ("version", "appVersion", "app_version"))
        or "installed version"
    )

    if _status_truthy(update_available):
        details = f"Update available for {app_name}."

        if latest_version:
            details = f"Update available for {app_name}: {current_version} → {latest_version}"

        return _service_status_warning("Update Available", details)

    return _service_status_healthy()


def _arr_api_get(source: dict, endpoint: str, params: dict | None = None) -> dict:
    source_url = str((source or {}).get("source_url") or "").strip().rstrip("/")
    api_key = str((source or {}).get("api_key") or "").strip()

    if not source_url or not api_key:
        return {
            "success": False,
            "message": "Source URL or API key is missing.",
            "reachable": False,
        }

    try:
        response = requests.get(
            f"{source_url}/api/v3/{endpoint.lstrip('/')}",
            headers={
                "X-Api-Key": api_key,
                "Accept": "application/json",
            },
            params=params or {},
            timeout=12,
        )

        if response.status_code in (401, 403):
            return {
                "success": False,
                "message": "Authentication failed. Check the API key.",
                "reachable": True,
            }

        response.raise_for_status()

        try:
            data = response.json()
        except ValueError:
            data = {}

        return {
            "success": True,
            "message": "Request successful.",
            "data": data,
            "reachable": True,
        }
    except requests.exceptions.ConnectionError:
        return {
            "success": False,
            "message": "Could not connect to service.",
            "reachable": False,
        }
    except requests.exceptions.Timeout:
        return {
            "success": False,
            "message": "Service status check timed out.",
            "reachable": False,
        }
    except Exception as error:
        return {
            "success": False,
            "message": f"Service status check failed: {error}",
            "reachable": True,
        }


def _arr_health_issue_is_update(issue: dict) -> bool:
    if not isinstance(issue, dict):
        return False

    source = str(issue.get("source") or "").strip().lower()
    message = str(issue.get("message") or issue.get("errorMessage") or issue.get("details") or "").strip().lower()
    wiki_url = str(issue.get("wikiUrl") or "").strip().lower()

    if source == "updatecheck":
        return True

    if "new update is available" in message:
        return True

    if "new-update-is-available" in wiki_url:
        return True

    return False


def _arr_health_update_message(issue: dict) -> str:
    message = str((issue or {}).get("message") or "").strip()

    if message:
        return message

    return "Update available."


def _arr_health_issue_message(issue: dict) -> str:
    if not isinstance(issue, dict):
        return "Unknown health warning"

    source = str(issue.get("source") or issue.get("type") or issue.get("wikiUrl") or "").strip()
    message = str(issue.get("message") or issue.get("errorMessage") or issue.get("details") or "").strip()

    if source and message:
        return f"{source}: {message}"

    return message or source or "Unknown health warning"


def _arr_version_tuple(value: str) -> tuple:
    parts = []

    for chunk in str(value or "").replace("-", ".").split("."):
        digits = "".join(character for character in chunk if character.isdigit())

        if digits:
            parts.append(int(digits))

    return tuple(parts)


def _arr_update_available(source: dict) -> dict:
    result = _arr_api_get(source, "update")

    if not result.get("success"):
        return {
            "available": False,
            "details": "",
        }

    data = result.get("data")

    if not isinstance(data, list) or not data:
        return {
            "available": False,
            "details": "",
        }

    installed_version = str(source.get("version") or "").strip()
    installed_tuple = _arr_version_tuple(installed_version)

    for item in data:
        if not isinstance(item, dict):
            continue

        version = str(
            item.get("version")
            or item.get("latestVersion")
            or item.get("newVersion")
            or ""
        ).strip()

        if not version or version == installed_version:
            continue

        version_tuple = _arr_version_tuple(version)

        if installed_tuple and version_tuple and version_tuple <= installed_tuple:
            continue

        installed_major = installed_tuple[0] if installed_tuple else None
        update_major = version_tuple[0] if version_tuple else None

        # Mirror Arr UI health behavior: do not warn for manual major upgrades
        # such as Sonarr v3 -> v4 when /api/v3/health reports no issues.
        if installed_major is not None and update_major is not None and update_major > installed_major:
            continue

        return {
            "available": True,
            "details": (
                f"Update available: {installed_version} → {version}"
                if installed_version and version
                else "Update available."
            ),
        }

    return {
        "available": False,
        "details": "",
    }


def _source_service_status(source: dict, queue_stats: dict | None = None) -> dict:
    source_name = source.get("source_name") or "Source"
    source_type = str(source.get("source_type") or "").strip().lower()

    if not source.get("connected"):
        return _service_status_disconnected(source_name)

    if source_type not in {"radarr", "sonarr"}:
        return _service_status_healthy()

    health_result = _arr_api_get(source, "health")

    if not health_result.get("success"):
        return _service_status_error(
            label="Unreachable" if not health_result.get("reachable") else "API Warning",
            details=health_result.get("message") or f"{source_name} health check failed.",
            reachable=bool(health_result.get("reachable")),
        )

    health_items = health_result.get("data")

    if isinstance(health_items, list) and health_items:
        update_items = [
            item
            for item in health_items
            if _arr_health_issue_is_update(item)
        ]
        problem_items = [
            item
            for item in health_items
            if not _arr_health_issue_is_update(item)
        ]

        if problem_items:
            messages = [_arr_health_issue_message(item) for item in problem_items]
            label = "1 Warning" if len(messages) == 1 else f"{len(messages)} Warnings"

            return _service_status_error(
                label=label,
                details=" | ".join(messages),
                reachable=True,
            )

        if update_items:
            update_messages = [_arr_health_update_message(item) for item in update_items]

            return _service_status_warning(
                label="Update Available",
                details=" | ".join(update_messages) or f"Update available for {source_name}.",
            )

    update = _arr_update_available(source)

    if update.get("available"):
        return _service_status_warning(
            label="Update Available",
            details=update.get("details") or f"Update available for {source_name}.",
        )

    if queue_stats and not queue_stats.get("success", True):
        return _service_status_error(
            label="API Warning",
            details=queue_stats.get("message") or f"{source_name} queue check failed.",
            reachable=True,
        )

    return _service_status_healthy()


def _downloader_service_status(downloader: dict, stats: dict | None = None) -> dict:
    downloader_name = downloader.get("downloader_name") or "Downloader"

    if not downloader.get("connected"):
        return _service_status_disconnected(downloader_name)

    if stats and not stats.get("success", True):
        return _service_status_error(
            label="API Warning",
            details=stats.get("message") or f"{downloader_name} queue check failed.",
            reachable=True,
        )

    return _service_status_healthy()


def _media_server_service_status(media_server: dict | None) -> dict:
    if not media_server:
        return _service_status_disconnected("Media server")

    if not media_server.get("connected"):
        return _service_status_disconnected(_media_server_type_label(media_server.get("server_type")))

    return _service_status_healthy()


def _build_service_status_maps(media_server, request_apps, request_app_stats, sources, source_queue_stats, downloaders, downloader_stats):
    return {
        "media_server": _media_server_service_status(media_server),
        "request_apps": {
            request_app["id"]: _request_app_update_status(
                request_app=request_app,
                stats=request_app_stats.get(request_app.get("id"), {}),
            )
            for request_app in request_apps
        },
        "sources": {
            source["id"]: _source_service_status(
                source=source,
                queue_stats=source_queue_stats.get(source.get("id"), {}),
            )
            for source in sources
        },
        "downloaders": {
            downloader["id"]: _downloader_service_status(
                downloader=downloader,
                stats=downloader_stats.get(downloader.get("id"), {}),
            )
            for downloader in downloaders
        },
    }



def _find_configured_library(library_id):
    target = str(library_id or "").strip()

    for source in get_sources():
        for library in source.get("libraries") or []:
            if str(library.get("library_id") or "").strip() == target:
                return source, library

    return None, None


def _library_count_item_type(library, source=None):
    source_type = str((source or {}).get("source_type") or "").strip().lower()
    library_type = str((library or {}).get("library_type") or "").strip().lower()
    library_name = str((library or {}).get("library_name") or "").strip().lower()

    if source_type == "sonarr":
        return "Series", "Shows"

    if source_type == "radarr":
        return "Movie", "Movies"

    if library_type in {"tvshows", "tv", "series", "shows"} or "tv" in library_name or "show" in library_name:
        return "Series", "Shows"

    return "Movie", "Movies"


def _get_emby_family_library_count(media_server, library_id, item_type):
    server_url = str((media_server or {}).get("server_url") or "").strip().rstrip("/")
    api_key = str((media_server or {}).get("api_key") or "").strip()

    if not server_url or not api_key or not library_id:
        return {
            "success": False,
            "item_count": 0,
            "message": "Media server configuration is incomplete.",
        }

    try:
        response = requests.get(
            f"{server_url}/Items",
            headers={
                "X-Emby-Token": api_key,
                "Accept": "application/json",
            },
            params={
                "ParentId": library_id,
                "Recursive": "true",
                "IncludeItemTypes": item_type,
                "Limit": "1",
            },
            timeout=15,
        )
        response.raise_for_status()
        data = response.json()
    except Exception as error:
        return {
            "success": False,
            "item_count": 0,
            "message": f"Library count unavailable: {error}",
        }

    return {
        "success": True,
        "item_count": _safe_int(data.get("TotalRecordCount"), 0) if isinstance(data, dict) else 0,
        "message": "Library count refreshed.",
    }


def _dashboard_library_count_payload(library_id):
    source, library = _find_configured_library(library_id)

    if not library:
        return {
            "success": False,
            "item_count": 0,
            "label": "Count unavailable",
            "message": "Configured library not found.",
        }

    media_server = get_media_server()
    server_type = str((media_server or {}).get("server_type") or "").strip().lower()
    item_type, label_type = _library_count_item_type(library, source)

    if server_type not in {"emby", "jellyfin"}:
        return {
            "success": False,
            "item_count": 0,
            "label": "Count unavailable",
            "message": "Library counts are not supported for this media server yet.",
        }

    result = _get_emby_family_library_count(media_server, library.get("library_id"), item_type)
    count = _safe_int(result.get("item_count"), 0)

    return {
        "success": bool(result.get("success")),
        "library_id": library.get("library_id"),
        "library_name": library.get("library_name"),
        "item_count": count,
        "item_type": label_type,
        "label": f"{count:,} {label_type}",
        "message": result.get("message", ""),
    }

@app.middleware("http")
async def auth_and_setup_gate(request: Request, call_next):
    path = request.url.path
    auth_paths = {"/auth/setup", "/login", "/logout"}
    setup_paths = {"/setup", "/setup/sources", "/setup/summary"}

    if (
        path.startswith("/static")
        or path == "/health"
        or path == "/manifest.webmanifest"
        or path == "/sw.js"
    ):
        return await call_next(request)

    has_admin = admin_exists()
    logged_in = _is_logged_in(request)

    if path.startswith("/api"):
        webhook_paths = (
            path.startswith("/api/source/webhook/")
            or path.startswith("/api/request-apps/webhook/seerr/")
        )

        if webhook_paths:
            return await call_next(request)

        if not has_admin:
            return RedirectResponse(url="/auth/setup", status_code=303)

        if not logged_in:
            return RedirectResponse(url="/login", status_code=303)

        return await call_next(request)

    if not has_admin:
        if path != "/auth/setup":
            return RedirectResponse(url="/auth/setup", status_code=303)
        return await call_next(request)

    if logged_in and path in {"/auth/setup", "/login"}:
        return RedirectResponse(url=_get_post_login_redirect(), status_code=303)

    if not logged_in and path not in auth_paths:
        return RedirectResponse(url="/login", status_code=303)

    if not logged_in:
        return await call_next(request)

    setup_complete = _is_setup_complete()

    if not setup_complete and path not in setup_paths:
        return RedirectResponse(url="/setup", status_code=303)

    if setup_complete and path in setup_paths:
        return RedirectResponse(url="/settings", status_code=303)

    return await call_next(request)


@app.get("/auth/setup")
async def auth_setup(request: Request):
    return templates.TemplateResponse(
        request,
        "auth_setup.html",
        {
            "active_page": "auth_setup",
            "app_name": "MediaSync",
            "media_server": get_media_server(),
            "error": None,
        },
    )


@app.post("/auth/setup")
async def create_auth_setup(
    request: Request,
    username: str = Form(...),
    password: str = Form(...),
    confirm_password: str = Form(...),
):
    if password != confirm_password:
        return templates.TemplateResponse(
            request,
            "auth_setup.html",
            {
                "active_page": "auth_setup",
                "app_name": "MediaSync",
                "media_server": get_media_server(),
                "error": "Passwords do not match.",
                "username": username,
            },
            status_code=400,
        )

    result = create_admin_user(username=username, password=password)

    if not result.get("success"):
        return templates.TemplateResponse(
            request,
            "auth_setup.html",
            {
                "active_page": "auth_setup",
                "app_name": "MediaSync",
                "media_server": get_media_server(),
                "error": result.get("message", "Unable to create admin account."),
                "username": username,
            },
            status_code=400,
        )

    _set_login_session(
        request,
        {
            "id": result["user_id"],
            "username": result["username"],
        },
    )

    return RedirectResponse(url=_get_post_login_redirect(), status_code=303)


@app.get("/login")
async def login(request: Request):
    return templates.TemplateResponse(
        request,
        "login.html",
        {
            "active_page": "login",
            "app_name": "MediaSync",
            "media_server": get_media_server(),
            "error": None,
        },
    )


@app.post("/login")
async def login_submit(
    request: Request,
    username: str = Form(...),
    password: str = Form(...),
):
    user = authenticate_admin(username=username, password=password)

    if not user:
        return templates.TemplateResponse(
            request,
            "login.html",
            {
                "active_page": "login",
                "app_name": "MediaSync",
                "media_server": get_media_server(),
                "error": "Invalid username or password.",
                "username": username,
            },
            status_code=401,
        )

    _set_login_session(request, user)
    return RedirectResponse(url=_get_post_login_redirect(), status_code=303)


@app.get("/logout")
async def logout(request: Request):
    request.session.clear()
    return RedirectResponse(url="/login", status_code=303)


@app.get("/")
@app.get("/dashboard")
async def dashboard(request: Request):
    media_server = get_media_server()
    sources = get_sources()
    request_apps = get_request_apps()
    downloaders = get_downloaders()
    settings = get_app_settings()

    library_count = sum(
        len(source.get("libraries", []))
        for source in sources
    )

    activity_display_limit = _safe_int(settings.get("activity_display_limit"), 20)
    if activity_display_limit <= 0:
        activity_display_limit = 20

    recent_events = get_activity_events(limit=activity_display_limit)
    request_app_stats, request_totals = _get_request_app_dashboard_stats(request_apps)
    downloader_stats, downloader_totals = _get_downloader_dashboard_stats(downloaders)
    source_queue_stats = _get_source_queue_dashboard_stats(sources)
    service_statuses = _build_service_status_maps(
        media_server=media_server,
        request_apps=request_apps,
        request_app_stats=request_app_stats,
        sources=sources,
        source_queue_stats=source_queue_stats,
        downloaders=downloaders,
        downloader_stats=downloader_stats,
    )
    action_items = _build_dashboard_action_items(
        request_apps=request_apps,
        request_app_stats=request_app_stats,
        sources=sources,
        source_queue_stats=source_queue_stats,
        downloaders=downloaders,
        downloader_stats=downloader_stats,
    )

    return templates.TemplateResponse(
        request,
        "dashboard.html",
        {
            "active_page": "dashboard",
            "app_name": "MediaSync",
            "media_server": media_server,
            "sources": sources,
            "request_apps": request_apps,
            "downloaders": downloaders,
            "downloader_stats": downloader_stats,
            "downloader_totals": downloader_totals,
            "request_app_stats": request_app_stats,
            "request_totals": request_totals,
            "source_queue_stats": source_queue_stats,
            "service_statuses": service_statuses,
            "action_items": action_items,
            "settings": settings,
            "source_count": len(sources),
            "request_app_count": len(request_apps),
            "downloader_count": len(downloaders),
            "library_count": library_count,
            "recent_events": recent_events,
        },
    )


@app.get("/setup")
async def setup(request: Request):
    media_server = get_media_server()
    settings = get_app_settings()

    return templates.TemplateResponse(
        request,
        "setup.html",
        {
            "active_page": "setup",
            "app_name": "MediaSync",
            "media_server": media_server,
            "settings": settings,
        },
    )


@app.get("/setup/sources")
async def setup_sources(request: Request):
    media_server = get_media_server()
    sources = get_sources()

    return templates.TemplateResponse(
        request,
        "sources.html",
        {
            "active_page": "setup",
            "app_name": "MediaSync",
            "media_server": media_server,
            "sources": sources,
        },
    )


@app.get("/setup/summary")
async def setup_summary(request: Request):
    media_server = get_media_server()
    sources = get_sources()

    library_count = sum(
        len(source.get("libraries", []))
        for source in sources
    )

    return templates.TemplateResponse(
        request,
        "summary.html",
        {
            "active_page": "setup",
            "app_name": "MediaSync",
            "media_server": media_server,
            "sources": sources,
            "source_count": len(sources),
            "library_count": library_count,
        },
    )


@app.get("/activity")
async def activity(request: Request):
    return RedirectResponse(url="/", status_code=303)


@app.get("/about")
async def about(request: Request):
    media_server = get_media_server()
    settings = get_app_settings()

    return templates.TemplateResponse(
        request,
        "about.html",
        {
            "active_page": "about",
            "app_name": "MediaSync",
            "media_server": media_server,
            "settings": settings,
        },
    )


@app.get("/settings")
async def settings(request: Request):
    media_server = get_media_server()
    sources = get_sources()
    request_apps = get_request_apps()
    downloaders = get_downloaders()
    app_settings = get_app_settings()

    return templates.TemplateResponse(
        request,
        "settings.html",
        {
            "active_page": "settings",
            "app_name": "MediaSync",
            "media_server": media_server,
            "sources": sources,
            "request_apps": request_apps,
            "downloaders": downloaders,
            "settings": app_settings,
        },
    )




@app.get("/api/dashboard/action-items")
async def dashboard_action_items():
    sources = get_sources()
    request_apps = get_request_apps()
    downloaders = get_downloaders()

    request_app_stats, request_totals = _get_request_app_dashboard_stats(request_apps)
    downloader_stats, downloader_totals = _get_downloader_dashboard_stats(downloaders)
    source_queue_stats = _get_source_queue_dashboard_stats(sources)
    action_items = _build_dashboard_action_items(
        request_apps=request_apps,
        request_app_stats=request_app_stats,
        sources=sources,
        source_queue_stats=source_queue_stats,
        downloaders=downloaders,
        downloader_stats=downloader_stats,
    )

    return {
        "success": True,
        "items": action_items,
        "request_totals": request_totals,
        "downloader_totals": downloader_totals,
    }



@app.get("/api/dashboard/library-count/{library_id}")
async def dashboard_library_count(library_id: str):
    return _dashboard_library_count_payload(library_id)


@app.get("/api/image-proxy")
async def image_proxy(url: str):
    if not url.startswith(("http://", "https://")):
        raise HTTPException(status_code=400, detail="Invalid image URL.")

    try:
        response = requests.get(url, timeout=20)
        response.raise_for_status()
    except Exception as error:
        raise HTTPException(status_code=502, detail=f"Unable to fetch image: {error}")

    content_type = response.headers.get("Content-Type") or "image/jpeg"

    return StreamingResponse(
        iter([response.content]),
        media_type=content_type,
        headers={"Cache-Control": "public, max-age=86400"},
    )

@app.get("/api/lifecycle/{lifecycle_id}")
async def lifecycle_detail(lifecycle_id: int):
    lifecycle_data = get_lifecycle(lifecycle_id)

    if not lifecycle_data:
        raise HTTPException(status_code=404, detail="Lifecycle not found.")

    media_server = get_media_server()
    lifecycle_data["media_server"] = media_server
    lifecycle_data["tv_overview"] = _get_tv_overview_for_lifecycle(lifecycle_data.get("lifecycle") or {})

    return {
        "success": True,
        **lifecycle_data,
    }


def _get_tv_overview_for_lifecycle(lifecycle):
    media_type = str((lifecycle or {}).get("media_type") or "").strip().lower()

    if media_type not in {"tv", "show", "series", "tvshows"}:
        return None

    sonarr_source = _get_first_source_by_type("sonarr")

    if not sonarr_source:
        return {
            "success": False,
            "message": "No Sonarr source is configured.",
            "seasons": [],
        }

    server_url = str(sonarr_source.get("source_url") or "").strip().rstrip("/")
    api_key = str(sonarr_source.get("api_key") or "").strip()

    if not server_url or not api_key:
        return {
            "success": False,
            "message": "Sonarr source URL or API key is missing.",
            "seasons": [],
        }

    headers = {
        "X-Api-Key": api_key,
        "Accept": "application/json",
    }

    try:
        series = _find_sonarr_series(
            server_url=server_url,
            headers=headers,
            lifecycle=lifecycle,
        )

        if not series:
            return {
                "success": False,
                "message": "Series not found in Sonarr.",
                "seasons": [],
            }

        episodes_response = requests.get(
            f"{server_url}/api/v3/episode",
            headers=headers,
            params={"seriesId": series.get("id")},
            timeout=20,
        )
        episodes_response.raise_for_status()
        episodes = episodes_response.json()

        if not isinstance(episodes, list):
            episodes = []

        queue_items = _get_sonarr_queue_items(server_url=server_url, headers=headers)
        media_server = get_media_server()
        media_server_episode_keys = _get_media_server_tv_episode_keys(
            media_server=media_server,
            source=sonarr_source,
            series=series,
        )

        return _build_tv_overview(
            series=series,
            episodes=episodes,
            queue_items=queue_items,
            sonarr_source=sonarr_source,
            media_server=media_server,
            media_server_episode_keys=media_server_episode_keys,
        )
    except Exception as error:
        return {
            "success": False,
            "message": f"Sonarr overview unavailable: {error}",
            "seasons": [],
        }


def _get_first_source_by_type(source_type):
    normalized_type = str(source_type or "").strip().lower()

    for source in get_sources():
        if str(source.get("source_type") or "").strip().lower() == normalized_type:
            return source

    return None


def _find_sonarr_series(server_url, headers, lifecycle):
    response = requests.get(
        f"{server_url}/api/v3/series",
        headers=headers,
        timeout=20,
    )
    response.raise_for_status()
    series_items = response.json()

    if not isinstance(series_items, list):
        return None

    tvdb_id = str((lifecycle or {}).get("tvdb_id") or "").strip()
    title = _normalize_title((lifecycle or {}).get("title"))

    if tvdb_id:
        for series in series_items:
            if str(series.get("tvdbId") or "").strip() == tvdb_id:
                return series

    if title:
        for series in series_items:
            if _normalize_title(series.get("title")) == title:
                return series

    return None


def _get_sonarr_queue_items(server_url, headers):
    try:
        response = requests.get(
            f"{server_url}/api/v3/queue",
            headers=headers,
            params={"page": 1, "pageSize": 500},
            timeout=20,
        )
        response.raise_for_status()
        data = response.json()
    except Exception:
        return []

    records = data.get("records") if isinstance(data, dict) else []
    return records if isinstance(records, list) else []


def _build_tv_overview(series, episodes, queue_items, sonarr_source=None, media_server=None, media_server_episode_keys=None):
    monitored_seasons = []

    for season in series.get("seasons") or []:
        if not season.get("monitored"):
            continue

        try:
            season_number = int(season.get("seasonNumber"))
        except (TypeError, ValueError):
            continue

        if season_number <= 0:
            continue

        monitored_seasons.append(season_number)

    monitored_seasons = sorted(set(monitored_seasons), reverse=True)

    queue_by_episode = {}

    for queue_item in queue_items:
        for episode in queue_item.get("episodes") or []:
            episode_id = episode.get("id")
            if episode_id is not None:
                queue_by_episode[str(episode_id)] = queue_item

        episode_id = queue_item.get("episodeId")
        if episode_id is not None:
            queue_by_episode[str(episode_id)] = queue_item

    seasons = []

    for season_number in monitored_seasons:
        season_episodes = [
            episode for episode in episodes
            if int(episode.get("seasonNumber") or -1) == season_number
        ]
        season_episodes.sort(key=lambda episode: int(episode.get("episodeNumber") or 0))

        normalized_episodes = [
            _normalize_episode_for_overview(episode, queue_by_episode, media_server_episode_keys or set())
            for episode in season_episodes
        ]

        available_count = sum(1 for episode in normalized_episodes if episode.get("status") == "available")
        downloading_count = sum(1 for episode in normalized_episodes if episode.get("status") == "downloading")
        future_count = sum(1 for episode in normalized_episodes if episode.get("status") == "future")
        total_count = len(normalized_episodes)
        percent_available = round((available_count / total_count) * 100) if total_count else 0
        is_complete = bool(total_count and available_count == total_count)
        is_expandable = not is_complete and bool(normalized_episodes)

        if is_complete:
            season_status = "available"
            season_status_label = "Available"
        elif downloading_count:
            season_status = "in_progress"
            season_status_label = "In Progress"
        else:
            season_status = "scheduled"
            season_status_label = "Scheduled"

        seasons.append(
            {
                "season_number": season_number,
                "label": f"Season {season_number}",
                "available_count": available_count,
                "downloading_count": downloading_count,
                "future_count": future_count,
                "total_count": total_count,
                "progress": percent_available,
                "percent_available": percent_available,
                "count_label": f"{available_count} / {total_count} Episodes",
                "status": season_status,
                "status_label": season_status_label,
                "is_complete": is_complete,
                "is_expandable": is_expandable,
                "episodes": normalized_episodes,
            }
        )

    total_episodes = sum(season.get("total_count", 0) for season in seasons)
    total_available = sum(season.get("available_count", 0) for season in seasons)
    total_downloading = sum(season.get("downloading_count", 0) for season in seasons)
    percent_available = round((total_available / total_episodes) * 100) if total_episodes else 0

    return {
        "success": True,
        "source": {
            "source_name": (sonarr_source or {}).get("source_name") or "Sonarr",
            "source_type": (sonarr_source or {}).get("source_type") or "sonarr",
            "source_id": (sonarr_source or {}).get("id"),
        },
        "series": {
            "title": series.get("title"),
            "network": series.get("network") or series.get("studio"),
            "status": series.get("status"),
            "first_air_date": series.get("firstAired"),
            "runtime": series.get("runtime"),
            "monitored_seasons": monitored_seasons,
            "total_seasons": len(monitored_seasons),
            "episodes_available": total_available,
            "episodes_downloading": total_downloading,
            "episodes_total": total_episodes,
            "percent_available": percent_available,
            "count_label": f"{total_available} / {total_episodes} Episodes",
            "poster_url": _sonarr_series_poster_url(series, sonarr_source),
            "availability_source": _media_server_type_label((media_server or {}).get("server_type")),
        },
        "poster_url": _sonarr_series_poster_url(series, sonarr_source),
        "seasons": seasons,
    }



def _sonarr_series_poster_url(series, source=None):
    source_url = str((source or {}).get("source_url") or "").strip().rstrip("/")

    for image in (series or {}).get("images") or []:
        if not isinstance(image, dict):
            continue

        cover_type = str(image.get("coverType") or "").strip().lower()
        if cover_type not in {"poster", "cover"}:
            continue

        for key in ("remoteUrl", "url"):
            value = str(image.get(key) or "").strip()
            if not value:
                continue

            if value.startswith("http://") or value.startswith("https://") or value.startswith("/static/"):
                return value

            if value.startswith("/") and source_url:
                return f"{source_url}{value}"

            if source_url:
                return f"{source_url}/{value.lstrip('/')}"

            return value

    return ""


def _get_media_server_tv_episode_keys(media_server, source, series):
    server_type = str((media_server or {}).get("server_type") or "").strip().lower()

    if server_type not in {"emby", "jellyfin"}:
        return set()

    server_url = str((media_server or {}).get("server_url") or "").strip().rstrip("/")
    library_ids = tuple(_tv_media_server_library_ids(source) or [""])
    series_key = str((series or {}).get("tvdbId") or (series or {}).get("id") or (series or {}).get("title") or "").strip().lower()
    cache_key = (server_type, server_url, library_ids, series_key)
    cached = TV_MEDIA_SERVER_EPISODE_CACHE.get(cache_key)

    if cached and time.time() - cached.get("created_at", 0) <= TV_MEDIA_SERVER_EPISODE_CACHE_TTL_SECONDS:
        return set(cached.get("episode_keys") or set())

    episode_keys = _get_emby_family_tv_episode_keys(media_server, source, series)
    TV_MEDIA_SERVER_EPISODE_CACHE[cache_key] = {
        "created_at": time.time(),
        "episode_keys": set(episode_keys),
    }
    return episode_keys


def _get_emby_family_tv_episode_keys(media_server, source, series):
    server_url = str((media_server or {}).get("server_url") or "").strip().rstrip("/")
    api_key = str((media_server or {}).get("api_key") or "").strip()
    series_title = str((series or {}).get("title") or "").strip()

    if not server_url or not api_key or not series_title:
        return set()

    library_ids = _tv_media_server_library_ids(source)
    episode_keys = set()

    for library_id in library_ids or [None]:
        series_items = _emby_find_series_items(
            server_url=server_url,
            api_key=api_key,
            library_id=library_id,
            series_title=series_title,
        )

        for series_item in series_items:
            series_id = series_item.get("Id") or series_item.get("id")
            if not series_id:
                continue

            for item in _emby_get_series_episodes(server_url=server_url, api_key=api_key, series_id=series_id):
                if not isinstance(item, dict):
                    continue

                try:
                    season_number = int(item.get("ParentIndexNumber"))
                    episode_number = int(item.get("IndexNumber"))
                except (TypeError, ValueError):
                    continue

                if season_number > 0 and episode_number > 0:
                    episode_keys.add((season_number, episode_number))

    return episode_keys


def _emby_find_series_items(server_url, api_key, library_id, series_title):
    params = {
        "Recursive": "true",
        "SearchTerm": series_title,
        "IncludeItemTypes": "Series",
        "Limit": "20",
        "Fields": "ProviderIds",
    }

    if library_id:
        params["ParentId"] = library_id

    try:
        response = requests.get(
            f"{server_url}/Items",
            headers={
                "X-Emby-Token": api_key,
                "Accept": "application/json",
            },
            params=params,
            timeout=10,
        )
        response.raise_for_status()
        data = response.json()
    except Exception:
        return []

    items = data.get("Items") if isinstance(data, dict) else []
    if not isinstance(items, list):
        return []

    return [
        item for item in items
        if isinstance(item, dict) and _titles_match(item.get("Name"), series_title)
    ]


def _emby_get_series_episodes(server_url, api_key, series_id):
    try:
        response = requests.get(
            f"{server_url}/Shows/{series_id}/Episodes",
            headers={
                "X-Emby-Token": api_key,
                "Accept": "application/json",
            },
            params={
                "Fields": "Path,MediaSources,SeriesName,ParentIndexNumber,IndexNumber",
                "Limit": "10000",
            },
            timeout=10,
        )
        response.raise_for_status()
        data = response.json()
    except Exception:
        return []

    items = data.get("Items") if isinstance(data, dict) else []
    return items if isinstance(items, list) else []


def _tv_media_server_library_ids(source):
    library_ids = []

    for library in (source or {}).get("libraries") or []:
        library_id = library.get("library_id")

        if library_id and library_id not in library_ids:
            library_ids.append(library_id)

    return library_ids


def _media_server_type_label(server_type):
    labels = {
        "emby": "Emby",
        "jellyfin": "Jellyfin",
        "plex": "Plex",
    }

    return labels.get(str(server_type or "").strip().lower(), "Media Server")


def _normalize_episode_for_overview(episode, queue_by_episode, media_server_episode_keys=None):
    episode_id = str(episode.get("id") or "")
    queue_item = queue_by_episode.get(episode_id)
    season_number = int(episode.get("seasonNumber") or 0)
    episode_number = int(episode.get("episodeNumber") or 0)
    air_date = episode.get("airDateUtc") or episode.get("airDate")
    media_server_episode_keys = media_server_episode_keys or set()
    is_available_in_media_server = (season_number, episode_number) in media_server_episode_keys

    if queue_item:
        status = "downloading"
        status_label = "Downloading"
        progress = 0
        indicator = "active"
    elif is_available_in_media_server:
        status = "available"
        status_label = "Available"
        progress = 100
        indicator = "available"
    else:
        status = "future"
        status_label = _episode_air_label(air_date)
        progress = 0
        indicator = "future"

    return {
        "episode_id": episode.get("id"),
        "season_number": season_number,
        "episode_number": episode_number,
        "episode_code": f"S{season_number:02d}E{episode_number:02d}",
        "title": episode.get("title") or f"Episode {episode_number}",
        "status": status,
        "status_label": status_label,
        "air_date": air_date,
        "progress": progress,
        "indicator": indicator,
        "is_available": status == "available",
        "is_active": status == "downloading",
    }


def _queue_status_label(queue_item):
    return "Downloading"


def _queue_percent(queue_item):
    try:
        size = float(queue_item.get("size") or 0)
        sizeleft = float(queue_item.get("sizeleft") or 0)
        if size > 0:
            return max(0, min(100, round(((size - sizeleft) / size) * 100)))
    except (TypeError, ValueError):
        pass

    return 0


def _episode_air_label(value):
    if not value:
        return "Unaired"

    try:
        raw = str(value).replace("Z", "+00:00")
        air_dt = datetime.fromisoformat(raw)
        if not air_dt.tzinfo:
            air_dt = air_dt.replace(tzinfo=timezone.utc)
        now = datetime.now(timezone.utc)
        delta_days = (air_dt.date() - now.date()).days
    except Exception:
        return str(value)

    formatted = air_dt.strftime("%b %-d, %Y") if os.name != "nt" else air_dt.strftime("%b %#d, %Y")

    if delta_days > 0:
        return f"Airs {formatted}"

    if delta_days == 0:
        return "Airs today"

    days_ago = abs(delta_days)
    return f"Aired {days_ago} day{'s' if days_ago != 1 else ''} ago"



def _titles_match(candidate, title):
    normalized_candidate = _normalize_title(candidate)
    normalized_title = _normalize_title(title)

    if not normalized_candidate or not normalized_title:
        return False

    return normalized_candidate == normalized_title or normalized_title in normalized_candidate or normalized_candidate in normalized_title


def _normalize_title(value):
    normalized = "".join(
        character.lower() if character.isalnum() else " "
        for character in str(value or "")
    )
    return " ".join(normalized.split())


@app.get("/api/activity/stream")
async def activity_stream():
    queue = subscribe_activity_queue()

    async def event_generator():
        try:
            while True:
                try:
                    event = await asyncio.wait_for(queue.get(), timeout=30)
                    yield f"data: {json.dumps(event)}\n\n"
                except asyncio.TimeoutError:
                    yield ": keep-alive\n\n"
        finally:
            unsubscribe_activity_queue(queue)

    return StreamingResponse(
        event_generator(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
        },
    )


@app.get("/manifest.webmanifest", include_in_schema=False)
async def manifest():
    return FileResponse(
        "app/static/manifest.webmanifest",
        media_type="application/manifest+json",
    )


@app.get("/sw.js", include_in_schema=False)
async def service_worker():
    return FileResponse(
        "app/static/sw.js",
        media_type="application/javascript",
        headers={
            "Cache-Control": "no-cache",
        },
    )


@app.get("/health")
async def health():
    return {
        "status": "MediaSync online",
    }


app.add_middleware(
    SessionMiddleware,
    secret_key=_get_session_secret(),
    same_site="lax",
    https_only=False,
)
