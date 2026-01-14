"""
Server model for server management
"""

import sqlite3
import os
from datetime import datetime

DB_PATH = os.path.join(os.path.dirname(os.path.dirname(__file__)), 'database.db')

class Server:
    def __init__(self, id, name, port, status='offline', created_at=None, last_started=None,
                 auto_start=False, java_args=None, hytale_authenticated=False,
                 hytale_credentials_path=None, server_version=None):
        self.id = id
        self.name = name
        self.port = port
        self.status = status
        self.created_at = created_at
        self.last_started = last_started
        self.auto_start = auto_start
        self.java_args = java_args
        self.hytale_authenticated = hytale_authenticated
        self.hytale_credentials_path = hytale_credentials_path
        self.server_version = server_version

    @staticmethod
    def get_all():
        """Get all servers"""
        conn = sqlite3.connect(DB_PATH)
        conn.row_factory = sqlite3.Row
        cursor = conn.cursor()

        cursor.execute('SELECT * FROM servers ORDER BY created_at DESC')
        rows = cursor.fetchall()
        conn.close()

        servers = []
        for row in rows:
            servers.append(Server(
                id=row['id'],
                name=row['name'],
                port=row['port'],
                status=row['status'],
                created_at=row['created_at'],
                last_started=row['last_started'],
                auto_start=bool(row['auto_start']),
                java_args=row['java_args'],
                hytale_authenticated=bool(row['hytale_authenticated']),
                hytale_credentials_path=row['hytale_credentials_path'],
                server_version=row['server_version']
            ))

        return servers

    @staticmethod
    def get_by_id(server_id):
        """Get server by ID"""
        conn = sqlite3.connect(DB_PATH)
        conn.row_factory = sqlite3.Row
        cursor = conn.cursor()

        cursor.execute('SELECT * FROM servers WHERE id = ?', (server_id,))
        row = cursor.fetchone()
        conn.close()

        if row:
            return Server(
                id=row['id'],
                name=row['name'],
                port=row['port'],
                status=row['status'],
                created_at=row['created_at'],
                last_started=row['last_started'],
                auto_start=bool(row['auto_start']),
                java_args=row['java_args'],
                hytale_authenticated=bool(row['hytale_authenticated']),
                hytale_credentials_path=row['hytale_credentials_path'],
                server_version=row['server_version']
            )
        return None

    @staticmethod
    def create(name, port, java_args=None):
        """Create a new server"""
        conn = sqlite3.connect(DB_PATH)
        cursor = conn.cursor()

        try:
            cursor.execute('''
                INSERT INTO servers (name, port, java_args)
                VALUES (?, ?, ?)
            ''', (name, port, java_args))

            conn.commit()
            server_id = cursor.lastrowid
            conn.close()

            return server_id
        except sqlite3.IntegrityError:
            conn.close()
            return None

    @staticmethod
    def update_status(server_id, status):
        """Update server status"""
        conn = sqlite3.connect(DB_PATH)
        cursor = conn.cursor()

        cursor.execute('''
            UPDATE servers
            SET status = ?, last_started = ?
            WHERE id = ?
        ''', (status, datetime.now().isoformat() if status == 'online' else None, server_id))

        conn.commit()
        conn.close()

    @staticmethod
    def update_authentication(server_id, authenticated, credentials_path=None):
        """Update server Hytale authentication status"""
        conn = sqlite3.connect(DB_PATH)
        cursor = conn.cursor()

        cursor.execute('''
            UPDATE servers
            SET hytale_authenticated = ?, hytale_credentials_path = ?
            WHERE id = ?
        ''', (int(authenticated), credentials_path, server_id))

        conn.commit()
        conn.close()

    @staticmethod
    def delete(server_id):
        """Delete server"""
        conn = sqlite3.connect(DB_PATH)
        cursor = conn.cursor()

        cursor.execute('DELETE FROM servers WHERE id = ?', (server_id,))

        conn.commit()
        conn.close()

    @staticmethod
    def get_count():
        """Get total number of servers"""
        conn = sqlite3.connect(DB_PATH)
        cursor = conn.cursor()

        cursor.execute('SELECT COUNT(*) FROM servers')
        count = cursor.fetchone()[0]
        conn.close()

        return count

    @staticmethod
    def port_exists(port):
        """Check if port is already in use by a server"""
        conn = sqlite3.connect(DB_PATH)
        cursor = conn.cursor()

        cursor.execute('SELECT COUNT(*) FROM servers WHERE port = ?', (port,))
        count = cursor.fetchone()[0]
        conn.close()

        return count > 0

    def to_dict(self):
        """Convert server object to dictionary"""
        return {
            'id': self.id,
            'name': self.name,
            'port': self.port,
            'status': self.status,
            'created_at': self.created_at,
            'last_started': self.last_started,
            'auto_start': self.auto_start,
            'java_args': self.java_args,
            'hytale_authenticated': self.hytale_authenticated,
            'server_version': self.server_version
        }
