"""
Settings helpers for system settings stored in SQLite.
"""

import logging
import sqlite3

from utils.database import get_db

logger = logging.getLogger(__name__)


def get_setting(db_path, key, default=None):
    try:
        with get_db(db_path) as conn:
            cursor = conn.cursor()
            cursor.execute("SELECT value FROM settings WHERE key = ?", (key,))
            row = cursor.fetchone()
        if row and row[0] is not None:
            return row[0]
    except sqlite3.Error as exc:
        logger.error(f"Error reading setting '{key}': {exc}", exc_info=True)
        return default
    return default


def set_setting(db_path, key, value):
    with get_db(db_path) as conn:
        cursor = conn.cursor()
        cursor.execute(
            "INSERT OR REPLACE INTO settings (key, value) VALUES (?, ?)",
            (key, value),
        )


def get_settings(db_path, keys):
    if not keys:
        return {}
    with get_db(db_path) as conn:
        cursor = conn.cursor()
        placeholders = ",".join("?" for _ in keys)
        cursor.execute(
            f"SELECT key, value FROM settings WHERE key IN ({placeholders})",
            list(keys),
        )
        rows = cursor.fetchall()
    return {row[0]: row[1] for row in rows}
