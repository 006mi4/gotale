"""
User model for authentication and user management
"""

import sqlite3
import os
from flask_login import UserMixin
from werkzeug.security import generate_password_hash, check_password_hash

DB_PATH = os.path.join(os.path.dirname(os.path.dirname(__file__)), 'database.db')

class User(UserMixin):
    def __init__(self, id, username, email, is_superadmin=False):
        self.id = id
        self.username = username
        self.email = email
        self.is_superadmin = is_superadmin

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
                is_superadmin=bool(row['is_superadmin'])
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
                is_superadmin=bool(row['is_superadmin'])
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
                is_superadmin=bool(row['is_superadmin'])
            )
        return None

    @staticmethod
    def create_user(username, email, password, is_superadmin=False):
        """Create a new user"""
        conn = sqlite3.connect(DB_PATH)
        cursor = conn.cursor()

        password_hash = generate_password_hash(password)

        try:
            cursor.execute('''
                INSERT INTO users (username, email, password_hash, is_superadmin)
                VALUES (?, ?, ?, ?)
            ''', (username, email, password_hash, int(is_superadmin)))

            conn.commit()
            user_id = cursor.lastrowid
            conn.close()

            return User(
                id=user_id,
                username=username,
                email=email,
                is_superadmin=is_superadmin
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
    def get_user_count():
        """Get total number of users"""
        conn = sqlite3.connect(DB_PATH)
        cursor = conn.cursor()

        cursor.execute('SELECT COUNT(*) FROM users')
        count = cursor.fetchone()[0]
        conn.close()

        return count
