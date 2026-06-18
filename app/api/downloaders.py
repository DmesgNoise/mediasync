from fastapi import APIRouter, Form

from app.database import (
    delete_downloader,
    get_downloader,
    get_downloaders,
    reorder_downloaders,
    save_downloader,
    update_downloader_config,
)
from app.providers.downloaders.base import (
    build_downloader_provider,
    get_supported_downloader_types,
)

router = APIRouter(prefix="/api/downloaders", tags=["downloaders"])


def _downloader_auth_value(
    api_key: str | None = "",
    username: str | None = "",
    password: str | None = "",
) -> str:
    normalized_api_key = str(api_key or "").strip()
    normalized_username = str(username or "").strip()
    normalized_password = str(password or "").strip()

    if normalized_api_key:
        return normalized_api_key

    if normalized_username or normalized_password:
        return f"{normalized_username}:{normalized_password}"

    return ""


def _stored_downloader_auth_value(downloader: dict) -> str:
    return _downloader_auth_value(
        api_key=downloader.get("api_key"),
        username=downloader.get("username"),
        password=downloader.get("password"),
    )


@router.get("")
async def list_downloaders():
    return {
        "success": True,
        "downloaders": get_downloaders(),
        "supported_types": get_supported_downloader_types(),
    }


@router.post("/test")
async def test_downloader(
    downloader_type: str = Form(...),
    downloader_url: str = Form(...),
    api_key: str = Form(""),
    username: str = Form(""),
    password: str = Form(""),
):
    normalized_type = downloader_type.strip().lower()

    if normalized_type not in get_supported_downloader_types():
        return {
            "success": False,
            "message": "Unsupported downloader type.",
        }

    provider = build_downloader_provider(
        downloader_type=normalized_type,
        server_url=downloader_url,
        api_key=_downloader_auth_value(api_key, username, password),
    )

    if not provider:
        return {
            "success": False,
            "message": "Unsupported downloader type.",
        }

    return provider.test_connection()


@router.post("/save")
async def save_downloader_settings(
    downloader_name: str = Form(...),
    downloader_type: str = Form(...),
    downloader_url: str = Form(...),
    api_key: str = Form(""),
    username: str = Form(""),
    password: str = Form(""),
    downloader_id: str = Form(""),
):
    normalized_type = downloader_type.strip().lower()

    if normalized_type not in get_supported_downloader_types():
        return {
            "success": False,
            "message": "Unsupported downloader type.",
        }

    provider = build_downloader_provider(
        downloader_type=normalized_type,
        server_url=downloader_url,
        api_key=_downloader_auth_value(api_key, username, password),
    )

    if not provider:
        return {
            "success": False,
            "message": "Unsupported downloader type.",
        }

    result = provider.test_connection()

    if not result.get("success"):
        return result

    normalized_downloader_id = None

    if downloader_id.strip():
        try:
            normalized_downloader_id = int(downloader_id)
        except ValueError:
            return {
                "success": False,
                "message": "Downloader ID is invalid.",
            }

    saved_downloader_id = save_downloader(
        downloader_id=normalized_downloader_id,
        downloader_name=downloader_name,
        downloader_type=normalized_type,
        downloader_url=downloader_url,
        api_key=api_key,
        username=username,
        password=password,
        version=result.get("version", "Unknown"),
        connected=1,
    )

    return {
        "success": True,
        "message": "Downloader saved successfully.",
        "downloader_id": saved_downloader_id,
        "version": result.get("version", "Unknown"),
        "status": result.get("status", "Unknown"),
    }


@router.post("/update")
async def update_downloader_settings(
    downloader_id: int = Form(...),
    downloader_name: str = Form(...),
    downloader_url: str = Form(...),
    api_key: str = Form(""),
    username: str = Form(""),
    password: str = Form(""),
):
    downloader = get_downloader(downloader_id)

    if not downloader:
        return {
            "success": False,
            "message": "Downloader not found.",
        }

    provider = build_downloader_provider(
        downloader_type=downloader["downloader_type"],
        server_url=downloader_url,
        api_key=_downloader_auth_value(api_key, username, password),
    )

    if not provider:
        return {
            "success": False,
            "message": "Unsupported downloader type.",
        }

    result = provider.test_connection()

    if not result.get("success"):
        return result

    update_downloader_config(
        downloader_id=downloader_id,
        downloader_name=downloader_name,
        downloader_url=downloader_url,
        api_key=api_key,
        username=username,
        password=password,
        version=result.get("version", "Unknown"),
        connected=1,
    )

    return {
        "success": True,
        "message": "Downloader updated successfully.",
        "version": result.get("version", "Unknown"),
        "status": result.get("status", "Unknown"),
    }


@router.post("/delete")
async def delete_downloader_settings(downloader_id: int = Form(...)):
    delete_downloader(downloader_id)

    return {
        "success": True,
        "message": "Downloader deleted successfully.",
    }


@router.post("/reorder")
async def reorder_downloader_settings(downloader_ids: str = Form(...)):
    ids = []

    for item in downloader_ids.split(","):
        item = item.strip()

        if not item:
            continue

        try:
            ids.append(int(item))
        except ValueError:
            return {
                "success": False,
                "message": "Invalid downloader order.",
            }

    reorder_downloaders(ids)

    return {
        "success": True,
        "message": "Downloader order saved.",
    }


@router.post("/queue")
async def get_downloader_queue(downloader_id: int = Form(...)):
    downloader = get_downloader(downloader_id)

    if not downloader:
        return {
            "success": False,
            "message": "Downloader not found.",
        }

    provider = build_downloader_provider(
        downloader_type=downloader["downloader_type"],
        server_url=downloader["downloader_url"],
        api_key=_stored_downloader_auth_value(downloader),
    )

    if not provider:
        return {
            "success": False,
            "message": "Unsupported downloader type.",
        }

    result = provider.get_queue()
    result["downloader_id"] = downloader["id"]
    result["downloader_name"] = downloader["downloader_name"]
    result["downloader_type"] = downloader["downloader_type"]

    return result


@router.get("/queue/all")
async def get_all_downloader_queues():
    queues = []
    overall_success = True

    for downloader in get_downloaders():
        provider = build_downloader_provider(
            downloader_type=downloader["downloader_type"],
            server_url=downloader["downloader_url"],
            api_key=_stored_downloader_auth_value(downloader),
        )

        if not provider:
            overall_success = False
            queues.append(
                {
                    "success": False,
                    "downloader_id": downloader["id"],
                    "downloader_name": downloader["downloader_name"],
                    "downloader_type": downloader["downloader_type"],
                    "message": "Unsupported downloader type.",
                    "downloads": [],
                }
            )
            continue

        result = provider.get_queue()
        result["downloader_id"] = downloader["id"]
        result["downloader_name"] = downloader["downloader_name"]
        result["downloader_type"] = downloader["downloader_type"]
        result["downloader_url"] = downloader.get("downloader_url") or ""
        result["version"] = downloader.get("version") or result.get("version") or "Unknown"

        if not result.get("success"):
            overall_success = False

        queues.append(result)

    return {
        "success": overall_success,
        "queues": queues,
    }
