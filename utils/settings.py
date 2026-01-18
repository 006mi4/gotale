"""
Settings helpers for system settings stored in SQLite.
"""

import sqlite3


def get_setting(db_path, key, default=None):
    try:
        conn = sqlite3.connect(db_path)
        cursor = conn.cursor()
        cursor.execute("SELECT value FROM settings WHERE key = ?", (key,))
        row = cursor.fetchone()
        conn.close()
        if row and row[0] is not None:
            return row[0]
    except Exception:
        return default
    return default


def set_setting(db_path, key, value):
    conn = sqlite3.connect(db_path)
    cursor = conn.cursor()
    cursor.execute(
        "INSERT OR REPLACE INTO settings (key, value) VALUES (?, ?)",
        (key, value),
    )
    conn.commit()
    conn.close()


def get_settings(db_path, keys):
    if not keys:
        return {}
    conn = sqlite3.connect(db_path)
    cursor = conn.cursor()
    placeholders = ",".join("?" for _ in keys)
    cursor.execute(
        f"SELECT key, value FROM settings WHERE key IN ({placeholders})",
        list(keys),
    )
    rows = cursor.fetchall()
    conn.close()
    return {row[0]: row[1] for row in rows}
