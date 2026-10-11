import logging
from datetime import datetime, timedelta
from pathlib import Path

from fastapi import Depends, FastAPI, Request
from fastapi.responses import FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from sqlalchemy import text
from sqlalchemy.orm import Session
from starlette.middleware.sessions import SessionMiddleware

from .api import admin, auth, photos, plates, review
from .config import get_settings
from .db import get_db
from .pipeline import vlm
from .services import appsettings

log = logging.getLogger("platedex")


def create_app() -> FastAPI:
    s = get_settings()
    if s.secret_key == "change-me":
        log.warning("SECRET_KEY is not set. Set it in .env so sessions survive restarts and stay private.")
    app = FastAPI(title="Platedex", docs_url="/api/docs", openapi_url="/api/openapi.json", redoc_url=None)
    app.add_middleware(
        SessionMiddleware,
        secret_key=s.secret_key,
        session_cookie="platedex_session",
        max_age=s.session_days * 86400,
        same_site="lax",
        https_only=s.secure_cookies,
    )
    for r in (auth.router, photos.router, review.router, plates.router, admin.router):
        app.include_router(r)

    @app.get("/api/health")
    def health(db: Session = Depends(get_db)):
        db.execute(text("SELECT 1"))
        beat = appsettings.get(db, "worker_heartbeat")
        worker_ok = False
        if beat:
            worker_ok = datetime.utcnow() - datetime.fromisoformat(beat) < timedelta(minutes=2)
        mode = appsettings.get(db, "vlm_mode")
        return {"ok": True, "worker": worker_ok, "vlm_mode": mode, "vlm": vlm.status() if mode != "off" else None}

    static = s.static_dir or Path(__file__).resolve().parents[3] / "frontend" / "build"
    if static.exists():
        app.mount("/_app", StaticFiles(directory=static / "_app"), name="assets")
        index = static / "index.html"

        @app.get("/{path:path}", include_in_schema=False)
        def spa(path: str, request: Request):
            if path.startswith("api/"):
                return JSONResponse({"detail": "Not found"}, status_code=404)
            f = (static / path).resolve()
            if path and f.is_file() and static.resolve() in f.parents:
                return FileResponse(f)
            return FileResponse(index, headers={"Cache-Control": "no-cache"})
    else:
        log.warning("Frontend build not found at %s; serving the API only", static)
    return app


app = create_app()
