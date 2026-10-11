"""A small job queue stored in the database. One worker process drains it."""

from typing import Any

from sqlalchemy import select, update
from sqlalchemy.orm import Session

from ..db import utcnow
from ..models import Job

PRIORITY_INTERACTIVE = 0  # a user is waiting (drew a box)
PRIORITY_UPLOAD = 5
PRIORITY_BACKGROUND = 9  # reprocess-all


def enqueue(
    db: Session, kind: str, payload: dict[str, Any], priority: int = PRIORITY_UPLOAD, batch: str | None = None
) -> Job:
    job = Job(kind=kind, payload=payload, priority=priority, batch=batch)
    db.add(job)
    db.flush()
    return job


def claim_next(db: Session, paused_batch: str | None = None) -> Job | None:
    stmt = select(Job).where(Job.status == "queued").order_by(Job.priority, Job.id).limit(1)
    if paused_batch:
        stmt = stmt.where((Job.batch.is_(None)) | (Job.batch != paused_batch))
    job = db.scalars(stmt).first()
    if job is None:
        return None
    job.status = "running"
    job.started_at = utcnow()
    job.attempts += 1
    db.commit()
    return job


def requeue_stale(db: Session) -> int:
    """Jobs left 'running' by a crashed worker go back to the queue."""
    res = db.execute(update(Job).where(Job.status == "running").values(status="queued"))
    db.commit()
    return res.rowcount or 0


def batch_progress(db: Session, batch: str) -> dict[str, int]:
    rows = db.execute(select(Job.status, Job.result).where(Job.batch == batch, Job.kind == "process_photo"))
    total = done = changed = 0
    for status, result in rows:
        total += 1
        if status in ("done", "failed"):
            done += 1
            if result and result.get("changed"):
                changed += 1
    return {"total": total, "done": done, "changed": changed}
