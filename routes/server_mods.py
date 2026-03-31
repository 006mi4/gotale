"""
Mod management routes for Hytale servers (CurseForge integration + local uploads)
"""

from flask import Blueprint, render_template, request, jsonify, current_app
from flask_login import login_required, current_user
import logging
import os
import datetime
import traceback
import urllib.parse
import json
from werkzeug.utils import secure_filename

logger = logging.getLogger(__name__)

from models.server import Server
from models.user import User
from utils import server_manager
from utils import settings as settings_utils
from utils import curseforge
from utils.authz import require_permission

from routes.server_routes import (
    _get_server_or_404,
    _has_server_access,
    _get_host_os,
    _read_json_file,
    _write_json_file,
)

mods_bp = Blueprint('mods', __name__)

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

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


# ---------------------------------------------------------------------------
# Helper functions
# ---------------------------------------------------------------------------

def _get_mods_dir(server_id):
    return os.path.join(server_manager.get_server_data_dir(server_id), 'mods')


def _get_mod_manifest_path(server_id):
    return os.path.join(server_manager.get_server_data_dir(server_id), MOD_MANIFEST_FILENAME)


def _load_mod_manifest(server_id):
    path = _get_mod_manifest_path(server_id)
    if not os.path.exists(path):
        return {'mods': []}
    try:
        data = _read_json_file(path)
        if isinstance(data, dict) and isinstance(data.get('mods'), list):
            return data
    except (json.JSONDecodeError, IOError, OSError) as exc:
        logger.error(f"Error reading mod manifest for server {server_id}: {exc}", exc_info=True)
    return {'mods': []}


def _save_mod_manifest(server_id, data):
    path = _get_mod_manifest_path(server_id)
    try:
        _write_json_file(path, data)
    except (IOError, OSError) as exc:
        logger.error(f"Error writing mod manifest for server {server_id}: {exc}", exc_info=True)


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


def _normalize_mod_filename(filename):
    name = secure_filename(filename or '')
    return name if name else None


def _is_allowed_mod_filename(filename):
    if not filename:
        return False
    lowered = filename.lower()
    return lowered.endswith('.jar') or lowered.endswith('.zip')


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


def _install_mod_recursive(server_id, mod_id, file_id, api_key, server_version, manifest, visited, cache, auto_installed=False, auto_update=False):
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
        'auto_update': bool(auto_update),
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
            auto_update=False,
        )


def _apply_auto_updates(server_id, manifest, api_key, server_version):
    mods_dir = _get_mods_dir(server_id)
    os.makedirs(mods_dir, exist_ok=True)
    cache = {}
    updated = []

    for entry in manifest.get('mods', []):
        if not entry.get('auto_update'):
            continue
        mod_id = entry.get('mod_id')
        file_id = entry.get('file_id')
        if not mod_id or not file_id:
            continue

        files = cache.get(mod_id)
        if files is None:
            resp, error = curseforge.get_mod_files(
                api_key,
                mod_id,
                params={'pageSize': 50, 'index': 0},
            )
            if error:
                continue
            files = resp.get('data') or []
            cache[mod_id] = files

        latest_file = _select_best_file(files, server_version)
        if not latest_file:
            continue
        latest_id = latest_file.get('id')
        if not latest_id or int(latest_id) == int(file_id):
            continue

        file_name = _sanitize_filename(latest_file.get('fileName'), f"{mod_id}-{latest_id}.jar")
        destination = os.path.join(mods_dir, file_name)
        if not os.path.exists(destination):
            download_url = latest_file.get('downloadUrl')
            if not download_url:
                download_resp, error = curseforge.get_download_url(api_key, mod_id, latest_id)
                if error:
                    fallback_url = _build_forgecdn_url(latest_id, latest_file.get('fileName'))
                    download_url = fallback_url
                else:
                    download_data = download_resp.get('data') if download_resp else None
                    if isinstance(download_data, str):
                        download_url = download_data
                    elif isinstance(download_data, dict):
                        download_url = download_data.get('downloadUrl') or download_data.get('url')
                    if not download_url:
                        download_url = _build_forgecdn_url(latest_id, latest_file.get('fileName'))
            if not download_url:
                continue
            curseforge.download_file(download_url, destination)

        old_name = entry.get('file_name')
        if old_name and old_name != file_name:
            old_path = os.path.join(mods_dir, _sanitize_filename(old_name, old_name))
            if os.path.exists(old_path):
                os.remove(old_path)

        old_file_id = entry.get('file_id')
        old_file_name = entry.get('file_name')
        entry['file_id'] = latest_id
        entry['file_name'] = file_name
        entry['file_length'] = latest_file.get('fileLength')
        entry['installed_at'] = _iso_now()
        entry['updated_at'] = _iso_now()
        entry['restart_required'] = True
        updated.append({
            'name': entry.get('name') or file_name,
            'mod_id': mod_id,
            'from_file_id': old_file_id,
            'to_file_id': latest_id,
            'from_file_name': old_file_name,
            'to_file_name': file_name,
        })

    return updated


def _clear_restart_required(server_id):
    manifest = _load_mod_manifest(server_id)
    changed = False
    for entry in manifest.get('mods', []):
        if entry.get('restart_required'):
            entry['restart_required'] = False
            changed = True
    if changed:
        _save_mod_manifest(server_id, manifest)


def apply_auto_updates_for_server(server_id):
    api_key, _, error = _get_curseforge_config()
    if error:
        return [], error

    manifest = _load_mod_manifest(server_id)
    server_version = server_manager.get_server_version(server_id)
    updated_mods = _apply_auto_updates(server_id, manifest, api_key, server_version)
    if updated_mods:
        _save_mod_manifest(server_id, manifest)
    return updated_mods, None


# ---------------------------------------------------------------------------
# Page views
# ---------------------------------------------------------------------------

@mods_bp.route('/server/<int:server_id>/mods')
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


@mods_bp.route('/server/<int:server_id>/mods/installed')
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


# ---------------------------------------------------------------------------
# API routes
# ---------------------------------------------------------------------------

@mods_bp.route('/api/server/<int:server_id>/mods/search')
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


@mods_bp.route('/api/server/<int:server_id>/mods/<int:mod_id>/files')
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


@mods_bp.route('/api/server/<int:server_id>/mods/install', methods=['POST'])
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
    auto_update = bool(payload.get('auto_update', False))
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
            auto_update=auto_update,
        )
    except Exception as exc:
        error_text = str(exc)
        _log_mod_install_error(server_id, mod_id, file_id, error_text)
        traceback_text = traceback.format_exc()
        _log_mod_install_error(server_id, mod_id, file_id, traceback_text.strip())
        logger.error(f"Error installing mod {mod_id} file {file_id} on server {server_id}: {error_text}", exc_info=True)
        return jsonify({'success': False, 'error': error_text}), 500

    _save_mod_manifest(server_id, manifest)
    return jsonify({'success': True})


@mods_bp.route('/api/server/<int:server_id>/mods/upload', methods=['POST'])
@login_required
@require_permission('manage_configs')
def upload_mod(server_id):
    server = Server.get_by_id(server_id)
    if not server:
        return jsonify({'success': False, 'error': 'Server not found'}), 404
    if not _has_server_access(server_id):
        return jsonify({'success': False, 'error': 'Forbidden'}), 403

    if 'file' not in request.files:
        return jsonify({'success': False, 'error': 'No file provided'}), 400
    upload = request.files['file']
    filename = _normalize_mod_filename(upload.filename)
    if not filename:
        return jsonify({'success': False, 'error': 'Invalid filename'}), 400
    if not _is_allowed_mod_filename(filename):
        return jsonify({'success': False, 'error': 'Only .jar or .zip files are allowed'}), 400

    mods_dir = _get_mods_dir(server_id)
    os.makedirs(mods_dir, exist_ok=True)
    destination = os.path.join(mods_dir, filename)
    if os.path.exists(destination):
        return jsonify({'success': False, 'error': 'A file with this name already exists'}), 409

    try:
        upload.save(destination)
    except (IOError, OSError) as exc:
        logger.error(f"Error uploading mod for server {server_id}: {exc}", exc_info=True)
        return jsonify({'success': False, 'error': 'Upload failed'}), 500

    return jsonify({'success': True, 'file_name': filename})


@mods_bp.route('/api/server/<int:server_id>/mods/replace', methods=['POST'])
@login_required
@require_permission('manage_configs')
def replace_mod(server_id):
    server = Server.get_by_id(server_id)
    if not server:
        return jsonify({'success': False, 'error': 'Server not found'}), 404
    if not _has_server_access(server_id):
        return jsonify({'success': False, 'error': 'Forbidden'}), 403

    old_file = _normalize_mod_filename(request.form.get('old_file', ''))
    if not old_file or not _is_allowed_mod_filename(old_file):
        return jsonify({'success': False, 'error': 'Invalid original file'}), 400
    if 'file' not in request.files:
        return jsonify({'success': False, 'error': 'No file provided'}), 400

    upload = request.files['file']
    new_file = _normalize_mod_filename(upload.filename)
    if not new_file:
        return jsonify({'success': False, 'error': 'Invalid filename'}), 400
    if not _is_allowed_mod_filename(new_file):
        return jsonify({'success': False, 'error': 'Only .jar or .zip files are allowed'}), 400

    mods_dir = _get_mods_dir(server_id)
    os.makedirs(mods_dir, exist_ok=True)
    old_path = os.path.join(mods_dir, old_file)
    if not os.path.exists(old_path):
        return jsonify({'success': False, 'error': 'Original file not found'}), 404

    manifest = _load_mod_manifest(server_id)
    manifest_entry = None
    for entry in manifest.get('mods', []):
        if entry.get('file_name') == old_file:
            manifest_entry = entry
            break
    if manifest_entry and manifest_entry.get('mod_id'):
        return jsonify({'success': False, 'error': 'Use CurseForge update for this mod'}), 400

    destination = os.path.join(mods_dir, new_file)
    if os.path.exists(destination) and destination != old_path:
        return jsonify({'success': False, 'error': 'A file with the new name already exists'}), 409

    try:
        upload.save(destination)
        if old_path != destination and os.path.exists(old_path):
            os.remove(old_path)
    except (IOError, OSError) as exc:
        logger.error(f"Error replacing mod for server {server_id}: {exc}", exc_info=True)
        return jsonify({'success': False, 'error': 'Update failed'}), 500

    if manifest_entry and not manifest_entry.get('mod_id'):
        manifest_entry['file_name'] = new_file
        manifest_entry['file_length'] = os.path.getsize(destination)
        manifest_entry['installed_at'] = _iso_now()
        manifest_entry['updated_at'] = _iso_now()
        manifest_entry['restart_required'] = True
        _save_mod_manifest(server_id, manifest)

    return jsonify({'success': True, 'file_name': new_file})


@mods_bp.route('/api/server/<int:server_id>/mods/installed')
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
    updated_mods = []
    update_error = None

    if request.args.get('check_updates'):
        api_key, _, error = _get_curseforge_config()
        if error:
            update_error = error
        else:
            try:
                updated_mods, update_error = apply_auto_updates_for_server(server_id)
            except Exception as exc:
                update_error = str(exc)
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
            entry.setdefault('auto_update', False)
            entry.setdefault('restart_required', False)
            entry.setdefault('local', not entry.get('mod_id'))
            entry['file_length'] = os.path.getsize(file_path)
            entry.setdefault('installed_at', datetime.datetime.utcfromtimestamp(
                os.path.getmtime(file_path)
            ).replace(microsecond=0).isoformat() + 'Z')
            results.append(entry)

    return jsonify({
        'success': True,
        'mods': results,
        'updated_mods': updated_mods,
        'update_error': update_error,
    })


@mods_bp.route('/api/server/<int:server_id>/mods/auto-update', methods=['POST'])
@login_required
@require_permission('manage_configs')
def set_mod_auto_update(server_id):
    server = Server.get_by_id(server_id)
    if not server:
        return jsonify({'success': False, 'error': 'Server not found'}), 404
    if not _has_server_access(server_id):
        return jsonify({'success': False, 'error': 'Forbidden'}), 403

    payload = request.get_json(silent=True) or {}
    file_name = payload.get('file_name')
    auto_update = bool(payload.get('auto_update', False))
    if not file_name:
        return jsonify({'success': False, 'error': 'Missing file name'}), 400

    manifest = _load_mod_manifest(server_id)
    updated = False
    for entry in manifest.get('mods', []):
        if entry.get('file_name') == file_name:
            if not entry.get('mod_id'):
                return jsonify({'success': False, 'error': 'Auto-update requires a CurseForge-installed mod'}), 400
            entry['auto_update'] = auto_update
            updated = True
            break

    if not updated:
        return jsonify({'success': False, 'error': 'Mod not found in manifest'}), 404

    _save_mod_manifest(server_id, manifest)
    return jsonify({'success': True})


@mods_bp.route('/api/server/<int:server_id>/mods/uninstall', methods=['POST'])
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


@mods_bp.route('/api/server/<int:server_id>/mods/check-updates', methods=['POST'])
@login_required
@require_permission('manage_configs')
def check_mod_updates(server_id):
    server = Server.get_by_id(server_id)
    if not server:
        return jsonify({'success': False, 'error': 'Server not found'}), 404
    if not _has_server_access(server_id):
        return jsonify({'success': False, 'error': 'Forbidden'}), 403

    try:
        updated_mods, error = apply_auto_updates_for_server(server_id)
        if error:
            return jsonify({'success': False, 'error': error}), 400
        return jsonify({'success': True, 'updated_mods': updated_mods, 'updated_count': len(updated_mods)})
    except Exception as exc:
        return jsonify({'success': False, 'error': str(exc)}), 500
