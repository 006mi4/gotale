"""
Role model for managing roles and permissions.
"""

import sqlite3
import os

DB_PATH = os.path.join(os.path.dirname(os.path.dirname(__file__)), 'database.db')


class Role:
    def __init__(self, id, name, description=None):
        self.id = id
        self.name = name
        self.description = description

    @staticmethod
    def get_all():
        conn = sqlite3.connect(DB_PATH)
        conn.row_factory = sqlite3.Row
        cursor = conn.cursor()
        cursor.execute('SELECT * FROM roles ORDER BY name')
        rows = cursor.fetchall()
        conn.close()
        return [
            Role(id=row['id'], name=row['name'], description=row['description'])
            for row in rows
        ]

    @staticmethod
    def get_by_id(role_id):
        conn = sqlite3.connect(DB_PATH)
        conn.row_factory = sqlite3.Row
        cursor = conn.cursor()
        cursor.execute('SELECT * FROM roles WHERE id = ?', (role_id,))
        row = cursor.fetchone()
        conn.close()
        if not row:
            return None
        return Role(id=row['id'], name=row['name'], description=row['description'])

    @staticmethod
    def create(name, description=None):
        conn = sqlite3.connect(DB_PATH)
        cursor = conn.cursor()
        try:
            cursor.execute(
                'INSERT INTO roles (name, description) VALUES (?, ?)',
                (name, description),
            )
            conn.commit()
            role_id = cursor.lastrowid
            conn.close()
            return role_id
        except sqlite3.IntegrityError:
            conn.close()
            return None

    @staticmethod
    def delete(role_id):
        conn = sqlite3.connect(DB_PATH)
        cursor = conn.cursor()
        cursor.execute('DELETE FROM role_permissions WHERE role_id = ?', (role_id,))
        cursor.execute('DELETE FROM user_roles WHERE role_id = ?', (role_id,))
        cursor.execute('DELETE FROM roles WHERE id = ?', (role_id,))
        conn.commit()
        conn.close()

    @staticmethod
    def set_permissions(role_id, permission_ids):
        conn = sqlite3.connect(DB_PATH)
        cursor = conn.cursor()
        cursor.execute('DELETE FROM role_permissions WHERE role_id = ?', (role_id,))
        for permission_id in permission_ids:
            cursor.execute(
                'INSERT OR IGNORE INTO role_permissions (role_id, permission_id) VALUES (?, ?)',
                (role_id, permission_id),
            )
        conn.commit()
        conn.close()

    @staticmethod
    def get_permissions(role_id):
        conn = sqlite3.connect(DB_PATH)
        cursor = conn.cursor()
        cursor.execute('''
            SELECT permissions.id, permissions.key, permissions.description
            FROM permissions
            INNER JOIN role_permissions ON role_permissions.permission_id = permissions.id
            WHERE role_permissions.role_id = ?
        ''', (role_id,))
        rows = cursor.fetchall()
        conn.close()
        return rows

    @staticmethod
    def get_permission_ids(role_id):
        conn = sqlite3.connect(DB_PATH)
        cursor = conn.cursor()
        cursor.execute('''
            SELECT permission_id
            FROM role_permissions
            WHERE role_id = ?
        ''', (role_id,))
        ids = {row[0] for row in cursor.fetchall()}
        conn.close()
        return ids

    @staticmethod
    def get_permission_catalog():
        conn = sqlite3.connect(DB_PATH)
        conn.row_factory = sqlite3.Row
        cursor = conn.cursor()
        cursor.execute('SELECT * FROM permissions ORDER BY key')
        rows = cursor.fetchall()
        conn.close()
        return rows
