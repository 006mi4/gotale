"""
Background WebSocket bridge from GoTaleManager to Flask-SocketIO.
"""

import json
import threading
import time
import queue
import urllib.request
import urllib.error
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
_webhook_queues = {}
_webhook_workers = {}
_webhook_settings_cache = {}
_webhook_diagnostics = {}
_WEBHOOK_QUEUE_MAXSIZE = 1000
_WEBHOOK_SETTINGS_TTL_SECONDS = 15


def _trim_webhook_message(content, max_length=1900):
    if content is None:
        return None
    text = str(content)
    if len(text) <= max_length:
        return text
    return f"{text[:max_length - 3]}..."


def _get_webhook_diag(server_id):
    diag = _webhook_diagnostics.get(server_id)
    if diag is not None:
        return diag
    diag = {
        'sent_total': 0,
        'failed_total': 0,
        'dropped_total': 0,
        'enqueued_total': 0,
        'rate_limited_total': 0,
        'last_success_at': None,
        'last_failure_at': None,
        'last_error': '',
        'last_error_code': None,
        'last_event_type': '',
        'last_success_event_type': '',
        'last_failure_event_type': '',
        'updated_at': time.time(),
    }
    _webhook_diagnostics[server_id] = diag
    return diag


def _note_webhook_enqueued(server_id, event_type):
    diag = _get_webhook_diag(server_id)
    diag['enqueued_total'] += 1
    diag['last_event_type'] = event_type or ''
    diag['updated_at'] = time.time()


def _note_webhook_dropped(server_id, event_type):
    diag = _get_webhook_diag(server_id)
    diag['dropped_total'] += 1
    diag['last_event_type'] = event_type or ''
    diag['updated_at'] = time.time()


def _note_webhook_success(server_id, event_type):
    diag = _get_webhook_diag(server_id)
    now = time.time()
    diag['sent_total'] += 1
    diag['last_success_at'] = now
    diag['last_success_event_type'] = event_type or ''
    diag['last_event_type'] = event_type or ''
    diag['updated_at'] = now


def _note_webhook_failure(server_id, event_type, error_message='', error_code=None, rate_limited=False):
    diag = _get_webhook_diag(server_id)
    now = time.time()
    diag['failed_total'] += 1
    if rate_limited:
        diag['rate_limited_total'] += 1
    diag['last_failure_at'] = now
    diag['last_failure_event_type'] = event_type or ''
    diag['last_event_type'] = event_type or ''
    diag['last_error'] = str(error_message or '')
    diag['last_error_code'] = error_code
    diag['updated_at'] = now


def _send_webhook(url, content, server_id=None, event_type=None):
    if not url:
        return False
    content = _trim_webhook_message(content)
    if not content:
        return False

    max_attempts = 4
    for attempt in range(1, max_attempts + 1):
        payload = json.dumps({'content': content}).encode('utf-8')
        req = urllib.request.Request(
            url,
            data=payload,
            headers={'Content-Type': 'application/json'},
            method='POST'
        )
        try:
            with urllib.request.urlopen(req, timeout=8):
                if server_id is not None:
                    _note_webhook_success(server_id, event_type)
                return True
        except urllib.error.HTTPError as exc:
            retry_after = 0.0
            response_body = ''
            try:
                response_body = (exc.read() or b'').decode('utf-8', errors='ignore')
            except Exception:
                response_body = ''

            if exc.code == 429:
                header_retry = exc.headers.get('Retry-After') if exc.headers else None
                if header_retry:
                    try:
                        retry_after = float(header_retry)
                    except Exception:
                        retry_after = 0.0
                if not retry_after and response_body:
                    try:
                        retry_after = float((json.loads(response_body) or {}).get('retry_after', 0))
                    except Exception:
                        retry_after = 0.0
                if attempt < max_attempts:
                    time.sleep(min(max(retry_after, 1.0), 30.0))
                    continue
            elif 500 <= exc.code < 600 and attempt < max_attempts:
                time.sleep(float(attempt))
                continue

            print(f"[GoTaleBridge] Discord webhook HTTP {exc.code} (attempt {attempt}): {response_body[:200]}")
            if server_id is not None:
                _note_webhook_failure(
                    server_id,
                    event_type,
                    error_message=response_body[:200] or f'HTTP {exc.code}',
                    error_code=exc.code,
                    rate_limited=(exc.code == 429)
                )
            return False
        except Exception as exc:
            if attempt < max_attempts:
                time.sleep(float(attempt))
                continue
            print(f"[GoTaleBridge] Discord webhook request failed after retries: {exc}")
            if server_id is not None:
                _note_webhook_failure(server_id, event_type, error_message=str(exc))
            return False
    return False


def _get_cached_webhooks(db_path, server_id):
    now = time.time()
    cached = _webhook_settings_cache.get(server_id)
    if cached and (now - cached.get('loaded_at', 0)) < _WEBHOOK_SETTINGS_TTL_SECONDS:
        return cached.get('data', {})
    try:
        data = server_webhooks.get_webhooks(db_path, server_id) or {}
    except Exception as exc:
        print(f"[GoTaleBridge] Failed reading webhook settings for server {server_id}: {exc}")
        if cached:
            return cached.get('data', {})
        return {}
    _webhook_settings_cache[server_id] = {'loaded_at': now, 'data': data}
    return data


def _ensure_webhook_worker(server_id, stop_event):
    worker = _webhook_workers.get(server_id)
    if worker and worker.is_alive():
        return
    task_queue = _webhook_queues.get(server_id)
    if task_queue is None:
        task_queue = queue.Queue(maxsize=_WEBHOOK_QUEUE_MAXSIZE)
        _webhook_queues[server_id] = task_queue

    def _worker_loop():
        while not stop_event.is_set():
            try:
                url, message, event_type = task_queue.get(timeout=1.0)
            except queue.Empty:
                continue
            try:
                _send_webhook(url, message, server_id=server_id, event_type=event_type)
            finally:
                task_queue.task_done()

    worker = threading.Thread(target=_worker_loop, daemon=True)
    _webhook_workers[server_id] = worker
    worker.start()


def _dispatch_webhook(db_path, server_id, payload, stop_event):
    event_type = payload.get('type')
    if not event_type:
        return
    webhooks = _get_cached_webhooks(db_path, server_id)
    entry = webhooks.get(event_type)
    if not entry or not entry.get('enabled') or not entry.get('url'):
        return
    message = server_webhooks.render_message(event_type, payload, entry.get('template'))
    if not message:
        return
    _ensure_webhook_worker(server_id, stop_event)
    task_queue = _webhook_queues.get(server_id)
    if not task_queue:
        return
    try:
        task_queue.put_nowait((entry['url'], message, event_type))
        _note_webhook_enqueued(server_id, event_type)
    except queue.Full:
        _note_webhook_dropped(server_id, event_type)
        try:
            task_queue.get_nowait()
            task_queue.task_done()
        except Exception:
            pass
        try:
            task_queue.put_nowait((entry['url'], message, event_type))
            _note_webhook_enqueued(server_id, event_type)
        except Exception:
            print(f"[GoTaleBridge] Webhook queue full for server {server_id}; dropping event {event_type}.")


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
        _ensure_webhook_worker(server_id, stop_event)

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
            try:
                _dispatch_webhook(db_path, server_id, payload, stop_event)
            except Exception as exc:
                print(f"[GoTaleBridge] Webhook dispatch error for server {server_id}: {exc}")

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


def get_webhook_diagnostics(server_id):
    diag = dict(_get_webhook_diag(server_id))
    task_queue = _webhook_queues.get(server_id)
    worker = _webhook_workers.get(server_id)
    cache_state = _webhook_settings_cache.get(server_id) or {}
    loaded_at = cache_state.get('loaded_at')

    queue_size = 0
    if task_queue is not None:
        try:
            queue_size = task_queue.qsize()
        except Exception:
            queue_size = 0

    diag.update({
        'connected': bool(_status.get(server_id)),
        'queue_size': queue_size,
        'queue_maxsize': _WEBHOOK_QUEUE_MAXSIZE,
        'worker_alive': bool(worker and worker.is_alive()),
        'settings_cache_age_seconds': (time.time() - loaded_at) if loaded_at else None,
    })
    return diag
