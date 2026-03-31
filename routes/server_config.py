"""
Server configuration and world editor routes
"""

from flask import Blueprint, render_template, request, jsonify, current_app
from flask_login import login_required, current_user
import logging
import os
import json

logger = logging.getLogger(__name__)

from models.server import Server
from utils import server_manager
from utils import settings as settings_utils
from utils.authz import require_permission

from routes.server_routes import (
    _get_server_or_404,
    _has_server_access,
    _get_host_os,
    _read_json_file,
    _write_json_file,
)

config_bp = Blueprint('server_config', __name__)


# ---------------------------------------------------------------------------
# Helper functions
# ---------------------------------------------------------------------------

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


def _extract_player_display_name(data, fallback):
    if not isinstance(data, dict):
        return fallback
    components = data.get('Components') or {}
    display_name = components.get('DisplayName') or {}
    display_value = display_name.get('DisplayName') or {}
    raw_text = display_value.get('RawText')
    if isinstance(raw_text, str) and raw_text.strip():
        return raw_text.strip()
    nameplate = components.get('Nameplate') or {}
    nameplate_text = nameplate.get('Text')
    if isinstance(nameplate_text, str) and nameplate_text.strip():
        return nameplate_text.strip()
    return fallback


# ---------------------------------------------------------------------------
# Page views
# ---------------------------------------------------------------------------

@config_bp.route('/server/<int:server_id>/config')
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
                           active_page='config',
                           nav_mode='server',
                           nav_server={'id': server.id, 'name': server.name, 'status': server.status})


@config_bp.route('/server/<int:server_id>/world')
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
                           active_page='world',
                           nav_mode='server',
                           nav_server={'id': server.id, 'name': server.name, 'status': server.status})


# ---------------------------------------------------------------------------
# API routes
# ---------------------------------------------------------------------------

@config_bp.route('/api/server/<int:server_id>/config-files')
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


@config_bp.route('/api/server/<int:server_id>/world-files')
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


@config_bp.route('/api/server/<int:server_id>/player-files')
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
        display_name = name
        try:
            data = _read_json_file(file_map[name])
            display_name = _extract_player_display_name(data, name)
        except (json.JSONDecodeError, IOError, OSError) as e:
            logger.error(f"Error reading player file {name}: {e}", exc_info=True)
        files.append({
            'value': name,
            'label': display_name,
            'fileLabel': name
        })

    return jsonify({'success': True, 'files': files})


@config_bp.route('/api/server/<int:server_id>/player-summaries')
@login_required
@require_permission('manage_configs')
def get_player_summaries(server_id):
    server = _get_server_or_404(server_id)
    if not server:
        return jsonify({'success': False, 'error': 'Server not found'}), 404
    if not _has_server_access(server_id):
        return jsonify({'success': False, 'error': 'Forbidden'}), 403

    file_map = _get_player_file_map(server_id)
    players = []
    for filename, path in file_map.items():
        uuid = filename.rsplit('.json', 1)[0]
        try:
            data = _read_json_file(path)
            display_name = _extract_player_display_name(data, uuid)
        except (json.JSONDecodeError, IOError, OSError) as e:
            logger.error(f"Error reading player file {filename}: {e}", exc_info=True)
            display_name = uuid
        players.append({
            'uuid': uuid,
            'name': display_name,
            'file': filename,
        })

    return jsonify({'success': True, 'players': players})


@config_bp.route('/api/server/<int:server_id>/config-file', methods=['GET', 'POST'])
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
        except (json.JSONDecodeError, IOError, OSError) as e:
            logger.error(f"Error reading config file: {e}", exc_info=True)
            return jsonify({'success': False, 'error': 'Failed to read config file'}), 500

    payload = request.get_json(silent=True)
    if payload is None:
        return jsonify({'success': False, 'error': 'Missing JSON payload'}), 400

    data = payload.get('data', payload)
    try:
        _write_json_file(file_map[name], data)
        return jsonify({'success': True})
    except (IOError, OSError) as e:
        logger.error(f"Error writing config file: {e}", exc_info=True)
        return jsonify({'success': False, 'error': 'Failed to write config file'}), 500


@config_bp.route('/api/server/<int:server_id>/world-file', methods=['GET', 'POST'])
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
        except (json.JSONDecodeError, IOError, OSError) as e:
            logger.error(f"Error reading world file: {e}", exc_info=True)
            return jsonify({'success': False, 'error': 'Failed to read world file'}), 500

    payload = request.get_json(silent=True)
    if payload is None:
        return jsonify({'success': False, 'error': 'Missing JSON payload'}), 400

    data = payload.get('data', payload)
    try:
        _write_json_file(file_map[name], data)
        return jsonify({'success': True})
    except (IOError, OSError) as e:
        logger.error(f"Error writing world file: {e}", exc_info=True)
        return jsonify({'success': False, 'error': 'Failed to write world file'}), 500


@config_bp.route('/api/server/<int:server_id>/player-file', methods=['GET', 'POST'])
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
        except (json.JSONDecodeError, IOError, OSError) as e:
            logger.error(f"Error reading player file: {e}", exc_info=True)
            return jsonify({'success': False, 'error': 'Failed to read player file'}), 500

    payload = request.get_json(silent=True)
    if payload is None:
        return jsonify({'success': False, 'error': 'Missing JSON payload'}), 400

    data = payload.get('data', payload)
    try:
        _write_json_file(file_map[name], data)
        return jsonify({'success': True})
    except (IOError, OSError) as e:
        logger.error(f"Error writing player file: {e}", exc_info=True)
        return jsonify({'success': False, 'error': 'Failed to write player file'}), 500


@config_bp.route('/api/server/<int:server_id>/jvm-options', methods=['GET'])
@login_required
@require_permission('manage_servers')
def get_jvm_options(server_id):
    server = _get_server_or_404(server_id)
    if not server:
        return jsonify({'success': False, 'error': 'Server not found'}), 404
    if not _has_server_access(server_id):
        return jsonify({'success': False, 'error': 'Forbidden'}), 403

    server_dir = server_manager.get_server_path(server_id)
    jvm_options_path = os.path.join(server_dir, 'jvm.options')

    if os.path.isfile(jvm_options_path):
        try:
            with open(jvm_options_path, 'r', encoding='utf-8') as f:
                content = f.read()
        except OSError as e:
            logger.error(f"Failed to read jvm.options for server {server_id}: {e}")
            return jsonify({'success': False, 'error': 'Failed to read jvm.options'}), 500
    else:
        content = (
            "# jvm.options — one JVM argument per line\n"
            "# Lines starting with '#' are comments and will be ignored.\n"
            "# Pass this file to the JVM using @jvm.options syntax.\n"
            "#\n"
            "# Example flags:\n"
            "# -Xms1024M\n"
            "# -Xmx4096M\n"
            "# -XX:+UseG1GC\n"
        )

    return jsonify({'success': True, 'content': content})


@config_bp.route('/api/server/<int:server_id>/jvm-options', methods=['POST'])
@login_required
@require_permission('manage_servers')
def save_jvm_options(server_id):
    server = _get_server_or_404(server_id)
    if not server:
        return jsonify({'success': False, 'error': 'Server not found'}), 404
    if not _has_server_access(server_id):
        return jsonify({'success': False, 'error': 'Forbidden'}), 403

    payload = request.get_json(silent=True) or {}
    content = payload.get('content', '')
    if not isinstance(content, str):
        return jsonify({'success': False, 'error': 'Invalid content'}), 400

    server_dir = server_manager.get_server_path(server_id)
    jvm_options_path = os.path.join(server_dir, 'jvm.options')

    try:
        os.makedirs(server_dir, exist_ok=True)
        with open(jvm_options_path, 'w', encoding='utf-8') as f:
            f.write(content)
    except OSError as e:
        logger.error(f"Failed to write jvm.options for server {server_id}: {e}")
        return jsonify({'success': False, 'error': 'Failed to save jvm.options'}), 500

    return jsonify({'success': True})
