import asyncio
import json
from contextlib import asynccontextmanager

from fastapi import FastAPI, Request
from fastapi.responses import RedirectResponse, StreamingResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates

from app.api.server import router as server_router
from app.api.source import router as source_router
from app.api.settings import router as settings_router
from app.database import (
    get_activity_events,
    get_app_settings,
    get_media_server,
    get_sources,
    init_db,
    register_activity_loop,
    subscribe_activity_queue,
    unsubscribe_activity_queue,
)


@asynccontextmanager
async def lifespan(app: FastAPI):
    init_db()
    register_activity_loop(asyncio.get_running_loop())
    yield


app = FastAPI(
    title="MediaSync",
    lifespan=lifespan,
)

templates = Jinja2Templates(
    directory="app/templates",
)

app.mount(
    "/static",
    StaticFiles(directory="app/static"),
    name="static",
)

app.include_router(server_router)
app.include_router(source_router)
app.include_router(settings_router)


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


@app.middleware("http")
async def setup_gate(request: Request, call_next):
    path = request.url.path
    setup_paths = {"/setup", "/setup/sources", "/setup/summary"}

    if (
        path.startswith("/api")
        or path.startswith("/static")
        or path == "/health"
    ):
        return await call_next(request)

    setup_complete = _is_setup_complete()

    if not setup_complete and path not in setup_paths:
        return RedirectResponse(url="/setup", status_code=303)

    if setup_complete and path in setup_paths:
        return RedirectResponse(url="/settings", status_code=303)

    return await call_next(request)


@app.get("/")
async def dashboard(request: Request):
    media_server = get_media_server()
    sources = get_sources()
    settings = get_app_settings()

    library_count = sum(
        len(source.get("libraries", []))
        for source in sources
    )

    recent_events = get_activity_events(limit=25)

    return templates.TemplateResponse(
        request,
        "dashboard.html",
        {
            "active_page": "dashboard",
            "app_name": "MediaSync",
            "media_server": media_server,
            "sources": sources,
            "settings": settings,
            "source_count": len(sources),
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
    media_server = get_media_server()
    settings = get_app_settings()

    try:
        display_limit = int(settings.get("activity_display_limit", "100"))
    except ValueError:
        display_limit = 100

    events = get_activity_events(limit=display_limit)

    return templates.TemplateResponse(
        request,
        "activity.html",
        {
            "active_page": "activity",
            "app_name": "MediaSync",
            "media_server": media_server,
            "settings": settings,
            "events": events,
        },
    )


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
    app_settings = get_app_settings()

    return templates.TemplateResponse(
        request,
        "settings.html",
        {
            "active_page": "settings",
            "app_name": "MediaSync",
            "media_server": media_server,
            "sources": sources,
            "settings": app_settings,
        },
    )


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


@app.get("/health")
async def health():
    return {
        "status": "MediaSync online",
    }
