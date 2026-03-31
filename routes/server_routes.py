"""
Server control routes for start, stop, restart operations
"""

from flask import Blueprint, render_template, request, jsonify, current_app
from flask_login import login_required, current_user
import logging
import os
import sqlite3
import time
import json

logger = logging.getLogger(__name__)

from models.server import Server
from models.user import User
from utils import server_manager, java_checker, port_checker
from utils import settings as settings_utils
from utils import gotale_config
from utils.authz import require_permission
from utils.database import get_db

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
        with get_db(current_app.config['DATABASE']) as conn:
            cursor = conn.cursor()
            cursor.execute("SELECT value FROM settings WHERE key = 'host_os'")
            result = cursor.fetchone()
        if result and result[0]:
            host_os = result[0]
    except sqlite3.Error as e:
        logger.error(f"Error reading host_os setting: {e}", exc_info=True)
    return host_os

def _read_json_file(path):
    with open(path, 'r', encoding='utf-8') as file:
        return json.load(file)

def _write_json_file(path, data):
    with open(path, 'w', encoding='utf-8') as file:
        json.dump(data, file, indent=2, ensure_ascii=True)
        file.write('\n')


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

    db_path = current_app.config['DATABASE']
    api_key = settings_utils.get_setting(db_path, 'curseforge_api_key', '')

    return render_template('server_console.html',
                         server=server,
                         console_history=console_history,
                         is_running=is_running,
                         java_info=java_info,
                         curseforge_ready=bool(api_key),
                         user=current_user,
                         host_os=_get_host_os(),
                         active_page='dashboard',
                         nav_mode='server',
                         nav_server={'id': server.id, 'name': server.name, 'status': server.status})


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
                           active_page='backup',
                           nav_mode='server',
                           nav_server={'id': server.id, 'name': server.name, 'status': server.status})

@bp.route('/server/<int:server_id>/startup')
@login_required
@require_permission('manage_servers')
def startup_view(server_id):
    server = _get_server_or_404(server_id)
    if not server:
        return render_template('404.html'), 404
    if not _has_server_access(server_id):
        return render_template('403.html'), 403

    return render_template('server_startup.html',
                           server=server,
                           user=current_user,
                           host_os=_get_host_os(),
                           active_page='startup',
                           nav_mode='server',
                           nav_server={'id': server.id, 'name': server.name, 'status': server.status})


@bp.route('/server/<int:server_id>/webhooks')
@login_required
@require_permission('manage_configs')
def webhooks_view(server_id):
    server = _get_server_or_404(server_id)
    if not server:
        return render_template('404.html'), 404
    if not _has_server_access(server_id):
        return render_template('403.html'), 403

    return render_template(
        'server_webhooks.html',
        server=server,
        user=current_user,
        host_os=_get_host_os(),
        active_page='webhooks',
        nav_mode='server',
        nav_server={'id': server.id, 'name': server.name, 'status': server.status},
    )


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

@bp.route('/api/server/<int:server_id>/startup-settings', methods=['GET', 'POST'])
@login_required
@require_permission('manage_servers')
def startup_settings(server_id):
    server = _get_server_or_404(server_id)
    if not server:
        return jsonify({'success': False, 'error': 'Server not found'}), 404
    if not _has_server_access(server_id):
        return jsonify({'success': False, 'error': 'Forbidden'}), 403

    if request.method == 'GET':
        settings = server_manager.read_startup_settings(server_id)
        settings['port'] = server.port
        return jsonify({'success': True, 'settings': settings})

    payload = request.get_json(silent=True) or {}
    port_value = payload.get('port', server.port)
    try:
        port_value = int(port_value)
    except (TypeError, ValueError):
        return jsonify({'success': False, 'error': 'Invalid port number'}), 400

    if port_value < 1024 or port_value > 65535:
        return jsonify({'success': False, 'error': 'Port must be between 1024 and 65535'}), 400

    if port_value != server.port:
        if not port_checker.is_port_available(port_value):
            suggested = port_checker.get_next_available_port(port_value)
            return jsonify({
                'success': False,
                'error': f'Port {port_value} is already in use',
                'suggested_port': suggested
            }), 400
        if Server.port_exists_excluding(port_value, server_id):
            suggested = port_checker.get_next_available_port(port_value)
            return jsonify({
                'success': False,
                'error': f'Port {port_value} is already assigned to another server',
                'suggested_port': suggested
            }), 400
        Server.update_port(server_id, port_value)
    settings = {
        'min_ram_mb': payload.get('min_ram_mb'),
        'max_ram_mb': payload.get('max_ram_mb'),
        'game_profile': payload.get('game_profile', ''),
        'auth_mode': payload.get('auth_mode', ''),
        'automatic_update': bool(payload.get('automatic_update', False)),
        'allow_op': bool(payload.get('allow_op', True)),
        'accept_early_plugins': bool(payload.get('accept_early_plugins', False)),
        'asset_pack': payload.get('asset_pack', ''),
        'enable_backups': bool(payload.get('enable_backups', False)),
        'backup_directory': payload.get('backup_directory', ''),
        'backup_frequency': payload.get('backup_frequency', 30),
        'disable_sentry': bool(payload.get('disable_sentry', False)),
        'jvm_args': payload.get('jvm_args', ''),
        'leverage_aot_cache': bool(payload.get('leverage_aot_cache', True)),
        'crash_detection_enabled': bool(payload.get('crash_detection_enabled', False)),
        'crash_webhook_url': payload.get('crash_webhook_url', ''),
        'crash_auto_restart': bool(payload.get('crash_auto_restart', False))
    }

    saved = server_manager.write_startup_settings(server_id, settings)
    if not saved:
        return jsonify({'success': False, 'error': 'Failed to save settings'}), 500
    saved['port'] = port_value
    return jsonify({'success': True, 'settings': saved})

@bp.route('/api/server/<int:server_id>/port-check')
@login_required
@require_permission('manage_servers')
def check_server_port(server_id):
    server = _get_server_or_404(server_id)
    if not server:
        return jsonify({'success': False, 'error': 'Server not found'}), 404
    if not _has_server_access(server_id):
        return jsonify({'success': False, 'error': 'Forbidden'}), 403

    port_value = request.args.get('port', type=int)
    if not port_value:
        return jsonify({'success': False, 'error': 'Missing port'}), 400
    if port_value < 1024 or port_value > 65535:
        return jsonify({'success': False, 'error': 'Port must be between 1024 and 65535'}), 400

    if port_value == server.port:
        return jsonify({'success': True, 'available': True, 'current': True})

    available = port_checker.is_port_available(port_value)
    assigned = Server.port_exists_excluding(port_value, server_id)
    suggested = None
    if not available or assigned:
        suggested = port_checker.get_next_available_port(port_value)
    return jsonify({
        'success': True,
        'available': available and not assigned,
        'current': False,
        'assigned': assigned,
        'suggested_port': suggested
    })


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
        logger.error(f"Error creating backup for server {server_id}: {e}", exc_info=True)
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
        logger.error(f"Error restoring backup for server {server_id}: {e}", exc_info=True)
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
            logger.error(f"Error running startup backup for server {server_id}: {e}", exc_info=True)
            return jsonify({'success': False, 'error': 'Backup on start failed'}), 500

        # Update status to starting
        Server.update_status(server_id, 'starting')

        # Get SocketIO instance
        from app import socketio

        # Start server in new terminal window
        if server_manager.has_gotale_plugin(server_id):
            try:
                gotale_config.ensure_gotale_config(server_id, create_if_missing=True)
            except Exception as exc:
                logger.error(f"GoTale config update failed for server {server_id}: {exc}", exc_info=True)
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
        _clear_restart_required(server_id)

        return jsonify({'success': True, 'message': 'Server started successfully'})

    except Exception as e:
        logger.error(f"Error starting server: {e}", exc_info=True)
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
        logger.error(f"Error stopping server: {e}", exc_info=True)
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
            logger.error(f"Error running startup backup for server {server_id}: {e}", exc_info=True)
            return jsonify({'success': False, 'error': 'Backup on start failed'}), 500

        # Start server
        Server.update_status(server_id, 'starting')

        from app import socketio

        if server_manager.has_gotale_plugin(server_id):
            try:
                gotale_config.ensure_gotale_config(server_id, create_if_missing=True)
            except Exception as exc:
                logger.error(f"GoTale config update failed for server {server_id}: {exc}", exc_info=True)
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
        _clear_restart_required(server_id)

        return jsonify({'success': True, 'message': 'Server restarted successfully'})

    except Exception as e:
        logger.error(f"Error restarting server: {e}", exc_info=True)
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
        status = server.status

        # Reconcile DB status with actual process state
        if is_running and status != 'online':
            status = 'online'
            Server.update_status(server_id, status)
        elif not is_running and status in ('online', 'starting', 'stopping'):
            status = 'offline'
            Server.update_status(server_id, status)

        return jsonify({
            'success': True,
            'status': status,
            'is_running': is_running,
            'port': server.port
        })

    except Exception as e:
        logger.error(f"Error getting server status: {e}", exc_info=True)
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
        logger.error(f"Error getting auth status: {e}", exc_info=True)
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
            ok, reason = server_manager.request_auth_login(server_id, 'manual')
            if not ok and reason in ('already_pending', 'cooldown'):
                return jsonify({'success': True, 'skipped': True, 'reason': reason})
            if not ok:
                return jsonify({'success': False, 'error': 'Failed to send auth command'}), 500
        else:
            ok = server_manager.send_command(server_id, '/auth status')
            if not ok:
                return jsonify({'success': False, 'error': 'Failed to send auth command'}), 500

        return jsonify({'success': True})
    except Exception as e:
        logger.error(f"Error triggering auth for server {server_id}: {e}", exc_info=True)
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
        logger.error(f"Error getting console output: {e}", exc_info=True)
        return jsonify({'success': False, 'error': 'An unexpected error occurred'}), 500


def _clear_restart_required(server_id):
    """Clear restart_required flags in the mod manifest after a server start/restart."""
    from routes.server_mods import _load_mod_manifest, _save_mod_manifest
    manifest = _load_mod_manifest(server_id)
    changed = False
    for entry in manifest.get('mods', []):
        if entry.get('restart_required'):
            entry['restart_required'] = False
            changed = True
    if changed:
        _save_mod_manifest(server_id, manifest)
