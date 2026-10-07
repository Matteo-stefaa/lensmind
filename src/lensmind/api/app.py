"""FastAPI application: lifespan, error mapping, routes and the static web app."""

from collections.abc import AsyncIterator, Callable
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse
from fastapi.staticfiles import StaticFiles

from lensmind.api.routes_camera import router as camera_router
from lensmind.camera.base import Camera, CameraError
from lensmind.camera.session import CameraSession
from lensmind.settings import Settings
from lensmind.storage import PhotoStore

# src/lensmind/api/app.py -> repository root -> web/ (the package is installed editable).
WEB_DIR = Path(__file__).resolve().parents[3] / "web"


def camera_factory_for(settings: Settings) -> Callable[[], Camera]:
    if settings.mock:
        from lensmind.camera.mock import MockCamera

        return lambda: MockCamera(dial=settings.mock_dial, lang=settings.language)
    from lensmind.camera.gphoto import GPhotoCamera

    return lambda: GPhotoCamera(lang=settings.language)


async def camera_error_handler(request: Request, error: Exception) -> JSONResponse:
    assert isinstance(error, CameraError)
    return JSONResponse(status_code=error.status, content={"detail": error.message})


def create_app(
    settings: Settings | None = None,
    camera_factory: Callable[[], Camera] | None = None,
    web_dir: Path = WEB_DIR,
) -> FastAPI:
    config = settings or Settings.from_env()
    factory = camera_factory or camera_factory_for(config)

    @asynccontextmanager
    async def lifespan(app: FastAPI) -> AsyncIterator[None]:
        session = CameraSession(factory, idle_seconds=config.liveview_idle_seconds)
        session.start_watchdog()
        app.state.settings = config
        app.state.session = session
        app.state.store = PhotoStore(config.photos_dir)
        try:
            yield
        finally:
            session.close()

    app = FastAPI(title="lensmind", lifespan=lifespan)
    app.add_exception_handler(CameraError, camera_error_handler)
    app.include_router(camera_router)
    app.mount("/", StaticFiles(directory=web_dir, html=True), name="web")
    return app
