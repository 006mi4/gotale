"""
Database initialization script for Hytale Server Manager
Creates the SQLite database and all required tables
"""

import sqlite3
import os
from datetime import datetime

# Database file path
DB_PATH = os.path.join(os.path.dirname(__file__), 'database.db')

def init_database():
    """Initialize the database with all required tables"""

    # Remove existing database if it exists (for fresh start)
    if os.path.exists(DB_PATH):
        print(f"Existing database found at {DB_PATH}")
        response = input("Do you want to delete it and create a fresh database? (y/n): ")
        if response.lower() == 'y':
            os.remove(DB_PATH)
            print("Existing database deleted.")
        else:
            print("Keeping existing database.")
            return

    # Create database connection
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()

    print("Creating database tables...")

    # Users table
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS users (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            username TEXT UNIQUE NOT NULL,
            email TEXT UNIQUE NOT NULL,
            password_hash TEXT NOT NULL,
            is_superadmin BOOLEAN DEFAULT 0,
            must_change_password BOOLEAN DEFAULT 0,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    ''')
    print("✓ Users table created")

    # Servers table
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS servers (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT NOT NULL,
            port INTEGER UNIQUE NOT NULL,
            status TEXT DEFAULT 'offline',
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            last_started TIMESTAMP,
            auto_start BOOLEAN DEFAULT 0,
            java_args TEXT,
            hytale_authenticated BOOLEAN DEFAULT 0,
            hytale_credentials_path TEXT,
            server_version TEXT
        )
    ''')
    print("✓ Servers table created")

    # Server logs table (for persistent console history)
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS server_logs (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            server_id INTEGER NOT NULL,
            timestamp TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            log_type TEXT,
            message TEXT NOT NULL,
            FOREIGN KEY (server_id) REFERENCES servers(id) ON DELETE CASCADE
        )
    ''')
    print("✓ Server logs table created")

    # System settings table
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS settings (
            key TEXT PRIMARY KEY,
            value TEXT NOT NULL
        )
    ''')
    print("✓ Settings table created")

    cursor.execute('''
        CREATE TABLE IF NOT EXISTS roles (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT UNIQUE NOT NULL,
            description TEXT,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    ''')
    print("✓ Roles table created")

    cursor.execute('''
        CREATE TABLE IF NOT EXISTS permissions (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            key TEXT UNIQUE NOT NULL,
            description TEXT
        )
    ''')
    print("✓ Permissions table created")

    cursor.execute('''
        CREATE TABLE IF NOT EXISTS role_permissions (
            role_id INTEGER NOT NULL,
            permission_id INTEGER NOT NULL,
            PRIMARY KEY (role_id, permission_id),
            FOREIGN KEY (role_id) REFERENCES roles(id) ON DELETE CASCADE,
            FOREIGN KEY (permission_id) REFERENCES permissions(id) ON DELETE CASCADE
        )
    ''')
    print("✓ Role permissions table created")

    cursor.execute('''
        CREATE TABLE IF NOT EXISTS user_roles (
            user_id INTEGER NOT NULL,
            role_id INTEGER NOT NULL,
            PRIMARY KEY (user_id, role_id),
            FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE CASCADE,
            FOREIGN KEY (role_id) REFERENCES roles(id) ON DELETE CASCADE
        )
    ''')
    print("✓ User roles table created")

    # Insert default settings
    cursor.execute('''
        INSERT OR IGNORE INTO settings (key, value)
        VALUES ('setup_completed', '0')
    ''')

    cursor.execute('''
        INSERT OR IGNORE INTO settings (key, value)
        VALUES ('version', '1.0.0')
    ''')

    cursor.execute('''
        INSERT OR IGNORE INTO settings (key, value)
        VALUES ('host_os', 'windows')
    ''')

    cursor.executemany('''
        INSERT OR IGNORE INTO permissions (key, description)
        VALUES (?, ?)
    ''', [
        ('view_servers', 'View dashboard and server pages'),
        ('manage_servers', 'Create, start, stop, restart, and delete servers'),
        ('manage_configs', 'Edit server config, world, and player data'),
        ('manage_users', 'Create users and reset passwords'),
        ('manage_roles', 'Create roles and assign permissions'),
        ('manage_updates', 'Run system update actions'),
        ('manage_downloads', 'Download server files'),
    ])

    print("✓ Default settings inserted")

    # Commit changes and close connection
    conn.commit()
    conn.close()

    print(f"\nDatabase initialized successfully at: {DB_PATH}")
    print("You can now start the application with: python app.py")

if __name__ == '__main__':
    init_database()
