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
import json
from datetime import datetime
from pathlib import Path

from models.server import Server
from models.user import User
from utils import port_checker, java_checker, server_manager, settings as settings_utils
from utils.authz import require_permission

bp = Blueprint('dashboard', __name__)
_restart_in_progress = False

def _get_host_os():
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
    return host_os

@bp.route('/dashboard')
@login_required
@require_permission('view_servers')
def index():
    """Main dashboard page - shows server list"""

    # Get all servers (filtered by access when needed)
    all_servers = Server.get_all()
    if current_user.is_superadmin or User.has_all_servers_access(current_user.id):
        servers = all_servers
    else:
        allowed_ids = User.get_server_access_ids(current_user.id)
        servers = [server for server in all_servers if server.id in allowed_ids]

    # Get server count
    server_count = len(servers)
    max_servers = 100 if current_user.is_superadmin else (server_count if server_count > 0 else 1)

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

    host_os = _get_host_os()
    api_key = settings_utils.get_setting(current_app.config['DATABASE'], 'curseforge_api_key', '')

    template_version = server_manager.get_template_version()
    for server in servers:
        server.file_version = server_manager.get_server_version(server.id)
        server.update_available = bool(template_version and server.file_version != template_version)

    return render_template('dashboard.html',
                         servers=servers,
                         server_count=server_count,
                         max_servers=max_servers,
                         java_info=java_info,
                         game_files_exist=game_files_exist,
                         user=current_user,
                         host_os=host_os,
                         template_version=template_version,
                         curseforge_ready=bool(api_key),
                         nav_mode='dashboard')

@bp.route('/api/server/create', methods=['POST'])
@login_required
@require_permission('manage_servers')
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

        if not current_user.is_superadmin and not User.has_all_servers_access(current_user.id):
            User.grant_server_access(current_user.id, server_id)

        # Create server directory
        if not server_manager.create_server_directory(server_id, name):
            Server.delete(server_id)
            return jsonify({'success': False, 'error': 'Failed to create server directory'}), 500

        plugin_ok, plugin_status = server_manager.ensure_gotale_plugin(server_id)
        if not plugin_ok:
            print(f"[GoTaleManager] Plugin install failed for server {server_id}: {plugin_status}")

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
@require_permission('manage_servers')
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

        # Clear access entries
        User.remove_server_access_for_server(server_id)

        # Delete from database
        Server.delete(server_id)

        return jsonify({'success': True, 'message': 'Server deleted successfully'})

    except Exception as e:
        print(f"Error deleting server: {e}")
        return jsonify({'success': False, 'error': 'An unexpected error occurred'}), 500

@bp.route('/api/port-check/<int:port>')
@login_required
@require_permission('manage_servers')
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
@require_permission('manage_updates')
def update_system():
    """Update the web interface via git and restart the app"""
    global _restart_in_progress
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

    if _restart_in_progress:
        return jsonify({'success': True, 'updated': True, 'message': 'Restart already in progress'})

    _restart_in_progress = True

    def _restart():
        app_path = os.path.join(system_dir, 'app.py')
        try:
            subprocess.Popen([sys.executable, app_path], cwd=system_dir)
        except Exception as exc:
            print(f"Restart failed: {exc}")
            return
        os._exit(0)

    threading.Timer(1.0, _restart).start()

    return jsonify({'success': True, 'updated': True, 'message': 'Update installed, restarting web interface'})

@bp.route('/api/system/health')
def system_health():
    """Health check endpoint for restart polling."""
    return jsonify({'success': True, 'status': 'ok'})

@bp.route('/system/restarting')
def system_restarting():
    """Lightweight restart page without auth/session dependencies."""
    return render_template('system_restarting.html')

@bp.route('/api/server/scan', methods=['POST'])
@login_required
@require_permission('manage_servers')
def scan_servers():
    """Scan servers folder and add missing servers to the database."""
    base_path = Path(__file__).parent.parent.parent
    servers_dir = base_path / 'servers'
    if not servers_dir.exists():
        return jsonify({'success': False, 'error': 'Servers directory not found'}), 404

    existing_servers = Server.get_all()
    existing_ids = {server.id for server in existing_servers}
    existing_ports = {server.port for server in existing_servers}

    added = []
    skipped = 0
    errors = []

    def _pick_port(start_port=5520):
        port = start_port
        while True:
            if port not in existing_ports and port_checker.is_port_available(port):
                existing_ports.add(port)
                return port
            port += 1

    for entry in sorted(os.listdir(servers_dir)):
        if not entry.startswith('server_'):
            continue
        try:
            server_id = int(entry.split('_', 1)[1])
        except (ValueError, IndexError):
            continue

        if server_id in existing_ids:
            skipped += 1
            continue

        config_path = servers_dir / entry / 'config.json'
        name = f'Server {server_id}'
        if config_path.exists():
            try:
                with open(config_path, 'r', encoding='utf-8') as handle:
                    payload = json.load(handle)
                name = payload.get('ServerName') or name
            except Exception as exc:
                errors.append(f'Failed to read {entry}/config.json: {exc}')

        port = _pick_port()
        try:
            conn = sqlite3.connect(current_app.config['DATABASE'])
            cursor = conn.cursor()
            cursor.execute(
                '''
                INSERT INTO servers (id, name, port, status)
                VALUES (?, ?, ?, 'offline')
                ''',
                (server_id, name, port)
            )
            conn.commit()
            conn.close()
            if not current_user.is_superadmin and not User.has_all_servers_access(current_user.id):
                User.grant_server_access(current_user.id, server_id)
            added.append({'id': server_id, 'name': name, 'port': port})
            existing_ids.add(server_id)
        except Exception as exc:
            errors.append(f'Failed to add {entry}: {exc}')

    return jsonify({
        'success': True,
        'added': added,
        'added_count': len(added),
        'skipped': skipped,
        'errors': errors
    })

@bp.route('/api/system/service-status')
@login_required
@require_permission('view_servers')
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
@require_permission('manage_downloads')
def download_game_files_route():
    """API endpoint to download Hytale game files"""

    try:
        import threading
        host_os = _get_host_os()

        # Start download in background thread
        def download_task():
            server_manager.download_game_files(socketio=None, host_os=host_os)

        thread = threading.Thread(target=download_task, daemon=True)
        thread.start()

        return jsonify({'success': True, 'message': 'Download started'})

    except Exception as e:
        print(f"Error starting download: {e}")
        return jsonify({'success': False, 'error': 'Failed to start download'}), 500

@bp.route('/api/download-status')
@login_required
@require_permission('manage_downloads')
def download_status_route():
    """API endpoint to get download status (polling)"""
    status = server_manager.get_download_status()
    return jsonify(status)

@bp.route('/api/hytale/update-check', methods=['POST'])
@login_required
@require_permission('manage_downloads')
def hytale_update_check():
    """Check if a newer Hytale server release is available."""
    host_os = _get_host_os()
    latest_version, error = server_manager.get_latest_game_version(host_os)
    if error:
        print(f"Hytale update check failed: {error}")
        return jsonify({'success': False, 'error': error}), 500

    template_version = server_manager.get_template_version()
    update_available = bool(latest_version and template_version != latest_version)

    return jsonify({
        'success': True,
        'latest_version': latest_version,
        'template_version': template_version,
        'update_available': update_available
    })

@bp.route('/api/server/<int:server_id>/apply-update', methods=['POST'])
@login_required
@require_permission('manage_servers')
def apply_server_update(server_id):
    """Apply the latest server template files to a specific server."""
    try:
        server = Server.get_by_id(server_id)
        if not server:
            return jsonify({'success': False, 'error': 'Server not found'}), 404

        if server_manager.is_server_running(server_id):
            return jsonify({'success': False, 'error': 'Server must be stopped before applying updates'}), 400

        success = server_manager.copy_downloaded_files_to_server(server_id)
        if not success:
            return jsonify({'success': False, 'error': 'Failed to apply update'}), 500

        return jsonify({'success': True, 'message': 'Update applied successfully'})
    except Exception as e:
        print(f"Error applying update to server {server_id}: {e}")
        return jsonify({'success': False, 'error': 'An unexpected error occurred'}), 500

@bp.route('/api/server/<int:server_id>/copy-game-files', methods=['POST'])
@login_required
@require_permission('manage_servers')
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
