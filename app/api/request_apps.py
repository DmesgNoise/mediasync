from fastapi import APIRouter, Form, Request

from app.actions.seerr_webhook_activity import process_seerr_webhook_event
from app.database import (
    delete_request_app,
    get_app_settings,
    get_request_app,
    get_request_apps,
    reorder_request_apps,
    save_request_app,
    update_request_app_config,
)
from app.providers.request_apps.base import (
    build_request_app_provider,
    get_supported_request_app_types,
)

router = APIRouter(prefix="/api/request-apps", tags=["request-apps"])


@router.get("")
async def list_request_apps():
    return {
        "success": True,
        "request_apps": get_request_apps(),
    }


@router.post("/test")
async def test_request_app(
    app_type: str = Form(...),
    app_url: str = Form(...),
    api_key: str = Form(...),
):
    normalized_type = app_type.strip().lower()

    if normalized_type not in get_supported_request_app_types():
        return {
            "success": False,
            "message": "Unsupported request app type.",
        }

    provider = build_request_app_provider(
        app_type=normalized_type,
        server_url=app_url,
        api_key=api_key,
    )

    if not provider:
        return {
            "success": False,
            "message": "Unsupported request app type.",
        }

    return provider.test_connection()


@router.post("/save")
async def save_request_app_settings(
    app_name: str = Form(...),
    app_type: str = Form(...),
    app_url: str = Form(...),
    api_key: str = Form(...),
    request_app_id: str = Form(""),
):
    normalized_type = app_type.strip().lower()

    if normalized_type not in get_supported_request_app_types():
        return {
            "success": False,
            "message": "Unsupported request app type.",
        }

    provider = build_request_app_provider(
        app_type=normalized_type,
        server_url=app_url,
        api_key=api_key,
    )

    if not provider:
        return {
            "success": False,
            "message": "Unsupported request app type.",
        }

    result = provider.test_connection()

    if not result.get("success"):
        return result

    normalized_request_app_id = None

    if request_app_id.strip():
        try:
            normalized_request_app_id = int(request_app_id)
        except ValueError:
            return {
                "success": False,
                "message": "Request app ID is invalid.",
            }

    saved_request_app_id = save_request_app(
        request_app_id=normalized_request_app_id,
        app_name=app_name,
        app_type=normalized_type,
        app_url=app_url,
        api_key=api_key,
        version=result.get("version", "Unknown"),
        connected=1,
    )

    saved_request_app = get_request_app(saved_request_app_id)
    webhook_result = _register_request_app_webhook(saved_request_app)

    response = {
        "success": True,
        "message": "Request app saved successfully.",
        "request_app_id": saved_request_app_id,
        "version": result.get("version", "Unknown"),
        "webhook": webhook_result,
    }

    if webhook_result.get("attempted") and not webhook_result.get("success"):
        response["message"] = (
            "Request app saved, but automatic webhook registration failed. "
            f"{webhook_result.get('message', '')}"
        )

    return response


@router.post("/update")
async def update_request_app_settings(
    request_app_id: int = Form(...),
    app_name: str = Form(...),
    app_url: str = Form(...),
    api_key: str = Form(...),
):
    request_app = get_request_app(request_app_id)

    if not request_app:
        return {
            "success": False,
            "message": "Request app not found.",
        }

    provider = build_request_app_provider(
        app_type=request_app["app_type"],
        server_url=app_url,
        api_key=api_key,
    )

    if not provider:
        return {
            "success": False,
            "message": "Unsupported request app type.",
        }

    result = provider.test_connection()

    if not result.get("success"):
        return result

    update_request_app_config(
        request_app_id=request_app_id,
        app_name=app_name,
        app_url=app_url,
        api_key=api_key,
        version=result.get("version", "Unknown"),
        connected=1,
    )

    updated_request_app = get_request_app(request_app_id)
    webhook_result = _register_request_app_webhook(updated_request_app)

    response = {
        "success": True,
        "message": "Request app updated successfully.",
        "version": result.get("version", "Unknown"),
        "webhook": webhook_result,
    }

    if webhook_result.get("attempted") and not webhook_result.get("success"):
        response["message"] = (
            "Request app updated, but automatic webhook registration failed. "
            f"{webhook_result.get('message', '')}"
        )

    return response


@router.post("/delete")
async def delete_request_app_settings(request_app_id: int = Form(...)):
    delete_request_app(request_app_id)

    return {
        "success": True,
        "message": "Request app deleted successfully.",
    }


@router.post("/reorder")
async def reorder_request_app_settings(request_app_ids: str = Form(...)):
    ids = []

    for item in request_app_ids.split(","):
        item = item.strip()

        if not item:
            continue

        try:
            ids.append(int(item))
        except ValueError:
            return {
                "success": False,
                "message": "Invalid request app order.",
            }

    reorder_request_apps(ids)

    return {
        "success": True,
        "message": "Request app order saved.",
    }


@router.post("/counts")
async def get_request_app_counts(request_app_id: int = Form(...)):
    request_app = get_request_app(request_app_id)

    if not request_app:
        return {
            "success": False,
            "message": "Request app not found.",
        }

    provider = build_request_app_provider(
        app_type=request_app["app_type"],
        server_url=request_app["app_url"],
        api_key=request_app["api_key"],
    )

    if not provider:
        return {
            "success": False,
            "message": "Unsupported request app type.",
        }

    return provider.get_request_counts()


@router.post("/recent")
async def get_recent_request_app_requests(
    request_app_id: int = Form(...),
    limit: int = Form(10),
):
    request_app = get_request_app(request_app_id)

    if not request_app:
        return {
            "success": False,
            "message": "Request app not found.",
        }

    provider = build_request_app_provider(
        app_type=request_app["app_type"],
        server_url=request_app["app_url"],
        api_key=request_app["api_key"],
    )

    if not provider:
        return {
            "success": False,
            "message": "Unsupported request app type.",
        }

    return {
        "success": True,
        "requests": provider.get_recent_requests(limit=limit),
    }


@router.post("/webhook/seerr/{request_app_id}")
async def seerr_webhook(request_app_id: int, request: Request):
    request_app = get_request_app(request_app_id)

    if not request_app:
        return {
            "success": False,
            "message": "Request app not found.",
        }

    if str(request_app.get("app_type", "")).strip().lower() != "seerr":
        return {
            "success": False,
            "message": "Request app is not a Seerr integration.",
        }

    try:
        payload = await request.json()
    except Exception:
        payload = {}

    provider = build_request_app_provider(
        app_type=request_app["app_type"],
        server_url=request_app["app_url"],
        api_key=request_app["api_key"],
    )

    return process_seerr_webhook_event(
        request_app=request_app,
        payload=payload,
        provider=provider,
    )


def _register_request_app_webhook(request_app):
    if not request_app:
        return {
            "attempted": False,
            "success": False,
            "message": "Request app not found after save.",
        }

    provider = build_request_app_provider(
        app_type=request_app.get("app_type"),
        server_url=request_app.get("app_url"),
        api_key=request_app.get("api_key"),
    )

    if not provider:
        return {
            "attempted": False,
            "success": False,
            "message": "Unsupported request app type.",
        }

    if not hasattr(provider, "register_mediasync_webhook"):
        return {
            "attempted": False,
            "success": True,
            "message": "Request app does not support automatic webhook registration.",
        }

    settings = get_app_settings()
    mediasync_url = str(settings.get("mediasync_url", "")).strip().rstrip("/")

    if not mediasync_url:
        return {
            "attempted": False,
            "success": False,
            "message": "MediaSync URL is not configured.",
        }

    app_type = str(request_app.get("app_type", "")).strip().lower()

    if app_type == "seerr":
        webhook_url = f"{mediasync_url}/api/request-apps/webhook/seerr/{request_app['id']}"
    else:
        return {
            "attempted": False,
            "success": True,
            "message": "No webhook registration path is defined for this request app.",
        }

    try:
        return provider.register_mediasync_webhook(webhook_url=webhook_url)
    except Exception as error:
        return {
            "attempted": True,
            "success": False,
            "message": f"Webhook registration failed: {error}",
        }
