"""
Server control routes for start, stop, restart operations
"""

from flask import Blueprint, render_template, request, jsonify, current_app
from flask_login import login_required, current_user
import os
import time
import datetime
import traceback
import urllib.parse
import json
import sqlite3

from models.server import Server
from models.user import User
from utils import server_manager, java_checker
from utils import settings as settings_utils
from utils import curseforge
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

MOD_MANIFEST_FILENAME = 'mods_manifest.json'

MOD_CLASS_LABELS = {
    6: 'Mod',
    4471: 'Plugin',
    4475: 'Modpack',
}

SORT_FIELD_MAP = {
    'popularity': 2,
    'latest': 3,
    'downloads': 6,
}

REQUIRED_RELATIONS = {3, 6}


def _get_mods_dir(server_id):
    return os.path.join(server_manager.get_server_path(server_id), 'mods')


def _get_mod_manifest_path(server_id):
    return os.path.join(server_manager.get_server_path(server_id), MOD_MANIFEST_FILENAME)


def _load_mod_manifest(server_id):
    path = _get_mod_manifest_path(server_id)
    if not os.path.exists(path):
        return {'mods': []}
    try:
        data = _read_json_file(path)
        if isinstance(data, dict) and isinstance(data.get('mods'), list):
            return data
    except Exception as exc:
        print(f"Error reading mod manifest for server {server_id}: {exc}")
    return {'mods': []}


def _save_mod_manifest(server_id, data):
    path = _get_mod_manifest_path(server_id)
    try:
        _write_json_file(path, data)
    except Exception as exc:
        print(f"Error writing mod manifest for server {server_id}: {exc}")


def _iso_now():
    return datetime.datetime.utcnow().replace(microsecond=0).isoformat() + 'Z'


def _detect_side_label(game_versions):
    if not game_versions:
        return None
    lowered = [str(item).lower() for item in game_versions]
    has_server = any('server' in item for item in lowered)
    has_client = any('client' in item for item in lowered)
    if has_server and has_client:
        return 'Client & Server'
    if has_server:
        return 'Server-only'
    if has_client:
        return 'Client-only'
    return None


def _sanitize_filename(name, fallback):
    if not name:
        return fallback
    return os.path.basename(name)


def _select_best_file(files, server_version=None):
    if not files:
        return None
    if server_version:
        for file in files:
            if server_version in (file.get('gameVersions') or []):
                return file
    return sorted(files, key=lambda item: item.get('fileDate') or '', reverse=True)[0]


def _log_mod_install_error(server_id, mod_id, file_id, error_message):
    base_path = os.path.abspath(os.path.join(os.path.dirname(__file__), '..', '..'))
    log_dir = os.path.join(base_path, 'logs')
    os.makedirs(log_dir, exist_ok=True)
    log_path = os.path.join(log_dir, 'curseforge_mods.log')
    timestamp = datetime.datetime.utcnow().isoformat() + 'Z'
    with open(log_path, 'a', encoding='utf-8') as handle:
        handle.write(f"[{timestamp}] server={server_id} mod={mod_id} file={file_id} error={error_message}\n")


def _build_forgecdn_url(file_id, file_name):
    if not file_id or not file_name:
        return None
    try:
        file_id = int(file_id)
    except (TypeError, ValueError):
        return None
    major = file_id // 1000
    minor = file_id % 1000
    encoded_name = urllib.parse.quote(str(file_name))
    return f"https://edge.forgecdn.net/files/{major}/{minor}/{encoded_name}"


def _get_curseforge_config():
    db_path = current_app.config['DATABASE']
    api_key = settings_utils.get_setting(db_path, 'curseforge_api_key', '').strip()
    if not api_key:
        return None, None, 'CurseForge API key is missing.'
    game_id = settings_utils.get_setting(db_path, 'curseforge_game_id', '70216').strip()
    if not game_id.isdigit():
        game_id = '432'
    return api_key, int(game_id), None


def _build_mod_card(mod):
    latest_file = _select_best_file(mod.get('latestFiles') or [])
    logo = mod.get('logo') or {}
    logo_url = logo.get('thumbnailUrl') or logo.get('url')
    side_label = None
    latest_file_size = None
    latest_file_name = None
    if latest_file:
        latest_file_name = latest_file.get('fileName')
        side_label = _detect_side_label(latest_file.get('gameVersions'))
        latest_file_size = latest_file.get('fileLength')
    return {
        'id': mod.get('id'),
        'name': mod.get('name'),
        'summary': mod.get('summary'),
        'download_count': mod.get('downloadCount'),
        'logo_url': logo_url,
        'date_modified': mod.get('dateModified'),
        'date_created': mod.get('dateCreated'),
        'latest_file_size': latest_file_size,
        'latest_file_name': latest_file_name,
        'type_label': MOD_CLASS_LABELS.get(mod.get('classId'), 'Mod'),
        'side_label': side_label,
    }


def _upsert_manifest_entry(manifest, entry):
    mods = manifest.get('mods', [])
    for idx, existing in enumerate(mods):
        if existing.get('file_name') == entry.get('file_name'):
            mods[idx] = entry
            manifest['mods'] = mods
            return
        if entry.get('mod_id') and existing.get('mod_id') == entry.get('mod_id'):
            mods[idx] = entry
            manifest['mods'] = mods
            return
    mods.append(entry)
    manifest['mods'] = mods


def _install_mod_recursive(server_id, mod_id, file_id, api_key, server_version, manifest, visited, cache, auto_installed=False):
    key = (mod_id, file_id)
    if key in visited:
        return
    visited.add(key)

    mod_data = cache['mods'].get(mod_id)
    if not mod_data:
        mod_resp, error = curseforge.get_mod(api_key, mod_id)
        if error:
            raise RuntimeError(f"Failed to load mod {mod_id}: {error}")
        mod_data = mod_resp.get('data')
        cache['mods'][mod_id] = mod_data

    file_resp, error = curseforge.get_mod_file(api_key, mod_id, file_id)
    if error:
        raise RuntimeError(f"Failed to load file {file_id} for mod {mod_id}: {error}")
    file_data = file_resp.get('data')
    if not file_data:
        raise RuntimeError(f"File {file_id} not found for mod {mod_id}")

    download_url = file_data.get('downloadUrl')
    file_name_hint = file_data.get('fileName')
    if not download_url:
        download_resp, error = curseforge.get_download_url(api_key, mod_id, file_id)
        if error:
            fallback_url = _build_forgecdn_url(file_id, file_name_hint)
            if fallback_url:
                download_url = fallback_url
            else:
                raise RuntimeError(f"Failed to get download URL for {mod_id}:{file_id}: {error}")
        if not download_url:
            download_data = download_resp.get('data') if download_resp else None
            if isinstance(download_data, str):
                download_url = download_data
            elif isinstance(download_data, dict):
                download_url = download_data.get('downloadUrl') or download_data.get('url')
        if not download_url:
            download_url = _build_forgecdn_url(file_id, file_name_hint)
    if not download_url:
        raise RuntimeError(f"Download URL missing for {mod_id}:{file_id}")

    mods_dir = _get_mods_dir(server_id)
    os.makedirs(mods_dir, exist_ok=True)
    file_name = _sanitize_filename(file_data.get('fileName'), f"{mod_id}-{file_id}.jar")
    destination = os.path.join(mods_dir, file_name)

    if not os.path.exists(destination):
        curseforge.download_file(download_url, destination)

    side_label = _detect_side_label(file_data.get('gameVersions'))
    logo = mod_data.get('logo') or {}
    entry = {
        'mod_id': mod_id,
        'file_id': file_id,
        'name': mod_data.get('name'),
        'summary': mod_data.get('summary'),
        'file_name': file_name,
        'file_length': file_data.get('fileLength'),
        'download_count': mod_data.get('downloadCount'),
        'logo_url': logo.get('thumbnailUrl') or logo.get('url'),
        'installed_at': _iso_now(),
        'side_label': side_label,
        'auto_installed': bool(auto_installed),
    }
    _upsert_manifest_entry(manifest, entry)

    dependencies = file_data.get('dependencies') or []
    if not dependencies:
        return

    for dependency in dependencies:
        relation_type = dependency.get('relationType')
        dep_mod_id = dependency.get('modId')
        if relation_type not in REQUIRED_RELATIONS or not dep_mod_id:
            continue
        dep_files = cache['files'].get(dep_mod_id)
        if dep_files is None:
            dep_resp, error = curseforge.get_mod_files(
                api_key,
                dep_mod_id,
                params={'pageSize': 50, 'index': 0},
            )
            if error:
                raise RuntimeError(f"Failed to load files for dependency {dep_mod_id}: {error}")
            dep_files = dep_resp.get('data') or []
            cache['files'][dep_mod_id] = dep_files
        dep_file = _select_best_file(dep_files, server_version)
        if not dep_file:
            raise RuntimeError(f"No compatible file found for dependency {dep_mod_id}")
        _install_mod_recursive(
            server_id,
            dep_mod_id,
            dep_file.get('id'),
            api_key,
            server_version,
            manifest,
            visited,
            cache,
            auto_installed=True,
        )

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
                         active_page='dashboard',
                         nav_mode='server',
                         nav_server={'id': server.id, 'name': server.name, 'status': server.status})

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
                           active_page='config',
                           nav_mode='server',
                           nav_server={'id': server.id, 'name': server.name, 'status': server.status})

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
                           active_page='world',
                           nav_mode='server',
                           nav_server={'id': server.id, 'name': server.name, 'status': server.status})

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
                           active_page='players',
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


@bp.route('/server/<int:server_id>/mods')
@login_required
@require_permission('manage_configs')
def mods_view(server_id):
    server = _get_server_or_404(server_id)
    if not server:
        return render_template('404.html'), 404
    if not _has_server_access(server_id):
        return render_template('403.html'), 403

    db_path = current_app.config['DATABASE']
    api_key = settings_utils.get_setting(db_path, 'curseforge_api_key', '')
    server_version = server_manager.get_server_version(server_id)

    return render_template(
        'server_mods.html',
        server=server,
        user=current_user,
        host_os=_get_host_os(),
        active_page='mods',
        curseforge_ready=bool(api_key),
        server_version=server_version,
        nav_mode='server',
        nav_server={'id': server.id, 'name': server.name, 'status': server.status},
    )


@bp.route('/server/<int:server_id>/mods/installed')
@login_required
@require_permission('manage_configs')
def mods_installed_view(server_id):
    server = _get_server_or_404(server_id)
    if not server:
        return render_template('404.html'), 404
    if not _has_server_access(server_id):
        return render_template('403.html'), 403

    return render_template(
        'server_mods_installed.html',
        server=server,
        user=current_user,
        host_os=_get_host_os(),
        active_page='mods_installed',
        nav_mode='server',
        nav_server={'id': server.id, 'name': server.name, 'status': server.status},
    )

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


@bp.route('/api/server/<int:server_id>/mods/search')
@login_required
@require_permission('manage_configs')
def search_mods(server_id):
    server = Server.get_by_id(server_id)
    if not server:
        return jsonify({'success': False, 'error': 'Server not found'}), 404
    if not _has_server_access(server_id):
        return jsonify({'success': False, 'error': 'Forbidden'}), 403

    api_key, game_id, error = _get_curseforge_config()
    if error:
        return jsonify({'success': False, 'error': error}), 400

    query = request.args.get('query', '').strip()
    sort = request.args.get('sort', 'relevancy').strip().lower()
    index = max(0, request.args.get('index', type=int) or 0)
    page_size = request.args.get('page_size', type=int) or 12
    page_size = max(1, min(page_size, 50))

    params = {
        'gameId': game_id,
        'pageSize': page_size,
        'index': index,
    }
    if query:
        params['searchFilter'] = query
    sort_field = SORT_FIELD_MAP.get(sort)
    if sort_field:
        params['sortField'] = sort_field
        params['sortOrder'] = 'desc'

    resp, error = curseforge.search_mods(api_key, params)
    if error:
        return jsonify({'success': False, 'error': error}), 502

    mods = resp.get('data') or []
    if sort == 'creation':
        mods = sorted(mods, key=lambda item: item.get('dateCreated') or '', reverse=True)

    manifest = _load_mod_manifest(server_id)
    installed_ids = {
        item.get('mod_id') for item in manifest.get('mods', [])
        if item.get('mod_id')
    }
    items = []
    for mod in mods:
        card = _build_mod_card(mod)
        card['installed'] = bool(card.get('id') in installed_ids)
        items.append(card)
    pagination = resp.get('pagination') or {}

    return jsonify({
        'success': True,
        'mods': items,
        'pagination': {
            'index': pagination.get('index', index),
            'page_size': pagination.get('pageSize', page_size),
            'total_count': pagination.get('totalCount', 0),
        },
    })


@bp.route('/api/server/<int:server_id>/mods/<int:mod_id>/files')
@login_required
@require_permission('manage_configs')
def get_mod_files(server_id, mod_id):
    server = Server.get_by_id(server_id)
    if not server:
        return jsonify({'success': False, 'error': 'Server not found'}), 404
    if not _has_server_access(server_id):
        return jsonify({'success': False, 'error': 'Forbidden'}), 403

    api_key, _, error = _get_curseforge_config()
    if error:
        return jsonify({'success': False, 'error': error}), 400

    resp, error = curseforge.get_mod_files(api_key, mod_id, params={'pageSize': 50, 'index': 0})
    if error:
        return jsonify({'success': False, 'error': error}), 502

    server_version = server_manager.get_server_version(server_id)
    files = []
    for file in sorted(resp.get('data') or [], key=lambda item: item.get('fileDate') or '', reverse=True):
        game_versions = file.get('gameVersions') or []
        side_label = _detect_side_label(game_versions)
        release_type = file.get('releaseType')
        release_label = {1: 'Release', 2: 'Beta', 3: 'Alpha'}.get(release_type)
        files.append({
            'id': file.get('id'),
            'display_name': file.get('displayName') or file.get('fileName'),
            'file_date': file.get('fileDate'),
            'file_length': file.get('fileLength'),
            'game_versions': game_versions[:6],
            'matches_server': bool(server_version and server_version in game_versions),
            'release_label': release_label,
            'side_label': side_label,
        })

    return jsonify({
        'success': True,
        'files': files,
        'server_version': server_version,
    })


@bp.route('/api/server/<int:server_id>/mods/install', methods=['POST'])
@login_required
@require_permission('manage_configs')
def install_mod(server_id):
    server = Server.get_by_id(server_id)
    if not server:
        return jsonify({'success': False, 'error': 'Server not found'}), 404
    if not _has_server_access(server_id):
        return jsonify({'success': False, 'error': 'Forbidden'}), 403

    payload = request.get_json(silent=True) or {}
    mod_id = payload.get('mod_id')
    file_id = payload.get('file_id')
    if not mod_id or not file_id:
        return jsonify({'success': False, 'error': 'Missing mod or file ID'}), 400

    api_key, _, error = _get_curseforge_config()
    if error:
        return jsonify({'success': False, 'error': error}), 400

    manifest = _load_mod_manifest(server_id)
    server_version = server_manager.get_server_version(server_id)
    visited = set()
    cache = {'mods': {}, 'files': {}}
    try:
        _install_mod_recursive(
            server_id,
            int(mod_id),
            int(file_id),
            api_key,
            server_version,
            manifest,
            visited,
            cache,
            auto_installed=False,
        )
    except Exception as exc:
        error_text = str(exc)
        _log_mod_install_error(server_id, mod_id, file_id, error_text)
        traceback_text = traceback.format_exc()
        _log_mod_install_error(server_id, mod_id, file_id, traceback_text.strip())
        print(f"Error installing mod {mod_id} file {file_id} on server {server_id}: {error_text}")
        return jsonify({'success': False, 'error': error_text}), 500

    _save_mod_manifest(server_id, manifest)
    return jsonify({'success': True})


@bp.route('/api/server/<int:server_id>/mods/installed')
@login_required
@require_permission('manage_configs')
def list_installed_mods(server_id):
    server = Server.get_by_id(server_id)
    if not server:
        return jsonify({'success': False, 'error': 'Server not found'}), 404
    if not _has_server_access(server_id):
        return jsonify({'success': False, 'error': 'Forbidden'}), 403

    mods_dir = _get_mods_dir(server_id)
    manifest = _load_mod_manifest(server_id)
    manifest_map = {item.get('file_name'): item for item in manifest.get('mods', [])}
    results = []

    if os.path.isdir(mods_dir):
        for filename in sorted(os.listdir(mods_dir)):
            if not (filename.endswith('.jar') or filename.endswith('.zip')):
                continue
            file_path = os.path.join(mods_dir, filename)
            entry = manifest_map.get(filename, {}).copy()
            entry.setdefault('file_name', filename)
            entry.setdefault('name', filename)
            entry.setdefault('summary', filename)
            entry['file_length'] = os.path.getsize(file_path)
            entry.setdefault('installed_at', datetime.datetime.utcfromtimestamp(
                os.path.getmtime(file_path)
            ).replace(microsecond=0).isoformat() + 'Z')
            results.append(entry)

    return jsonify({'success': True, 'mods': results})


@bp.route('/api/server/<int:server_id>/mods/uninstall', methods=['POST'])
@login_required
@require_permission('manage_configs')
def uninstall_mod(server_id):
    server = Server.get_by_id(server_id)
    if not server:
        return jsonify({'success': False, 'error': 'Server not found'}), 404
    if not _has_server_access(server_id):
        return jsonify({'success': False, 'error': 'Forbidden'}), 403

    payload = request.get_json(silent=True) or {}
    file_name = payload.get('file_name')
    if not file_name:
        return jsonify({'success': False, 'error': 'Missing file name'}), 400

    mods_dir = _get_mods_dir(server_id)
    safe_name = _sanitize_filename(file_name, file_name)
    file_path = os.path.join(mods_dir, safe_name)
    if os.path.exists(file_path):
        os.remove(file_path)

    manifest = _load_mod_manifest(server_id)
    manifest['mods'] = [
        item for item in manifest.get('mods', [])
        if item.get('file_name') != safe_name
    ]
    _save_mod_manifest(server_id, manifest)

    return jsonify({'success': True})
