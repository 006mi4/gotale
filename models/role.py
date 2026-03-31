"""
Role model for managing roles and permissions.
"""

from utils.database import get_db


class Role:
    def __init__(self, id, name, description=None):
        self.id = id
        self.name = name
        self.description = description

    @staticmethod
    def get_all():
        with get_db() as conn:
            cursor = conn.cursor()
            cursor.execute('SELECT * FROM roles ORDER BY name')
            rows = cursor.fetchall()
        return [
            Role(id=row['id'], name=row['name'], description=row['description'])
            for row in rows
        ]

    @staticmethod
    def get_by_id(role_id):
        with get_db() as conn:
            cursor = conn.cursor()
            cursor.execute('SELECT * FROM roles WHERE id = ?', (role_id,))
            row = cursor.fetchone()
        if not row:
            return None
        return Role(id=row['id'], name=row['name'], description=row['description'])

    @staticmethod
    def create(name, description=None):
        import sqlite3
        try:
            with get_db() as conn:
                cursor = conn.cursor()
                cursor.execute(
                    'INSERT INTO roles (name, description) VALUES (?, ?)',
                    (name, description),
                )
                role_id = cursor.lastrowid
            return role_id
        except sqlite3.IntegrityError:
            return None

    @staticmethod
    def delete(role_id):
        with get_db() as conn:
            cursor = conn.cursor()
            cursor.execute('DELETE FROM role_permissions WHERE role_id = ?', (role_id,))
            cursor.execute('DELETE FROM user_roles WHERE role_id = ?', (role_id,))
            cursor.execute('DELETE FROM roles WHERE id = ?', (role_id,))

    @staticmethod
    def set_permissions(role_id, permission_ids):
        with get_db() as conn:
            cursor = conn.cursor()
            cursor.execute('DELETE FROM role_permissions WHERE role_id = ?', (role_id,))
            for permission_id in permission_ids:
                cursor.execute(
                    'INSERT OR IGNORE INTO role_permissions (role_id, permission_id) VALUES (?, ?)',
                    (role_id, permission_id),
                )

    @staticmethod
    def get_permissions(role_id):
        with get_db() as conn:
            cursor = conn.cursor()
            cursor.execute('''
                SELECT permissions.id, permissions.key, permissions.description
                FROM permissions
                INNER JOIN role_permissions ON role_permissions.permission_id = permissions.id
                WHERE role_permissions.role_id = ?
            ''', (role_id,))
            rows = cursor.fetchall()
        return rows

    @staticmethod
    def get_permission_ids(role_id):
        with get_db() as conn:
            cursor = conn.cursor()
            cursor.execute('''
                SELECT permission_id
                FROM role_permissions
                WHERE role_id = ?
            ''', (role_id,))
            ids = {row[0] for row in cursor.fetchall()}
        return ids

    @staticmethod
    def get_permission_catalog():
        with get_db() as conn:
            cursor = conn.cursor()
            cursor.execute('SELECT * FROM permissions ORDER BY key')
            rows = cursor.fetchall()
        return rows
