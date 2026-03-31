"""
Server model for server management
"""

from datetime import datetime

from utils.database import get_db

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
        with get_db() as conn:
            cursor = conn.cursor()
            cursor.execute('SELECT * FROM servers ORDER BY created_at DESC')
            rows = cursor.fetchall()

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
        with get_db() as conn:
            cursor = conn.cursor()
            cursor.execute('SELECT * FROM servers WHERE id = ?', (server_id,))
            row = cursor.fetchone()

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
        import sqlite3
        try:
            with get_db() as conn:
                cursor = conn.cursor()
                cursor.execute('''
                    INSERT INTO servers (name, port, java_args)
                    VALUES (?, ?, ?)
                ''', (name, port, java_args))

                server_id = cursor.lastrowid

            return server_id
        except sqlite3.IntegrityError:
            return None

    @staticmethod
    def update_status(server_id, status):
        """Update server status"""
        with get_db() as conn:
            cursor = conn.cursor()
            cursor.execute('''
                UPDATE servers
                SET status = ?, last_started = ?
                WHERE id = ?
            ''', (status, datetime.now().isoformat() if status == 'online' else None, server_id))

    @staticmethod
    def update_authentication(server_id, authenticated, credentials_path=None):
        """Update server Hytale authentication status"""
        with get_db() as conn:
            cursor = conn.cursor()
            cursor.execute('''
                UPDATE servers
                SET hytale_authenticated = ?, hytale_credentials_path = ?
                WHERE id = ?
            ''', (int(authenticated), credentials_path, server_id))

    @staticmethod
    def delete(server_id):
        """Delete server"""
        with get_db() as conn:
            cursor = conn.cursor()
            cursor.execute('DELETE FROM servers WHERE id = ?', (server_id,))

    @staticmethod
    def get_count():
        """Get total number of servers"""
        with get_db() as conn:
            cursor = conn.cursor()
            cursor.execute('SELECT COUNT(*) FROM servers')
            count = cursor.fetchone()[0]
        return count

    @staticmethod
    def port_exists(port):
        """Check if port is already in use by a server"""
        with get_db() as conn:
            cursor = conn.cursor()
            cursor.execute('SELECT COUNT(*) FROM servers WHERE port = ?', (port,))
            count = cursor.fetchone()[0]
        return count > 0

    @staticmethod
    def port_exists_excluding(port, server_id):
        """Check if port is already in use by another server"""
        with get_db() as conn:
            cursor = conn.cursor()
            cursor.execute('SELECT COUNT(*) FROM servers WHERE port = ? AND id != ?', (port, server_id))
            count = cursor.fetchone()[0]
        return count > 0

    @staticmethod
    def update_port(server_id, port):
        """Update server port"""
        with get_db() as conn:
            cursor = conn.cursor()
            cursor.execute('UPDATE servers SET port = ? WHERE id = ?', (port, server_id))

    @staticmethod
    def update_launch_settings(server_id, **kwargs):
        """Update server launch settings (jvm_options_file, use_aot, backup_enabled, backup_frequency_minutes, auto_restart_on_update)."""
        allowed = {'jvm_options_file', 'use_aot', 'backup_enabled', 'backup_frequency_minutes', 'auto_restart_on_update'}
        fields = {k: v for k, v in kwargs.items() if k in allowed}
        if not fields:
            return
        set_clause = ', '.join(f'{k}=?' for k in fields)
        values = list(fields.values()) + [server_id]
        with get_db() as conn:
            conn.execute(f'UPDATE servers SET {set_clause} WHERE id=?', values)

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
