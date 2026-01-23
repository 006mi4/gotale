"""
Background WebSocket bridge from GoTaleManager to Flask-SocketIO.
"""

import json
import threading
import time
import urllib.request
from urllib.parse import urlencode, urlparse

try:
    from websocket import WebSocketApp
except Exception:  # pragma: no cover - handled at runtime
    WebSocketApp = None

from utils import server_webhooks
from utils import gotale_events


_lock = threading.Lock()
_threads = {}
_stop_flags = {}
_status = {}


def _send_webhook(url, content):
    if not url:
        return False
    payload = json.dumps({'content': content}).encode('utf-8')
    req = urllib.request.Request(
        url,
        data=payload,
        headers={'Content-Type': 'application/json'},
        method='POST'
    )
    try:
        with urllib.request.urlopen(req, timeout=6):
            return True
    except Exception:
        return False


def _dispatch_webhook(db_path, server_id, payload):
    event_type = payload.get('type')
    if not event_type:
        return
    webhooks = server_webhooks.get_webhooks(db_path, server_id)
    entry = webhooks.get(event_type)
    if not entry or not entry.get('enabled') or not entry.get('url'):
        return
    message = server_webhooks.render_message(event_type, payload, entry.get('template'))
    if not message:
        return
    _send_webhook(entry['url'], message)


def _bridge_loop(server_id, settings, socketio, db_path, stop_event):
    if WebSocketApp is None:
        print('websocket-client not installed; GoTale bridge disabled.')
        return

    host = settings.get('host', '127.0.0.1')
    port = settings.get('port', 50000)
    ws_scheme = settings.get('ws_scheme')
    ws_host = settings.get('ws_host') or host
    ws_port = settings.get('ws_port') or port
    ws_path = settings.get('ws_path') or '/ws'
    if not ws_path.startswith('/'):
        ws_path = f'/{ws_path}'

    ws_url = settings.get('ws_url')
    if not ws_scheme:
        if ws_url:
            parsed = urlparse(ws_url)
            if parsed.scheme in ('ws', 'wss'):
                ws_scheme = parsed.scheme
        if not ws_scheme:
            ws_scheme = 'wss' if settings.get('auth_enabled') else 'ws'

    ws_auth_token = settings.get('auth_token') if settings.get('auth_enabled') else None
    ws_auth_query = settings.get('auth_query_param')

    base_ws_url = ws_url or f"{ws_scheme}://{ws_host}:{ws_port}{ws_path}"
    ws_urls = [base_ws_url]
    if ws_scheme == 'wss' and not settings.get('ws_insecure', False):
        ws_urls.append(f"ws://{ws_host}:{ws_port}{ws_path}")

    def _with_query(url):
        if ws_auth_token and ws_auth_query and ws_auth_query not in url:
            separator = '&' if '?' in url else '?'
            return f"{url}{separator}{urlencode({ws_auth_query: ws_auth_token})}"
        return url
    room = f'gotale_{server_id}'
    _status[server_id] = False

    while not stop_event.is_set():
        ping_stop = threading.Event()

        def _set_status(connected):
            _status[server_id] = connected
            socketio.emit('gotale_status', {
                'server_id': server_id,
                'connected': connected
            }, room=room)

        opened = False

        def on_open(ws):
            print(f"[GoTaleBridge] Connected to {ws_url} for server {server_id}")
            nonlocal opened
            opened = True
            _set_status(True)
            ping_stop.clear()

            def _ping_loop():
                while not ping_stop.wait(25):
                    try:
                        ws.send(json.dumps({'type': 'ping'}))
                    except Exception:
                        break

            threading.Thread(target=_ping_loop, daemon=True).start()

        def on_message(ws, message):
            try:
                payload = json.loads(message)
            except Exception:
                return
            if not isinstance(payload, dict) or 'type' not in payload:
                return
            gotale_events.store_event(db_path, server_id, payload)
            socketio.emit('gotale_event', {
                'server_id': server_id,
                'event': payload
            }, room=room)
            _dispatch_webhook(db_path, server_id, payload)

        def on_close(ws, *_):
            print(f"[GoTaleBridge] Disconnected from {ws_url} for server {server_id}")
            ping_stop.set()
            _set_status(False)

        def on_error(ws, *_):
            print(f"[GoTaleBridge] Error connecting to {ws_url} for server {server_id}")
            ping_stop.set()
            _set_status(False)

        headers = []
        if ws_auth_token and not ws_auth_query:
            headers.append(f"Authorization: Bearer {ws_auth_token}")

        for candidate in ws_urls:
            candidate_url = _with_query(candidate)
            try:
                ws_url = candidate_url
                opened = False
                ws = WebSocketApp(
                    candidate_url,
                    header=headers or None,
                    on_open=on_open,
                    on_message=on_message,
                    on_close=on_close,
                    on_error=on_error
                )
                ws.run_forever()
                if opened:
                    break
            except Exception:
                _set_status(False)
                continue

        if stop_event.wait(5):
            break


def ensure_bridge(server_id, settings, socketio, db_path):
    if not settings or not settings.get('enabled'):
        _status[server_id] = False
        return
    with _lock:
        thread = _threads.get(server_id)
        if thread and thread.is_alive():
            return
        stop_event = threading.Event()
        _stop_flags[server_id] = stop_event
        thread = threading.Thread(
            target=_bridge_loop,
            args=(server_id, settings, socketio, db_path, stop_event),
            daemon=True
        )
        _threads[server_id] = thread
        thread.start()


def get_status(server_id):
    return bool(_status.get(server_id))
