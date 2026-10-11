import argparse
import getpass
import sys
from pathlib import Path


def _migrate() -> None:
    from alembic import command
    from alembic.config import Config

    from .config import get_settings

    s = get_settings()
    s.data_dir.mkdir(parents=True, exist_ok=True)
    cfg = Config()
    cfg.set_main_option("script_location", str(Path(__file__).parent / "migrations"))
    cfg.set_main_option("sqlalchemy.url", s.db_url)
    command.upgrade(cfg, "head")


def main(argv: list[str] | None = None) -> None:
    ap = argparse.ArgumentParser(prog="platedex")
    sub = ap.add_subparsers(dest="cmd", required=True)
    sub.add_parser("migrate", help="Create or upgrade the database")
    sub.add_parser("worker", help="Run the background worker")
    sd = sub.add_parser("seed-demo", help="Load the demo plates and users from the design prototype")
    sd.add_argument("--password", default="platedex-demo")
    ca = sub.add_parser("create-admin", help="Create an admin account")
    ca.add_argument("username")
    rp = sub.add_parser("reset-password", help="Set a user's password")
    rp.add_argument("username")
    pg = sub.add_parser("prepare-geo", help="Build the offline place-name file from a GeoNames dump")
    pg.add_argument("source", type=Path)
    pg.add_argument("--out", type=Path, default=None)
    sub.add_parser("download-models", help="Download the plate detector and OCR models")
    bk = sub.add_parser("backup", help="Write a consistent copy of the database (safe while running)")
    bk.add_argument("--out", type=Path, default=None)
    bs = sub.add_parser("build-shortcut", help="Write the iOS Shortcut template (README → iOS Shortcut)")
    bs.add_argument("--out", type=Path, default=Path("Platedex-unsigned.shortcut"))
    args = ap.parse_args(argv)

    if args.cmd == "migrate":
        _migrate()
        print("Database is up to date")
        from .db import db_session
        from .services.appsettings import sync_env

        with db_session() as db:
            names = sync_env(db)
        if names:
            print("Locked by environment (read-only in More → Admin): " + ", ".join(names))
    elif args.cmd == "worker":
        from .worker import main as worker_main

        worker_main()
    elif args.cmd == "seed-demo":
        from .db import db_session
        from .seed import seed_demo

        with db_session() as db:
            print(seed_demo(db, password=args.password))
    elif args.cmd in ("create-admin", "reset-password"):
        from sqlalchemy import select

        from .api.auth import USERNAME_RE, clean_username, next_color
        from .db import db_session, utcnow
        from .models import User
        from .security import hash_password

        username = clean_username(args.username)
        if not USERNAME_RE.match(username):
            sys.exit("Usernames are 2–32 characters: letters, numbers, . _ -")
        pw = getpass.getpass("Password: ")
        if len(pw) < 8:
            sys.exit("Use at least 8 characters")
        with db_session() as db:
            u = db.scalar(select(User).where(User.username == username))
            if args.cmd == "create-admin":
                if u is not None:
                    sys.exit("That user already exists; use reset-password")
                u = User(username=username, role="admin", color=next_color(db))
                db.add(u)
            elif u is None:
                sys.exit("No such user")
            u.password_hash, u.password_changed_at = hash_password(pw), utcnow()
            u.session_version = (u.session_version or 0) + 1
            db.commit()
        print("Done")
    elif args.cmd == "prepare-geo":
        from .services.geo import geo_dir, prepare_geo

        out = args.out or geo_dir() / "cities.tsv.gz"
        n = prepare_geo(args.source, out)
        print(f"Wrote {n} places to {out}")
    elif args.cmd == "backup":
        import sqlite3
        from datetime import datetime

        from .config import get_settings

        s = get_settings()
        out = args.out or s.data_dir / "backups" / f"platedex-{datetime.now():%Y%m%d-%H%M%S}.db"
        out.parent.mkdir(parents=True, exist_ok=True)
        src = sqlite3.connect(s.data_dir / "platedex.db")
        dst = sqlite3.connect(out)
        with dst:
            src.backup(dst)
        src.close()
        dst.close()
        print(f"Database copied to {out}. Back up {s.photos_dir} too (photos are plain files).")
    elif args.cmd == "download-models":
        from .pipeline.engines import get_engine

        get_engine()
        print("Models ready")
    elif args.cmd == "build-shortcut":
        from .services.shortcut import write_unsigned

        out = write_unsigned(args.out)
        print(f"Wrote {out}. Next, on a Mac (README → iOS Shortcut):\n"
              f"  shortcuts sign --mode anyone -i {out} -o Platedex.shortcut && open Platedex.shortcut\n"
              "Then share it from the Shortcuts app with Copy iCloud Link and paste that in More → Admin.")


if __name__ == "__main__":
    main()
