"""
GoTale integration routes - players, stats, chat, avatars, webhooks dispatch
"""

from flask import Blueprint, render_template, request, jsonify, current_app
from flask_login import login_required, current_user
import logging
import os
import time
import hashlib
import urllib.parse
import urllib.request
import urllib.error
import json

logger = logging.getLogger(__name__)

from models.server import Server
from utils import server_manager
from utils import server_webhooks
from utils import gotale_config
from utils import gotale_events
from utils import gotale_bridge
from utils.authz import require_permission

from routes.server_routes import (
    _get_server_or_404,
    _has_server_access,
    _get_host_os,
    _read_json_file,
)

gotale_bp = Blueprint('gotale', __name__)

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

GOTALE_API_KEY = 'hytale_2dc66172317b4c999a47e87ceb3ebb65'
_GOTALE_AVATAR_KEY_PARTS = (
    'gtl_b4ff476e88d3ed2f',
    'c27865bda9e2b456',
    'b16b9896',
)
GOTALE_AVATAR_API_KEY = ''.join(_GOTALE_AVATAR_KEY_PARTS)
AVATAR_CACHE_TTL_SECONDS = 24 * 60 * 60


# ---------------------------------------------------------------------------
# Helper functions
# ---------------------------------------------------------------------------

def _get_player_file_map(server_id):
    base_path = server_manager.get_server_data_dir(server_id)
    players_dir = os.path.join(base_path, 'universe', 'players')
    file_map = {}
    if os.path.isdir(players_dir):
        for filename in sorted(os.listdir(players_dir)):
            if filename.endswith('.json'):
                file_map[filename] = os.path.join(players_dir, filename)
    return file_map


def _get_avatar_cache_dir():
    cache_dir = os.path.join(current_app.root_path, 'cache', 'avatars')
    os.makedirs(cache_dir, exist_ok=True)
    return cache_dir


def _get_avatar_cache_paths(avatar_id):
    cache_key = hashlib.sha256(avatar_id.encode('utf-8')).hexdigest()
    cache_dir = _get_avatar_cache_dir()
    image_path = os.path.join(cache_dir, f'{cache_key}.img')
    type_path = os.path.join(cache_dir, f'{cache_key}.type')
    return image_path, type_path


def _read_avatar_cache(avatar_id, allow_stale=False):
    image_path, type_path = _get_avatar_cache_paths(avatar_id)
    if not os.path.isfile(image_path):
        return None
    try:
        age_seconds = time.time() - os.path.getmtime(image_path)
        if not allow_stale and age_seconds > AVATAR_CACHE_TTL_SECONDS:
            return None
        with open(image_path, 'rb') as file:
            payload = file.read()
        content_type = 'image/png'
        if os.path.isfile(type_path):
            with open(type_path, 'r', encoding='utf-8') as file:
                cached_type = file.read().strip()
                if cached_type:
                    content_type = cached_type
        return payload, content_type
    except (IOError, OSError) as e:
        logger.error(f"Error reading avatar cache for {avatar_id}: {e}", exc_info=True)
        return None


def _write_avatar_cache(avatar_id, payload, content_type):
    image_path, type_path = _get_avatar_cache_paths(avatar_id)
    try:
        with open(image_path, 'wb') as file:
            file.write(payload)
        with open(type_path, 'w', encoding='utf-8') as file:
            file.write((content_type or 'image/png').strip() or 'image/png')
    except (IOError, OSError) as e:
        logger.error(f"Error writing avatar cache for {avatar_id}: {e}", exc_info=True)


def _get_gotale_online_players_count(server_id):
    settings = gotale_config.get_gotale_api_settings(server_id)
    if not settings or not settings.get('enabled'):
        return None

    host = settings.get('host')
    port = settings.get('port')
    if not host or not port:
        return None

    url = f"http://{host}:{port}/api/players"
    headers = {'Accept': 'application/json'}
    if settings.get('auth_enabled') and settings.get('auth_token'):
        headers['Authorization'] = f"Bearer {settings['auth_token']}"

    req = urllib.request.Request(url, headers=headers, method='GET')
    try:
        with urllib.request.urlopen(req, timeout=4) as response:
            payload = response.read()
        data = json.loads(payload.decode('utf-8'))
        players = data.get('players')
        if isinstance(players, list):
            return len(players)
    except (urllib.error.URLError, json.JSONDecodeError, OSError) as exc:
        logger.debug(f"GoTale online player count failed for server {server_id}: {exc}")
    return None


# ---------------------------------------------------------------------------
# Page views
# ---------------------------------------------------------------------------

@gotale_bp.route('/server/<int:server_id>/players')
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


@gotale_bp.route('/server/<int:server_id>/stats')
@login_required
@require_permission('view_servers')
def stats_view(server_id):
    server = _get_server_or_404(server_id)
    if not server:
        return render_template('404.html'), 404
    if not _has_server_access(server_id):
        return render_template('403.html'), 403

    return render_template(
        'server_stats.html',
        server=server,
        user=current_user,
        host_os=_get_host_os(),
        active_page='stats',
        nav_mode='server',
        nav_server={'id': server.id, 'name': server.name, 'status': server.status},
    )


@gotale_bp.route('/server/<int:server_id>/chat')
@login_required
@require_permission('view_servers')
def chat_view(server_id):
    server = _get_server_or_404(server_id)
    if not server:
        return render_template('404.html'), 404
    if not _has_server_access(server_id):
        return render_template('403.html'), 403

    return render_template(
        'server_chat.html',
        server=server,
        user=current_user,
        host_os=_get_host_os(),
        active_page='chat',
        nav_mode='server',
        nav_server={'id': server.id, 'name': server.name, 'status': server.status},
    )


# ---------------------------------------------------------------------------
# API routes
# ---------------------------------------------------------------------------

@gotale_bp.route('/api/items/<item_id>')
@login_required
@require_permission('manage_configs')
def get_item_metadata(item_id):
    try:
        encoded_item = urllib.parse.quote(item_id)
        url = f'https://api.gotale.net/api/items/{encoded_item}?api_key={GOTALE_API_KEY}'
        with urllib.request.urlopen(url) as response:
            payload = response.read()
        data = json.loads(payload.decode('utf-8'))
        return jsonify(data)
    except (urllib.error.URLError, json.JSONDecodeError, OSError) as e:
        logger.error(f"Error fetching item metadata {item_id}: {e}", exc_info=True)
        return jsonify({'error': 'Failed to fetch item metadata'}), 502


@gotale_bp.route('/api/item-image/<item_id>')
@login_required
@require_permission('manage_configs')
def get_item_image(item_id):
    try:
        encoded_item = urllib.parse.quote(item_id)
        url = f'https://api.gotale.net/img/{encoded_item}.png'
        with urllib.request.urlopen(url) as response:
            payload = response.read()
        return current_app.response_class(payload, mimetype='image/png')
    except (urllib.error.URLError, OSError) as e:
        logger.error(f"Error fetching item image {item_id}: {e}", exc_info=True)
        return jsonify({'error': 'Failed to fetch item image'}), 502


@gotale_bp.route('/api/server/<int:server_id>/avatar/<path:avatar_id>')
@login_required
@require_permission('manage_configs')
def get_player_avatar(server_id, avatar_id):
    server = _get_server_or_404(server_id)
    if not server:
        return jsonify({'success': False, 'error': 'Server not found'}), 404
    if not _has_server_access(server_id):
        return jsonify({'success': False, 'error': 'Forbidden'}), 403

    avatar_id = (avatar_id or '').strip()
    if not avatar_id:
        return jsonify({'success': False, 'error': 'Missing avatar id'}), 400

    cached_avatar = _read_avatar_cache(avatar_id, allow_stale=False)
    if cached_avatar:
        payload, content_type = cached_avatar
        return current_app.response_class(payload, mimetype=content_type)

    try:
        encoded_avatar = urllib.parse.quote(avatar_id, safe='')
        url = f'https://gotale.net/api/avatar/{encoded_avatar}'
        req = urllib.request.Request(
            url,
            headers={'X-API-Key': GOTALE_AVATAR_API_KEY},
            method='GET'
        )
        with urllib.request.urlopen(req) as response:
            payload = response.read()
            content_type = response.headers.get_content_type() or 'image/png'
        _write_avatar_cache(avatar_id, payload, content_type)
        return current_app.response_class(payload, mimetype=content_type)
    except (urllib.error.URLError, OSError) as e:
        logger.error(f"Error fetching avatar {avatar_id}: {e}", exc_info=True)
        stale_avatar = _read_avatar_cache(avatar_id, allow_stale=True)
        if stale_avatar:
            payload, content_type = stale_avatar
            return current_app.response_class(payload, mimetype=content_type)
        return jsonify({'success': False, 'error': 'Failed to fetch avatar'}), 502


@gotale_bp.route('/api/server/<int:server_id>/gotale/config')
@login_required
@require_permission('view_servers')
def get_gotale_config(server_id):
    server = _get_server_or_404(server_id)
    if not server:
        return jsonify({'success': False, 'error': 'Server not found'}), 404
    if not _has_server_access(server_id):
        return jsonify({'success': False, 'error': 'Forbidden'}), 403

    settings = gotale_config.get_gotale_api_settings(server_id)
    if not settings:
        return jsonify({'success': True, 'configured': False}), 200

    return jsonify({
        'success': True,
        'configured': True,
        'enabled': settings['enabled'],
        'host': settings['host'],
        'port': settings['port'],
        'auth_enabled': settings['auth_enabled'],
    })


@gotale_bp.route('/api/server/<int:server_id>/gotale/plugin-status')
@login_required
@require_permission('view_servers')
def gotale_plugin_status(server_id):
    server = _get_server_or_404(server_id)
    if not server:
        return jsonify({'success': False, 'error': 'Server not found'}), 404
    if not _has_server_access(server_id):
        return jsonify({'success': False, 'error': 'Forbidden'}), 403

    installed = server_manager.has_gotale_plugin(server_id)
    return jsonify({'success': True, 'installed': installed})


@gotale_bp.route('/api/server/<int:server_id>/gotale/install-plugin', methods=['POST'])
@login_required
@require_permission('manage_configs')
def gotale_install_plugin(server_id):
    server = _get_server_or_404(server_id)
    if not server:
        return jsonify({'success': False, 'error': 'Server not found'}), 404
    if not _has_server_access(server_id):
        return jsonify({'success': False, 'error': 'Forbidden'}), 403

    ok, status = server_manager.ensure_gotale_plugin(server_id, force=True)
    if not ok:
        return jsonify({'success': False, 'error': status}), 500
    try:
        gotale_config.ensure_gotale_config(server_id, create_if_missing=True)
    except Exception as exc:
        logger.error(f"GoTale config update failed for server {server_id}: {exc}", exc_info=True)
    return jsonify({'success': True, 'status': status})


@gotale_bp.route('/api/server/<int:server_id>/gotale/proxy/<path:subpath>', methods=['GET', 'POST'])
@login_required
@require_permission('view_servers')
def proxy_gotale_api(server_id, subpath):
    server = _get_server_or_404(server_id)
    if not server:
        return jsonify({'success': False, 'error': 'Server not found'}), 404
    if not _has_server_access(server_id):
        return jsonify({'success': False, 'error': 'Forbidden'}), 403

    settings = gotale_config.get_gotale_api_settings(server_id)
    if not settings or not settings.get('enabled'):
        return jsonify({'success': False, 'error': 'GoTaleManager API disabled'}), 400

    host = settings['host']
    port = settings['port']
    base_url = f"http://{host}:{port}/api/{subpath}"
    if request.query_string:
        base_url = f"{base_url}?{request.query_string.decode('utf-8', errors='ignore')}"

    payload = None
    headers = {'Accept': 'application/json'}
    if settings.get('auth_enabled') and settings.get('auth_token'):
        headers['Authorization'] = f"Bearer {settings['auth_token']}"

    if request.method == 'POST':
        body = request.get_json(silent=True)
        payload = json.dumps(body or {}).encode('utf-8')
        headers['Content-Type'] = 'application/json'

    req = urllib.request.Request(base_url, data=payload, headers=headers, method=request.method)

    try:
        with urllib.request.urlopen(req, timeout=6) as response:
            data = response.read()
            content_type = response.headers.get('Content-Type', 'application/json')
            return current_app.response_class(data, status=response.status, mimetype=content_type)
    except urllib.error.HTTPError as exc:
        try:
            body = exc.read()
        except (IOError, OSError):
            body = None
        return current_app.response_class(
            body or json.dumps({'error': 'GoTaleManager error'}).encode('utf-8'),
            status=exc.code,
            mimetype='application/json'
        )
    except (urllib.error.URLError, OSError) as exc:
        logger.debug(f"GoTale proxy error for server {server_id}: {exc}")
        return jsonify({'success': False, 'error': 'GoTaleManager unreachable'}), 502


@gotale_bp.route('/api/server/<int:server_id>/gotale/webhooks', methods=['GET', 'POST'])
@login_required
@require_permission('manage_configs')
def gotale_webhooks(server_id):
    server = _get_server_or_404(server_id)
    if not server:
        return jsonify({'success': False, 'error': 'Server not found'}), 404
    if not _has_server_access(server_id):
        return jsonify({'success': False, 'error': 'Forbidden'}), 403

    db_path = current_app.config['DATABASE']
    if request.method == 'POST':
        payload = request.get_json(silent=True) or {}
        server_webhooks.set_webhooks(db_path, server_id, payload)
        return jsonify({'success': True})

    data = server_webhooks.get_webhooks(db_path, server_id)
    return jsonify({'success': True, 'webhooks': data})


@gotale_bp.route('/api/server/<int:server_id>/gotale/webhooks/diagnostics')
@login_required
@require_permission('manage_configs')
def gotale_webhook_diagnostics(server_id):
    server = _get_server_or_404(server_id)
    if not server:
        return jsonify({'success': False, 'error': 'Server not found'}), 404
    if not _has_server_access(server_id):
        return jsonify({'success': False, 'error': 'Forbidden'}), 403

    diagnostics = gotale_bridge.get_webhook_diagnostics(server_id)
    return jsonify({'success': True, 'diagnostics': diagnostics})


@gotale_bp.route('/api/server/<int:server_id>/gotale/dispatch', methods=['POST'])
@login_required
@require_permission('view_servers')
def gotale_dispatch(server_id):
    server = _get_server_or_404(server_id)
    if not server:
        return jsonify({'success': False, 'error': 'Server not found'}), 404
    if not _has_server_access(server_id):
        return jsonify({'success': False, 'error': 'Forbidden'}), 403

    payload = request.get_json(silent=True) or {}
    event_type = payload.get('type')
    data = payload.get('payload') or {}
    if not event_type:
        return jsonify({'success': False, 'error': 'Missing event type'}), 400

    db_path = current_app.config['DATABASE']
    webhooks = server_webhooks.get_webhooks(db_path, server_id)
    entry = webhooks.get(event_type)
    if not entry or not entry.get('enabled') or not entry.get('url'):
        return jsonify({'success': True, 'sent': False})

    message = server_webhooks.render_message(event_type, data, entry.get('template'))
    if not message:
        return jsonify({'success': True, 'sent': False})

    body = json.dumps({'content': message}).encode('utf-8')
    req = urllib.request.Request(
        entry['url'],
        data=body,
        headers={
            'Content-Type': 'application/json',
            'Accept': 'application/json',
            'User-Agent': 'HSM-GoTaleWebhook/1.0 (+https://gotale.net)'
        },
        method='POST'
    )
    try:
        with urllib.request.urlopen(req, timeout=6):
            return jsonify({'success': True, 'sent': True})
    except (urllib.error.URLError, OSError) as exc:
        logger.error(f"Discord webhook error for server {server_id}: {exc}", exc_info=True)
        return jsonify({'success': False, 'error': 'Webhook send failed'}), 502


@gotale_bp.route('/api/server/<int:server_id>/gotale/stats')
@login_required
@require_permission('view_servers')
def gotale_stats(server_id):
    server = _get_server_or_404(server_id)
    if not server:
        return jsonify({'success': False, 'error': 'Server not found'}), 404
    if not _has_server_access(server_id):
        return jsonify({'success': False, 'error': 'Forbidden'}), 403

    days = request.args.get('days', 7)
    db_path = current_app.config['DATABASE']
    stats = gotale_events.get_stats(db_path, server_id, days)
    player_files_total = len(_get_player_file_map(server_id))
    overview = stats.get('overview') or {}
    unique_players_seen = int(overview.get('unique_players_seen') or 0)
    total_players_ever = max(player_files_total, unique_players_seen)
    online_now = _get_gotale_online_players_count(server_id)
    stats['overview'] = {
        **overview,
        'players_with_save_files': player_files_total,
        'total_players_ever': total_players_ever,
        'online_now': online_now,
    }
    return jsonify({'success': True, **stats})


@gotale_bp.route('/api/server/<int:server_id>/gotale/chat/logs')
@login_required
@require_permission('view_servers')
def gotale_chat_logs(server_id):
    server = _get_server_or_404(server_id)
    if not server:
        return jsonify({'success': False, 'error': 'Server not found'}), 404
    if not _has_server_access(server_id):
        return jsonify({'success': False, 'error': 'Forbidden'}), 403

    limit = request.args.get('limit', 200)
    offset = request.args.get('offset', 0)
    db_path = current_app.config['DATABASE']
    messages = gotale_events.get_chat_messages(db_path, server_id, limit=limit, offset=offset)
    return jsonify({'success': True, 'messages': messages})


@gotale_bp.route('/api/server/<int:server_id>/gotale/chat/search')
@login_required
@require_permission('view_servers')
def gotale_chat_search(server_id):
    server = _get_server_or_404(server_id)
    if not server:
        return jsonify({'success': False, 'error': 'Server not found'}), 404
    if not _has_server_access(server_id):
        return jsonify({'success': False, 'error': 'Forbidden'}), 403

    query = (request.args.get('q') or '').strip()
    if not query:
        return jsonify({'success': True, 'messages': []})
    limit = request.args.get('limit', 200)
    db_path = current_app.config['DATABASE']
    messages = gotale_events.search_chat_messages(db_path, server_id, query=query, limit=limit)
    return jsonify({'success': True, 'messages': messages})
