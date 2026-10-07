"""Camera, live view and photo endpoints. Sync: FastAPI runs them in its thread pool."""

from typing import Annotated

from fastapi import APIRouter, HTTPException, Query, Request, Response
from fastapi.responses import FileResponse

from lensmind.api.messages import msg
from lensmind.api.schemas import (
    CameraStatusOut,
    GroupOut,
    SettingOut,
    SettingsOut,
    SetValueIn,
    ShotOut,
    StatusOut,
)
from lensmind.camera.base import CameraError
from lensmind.camera.primary import resolve_primary
from lensmind.camera.session import CameraSession
from lensmind.storage import PhotoStore

router = APIRouter(prefix="/api")


def _session(request: Request) -> CameraSession:
    return request.app.state.session


def _store(request: Request) -> PhotoStore:
    return request.app.state.store


def _language(request: Request) -> str:
    return request.app.state.settings.language


@router.get("/status")
def get_status(request: Request) -> StatusOut:
    try:
        status = _session(request).status()
    except CameraError as error:
        return StatusOut(connected=False, detail=error.message, language=_language(request))
    return StatusOut(
        connected=True, language=_language(request), camera=CameraStatusOut.from_model(status)
    )


@router.get("/settings")
def get_settings(request: Request) -> SettingsOut:
    groups = _session(request).settings()
    return SettingsOut(
        groups=[GroupOut.from_model(g) for g in groups], primary=resolve_primary(groups)
    )


@router.put("/settings/{name}")
def put_setting(name: str, body: SetValueIn, request: Request) -> SettingOut:
    return SettingOut.from_model(_session(request).set(name, body.value))


@router.post("/capture")
def capture(request: Request) -> ShotOut:
    files = _session(request).capture()
    return ShotOut.from_shot(_store(request).save(files))


@router.get("/preview")
def preview(request: Request) -> Response:
    frame = _session(request).preview()
    return Response(content=frame, media_type="image/jpeg", headers={"Cache-Control": "no-store"})


@router.post("/liveview/stop", status_code=204)
def stop_liveview(request: Request) -> Response:
    _session(request).end_liveview()
    return Response(status_code=204)


@router.get("/photos")
def list_photos(request: Request, limit: Annotated[int, Query(ge=1, le=500)] = 50) -> list[ShotOut]:
    return [ShotOut.from_shot(shot) for shot in _store(request).list_shots(limit)]


@router.get("/photos/{name}")
def get_photo(name: str, request: Request) -> FileResponse:
    path = _store(request).resolve(name)
    if path is None:
        raise HTTPException(404, detail=msg(_language(request), "photo_not_found", name=name))
    return FileResponse(path)


@router.get("/photos/{name}/thumb")
def get_thumb(name: str, request: Request) -> FileResponse:
    path = _store(request).thumb_path(name)
    if path is None:
        raise HTTPException(404, detail=msg(_language(request), "photo_not_found", name=name))
    return FileResponse(path, media_type="image/jpeg")
