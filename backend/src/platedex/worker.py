"""Background worker: drains the job queue (plate reading) and watches the import folder."""

import logging
import signal
import threading
import time
import traceback

from sqlalchemy import select

from .config import get_settings
from .db import db_session, utcnow
from .models import Detection, Job, Photo, User
from .pipeline import vlm
from .pipeline.engines import get_engine
from .pipeline.process import process_photo, read_box, update_photo_status
from .services import appsettings, jobs

log = logging.getLogger("platedex.worker")
IMAGE_EXT = {".jpg", ".jpeg", ".heic", ".heif", ".png", ".webp", ".avif"}
MAX_ATTEMPTS = 3


def handle(db, job: Job) -> dict:
    if job.kind == "process_photo":
        return process_photo(db, job.payload["photo_id"], reprocess=bool(job.payload.get("reprocess")))
    if job.kind == "read_box":
        det = read_box(db, job.payload["detection_id"], job.payload["bbox"])
        return {"status": det.status, "text": det.text}
    raise ValueError(f"Unknown job kind {job.kind}")


def _fail(job_id: int, err: str) -> None:
    with db_session() as db:
        job = db.get(Job, job_id)
        if job is None:
            return
        retry = job.attempts < MAX_ATTEMPTS and "FileNotFoundError" not in err
        job.status = "queued" if retry else "failed"
        job.error = err[-2000:]
        job.finished_at = None if retry else utcnow()
        if not retry:
            if job.kind == "process_photo":
                photo = db.get(Photo, job.payload.get("photo_id"))
                if photo is not None:
                    photo.status = "failed"
                    photo.error = "Couldn't read this photo: " + err.strip().splitlines()[-1][:160]
            elif job.kind == "read_box":
                det = db.get(Detection, job.payload.get("detection_id"))
                if det is not None:
                    det.status, det.reason = "needs_identify", "Couldn't read that box. Try again."
                    update_photo_status(det.photo)
        db.commit()


def run_once() -> bool:
    """Run one job if there is one. Returns True if a job ran."""
    with db_session() as db:
        paused = appsettings.get(db, "reprocess_batch") if appsettings.get(db, "reprocess_paused") else None
        job = jobs.claim_next(db, paused_batch=paused)
        if job is None:
            return False
        job_id = job.id
        try:
            result = handle(db, job)
            job = db.get(Job, job_id)
            job.status, job.result, job.finished_at, job.error = "done", result, utcnow(), None
            db.commit()
        except Exception:  # noqa: BLE001
            db.rollback()
            err = traceback.format_exc()
            log.error("Job %s (%s) failed:\n%s", job_id, job.kind, err)
            _fail(job_id, err)
    return True


def scan_import_dir() -> int:
    s = get_settings()
    if not s.import_dir or not s.import_user or not s.import_dir.exists():
        return 0
    from .api.photos import ingest

    done_dir = s.import_dir / ".imported"
    n = 0
    with db_session() as db:
        user = db.scalar(select(User).where(User.username == s.import_user))
        if user is None:
            log.warning("IMPORT_USER %s doesn't exist; skipping import folder", s.import_user)
            return 0
        for path in sorted(s.import_dir.rglob("*")):
            if done_dir in path.parents or not path.is_file() or path.suffix.lower() not in IMAGE_EXT:
                continue
            if time.time() - path.stat().st_mtime < 10:
                continue  # still being written by the sync tool
            try:
                ingest(db, user, path.read_bytes(), path.name, capture_mode="import")
                dest = done_dir / path.relative_to(s.import_dir)
                dest.parent.mkdir(parents=True, exist_ok=True)
                path.rename(dest)
                n += 1
            except Exception as e:  # noqa: BLE001
                db.rollback()
                log.warning("Import of %s failed: %s", path, e)
    return n


def main() -> None:
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")
    stop = threading.Event()
    signal.signal(signal.SIGTERM, lambda *_: stop.set())
    signal.signal(signal.SIGINT, lambda *_: stop.set())

    with db_session() as db:
        n = jobs.requeue_stale(db)
        if n:
            log.info("Requeued %d interrupted jobs", n)
        mode = appsettings.get(db, "vlm_mode")
    if mode != "off" and get_settings().ollama_url:
        threading.Thread(target=_pull_model, daemon=True).start()
    get_engine()
    log.info("Worker ready")

    last_beat = last_scan = 0.0
    while not stop.is_set():
        now = time.monotonic()
        if now - last_beat > 15:
            with db_session() as db:
                appsettings.put(db, "worker_heartbeat", utcnow().isoformat())
            last_beat = now
        if now - last_scan > 30:
            try:
                scan_import_dir()
            except Exception as e:  # noqa: BLE001
                log.warning("Import scan failed: %s", e)
            last_scan = now
        if not run_once():
            stop.wait(1.0)
    log.info("Worker stopped")


def _pull_model() -> None:
    for _ in range(60):  # Ollama may still be starting
        try:
            if vlm.status()["reachable"]:
                vlm.ensure_model()
                return
        except Exception as e:  # noqa: BLE001
            log.warning("Model pull failed: %s", e)
            return
        time.sleep(5)


if __name__ == "__main__":
    main()

