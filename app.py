"""
Hytale Server Manager - Main Flask Application
Web-based interface for managing multiple Hytale servers
"""

from flask import Flask, render_template, redirect, url_for, request, session, abort
from flask_socketio import SocketIO
from flask_login import LoginManager, login_required, current_user
import threading
import time
import sqlite3
import os
import secrets
from datetime import timedelta

DB_PATH = os.path.join(os.path.dirname(__file__), 'database.db')


def _ensure_secret_key(db_path):
    env_key = os.environ.get('HSM_SECRET_KEY')
    if env_key:
        return env_key
    if not os.path.exists(db_path):
        return secrets.token_hex(32)
    try:
        conn = sqlite3.connect(db_path)
        cursor = conn.cursor()
        cursor.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='settings'")
        if not cursor.fetchone():
            conn.close()
            return secrets.token_hex(32)
        cursor.execute("SELECT value FROM settings WHERE key = 'secret_key'")
        row = cursor.fetchone()
        if row and row[0]:
            conn.close()
            return row[0]
        generated = secrets.token_hex(32)
        cursor.execute(
            "INSERT OR REPLACE INTO settings (key, value) VALUES ('secret_key', ?)",
            (generated,),
        )
        conn.commit()
        conn.close()
        return generated
    except Exception as exc:
        print(f"Error loading secret key from database: {exc}")
        return secrets.token_hex(32)

# Import models
from models.user import User
from models.server import Server
from utils import server_manager
from utils.db_schema import ensure_schema

# Initialize Flask app
app = Flask(__name__)

# Load a stable secret key for persistent sessions
app.config['DATABASE'] = DB_PATH
app.config['SECRET_KEY'] = _ensure_secret_key(DB_PATH)
app.config['PERMANENT_SESSION_LIFETIME'] = timedelta(days=182)

# Initialize SocketIO for WebSocket support
socketio = SocketIO(app, cors_allowed_origins="*", async_mode='threading')

# Initialize Login Manager
login_manager = LoginManager()
login_manager.init_app(app)
login_manager.login_view = 'auth.login'

# User loader for Flask-Login
@login_manager.user_loader
def load_user(user_id):
    return User.get_by_id(int(user_id))

# Import and register blueprints
from routes import auth, dashboard, server_routes, console, admin

app.register_blueprint(auth.bp)
app.register_blueprint(dashboard.bp)
app.register_blueprint(server_routes.bp)
app.register_blueprint(admin.bp)

# Register console event handlers
console.register_socketio_events(socketio)

def _get_csrf_token():
    token = session.get('_csrf_token')
    if not token:
        token = secrets.token_hex(16)
        session['_csrf_token'] = token
    return token

@app.context_processor
def inject_globals():
    permissions = set()
    is_superadmin = False
    nav_servers = []
    if current_user.is_authenticated:
        is_superadmin = current_user.is_superadmin
        if not is_superadmin:
            permissions = User.get_permissions(current_user.id)
        try:
            servers = Server.get_all()
            if is_superadmin or current_user.all_servers_access:
                nav_servers = servers
            else:
                allowed_ids = User.get_server_access_ids(current_user.id)
                nav_servers = [server for server in servers if server.id in allowed_ids]
        except Exception as exc:
            print(f"Error loading servers for navbar: {exc}")
    return {
        'csrf_token': _get_csrf_token,
        'user_permissions': permissions,
        'is_superadmin': is_superadmin,
        'nav_servers': nav_servers,
    }

@app.before_request
def csrf_protect():
    if request.method in ('POST', 'PUT', 'PATCH', 'DELETE'):
        token = session.get('_csrf_token')
        header_token = request.headers.get('X-CSRFToken')
        form_token = request.form.get('csrf_token')
        if not token or (header_token != token and form_token != token):
            abort(403)

@app.before_request
def enforce_password_change():
    if not current_user.is_authenticated:
        return
    if not getattr(current_user, 'must_change_password', False):
        return
    allowed_endpoints = {'auth.change_password', 'auth.logout', 'static'}
    if request.endpoint in allowed_endpoints:
        return
    if request.path.startswith('/api/'):
        abort(403)
    return redirect(url_for('auth.change_password'))

def is_first_run():
    """Check if this is the first time running the application"""
    try:
        conn = sqlite3.connect(app.config['DATABASE'])
        cursor = conn.cursor()

        cursor.execute("SELECT value FROM settings WHERE key = 'setup_completed'")
        result = cursor.fetchone()
        conn.close()

        if result and result[0] == '1':
            return False
        return True
    except:
        return True

def monitor_servers():
    """
    Background thread to monitor server statuses
    Updates database with current server statuses
    """
    while True:
        try:
            time.sleep(5)  # Check every 5 seconds

            # Get all servers from database
            servers = Server.get_all()

            for server in servers:
                # Check if process is running
                is_running = server_manager.is_server_running(server.id)

                # Update status if changed
                if is_running and server.status != 'online':
                    Server.update_status(server.id, 'online')
                    # Broadcast status change
                    socketio.emit('server_status_change', {
                        'server_id': server.id,
                        'status': 'online'
                    })
                elif not is_running and server.status == 'online':
                    Server.update_status(server.id, 'offline')
                    # Broadcast status change
                    socketio.emit('server_status_change', {
                        'server_id': server.id,
                        'status': 'offline'
                    })

        except Exception as e:
            print(f"Error in monitoring thread: {e}")
            time.sleep(10)

def monitor_backups():
    """Background thread to trigger scheduled backups."""
    while True:
        try:
            time.sleep(60)
            servers = Server.get_all()
            for server in servers:
                try:
                    server_manager.process_scheduled_backup(server.id)
                except Exception as exc:
                    print(f"Error running scheduled backup for server {server.id}: {exc}")
        except Exception as e:
            print(f"Error in backup monitoring: {e}")
            time.sleep(10)

# Root route
@app.route('/')
def index():
    """Redirect to dashboard or setup"""
    if is_first_run():
        return redirect(url_for('auth.setup'))
    return redirect(url_for('dashboard.index'))

# Error handlers
@app.errorhandler(404)
def not_found(e):
    return render_template('404.html'), 404

@app.errorhandler(403)
def forbidden(e):
    return render_template('403.html'), 403

@app.errorhandler(500)
def server_error(e):
    return render_template('500.html'), 500

if __name__ == '__main__':
    # Check if database exists
    if not os.path.exists(app.config['DATABASE']):
        print("Database not found!")
        print("Please run: python init_db.py")
        exit(1)

    ensure_schema(app.config['DATABASE'])

    # Start background monitoring thread
    monitoring_thread = threading.Thread(target=monitor_servers, daemon=True)
    monitoring_thread.start()

    backup_thread = threading.Thread(target=monitor_backups, daemon=True)
    backup_thread.start()

    # Check if first run and open setup page
    if is_first_run():
        print("\n" + "="*60)
        print("FIRST RUN DETECTED")
        print("="*60)
        print("Opening browser for initial setup...")
        print("Please create your administrator account.")
        print("="*60 + "\n")

        # Open browser after a short delay
        def open_browser():
            time.sleep(2)
            import webbrowser
            webbrowser.open('http://localhost:5000/setup')

        browser_thread = threading.Thread(target=open_browser, daemon=True)
        browser_thread.start()

    # Start Flask app with SocketIO
    print("\nStarting Hytale Server Manager...")
    print("Access the web interface at: http://localhost:5000")
    print("Press CTRL+C to stop\n")

    socketio.run(app, host='0.0.0.0', port=5000, debug=False, allow_unsafe_werkzeug=True)
