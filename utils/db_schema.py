"""
Database schema helpers for roles, permissions, and user flags.
"""

import sqlite3

PERMISSIONS = [
    ('view_servers', 'View dashboard and server pages'),
    ('manage_servers', 'Create, start, stop, restart, and delete servers'),
    ('manage_configs', 'Edit server config, world, and player data'),
    ('manage_users', 'Create users and reset passwords'),
    ('manage_roles', 'Create roles and assign permissions'),
    ('manage_updates', 'Run system update actions'),
    ('manage_downloads', 'Download server files'),
]


def _table_exists(cursor, name):
    cursor.execute(
        "SELECT name FROM sqlite_master WHERE type='table' AND name = ?",
        (name,),
    )
    return cursor.fetchone() is not None


def _column_exists(cursor, table_name, column_name):
    cursor.execute(f"PRAGMA table_info({table_name})")
    return any(row[1] == column_name for row in cursor.fetchall())


def ensure_schema(db_path):
    """Ensure role/permission tables and user flags exist."""
    conn = sqlite3.connect(db_path)
    cursor = conn.cursor()

    if not _table_exists(cursor, 'roles'):
        cursor.execute('''
            CREATE TABLE roles (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                name TEXT UNIQUE NOT NULL,
                description TEXT,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        ''')

    if not _table_exists(cursor, 'permissions'):
        cursor.execute('''
            CREATE TABLE permissions (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                key TEXT UNIQUE NOT NULL,
                description TEXT
            )
        ''')

    if not _table_exists(cursor, 'role_permissions'):
        cursor.execute('''
            CREATE TABLE role_permissions (
                role_id INTEGER NOT NULL,
                permission_id INTEGER NOT NULL,
                PRIMARY KEY (role_id, permission_id),
                FOREIGN KEY (role_id) REFERENCES roles(id) ON DELETE CASCADE,
                FOREIGN KEY (permission_id) REFERENCES permissions(id) ON DELETE CASCADE
            )
        ''')

    if not _table_exists(cursor, 'user_roles'):
        cursor.execute('''
            CREATE TABLE user_roles (
                user_id INTEGER NOT NULL,
                role_id INTEGER NOT NULL,
                PRIMARY KEY (user_id, role_id),
                FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE CASCADE,
                FOREIGN KEY (role_id) REFERENCES roles(id) ON DELETE CASCADE
            )
        ''')

    if not _column_exists(cursor, 'users', 'must_change_password'):
        cursor.execute('''
            ALTER TABLE users
            ADD COLUMN must_change_password BOOLEAN DEFAULT 0
        ''')

    for key, description in PERMISSIONS:
        cursor.execute(
            '''
            INSERT OR IGNORE INTO permissions (key, description)
            VALUES (?, ?)
            ''',
            (key, description),
        )

    conn.commit()
    conn.close()
