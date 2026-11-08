"""Watch folder (IMPORT_DIR): photos dropped in by a sync tool are credited to IMPORT_USER and moved aside."""

import os
import time

import pytest
from conftest import jpeg, make_admin

from platedex.config import get_settings
from platedex.db import db_session
from platedex.models import Job, Photo
from platedex.worker import scan_import_dir


def drop(folder, name, data, age=60):
    """Write a file as if a sync tool finished it `age` seconds ago."""
    path = folder / name
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(data)
    t = time.time() - age
    os.utime(path, (t, t))
    return path


@pytest.fixture()
def import_dir(client, tmp_path, monkeypatch):
    make_admin(client, "alex")
    folder = tmp_path / "import"
    folder.mkdir()
    monkeypatch.setattr(get_settings(), "import_dir", folder)
    monkeypatch.setattr(get_settings(), "import_user", "alex")
    return folder


def photos():
    with db_session() as db:
        return [(p.original_name, p.capture_mode, p.uploader.username, p.lat is not None) for p in
                db.query(Photo).order_by(Photo.id)]


def test_imports_photos_and_moves_them(import_dir):
    drop(import_dir, "IMG_1.jpg", jpeg())
    drop(import_dir, "trip/IMG_2.JPG", jpeg(color=(10, 20, 30)))
    assert scan_import_dir() == 2
    assert photos() == [("IMG_1.jpg", "import", "alex", True), ("IMG_2.JPG", "import", "alex", True)]
    assert (import_dir / ".imported" / "IMG_1.jpg").exists()
    assert (import_dir / ".imported" / "trip" / "IMG_2.JPG").exists()
    assert not (import_dir / "IMG_1.jpg").exists()
    with db_session() as db:
        assert db.query(Job).filter(Job.kind == "process_photo").count() == 2
    assert scan_import_dir() == 0  # moved files aren't read again


def test_waits_for_files_still_being_written(import_dir):
    drop(import_dir, "fresh.jpg", jpeg(), age=0)
    assert scan_import_dir() == 0
    assert (import_dir / "fresh.jpg").exists()


def test_skips_other_files(import_dir):
    drop(import_dir, "notes.txt", b"hello")
    drop(import_dir, ".DS_Store", b"\0")
    assert scan_import_dir() == 0
    assert (import_dir / "notes.txt").exists()
    assert photos() == []


def test_duplicate_is_moved_without_a_second_photo(import_dir):
    data = jpeg()
    drop(import_dir, "a.jpg", data)
    assert scan_import_dir() == 1
    drop(import_dir, "copy-of-a.jpg", data)
    assert scan_import_dir() == 1
    assert len(photos()) == 1
    assert (import_dir / ".imported" / "copy-of-a.jpg").exists()


def test_unreadable_photo_is_set_aside(import_dir):
    drop(import_dir, "broken.jpg", b"not really a jpeg")
    drop(import_dir, "good.jpg", jpeg())
    assert scan_import_dir() == 1
    assert (import_dir / ".failed" / "broken.jpg").exists()
    assert not (import_dir / "broken.jpg").exists()
    assert scan_import_dir() == 0  # not retried every scan
    assert [p[0] for p in photos()] == ["good.jpg"]


def test_unknown_import_user_imports_nothing(import_dir, monkeypatch):
    monkeypatch.setattr(get_settings(), "import_user", "nobody")
    drop(import_dir, "IMG_1.jpg", jpeg())
    assert scan_import_dir() == 0
    assert (import_dir / "IMG_1.jpg").exists()


def test_off_without_import_dir(client, monkeypatch):
    monkeypatch.setattr(get_settings(), "import_dir", None)
    assert scan_import_dir() == 0
