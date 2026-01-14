"""
Hytale Server Manager - Main Flask Application
Web-based interface for managing multiple Hytale servers
"""

from flask import Flask, render_template, redirect, url_for, request
from flask_socketio import SocketIO
from flask_login import LoginManager, login_required, current_user
import threading
import time
import sqlite3
import os
import secrets

# Import models
from models.user import User
from models.server import Server
from utils import server_manager

# Initialize Flask app
app = Flask(__name__)

# Generate a secure secret key
app.config['SECRET_KEY'] = secrets.token_hex(32)
app.config['DATABASE'] = os.path.join(os.path.dirname(__file__), 'database.db')

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
from routes import auth, dashboard, server_routes, console

app.register_blueprint(auth.bp)
app.register_blueprint(dashboard.bp)
app.register_blueprint(server_routes.bp)

# Register console event handlers
console.register_socketio_events(socketio)

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

@app.errorhandler(500)
def server_error(e):
    return render_template('500.html'), 500

if __name__ == '__main__':
    # Check if database exists
    if not os.path.exists(app.config['DATABASE']):
        print("Database not found!")
        print("Please run: python init_db.py")
        exit(1)

    # Start background monitoring thread
    monitoring_thread = threading.Thread(target=monitor_servers, daemon=True)
    monitoring_thread.start()

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
