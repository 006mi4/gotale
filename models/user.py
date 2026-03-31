"""
User model for authentication and user management
"""

import sqlite3
import os
from flask_login import UserMixin
from werkzeug.security import generate_password_hash, check_password_hash

DB_PATH = os.path.join(os.path.dirname(os.path.dirname(__file__)), 'database.db')

class User(UserMixin):
    def __init__(self, id, username, email, is_superadmin=False, must_change_password=False, all_servers_access=False):
        self.id = id
        self.username = username
        self.email = email
        self.is_superadmin = is_superadmin
        self.must_change_password = must_change_password
        self.all_servers_access = all_servers_access

    @staticmethod
    def get_by_id(user_id):
        """Get user by ID"""
        conn = sqlite3.connect(DB_PATH)
        conn.row_factory = sqlite3.Row
        cursor = conn.cursor()

        cursor.execute('SELECT * FROM users WHERE id = ?', (user_id,))
        row = cursor.fetchone()
        conn.close()

        if row:
            return User(
                id=row['id'],
                username=row['username'],
                email=row['email'],
                is_superadmin=bool(row['is_superadmin']),
                must_change_password=bool(row['must_change_password']),
                all_servers_access=bool(row['all_servers_access'])
            )
        return None

    @staticmethod
    def get_by_username(username):
        """Get user by username"""
        conn = sqlite3.connect(DB_PATH)
        conn.row_factory = sqlite3.Row
        cursor = conn.cursor()

        cursor.execute('SELECT * FROM users WHERE username = ?', (username,))
        row = cursor.fetchone()
        conn.close()

        if row:
            return User(
                id=row['id'],
                username=row['username'],
                email=row['email'],
                is_superadmin=bool(row['is_superadmin']),
                must_change_password=bool(row['must_change_password']),
                all_servers_access=bool(row['all_servers_access'])
            )
        return None

    @staticmethod
    def get_by_email(email):
        """Get user by email"""
        conn = sqlite3.connect(DB_PATH)
        conn.row_factory = sqlite3.Row
        cursor = conn.cursor()

        cursor.execute('SELECT * FROM users WHERE email = ?', (email,))
        row = cursor.fetchone()
        conn.close()

        if row:
            return User(
                id=row['id'],
                username=row['username'],
                email=row['email'],
                is_superadmin=bool(row['is_superadmin']),
                must_change_password=bool(row['must_change_password']),
                all_servers_access=bool(row['all_servers_access'])
            )
        return None

    @staticmethod
    def create_user(username, email, password, is_superadmin=False, must_change_password=False, all_servers_access=False):
        """Create a new user"""
        conn = sqlite3.connect(DB_PATH)
        cursor = conn.cursor()

        password_hash = generate_password_hash(password)

        try:
            cursor.execute('''
                INSERT INTO users (username, email, password_hash, is_superadmin, must_change_password, all_servers_access)
                VALUES (?, ?, ?, ?, ?, ?)
            ''', (username, email, password_hash, int(is_superadmin), int(must_change_password), int(all_servers_access)))

            conn.commit()
            user_id = cursor.lastrowid
            conn.close()

            return User(
                id=user_id,
                username=username,
                email=email,
                is_superadmin=is_superadmin,
                must_change_password=must_change_password,
                all_servers_access=all_servers_access
            )
        except sqlite3.IntegrityError:
            conn.close()
            return None

    @staticmethod
    def verify_password(username, password):
        """Verify user password"""
        conn = sqlite3.connect(DB_PATH)
        conn.row_factory = sqlite3.Row
        cursor = conn.cursor()

        cursor.execute('SELECT password_hash FROM users WHERE username = ?', (username,))
        row = cursor.fetchone()
        conn.close()

        if row:
            return check_password_hash(row['password_hash'], password)
        return False

    @staticmethod
    def set_password(user_id, new_password, must_change_password=False):
        """Set a new password for a user."""
        conn = sqlite3.connect(DB_PATH)
        cursor = conn.cursor()
        password_hash = generate_password_hash(new_password)
        cursor.execute('''
            UPDATE users
            SET password_hash = ?, must_change_password = ?
            WHERE id = ?
        ''', (password_hash, int(must_change_password), user_id))
        conn.commit()
        conn.close()

    @staticmethod
    def set_must_change_password(user_id, must_change_password):
        """Toggle the must_change_password flag."""
        conn = sqlite3.connect(DB_PATH)
        cursor = conn.cursor()
        cursor.execute('''
            UPDATE users
            SET must_change_password = ?
            WHERE id = ?
        ''', (int(must_change_password), user_id))
        conn.commit()
        conn.close()

    @staticmethod
    def set_all_servers_access(user_id, all_servers_access):
        """Toggle the all_servers_access flag."""
        conn = sqlite3.connect(DB_PATH)
        cursor = conn.cursor()
        cursor.execute('''
            UPDATE users
            SET all_servers_access = ?
            WHERE id = ?
        ''', (int(all_servers_access), user_id))
        conn.commit()
        conn.close()

    @staticmethod
    def has_all_servers_access(user_id):
        conn = sqlite3.connect(DB_PATH)
        cursor = conn.cursor()
        cursor.execute('SELECT all_servers_access FROM users WHERE id = ?', (user_id,))
        row = cursor.fetchone()
        conn.close()
        if not row:
            return False
        return bool(row[0])

    @staticmethod
    def get_roles(user_id):
        """Return role records for a user."""
        conn = sqlite3.connect(DB_PATH)
        conn.row_factory = sqlite3.Row
        cursor = conn.cursor()
        cursor.execute('''
            SELECT roles.id, roles.name, roles.description
            FROM roles
            INNER JOIN user_roles ON user_roles.role_id = roles.id
            WHERE user_roles.user_id = ?
            ORDER BY roles.name
        ''', (user_id,))
        roles = cursor.fetchall()
        conn.close()
        return roles

    @staticmethod
    def set_roles(user_id, role_ids):
        """Replace user roles with the provided list."""
        conn = sqlite3.connect(DB_PATH)
        cursor = conn.cursor()
        cursor.execute('DELETE FROM user_roles WHERE user_id = ?', (user_id,))
        for role_id in role_ids:
            cursor.execute(
                'INSERT OR IGNORE INTO user_roles (user_id, role_id) VALUES (?, ?)',
                (user_id, role_id)
            )
        conn.commit()
        conn.close()

    @staticmethod
    def get_permissions(user_id):
        """Return a set of permission keys for a user."""
        conn = sqlite3.connect(DB_PATH)
        cursor = conn.cursor()
        cursor.execute('''
            SELECT DISTINCT permissions.key
            FROM permissions
            INNER JOIN role_permissions ON role_permissions.permission_id = permissions.id
            INNER JOIN user_roles ON user_roles.role_id = role_permissions.role_id
            WHERE user_roles.user_id = ?
        ''', (user_id,))
        keys = {row[0] for row in cursor.fetchall()}
        conn.close()
        return keys

    @staticmethod
    def get_server_access_ids(user_id):
        conn = sqlite3.connect(DB_PATH)
        cursor = conn.cursor()
        cursor.execute('SELECT server_id FROM user_server_access WHERE user_id = ?', (user_id,))
        server_ids = {row[0] for row in cursor.fetchall()}
        conn.close()
        return server_ids

    @staticmethod
    def set_server_access(user_id, server_ids):
        conn = sqlite3.connect(DB_PATH)
        cursor = conn.cursor()
        cursor.execute('DELETE FROM user_server_access WHERE user_id = ?', (user_id,))
        for server_id in server_ids:
            cursor.execute(
                'INSERT OR IGNORE INTO user_server_access (user_id, server_id) VALUES (?, ?)',
                (user_id, server_id),
            )
        conn.commit()
        conn.close()

    @staticmethod
    def grant_server_access(user_id, server_id):
        conn = sqlite3.connect(DB_PATH)
        cursor = conn.cursor()
        cursor.execute(
            'INSERT OR IGNORE INTO user_server_access (user_id, server_id) VALUES (?, ?)',
            (user_id, server_id),
        )
        conn.commit()
        conn.close()

    @staticmethod
    def remove_server_access_for_server(server_id):
        conn = sqlite3.connect(DB_PATH)
        cursor = conn.cursor()
        cursor.execute('DELETE FROM user_server_access WHERE server_id = ?', (server_id,))
        conn.commit()
        conn.close()

    @staticmethod
    def has_server_access(user_id, server_id):
        if User.has_all_servers_access(user_id):
            return True
        conn = sqlite3.connect(DB_PATH)
        cursor = conn.cursor()
        cursor.execute('''
            SELECT 1
            FROM user_server_access
            WHERE user_id = ? AND server_id = ?
            LIMIT 1
        ''', (user_id, server_id))
        result = cursor.fetchone() is not None
        conn.close()
        return result

    @staticmethod
    def has_permission(user_id, permission_key):
        """Check if a user has a permission via roles."""
        conn = sqlite3.connect(DB_PATH)
        cursor = conn.cursor()
        cursor.execute('''
            SELECT 1
            FROM permissions
            INNER JOIN role_permissions ON role_permissions.permission_id = permissions.id
            INNER JOIN user_roles ON user_roles.role_id = role_permissions.role_id
            WHERE user_roles.user_id = ? AND permissions.key = ?
            LIMIT 1
        ''', (user_id, permission_key))
        result = cursor.fetchone() is not None
        conn.close()
        return result

    @staticmethod
    def get_user_count():
        """Get total number of users"""
        conn = sqlite3.connect(DB_PATH)
        cursor = conn.cursor()

        cursor.execute('SELECT COUNT(*) FROM users')
        count = cursor.fetchone()[0]
        conn.close()

        return count

    @staticmethod
    def get_all():
        """Get all users."""
        conn = sqlite3.connect(DB_PATH)
        conn.row_factory = sqlite3.Row
        cursor = conn.cursor()
        cursor.execute('SELECT * FROM users ORDER BY created_at DESC')
        rows = cursor.fetchall()
        conn.close()

        users = []
        for row in rows:
            users.append(User(
                id=row['id'],
                username=row['username'],
                email=row['email'],
                is_superadmin=bool(row['is_superadmin']),
                must_change_password=bool(row['must_change_password']),
                all_servers_access=bool(row['all_servers_access'])
            ))
        return users

    @staticmethod
    def delete_user(user_id):
        """Delete a user and related access rows."""
        conn = sqlite3.connect(DB_PATH)
        cursor = conn.cursor()
        cursor.execute('DELETE FROM user_roles WHERE user_id = ?', (user_id,))
        cursor.execute('DELETE FROM user_server_access WHERE user_id = ?', (user_id,))
        cursor.execute('DELETE FROM users WHERE id = ?', (user_id,))
        conn.commit()
        conn.close()
