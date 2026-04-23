"""Daily SQLite backup + retention cleanup."""
from __future__ import annotations

import logging
import shutil
from datetime import datetime, timedelta
from pathlib import Path

from config.settings import settings

logger = logging.getLogger(__name__)


def backup_database() -> Path | None:
    """Copy the SQLite DB to the backup directory using SQLite's online-backup API.

    Returns the path of the new backup file on success, None on failure.
    """
    src = Path(settings.db_path)
    if not src.exists():
        logger.warning("DB backup skipped — source not found at %s", src)
        return None

    dest_dir = Path(settings.db_backup_dir)
    dest_dir.mkdir(parents=True, exist_ok=True)
    stamp = datetime.utcnow().strftime("%Y%m%d_%H%M%S")
    dest = dest_dir / f"viralstack_{stamp}.db"

    try:
        # Use sqlite3 backup API for a consistent snapshot even under concurrent writes.
        import sqlite3
        with sqlite3.connect(str(src)) as src_conn, sqlite3.connect(str(dest)) as dst_conn:
            src_conn.backup(dst_conn)
        logger.info("DB backup created: %s (%.1f MB)", dest, dest.stat().st_size / 1e6)
    except Exception as e:
        logger.warning("SQLite online backup failed (%s), falling back to file copy", e)
        try:
            shutil.copy2(src, dest)
        except Exception as ee:
            logger.error("DB backup failed: %s", ee)
            return None

    _prune_old_backups(dest_dir)
    return dest


def _prune_old_backups(dest_dir: Path) -> None:
    keep_days = max(1, settings.db_backup_keep_days)
    cutoff = datetime.utcnow() - timedelta(days=keep_days)
    for f in dest_dir.glob("viralstack_*.db"):
        try:
            mtime = datetime.utcfromtimestamp(f.stat().st_mtime)
            if mtime < cutoff:
                f.unlink(missing_ok=True)
                logger.info("DB backup pruned: %s", f.name)
        except Exception as e:
            logger.warning("Backup prune failed for %s: %s", f, e)
