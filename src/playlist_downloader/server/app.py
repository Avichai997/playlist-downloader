"""Local HTTP API behind the desktop window.

Bound to 127.0.0.1 only. Endpoints that talk to YouTube are declared with plain
`def` so FastAPI runs them in its worker threadpool — a two-minute playlist
analysis must never block the event loop that is streaming progress.
"""
from __future__ import annotations

import asyncio
import subprocess
import sys
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI, HTTPException, WebSocket, WebSocketDisconnect
from fastapi.responses import JSONResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel

from .. import APP_NAME, __version__
from ..core import db as db_module
from ..core import native, ytdlp
from ..core.errors import PlaylistDownloaderError
from ..core.service import Service

WEB_DIR = Path(__file__).resolve().parent.parent / "web"

service = Service()


class AnalyzeRequest(BaseModel):
    url: str
    sampleSize: int | None = None
    container: str | None = None
    outputDir: str | None = None


class StartRequest(BaseModel):
    height: int | None = None
    container: str | None = None
    outputDir: str | None = None
    startFrom: int | None = None
    endAt: int | None = None
    redownload: bool = False


class OutputRequest(BaseModel):
    outputDir: str


class ContainerRequest(BaseModel):
    container: str


class PickFolderRequest(BaseModel):
    initial: str = ""


class RevealRequest(BaseModel):
    path: str


@asynccontextmanager
async def lifespan(_: FastAPI):
    service.events.bind(asyncio.get_running_loop())
    service.start()
    try:
        yield
    finally:
        service.shutdown()


app = FastAPI(title=APP_NAME, version=__version__, lifespan=lifespan)


@app.exception_handler(PlaylistDownloaderError)
async def _domain_error(_, exc: PlaylistDownloaderError) -> JSONResponse:
    return JSONResponse({"detail": str(exc)}, status_code=400)


@app.get("/api/health")
def health() -> dict:
    return {"ok": True, "version": __version__}


@app.get("/api/settings")
def get_settings() -> dict:
    return service.settings.to_dict()


@app.put("/api/settings")
def put_settings(changes: dict) -> dict:
    return service.update_settings(changes).to_dict()


@app.post("/api/analyze")
def analyze(request: AnalyzeRequest) -> dict:
    url = request.url.strip()
    if not url:
        raise HTTPException(400, "Paste a playlist or video link first.")
    return service.analyze(
        url,
        sample_size=request.sampleSize or 12,
        container=request.container,
        output_dir=request.outputDir,
    )


@app.post("/api/pick-folder")
def pick_folder(request: PickFolderRequest) -> dict:
    chosen = native.pick_folder(request.initial or None)
    return {"path": chosen}


@app.put("/api/playlists/{playlist_id}/output")
def set_playlist_output(playlist_id: str, request: OutputRequest) -> dict:
    if not request.outputDir.strip():
        raise HTTPException(400, "Choose a folder first.")
    try:
        return service.set_playlist_output(playlist_id, request.outputDir.strip())
    except KeyError as exc:
        raise HTTPException(404, "That playlist is not in the library.") from exc


@app.post("/api/playlists/{playlist_id}/qualities")
def refresh_qualities(playlist_id: str, request: ContainerRequest) -> dict:
    if request.container not in ("mkv", "mp4", "webm"):
        raise HTTPException(400, "Format must be mkv, mp4, or webm.")
    try:
        return service.refresh_qualities(playlist_id, container=request.container)
    except KeyError as exc:
        raise HTTPException(404, "That playlist is not in the library.") from exc


@app.get("/api/playlists")
def list_playlists() -> list[dict]:
    return service.db.list_playlists()


@app.post("/api/playlists/{playlist_id}/start")
def start_playlist(playlist_id: str, request: StartRequest) -> dict:
    try:
        return service.enqueue_range(
            playlist_id,
            height=request.height,
            container=request.container,
            output_dir=request.outputDir,
            start_from=request.startFrom,
            end_at=request.endAt,
            redownload=request.redownload,
        )
    except KeyError as exc:
        raise HTTPException(404, "That playlist is not in the library.") from exc


@app.post("/api/playlists/{playlist_id}/sync")
def sync_playlist(playlist_id: str) -> dict:
    try:
        return service.sync(playlist_id)
    except KeyError as exc:
        raise HTTPException(404, "That playlist is not in the library.") from exc


@app.get("/api/playlists/{playlist_id}/jobs")
def list_jobs(
    playlist_id: str,
    state: str = "",
    search: str = "",
    limit: int = 2000,
    offset: int = 0,
) -> dict:
    states = [part for part in state.split(",") if part] or None
    jobs = service.db.list_jobs(
        playlist_id, states=states, search=search, limit=limit, offset=offset
    )
    return {"jobs": jobs, "stats": service.db.stats(playlist_id)}


@app.get("/api/stats")
def stats(playlist_id: str = "") -> dict:
    return {
        "stats": service.db.stats(playlist_id or None),
        "bytes": service.db.downloaded_bytes(playlist_id or None),
        "paused": service.scheduler.paused,
    }


@app.post("/api/queue/pause")
def pause_queue() -> dict:
    service.scheduler.pause_all()
    return {"paused": True}


@app.post("/api/queue/resume")
def resume_queue() -> dict:
    service.scheduler.resume_all()
    return {"paused": False}


@app.post("/api/queue/retry-failed")
def retry_failed(playlist_id: str = "") -> dict:
    return {"requeued": service.scheduler.retry_failed(playlist_id or None)}


@app.post("/api/jobs/{job_id}/{action}")
def job_action(job_id: int, action: str) -> dict:
    actions = {
        "pause": service.scheduler.pause_job,
        "resume": service.scheduler.resume_job,
        "skip": service.scheduler.skip_job,
        "retry": service.scheduler.retry_job,
        "prioritise": service.scheduler.prioritise,
    }
    handler = actions.get(action)
    if handler is None:
        raise HTTPException(404, f"Unknown action '{action}'.")
    handler(job_id)
    return {"ok": True, "job": service.db.get_job(job_id)}


@app.get("/api/jobs/{job_id}/attempts")
def job_attempts(job_id: int) -> dict:
    return {"attempts": service.db.attempts_for(job_id)}


@app.get("/api/engine")
def engine() -> dict:
    try:
        return {"ytdlp": ytdlp.version()}
    except Exception as exc:  # noqa: BLE001 - report rather than fail the UI
        return {"ytdlp": "", "error": str(exc)}


@app.post("/api/reveal")
def reveal(request: RevealRequest) -> dict:
    target = Path(request.path)
    if not target.exists():
        raise HTTPException(404, "That file is no longer there.")
    if sys.platform == "darwin":
        argv = ["open", "-R", str(target)]
    elif sys.platform == "win32":
        argv = ["explorer", f"/select,{target}"]
    else:
        argv = ["xdg-open", str(target.parent)]
    subprocess.Popen(argv)
    return {"ok": True}


@app.websocket("/ws")
async def websocket(connection: WebSocket) -> None:
    await connection.accept()
    queue = service.events.subscribe()
    await connection.send_json(
        {
            "type": "stats",
            "stats": service.db.stats(),
            "paused": service.scheduler.paused,
            "concurrency": service.settings.parallel_videos,
        }
    )
    try:
        while True:
            event = await queue.get()
            await connection.send_json(event)
    except (WebSocketDisconnect, RuntimeError):
        pass
    finally:
        service.events.unsubscribe(queue)


if WEB_DIR.is_dir():
    app.mount("/", StaticFiles(directory=str(WEB_DIR), html=True), name="web")
else:

    @app.get("/", response_model=None)
    def _no_frontend() -> JSONResponse:
        return JSONResponse(
            {"detail": "The interface has not been built. Run `npm run build` in frontend/."},
            status_code=503,
        )
