"""
Background WebSocket bridge from GoTaleManager to Flask-SocketIO.
"""

import json
import threading
import time
import urllib.request

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
    ws_url = f"ws://{host}:{port}/ws"
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

        def on_open(ws):
            print(f"[GoTaleBridge] Connected to {ws_url} for server {server_id}")
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

        ws = WebSocketApp(
            ws_url,
            on_open=on_open,
            on_message=on_message,
            on_close=on_close,
            on_error=on_error
        )

        try:
            ws.run_forever()
        except Exception:
            _set_status(False)

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
