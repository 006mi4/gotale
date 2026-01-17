"""
Dashboard routes for server management interface
"""

from flask import Blueprint, render_template, request, jsonify, current_app
from flask_login import login_required, current_user
import sqlite3
import subprocess
import sys
import os
import threading
import shutil
from datetime import datetime
from pathlib import Path

from models.server import Server
from utils import port_checker, java_checker, server_manager

bp = Blueprint('dashboard', __name__)

@bp.route('/dashboard')
@login_required
def index():
    """Main dashboard page - shows server list"""

    # Get all servers
    servers = Server.get_all()

    # Get server count
    server_count = Server.get_count()
    max_servers = 100

    # Check Java installation
    java_info = java_checker.check_java()
    java_info['download_url'] = java_checker.get_java_download_url()

    # Check if server files exist (in servertemplate or any server directory)
    base_path = Path(__file__).parent.parent.parent

    game_files_exist = False

    # Check in servertemplate folder (preferred location)
    template_jar = os.path.join(base_path, 'servertemplate', 'HytaleServer.jar')
    if os.path.exists(template_jar):
        game_files_exist = True

    # Check in any server directory
    if not game_files_exist:
        servers_dir = os.path.join(base_path, 'servers')
        if os.path.exists(servers_dir):
            for server_dir in os.listdir(servers_dir):
                server_path = os.path.join(servers_dir, server_dir)
                if os.path.isdir(server_path):
                    jar_path = os.path.join(server_path, 'HytaleServer.jar')
                    if os.path.exists(jar_path):
                        game_files_exist = True
                        break

    host_os = 'windows'
    try:
        conn = sqlite3.connect(current_app.config['DATABASE'])
        cursor = conn.cursor()
        cursor.execute("SELECT value FROM settings WHERE key = 'host_os'")
        result = cursor.fetchone()
        conn.close()
        if result and result[0]:
            host_os = result[0]
    except Exception as e:
        print(f"Error reading host_os setting: {e}")

    return render_template('dashboard.html',
                         servers=servers,
                         server_count=server_count,
                         max_servers=max_servers,
                         java_info=java_info,
                         game_files_exist=game_files_exist,
                         user=current_user,
                         host_os=host_os)

@bp.route('/api/server/create', methods=['POST'])
@login_required
def create_server():
    """API endpoint to create a new server"""

    try:
        # Get form data
        name = request.form.get('name', '').strip()
        port = request.form.get('port', '5520')

        # Validation
        if not name:
            return jsonify({'success': False, 'error': 'Server name is required'}), 400

        if len(name) < 3 or len(name) > 50:
            return jsonify({'success': False, 'error': 'Server name must be between 3 and 50 characters'}), 400

        try:
            port = int(port)
        except ValueError:
            return jsonify({'success': False, 'error': 'Invalid port number'}), 400

        if port < 1024 or port > 65535:
            return jsonify({'success': False, 'error': 'Port must be between 1024 and 65535'}), 400

        # Check server limit
        if Server.get_count() >= 100:
            return jsonify({'success': False, 'error': 'Maximum of 100 servers reached'}), 400

        # Check if port is available
        if not port_checker.is_port_available(port):
            # Suggest next available port
            next_port = port_checker.get_next_available_port(port)
            return jsonify({
                'success': False,
                'error': f'Port {port} is already in use',
                'suggested_port': next_port
            }), 400

        # Check if port is already used by another server
        if Server.port_exists(port):
            return jsonify({'success': False, 'error': f'Port {port} is already assigned to another server'}), 400

        # Create server in database
        server_id = Server.create(name, port)

        if not server_id:
            return jsonify({'success': False, 'error': 'Failed to create server in database'}), 500

        # Create server directory
        if not server_manager.create_server_directory(server_id, name):
            Server.delete(server_id)
            return jsonify({'success': False, 'error': 'Failed to create server directory'}), 500

        # Copy or check for game files
        success, needs_download = server_manager.copy_game_files(server_id)

        if not success and not needs_download:
            server_manager.delete_server_files(server_id)
            Server.delete(server_id)
            return jsonify({'success': False, 'error': 'Failed to copy game files'}), 500

        # If needs_download, try to copy from downloads/game-files first
        if needs_download:
            if server_manager.copy_downloaded_files_to_server(server_id):
                needs_download = False

        return jsonify({
            'success': True,
            'server_id': server_id,
            'needs_download': needs_download,
            'message': 'Server created successfully!' if not needs_download else 'Server created. Please download game files first.'
        })

    except Exception as e:
        print(f"Error creating server: {e}")
        return jsonify({'success': False, 'error': 'An unexpected error occurred'}), 500

@bp.route('/api/server/<int:server_id>/delete', methods=['POST', 'DELETE'])
@login_required
def delete_server(server_id):
    """API endpoint to delete a server"""

    try:
        # Get server
        server = Server.get_by_id(server_id)

        if not server:
            return jsonify({'success': False, 'error': 'Server not found'}), 404

        # Stop server if running
        if server_manager.is_server_running(server_id):
            server_manager.stop_server(server_id)

        # Delete server files
        server_manager.delete_server_files(server_id)

        # Delete from database
        Server.delete(server_id)

        return jsonify({'success': True, 'message': 'Server deleted successfully'})

    except Exception as e:
        print(f"Error deleting server: {e}")
        return jsonify({'success': False, 'error': 'An unexpected error occurred'}), 500

@bp.route('/api/port-check/<int:port>')
@login_required
def check_port(port):
    """API endpoint to check if a port is available"""

    try:
        # Check if port is in valid range
        if port < 1024 or port > 65535:
            return jsonify({'available': False, 'error': 'Invalid port number'})

        # Check if port is available
        available = port_checker.is_port_available(port)

        # Check if port is used by another server
        if available:
            available = not Server.port_exists(port)

        # Get suggested port if not available
        suggested_port = None
        if not available:
            suggested_port = port_checker.get_next_available_port(port)

        return jsonify({
            'available': available,
            'port': port,
            'suggested_port': suggested_port
        })

    except Exception as e:
        print(f"Error checking port: {e}")
        return jsonify({'available': False, 'error': 'An unexpected error occurred'}), 500

@bp.route('/api/system/update', methods=['POST'])
@login_required
def update_system():
    """Update the web interface via git and restart the app"""
    system_dir = Path(__file__).parent.parent
    root_dir = system_dir.parent
    payload = request.get_json(silent=True) or {}
    mode = payload.get('mode', 'update')

    def _run_cmd(args):
        try:
            result = subprocess.run(
                args,
                cwd=system_dir,
                check=False,
                capture_output=True,
                text=True,
                timeout=120
            )
            return result.returncode == 0, result.stdout, result.stderr
        except FileNotFoundError:
            return False, '', 'command-not-found'
        except Exception as e:
            return False, '', str(e)

    ok, _, err = _run_cmd(['git', 'fetch', 'origin'])
    if not ok:
        return jsonify({'success': False, 'error': f'Git fetch failed: {err}'}), 500

    ok, stdout, err = _run_cmd(['git', 'rev-list', 'HEAD...origin/main', '--count'])
    if not ok:
        return jsonify({'success': False, 'error': f'Git check failed: {err}'}), 500

    try:
        update_count = int((stdout or '0').strip())
    except ValueError:
        update_count = 0

    if update_count == 0:
        return jsonify({'success': True, 'updated': False, 'message': 'No updates available'})

    if mode == 'check':
        return jsonify({'success': True, 'updated': False, 'message': f'{update_count} update(s) available', 'updates': update_count})

    backup_dir = root_dir / 'backups'
    backup_dir.mkdir(parents=True, exist_ok=True)
    backup_name = f"system_backup_{datetime.now().strftime('%Y%m%d_%H%M%S')}"
    backup_path = backup_dir / backup_name
    try:
        shutil.copytree(system_dir, backup_path)
    except Exception as e:
        return jsonify({'success': False, 'error': f'Backup failed: {e}'}), 500

    ok, _, err = _run_cmd(['git', 'pull', 'origin', 'main'])
    if not ok:
        return jsonify({'success': False, 'error': f'Git pull failed: {err}'}), 500

    ok, _, err = _run_cmd([sys.executable, '-m', 'pip', 'install', '-r', 'requirements.txt', '--upgrade'])
    if not ok:
        return jsonify({'success': False, 'error': f'Pip install failed: {err}'}), 500

    def _restart():
        app_path = os.path.join(system_dir, 'app.py')
        os.execv(sys.executable, [sys.executable, app_path])

    threading.Timer(1.0, _restart).start()

    return jsonify({'success': True, 'updated': True, 'message': 'Update installed, restarting web interface'})

@bp.route('/api/system/service-status')
@login_required
def get_service_status():
    """Check systemd service status for Linux hosts"""
    if not sys.platform.startswith('linux'):
        return jsonify({
            'success': True,
            'platform': sys.platform,
            'user_service': {'status': 'not-applicable'},
            'system_service': {'status': 'not-applicable'}
        })

    def _check_service(args):
        try:
            result = subprocess.run(
                args,
                check=False,
                capture_output=True,
                text=True,
                timeout=2
            )
            status = (result.stdout or '').strip() or (result.stderr or '').strip() or 'unknown'
            return status
        except FileNotFoundError:
            return 'systemctl-not-found'
        except Exception:
            return 'unknown'

    user_status = _check_service(['systemctl', '--user', 'is-active', 'hytale-server-manager.service'])
    system_status = _check_service(['systemctl', 'is-active', 'hytale-server-manager.service'])

    return jsonify({
        'success': True,
        'platform': 'linux',
        'user_service': {'status': user_status},
        'system_service': {'status': system_status}
    })

@bp.route('/api/download-game-files', methods=['POST'])
@login_required
def download_game_files_route():
    """API endpoint to download Hytale game files"""

    try:
        import threading

        # Start download in background thread
        def download_task():
            server_manager.download_game_files(socketio=None)

        thread = threading.Thread(target=download_task, daemon=True)
        thread.start()

        return jsonify({'success': True, 'message': 'Download started'})

    except Exception as e:
        print(f"Error starting download: {e}")
        return jsonify({'success': False, 'error': 'Failed to start download'}), 500

@bp.route('/api/download-status')
@login_required
def download_status_route():
    """API endpoint to get download status (polling)"""
    status = server_manager.get_download_status()
    return jsonify(status)

@bp.route('/api/server/<int:server_id>/copy-game-files', methods=['POST'])
@login_required
def copy_game_files_route(server_id):
    """API endpoint to copy downloaded game files to a server"""

    try:
        # Get server
        server = Server.get_by_id(server_id)

        if not server:
            return jsonify({'success': False, 'error': 'Server not found'}), 404

        # Copy files
        success = server_manager.copy_downloaded_files_to_server(server_id)

        if not success:
            return jsonify({'success': False, 'error': 'Failed to copy game files'}), 500

        return jsonify({'success': True, 'message': 'Game files copied successfully'})

    except Exception as e:
        print(f"Error copying game files: {e}")
        return jsonify({'success': False, 'error': 'An unexpected error occurred'}), 500
