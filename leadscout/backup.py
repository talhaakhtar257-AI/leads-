"""Automatic backups of the leads database, so a mistake or crash never loses your leads."""
from __future__ import annotations

import sqlite3
from datetime import datetime
from pathlib import Path

KEEP = 10


def backup_dir(db_path: str | Path) -> Path:
    return Path(db_path).resolve().parent / "backups"


def backup_db(db_path: str | Path, keep: int = KEEP) -> Path | None:
    """Copy the database with SQLite's online backup (safe while it's in use). Keeps the newest `keep`."""
    src_path = Path(db_path)
    if not src_path.exists():
        return None
    folder = backup_dir(src_path)
    folder.mkdir(parents=True, exist_ok=True)
    stamp = datetime.now().strftime("%Y%m%d-%H%M%S-%f")
    dest_path = folder / f"{src_path.stem}-{stamp}.db"
    src = sqlite3.connect(str(src_path))
    dest = sqlite3.connect(str(dest_path))
    try:
        src.backup(dest)
    finally:
        dest.close()
        src.close()
    for old in list_backups(src_path)[keep:]:
        old.unlink(missing_ok=True)
    return dest_path


def list_backups(db_path: str | Path) -> list[Path]:
    """Newest first."""
    folder = backup_dir(db_path)
    return sorted(folder.glob(f"{Path(db_path).stem}-*.db"), reverse=True) if folder.exists() else []


def restore(backup_file: str | Path, db_path: str | Path) -> Path | None:
    """Replace the database with a backup. The current database is backed up first, just in case."""
    backup_file = Path(backup_file)
    if not backup_file.exists():
        raise FileNotFoundError(f"No backup at {backup_file}")
    safety = backup_db(db_path, keep=KEEP + 1)
    src = sqlite3.connect(str(backup_file))
    dest = sqlite3.connect(str(db_path))
    try:
        src.backup(dest)
    finally:
        dest.close()
        src.close()
    return safety
