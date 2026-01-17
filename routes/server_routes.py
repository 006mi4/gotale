"""
Server control routes for start, stop, restart operations
"""

from flask import Blueprint, render_template, request, jsonify, current_app
from flask_login import login_required, current_user
import os
import time
import json
import sqlite3

from models.server import Server
from models.user import User
from utils import server_manager, java_checker
from utils.authz import require_permission

# Import socketio from app (will be set during initialization)
_socketio = None

bp = Blueprint('server', __name__)

def get_socketio():
    """Get the SocketIO instance from the current app"""
    from flask import current_app
    return getattr(current_app, 'socketio', None)

def _get_server_or_404(server_id):
    server = Server.get_by_id(server_id)
    if not server:
        return None
    return server

def _has_server_access(server_id):
    if current_user.is_superadmin:
        return True
    return User.has_server_access(current_user.id, server_id)

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

def _read_json_file(path):
    with open(path, 'r', encoding='utf-8') as file:
        return json.load(file)

def _write_json_file(path, data):
    with open(path, 'w', encoding='utf-8') as file:
        json.dump(data, file, indent=2, ensure_ascii=True)
        file.write('\n')

def _get_config_file_map(server_id):
    base_path = server_manager.get_server_path(server_id)
    config_files = {
        'config.json': 'Hauptkonfiguration',
        'permissions.json': 'Permissions',
        'bans.json': 'Bans',
        'whitelist.json': 'Whitelist'
    }
    file_map = {}
    for name in config_files.keys():
        path = os.path.join(base_path, name)
        if os.path.isfile(path):
            file_map[name] = path
    return file_map

def _get_world_file_map(server_id):
    base_path = server_manager.get_server_path(server_id)
    world_dir = os.path.join(base_path, 'universe', 'worlds', 'default')
    resources_dir = os.path.join(world_dir, 'resources')
    memories_path = os.path.join(base_path, 'universe', 'memories.json')

    file_map = {}
    world_config = os.path.join(world_dir, 'config.json')
    if os.path.isfile(world_config):
        file_map['config.json'] = world_config
    if os.path.isfile(memories_path):
        file_map['memories.json'] = memories_path
    if os.path.isdir(resources_dir):
        for filename in sorted(os.listdir(resources_dir)):
            if filename.endswith('.json'):
                file_map[f'resources/{filename}'] = os.path.join(resources_dir, filename)
    return file_map

def _get_player_file_map(server_id):
    base_path = server_manager.get_server_path(server_id)
    players_dir = os.path.join(base_path, 'universe', 'players')
    file_map = {}
    if os.path.isdir(players_dir):
        for filename in sorted(os.listdir(players_dir)):
            if filename.endswith('.json'):
                file_map[filename] = os.path.join(players_dir, filename)
    return file_map

@bp.route('/server/<int:server_id>')
@login_required
@require_permission('view_servers')
def console_view(server_id):
    """Console view page for a specific server"""

    # Get server from database
    server = Server.get_by_id(server_id)

    if not server:
        return render_template('404.html'), 404
    if not _has_server_access(server_id):
        return render_template('403.html'), 403

    # Get console history
    console_history = server_manager.get_console_output(server_id, lines=100)

    # Check if server is running
    is_running = server_manager.is_server_running(server_id)

    # Check Java
    java_info = java_checker.check_java()
    java_info['download_url'] = java_checker.get_java_download_url()

    return render_template('server_console.html',
                         server=server,
                         console_history=console_history,
                         is_running=is_running,
                         java_info=java_info,
                         user=current_user,
                         host_os=_get_host_os(),
                         active_page='dashboard')

@bp.route('/server/<int:server_id>/config')
@login_required
@require_permission('manage_configs')
def config_view(server_id):
    server = _get_server_or_404(server_id)
    if not server:
        return render_template('404.html'), 404
    if not _has_server_access(server_id):
        return render_template('403.html'), 403

    return render_template('server_config.html',
                           server=server,
                           user=current_user,
                           host_os=_get_host_os(),
                           active_page='config')

@bp.route('/server/<int:server_id>/world')
@login_required
@require_permission('manage_configs')
def world_view(server_id):
    server = _get_server_or_404(server_id)
    if not server:
        return render_template('404.html'), 404
    if not _has_server_access(server_id):
        return render_template('403.html'), 403

    return render_template('server_world.html',
                           server=server,
                           user=current_user,
                           host_os=_get_host_os(),
                           active_page='world')

@bp.route('/server/<int:server_id>/players')
@login_required
@require_permission('manage_configs')
def players_view(server_id):
    server = _get_server_or_404(server_id)
    if not server:
        return render_template('404.html'), 404
    if not _has_server_access(server_id):
        return render_template('403.html'), 403

    return render_template('server_players.html',
                           server=server,
                           user=current_user,
                           host_os=_get_host_os(),
                           active_page='players')

@bp.route('/server/<int:server_id>/backup')
@login_required
@require_permission('manage_configs')
def backup_view(server_id):
    server = _get_server_or_404(server_id)
    if not server:
        return render_template('404.html'), 404
    if not _has_server_access(server_id):
        return render_template('403.html'), 403

    return render_template('server_backup.html',
                           server=server,
                           user=current_user,
                           host_os=_get_host_os(),
                           active_page='backup')

@bp.route('/api/server/<int:server_id>/config-files')
@login_required
@require_permission('manage_configs')
def get_config_files(server_id):
    server = _get_server_or_404(server_id)
    if not server:
        return jsonify({'success': False, 'error': 'Server not found'}), 404
    if not _has_server_access(server_id):
        return jsonify({'success': False, 'error': 'Forbidden'}), 403

    file_map = _get_config_file_map(server_id)
    labels = {
        'config.json': 'Main configuration (config.json)',
        'permissions.json': 'Permissions (permissions.json)',
        'bans.json': 'Bans (bans.json)',
        'whitelist.json': 'Whitelist (whitelist.json)'
    }
    files = []
    for name in labels.keys():
        if name in file_map:
            files.append({
                'value': name,
                'label': labels[name]
            })

    return jsonify({'success': True, 'files': files})

@bp.route('/api/server/<int:server_id>/world-files')
@login_required
@require_permission('manage_configs')
def get_world_files(server_id):
    server = _get_server_or_404(server_id)
    if not server:
        return jsonify({'success': False, 'error': 'Server not found'}), 404
    if not _has_server_access(server_id):
        return jsonify({'success': False, 'error': 'Forbidden'}), 403

    file_map = _get_world_file_map(server_id)
    files = []

    if 'config.json' in file_map:
        files.append({
            'value': 'config.json',
            'label': 'World Config (config.json)',
            'description': 'Global world settings.'
        })
    if 'memories.json' in file_map:
        files.append({
            'value': 'memories.json',
            'label': 'Memories (memories.json)',
            'description': 'Server memories and history.'
        })

    for name in sorted(file_map.keys()):
        if name.startswith('resources/'):
            filename = name.split('/', 1)[1]
            files.append({
                'value': name,
                'label': f'Resource: {filename}',
                'description': 'World resource file.'
            })

    return jsonify({'success': True, 'files': files})

@bp.route('/api/server/<int:server_id>/player-files')
@login_required
@require_permission('manage_configs')
def get_player_files(server_id):
    server = _get_server_or_404(server_id)
    if not server:
        return jsonify({'success': False, 'error': 'Server not found'}), 404
    if not _has_server_access(server_id):
        return jsonify({'success': False, 'error': 'Forbidden'}), 403

    file_map = _get_player_file_map(server_id)
    files = []
    for name in sorted(file_map.keys()):
        files.append({
            'value': name,
            'label': name
        })

    return jsonify({'success': True, 'files': files})

@bp.route('/api/server/<int:server_id>/config-file', methods=['GET', 'POST'])
@login_required
@require_permission('manage_configs')
def config_file(server_id):
    server = _get_server_or_404(server_id)
    if not server:
        return jsonify({'success': False, 'error': 'Server not found'}), 404
    if not _has_server_access(server_id):
        return jsonify({'success': False, 'error': 'Forbidden'}), 403

    name = request.args.get('name', '')
    file_map = _get_config_file_map(server_id)
    if name not in file_map:
        return jsonify({'success': False, 'error': 'Config file not found'}), 404

    if request.method == 'GET':
        try:
            data = _read_json_file(file_map[name])
            return jsonify({'success': True, 'data': data})
        except Exception as e:
            print(f"Error reading config file: {e}")
            return jsonify({'success': False, 'error': 'Failed to read config file'}), 500

    payload = request.get_json(silent=True)
    if payload is None:
        return jsonify({'success': False, 'error': 'Missing JSON payload'}), 400

    data = payload.get('data', payload)
    try:
        _write_json_file(file_map[name], data)
        return jsonify({'success': True})
    except Exception as e:
        print(f"Error writing config file: {e}")
        return jsonify({'success': False, 'error': 'Failed to write config file'}), 500

@bp.route('/api/server/<int:server_id>/world-file', methods=['GET', 'POST'])
@login_required
@require_permission('manage_configs')
def world_file(server_id):
    server = _get_server_or_404(server_id)
    if not server:
        return jsonify({'success': False, 'error': 'Server not found'}), 404
    if not _has_server_access(server_id):
        return jsonify({'success': False, 'error': 'Forbidden'}), 403

    name = request.args.get('name', '')
    file_map = _get_world_file_map(server_id)
    if name not in file_map:
        return jsonify({'success': False, 'error': 'World file not found'}), 404

    if request.method == 'GET':
        try:
            data = _read_json_file(file_map[name])
            return jsonify({'success': True, 'data': data})
        except Exception as e:
            print(f"Error reading world file: {e}")
            return jsonify({'success': False, 'error': 'Failed to read world file'}), 500

    payload = request.get_json(silent=True)
    if payload is None:
        return jsonify({'success': False, 'error': 'Missing JSON payload'}), 400

    data = payload.get('data', payload)
    try:
        _write_json_file(file_map[name], data)
        return jsonify({'success': True})
    except Exception as e:
        print(f"Error writing world file: {e}")
        return jsonify({'success': False, 'error': 'Failed to write world file'}), 500

@bp.route('/api/server/<int:server_id>/player-file', methods=['GET', 'POST'])
@login_required
@require_permission('manage_configs')
def player_file(server_id):
    server = _get_server_or_404(server_id)
    if not server:
        return jsonify({'success': False, 'error': 'Server not found'}), 404
    if not _has_server_access(server_id):
        return jsonify({'success': False, 'error': 'Forbidden'}), 403

    name = request.args.get('name', '')
    file_map = _get_player_file_map(server_id)
    if name not in file_map:
        return jsonify({'success': False, 'error': 'Player file not found'}), 404

    if request.method == 'GET':
        try:
            data = _read_json_file(file_map[name])
            return jsonify({'success': True, 'data': data})
        except Exception as e:
            print(f"Error reading player file: {e}")
            return jsonify({'success': False, 'error': 'Failed to read player file'}), 500

    payload = request.get_json(silent=True)
    if payload is None:
        return jsonify({'success': False, 'error': 'Missing JSON payload'}), 400

    data = payload.get('data', payload)
    try:
        _write_json_file(file_map[name], data)
        return jsonify({'success': True})
    except Exception as e:
        print(f"Error writing player file: {e}")
        return jsonify({'success': False, 'error': 'Failed to write player file'}), 500

@bp.route('/api/server/<int:server_id>/backup-settings', methods=['GET', 'POST'])
@login_required
@require_permission('manage_configs')
def backup_settings(server_id):
    server = _get_server_or_404(server_id)
    if not server:
        return jsonify({'success': False, 'error': 'Server not found'}), 404
    if not _has_server_access(server_id):
        return jsonify({'success': False, 'error': 'Forbidden'}), 403

    if request.method == 'GET':
        settings = server_manager.read_backup_settings(server_id)
        worlds = server_manager.list_worlds(server_id)
        return jsonify({'success': True, 'settings': settings, 'worlds': worlds})

    payload = request.get_json(silent=True) or {}
    settings = {
        'mode': payload.get('mode', 'worlds'),
        'selected_worlds': payload.get('selected_worlds', []),
        'schedule_enabled': bool(payload.get('schedule_enabled', False)),
        'interval_value': payload.get('interval_value', 24),
        'interval_unit': payload.get('interval_unit', 'hours'),
        'backup_on_start': bool(payload.get('backup_on_start', False))
    }
    saved = server_manager.write_backup_settings(server_id, settings)
    if not saved:
        return jsonify({'success': False, 'error': 'Failed to save settings'}), 500
    return jsonify({'success': True, 'settings': saved})

@bp.route('/api/server/<int:server_id>/backups', methods=['GET'])
@login_required
@require_permission('manage_configs')
def list_backups(server_id):
    server = _get_server_or_404(server_id)
    if not server:
        return jsonify({'success': False, 'error': 'Server not found'}), 404
    if not _has_server_access(server_id):
        return jsonify({'success': False, 'error': 'Forbidden'}), 403

    backups = server_manager.list_backups(server_id)
    return jsonify({'success': True, 'backups': backups})

@bp.route('/api/server/<int:server_id>/backups/run', methods=['POST'])
@login_required
@require_permission('manage_configs')
def run_backup(server_id):
    server = _get_server_or_404(server_id)
    if not server:
        return jsonify({'success': False, 'error': 'Server not found'}), 404
    if not _has_server_access(server_id):
        return jsonify({'success': False, 'error': 'Forbidden'}), 403

    payload = request.get_json(silent=True) or {}
    backup_type = payload.get('mode', 'worlds')
    selected_worlds = payload.get('selected_worlds', [])
    try:
        created = server_manager.create_backup(
            server_id,
            backup_type,
            selected_worlds,
            update_last=True
        )
        return jsonify({'success': True, 'created': created})
    except ValueError as e:
        return jsonify({'success': False, 'error': str(e)}), 400
    except Exception as e:
        print(f"Error creating backup for server {server_id}: {e}")
        return jsonify({'success': False, 'error': 'Backup failed'}), 500

@bp.route('/api/server/<int:server_id>/backups/restore', methods=['POST'])
@login_required
@require_permission('manage_configs')
def restore_backup(server_id):
    server = _get_server_or_404(server_id)
    if not server:
        return jsonify({'success': False, 'error': 'Server not found'}), 404
    if not _has_server_access(server_id):
        return jsonify({'success': False, 'error': 'Forbidden'}), 403
    if server_manager.is_server_running(server_id):
        return jsonify({'success': False, 'error': 'Stop the server before restoring backups.'}), 400

    payload = request.get_json(silent=True) or {}
    path = payload.get('path', '')
    if not path:
        return jsonify({'success': False, 'error': 'Missing backup path'}), 400
    try:
        server_manager.restore_backup(server_id, path)
        return jsonify({'success': True})
    except ValueError as e:
        return jsonify({'success': False, 'error': str(e)}), 400
    except Exception as e:
        print(f"Error restoring backup for server {server_id}: {e}")
        return jsonify({'success': False, 'error': 'Restore failed'}), 500

@bp.route('/api/server/<int:server_id>/start', methods=['POST'])
@login_required
@require_permission('manage_servers')
def start_server(server_id):
    """API endpoint to start a server"""

    try:
        # Get server from database
        server = Server.get_by_id(server_id)

        if not server:
            return jsonify({'success': False, 'error': 'Server not found'}), 404

        # Check if already running
        if server_manager.is_server_running(server_id):
            return jsonify({'success': False, 'error': 'Server is already running'}), 400

        # Check Java installation
        java_info = java_checker.check_java()
        if not java_info['installed']:
            return jsonify({
                'success': False,
                'error': 'Java 25 or higher is not installed',
                'java_download_url': java_checker.get_java_download_url()
            }), 400

        # Check if game files exist
        jar_path = server_manager.get_jar_path(server_id)
        assets_path = server_manager.get_assets_path(server_id)
        if not jar_path or not assets_path or not os.path.exists(jar_path) or not os.path.exists(assets_path):
            return jsonify({
                'success': False,
                'error': 'Server files are missing. Please download Hytale server files.'
            }), 400

        try:
            server_manager.run_startup_backup(server_id)
        except Exception as e:
            print(f"Error running startup backup for server {server_id}: {e}")
            return jsonify({'success': False, 'error': 'Backup on start failed'}), 500

        # Update status to starting
        Server.update_status(server_id, 'starting')

        # Get SocketIO instance
        from app import socketio

        # Start server in new terminal window
        success = server_manager.start_server(
            server_id,
            server.port,
            socketio=socketio,
            java_args=server.java_args,
            server_name=server.name
        )

        if not success:
            Server.update_status(server_id, 'offline')
            return jsonify({'success': False, 'error': 'Failed to start server'}), 500

        # Update status to online
        Server.update_status(server_id, 'online')

        return jsonify({'success': True, 'message': 'Server started successfully'})

    except Exception as e:
        print(f"Error starting server: {e}")
        Server.update_status(server_id, 'offline')
        return jsonify({'success': False, 'error': 'An unexpected error occurred'}), 500

@bp.route('/api/server/<int:server_id>/stop', methods=['POST'])
@login_required
@require_permission('manage_servers')
def stop_server(server_id):
    """API endpoint to stop a server"""

    try:
        # Get server from database
        server = Server.get_by_id(server_id)

        if not server:
            return jsonify({'success': False, 'error': 'Server not found'}), 404
        if not _has_server_access(server_id):
            return jsonify({'success': False, 'error': 'Forbidden'}), 403
        if not _has_server_access(server_id):
            return jsonify({'success': False, 'error': 'Forbidden'}), 403
        if not _has_server_access(server_id):
            return jsonify({'success': False, 'error': 'Forbidden'}), 403

        # Check if running
        if not server_manager.is_server_running(server_id):
            return jsonify({'success': False, 'error': 'Server is not running'}), 400

        # Update status to stopping
        Server.update_status(server_id, 'stopping')

        # Stop server
        success = server_manager.stop_server(server_id)

        if not success:
            Server.update_status(server_id, 'online')
            return jsonify({'success': False, 'error': 'Failed to stop server'}), 500

        # Update status to offline
        Server.update_status(server_id, 'offline')

        return jsonify({'success': True, 'message': 'Server stopped successfully'})

    except Exception as e:
        print(f"Error stopping server: {e}")
        return jsonify({'success': False, 'error': 'An unexpected error occurred'}), 500

@bp.route('/api/server/<int:server_id>/restart', methods=['POST'])
@login_required
@require_permission('manage_servers')
def restart_server(server_id):
    """API endpoint to restart a server"""

    try:
        # Get server from database
        server = Server.get_by_id(server_id)

        if not server:
            return jsonify({'success': False, 'error': 'Server not found'}), 404
        if not _has_server_access(server_id):
            return jsonify({'success': False, 'error': 'Forbidden'}), 403

        # Stop if running
        if server_manager.is_server_running(server_id):
            Server.update_status(server_id, 'stopping')
            server_manager.stop_server(server_id)

        # Wait a moment
        time.sleep(2)

        try:
            server_manager.run_startup_backup(server_id)
        except Exception as e:
            print(f"Error running startup backup for server {server_id}: {e}")
            return jsonify({'success': False, 'error': 'Backup on start failed'}), 500

        # Start server
        Server.update_status(server_id, 'starting')

        from app import socketio

        success = server_manager.start_server(
            server_id,
            server.port,
            socketio=socketio,
            java_args=server.java_args,
            server_name=server.name
        )

        if not success:
            Server.update_status(server_id, 'offline')
            return jsonify({'success': False, 'error': 'Failed to start server'}), 500

        Server.update_status(server_id, 'online')

        return jsonify({'success': True, 'message': 'Server restarted successfully'})

    except Exception as e:
        print(f"Error restarting server: {e}")
        Server.update_status(server_id, 'offline')
        return jsonify({'success': False, 'error': 'An unexpected error occurred'}), 500

@bp.route('/api/server/<int:server_id>/status')
@login_required
@require_permission('view_servers')
def get_status(server_id):
    """API endpoint to get server status"""

    try:
        # Get server from database
        server = Server.get_by_id(server_id)

        if not server:
            return jsonify({'success': False, 'error': 'Server not found'}), 404
        if not _has_server_access(server_id):
            return jsonify({'success': False, 'error': 'Forbidden'}), 403

        # Check if actually running
        is_running = server_manager.is_server_running(server_id)

        return jsonify({
            'success': True,
            'status': server.status,
            'is_running': is_running,
            'port': server.port
        })

    except Exception as e:
        print(f"Error getting server status: {e}")
        return jsonify({'success': False, 'error': 'An unexpected error occurred'}), 500

@bp.route('/api/server/<int:server_id>/auth-status')
@login_required
@require_permission('view_servers')
def get_auth_status(server_id):
    """API endpoint to get server authentication status"""
    try:
        server = Server.get_by_id(server_id)

        if not server:
            return jsonify({'success': False, 'error': 'Server not found'}), 404
        if not _has_server_access(server_id):
            return jsonify({'success': False, 'error': 'Forbidden'}), 403
        if not _has_server_access(server_id):
            return jsonify({'success': False, 'error': 'Forbidden'}), 403

        auth_status = server_manager.get_server_auth_status(server_id)

        return jsonify({
            'success': True,
            'auth_pending': auth_status['auth_pending'],
            'auth_url': auth_status['auth_url'],
            'auth_code': auth_status['auth_code']
        })

    except Exception as e:
        print(f"Error getting auth status: {e}")
        return jsonify({'success': False, 'error': 'An unexpected error occurred'}), 500

@bp.route('/api/server/<int:server_id>/auth-trigger', methods=['POST'])
@login_required
@require_permission('manage_servers')
def trigger_auth(server_id):
    """Force auth status or device login command"""
    try:
        server = Server.get_by_id(server_id)
        if not server:
            return jsonify({'success': False, 'error': 'Server not found'}), 404
        if not _has_server_access(server_id):
            return jsonify({'success': False, 'error': 'Forbidden'}), 403

        if not server_manager.is_server_running(server_id):
            return jsonify({'success': False, 'error': 'Server not running'}), 400

        payload = request.get_json(silent=True) or {}
        action = payload.get('action', 'status')

        if action == 'login_device':
            ok = server_manager.send_command(server_id, '/auth login device')
        else:
            ok = server_manager.send_command(server_id, '/auth status')

        if not ok:
            return jsonify({'success': False, 'error': 'Failed to send auth command'}), 500

        return jsonify({'success': True})
    except Exception as e:
        print(f"Error triggering auth for server {server_id}: {e}")
        return jsonify({'success': False, 'error': 'An unexpected error occurred'}), 500

@bp.route('/api/server/<int:server_id>/console')
@login_required
@require_permission('view_servers')
def get_console_output(server_id):
    """API endpoint to get recent console output"""
    try:
        server = Server.get_by_id(server_id)

        if not server:
            return jsonify({'success': False, 'error': 'Server not found'}), 404

        lines = request.args.get('lines', default=200, type=int)
        lines = max(1, min(lines, 1000))

        output = server_manager.get_console_output(server_id, lines=lines)

        return jsonify({
            'success': True,
            'lines': output
        })

    except Exception as e:
        print(f"Error getting console output: {e}")
        return jsonify({'success': False, 'error': 'An unexpected error occurred'}), 500
