"""
Helpers for loading GoTaleManager plugin configuration per server.
"""

import json
import os
import socket
from urllib.parse import urlparse

from utils import server_manager


DEFAULT_API_PORT = 50000
DEFAULT_QUERY_PORT = 27010
DEFAULT_CONFIG = {
    'api': {
        'enabled': True,
        'host': 'localhost',
        'port': DEFAULT_API_PORT,
        'authEnabled': False,
        'authToken': '',
        'corsEnabled': True,
        'corsOrigin': '*',
        'wsHeartbeatSeconds': 30,
        'logRequests': False
    },
    'query': {
        'enabled': True,
        'port': DEFAULT_QUERY_PORT
    }
}


def get_gotale_config_path(server_id):
    base_path = server_manager.get_server_path(server_id)
    return os.path.join(base_path, 'config', 'gotale-manager', 'config.json')


def read_gotale_config(server_id):
    path = get_gotale_config_path(server_id)
    if not os.path.exists(path):
        return None
    try:
        with open(path, 'r', encoding='utf-8') as handle:
            return json.load(handle)
    except Exception as exc:
        print(f"Error reading GoTaleManager config for server {server_id}: {exc}")
        return None


def write_gotale_config(server_id, config):
    path = get_gotale_config_path(server_id)
    try:
        os.makedirs(os.path.dirname(path), exist_ok=True)
        with open(path, 'w', encoding='utf-8') as handle:
            json.dump(config, handle, indent=2, ensure_ascii=True)
            handle.write('\n')
        return True
    except Exception as exc:
        print(f"Error writing GoTaleManager config for server {server_id}: {exc}")
        return False


def _iter_server_ids():
    base_path = os.path.dirname(server_manager.get_server_path(0))
    if not os.path.isdir(base_path):
        return []
    server_ids = []
    for entry in os.listdir(base_path):
        if not entry.startswith('server_'):
            continue
        suffix = entry[7:]
        if not suffix.isdigit():
            continue
        server_ids.append(int(suffix))
    return server_ids


def _collect_used_ports(exclude_server_id=None):
    api_ports = set()
    query_ports = set()
    for server_id in _iter_server_ids():
        if exclude_server_id is not None and server_id == exclude_server_id:
            continue
        config = read_gotale_config(server_id)
        if not isinstance(config, dict):
            continue
        api = config.get('api') or {}
        query = config.get('query') or {}
        try:
            api_ports.add(int(api.get('port', DEFAULT_API_PORT)))
        except (TypeError, ValueError):
            pass
        try:
            query_ports.add(int(query.get('port', DEFAULT_QUERY_PORT)))
        except (TypeError, ValueError):
            pass
    return api_ports, query_ports


def _is_tcp_port_available(port, host='0.0.0.0'):
    sock = None
    try:
        sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        sock.bind((host, port))
        sock.listen(1)
        sock.close()
        return True
    except OSError:
        return False
    except Exception:
        return False
    finally:
        try:
            sock.close()
        except Exception:
            pass


def _pick_next_port(start_port, used_ports, availability_check, max_attempts=2000):
    port = max(int(start_port), 1)
    attempts = 0
    while attempts < max_attempts:
        if port not in used_ports and availability_check(port):
            return port
        port += 1
        attempts += 1
    return None


def ensure_gotale_config(server_id, create_if_missing=True):
    config = read_gotale_config(server_id)
    created = False
    if not isinstance(config, dict):
        if not create_if_missing:
            return None, False, False
        config = json.loads(json.dumps(DEFAULT_CONFIG))
        created = True

    api = config.get('api') if isinstance(config.get('api'), dict) else {}
    query = config.get('query') if isinstance(config.get('query'), dict) else {}
    config['api'] = api
    config['query'] = query

    api.setdefault('enabled', True)
    api.setdefault('host', 'localhost')
    api.setdefault('port', DEFAULT_API_PORT)
    api.setdefault('authEnabled', False)
    api.setdefault('authToken', '')
    api.setdefault('corsEnabled', True)
    api.setdefault('corsOrigin', '*')
    api.setdefault('wsHeartbeatSeconds', 30)
    api.setdefault('logRequests', False)

    query.setdefault('enabled', True)
    query.setdefault('port', DEFAULT_QUERY_PORT)

    changed = created
    used_api_ports, used_query_ports = _collect_used_ports(exclude_server_id=server_id)

    try:
        api_port = int(api.get('port', DEFAULT_API_PORT))
    except (TypeError, ValueError):
        api_port = DEFAULT_API_PORT

    if api_port in used_api_ports or not _is_tcp_port_available(api_port):
        next_port = _pick_next_port(api_port + 1, used_api_ports, _is_tcp_port_available)
        if next_port is not None:
            api['port'] = next_port
            changed = True

    try:
        query_port = int(query.get('port', DEFAULT_QUERY_PORT))
    except (TypeError, ValueError):
        query_port = DEFAULT_QUERY_PORT

    if bool(query.get('enabled', True)):
        from utils import port_checker
        if query_port in used_query_ports or not port_checker.is_port_available(query_port):
            next_query = _pick_next_port(
                query_port + 1,
                used_query_ports,
                port_checker.is_port_available
            )
            if next_query is not None:
                query['port'] = next_query
                changed = True

    if changed:
        write_gotale_config(server_id, config)

    return config, changed, created


def get_gotale_api_settings(server_id):
    config = read_gotale_config(server_id)
    if not isinstance(config, dict):
        return None
    api = config.get('api') or {}
    if not isinstance(api, dict):
        api = {}
    host = str(api.get('host', 'localhost')).strip() or 'localhost'
    scheme = None
    ws_path = None
    if '://' in host:
        parsed = urlparse(host)
        if parsed.scheme in ('ws', 'wss', 'http', 'https'):
            scheme = 'wss' if parsed.scheme in ('wss', 'https') else 'ws'
        if parsed.hostname:
            host = parsed.hostname
        if parsed.path and parsed.path != '/':
            ws_path = parsed.path
    if host == '0.0.0.0':
        host = '127.0.0.1'

    def _pick_first(keys, default=None):
        for key in keys:
            if key in api and api[key] not in (None, ''):
                return api[key]
        return default

    ws_scheme = _pick_first(['wsScheme', 'ws_scheme'], None)
    ws_path = _pick_first(['wsPath', 'ws_path'], ws_path)
    ws_url = _pick_first(['wsUrl', 'ws_url'], None)
    ws_host = _pick_first(['wsHost', 'ws_host'], None)
    ws_port = _pick_first(['wsPort', 'ws_port'], None)
    ws_insecure = bool(_pick_first(['wsInsecure', 'ws_insecure'], False))
    auth_query = _pick_first(['authQueryParam', 'auth_query_param'], None)

    return {
        'enabled': bool(api.get('enabled', True)),
        'host': host,
        'port': int(api.get('port', DEFAULT_API_PORT)),
        'auth_enabled': bool(api.get('authEnabled', False)),
        'auth_token': str(api.get('authToken', '')).strip(),
        'ws_scheme': ws_scheme or scheme,
        'ws_path': ws_path,
        'ws_url': ws_url,
        'ws_host': ws_host,
        'ws_port': int(ws_port) if ws_port is not None else None,
        'ws_insecure': ws_insecure,
        'auth_query_param': auth_query,
    }
