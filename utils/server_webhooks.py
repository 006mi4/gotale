"""
Helper functions for per-server Discord webhook settings.
"""

import sqlite3


EVENT_KEYS = (
    'player_connect',
    'player_disconnect',
    'player_death',
    'player_chat',
)

DEFAULT_TEMPLATES = {
    'player_connect': '✅ Player connected: **{player}**',
    'player_disconnect': '👋 Player disconnected: **{player}**',
    'player_death': '💀 Player death: **{player}** ({cause}) in **{world}**',
    'player_chat': '💬 **{player}**: {message}',
}


def _normalize_url(value):
    if not value:
        return ''
    return str(value).strip()


def get_webhooks(db_path, server_id):
    """Return a mapping of event_key -> {url, enabled, template}."""
    conn = sqlite3.connect(db_path)
    cursor = conn.cursor()
    cursor.execute(
        'SELECT event_key, url, enabled, template FROM server_webhooks WHERE server_id = ?',
        (server_id,),
    )
    rows = cursor.fetchall()
    conn.close()

    result = {
        key: {
            'url': '',
            'enabled': False,
            'template': '',
            'default_template': DEFAULT_TEMPLATES.get(key, '')
        }
        for key in EVENT_KEYS
    }
    for event_key, url, enabled, template in rows:
        if event_key in result:
            result[event_key] = {
                'url': url or '',
                'enabled': bool(enabled),
                'template': template or '',
                'default_template': DEFAULT_TEMPLATES.get(event_key, '')
            }
    return result


def set_webhooks(db_path, server_id, payload):
    """Persist webhook settings for a server."""
    conn = sqlite3.connect(db_path)
    cursor = conn.cursor()

    for key in EVENT_KEYS:
        entry = payload.get(key) if isinstance(payload, dict) else None
        url = ''
        enabled = False
        if isinstance(entry, dict):
            url = _normalize_url(entry.get('url'))
            enabled = bool(entry.get('enabled')) and bool(url)
        elif isinstance(entry, str):
            url = _normalize_url(entry)
            enabled = bool(url)

        template = ''
        if isinstance(entry, dict):
            template = _normalize_url(entry.get('template'))
        cursor.execute(
            '''
            INSERT INTO server_webhooks (server_id, event_key, url, enabled, template)
            VALUES (?, ?, ?, ?, ?)
            ON CONFLICT(server_id, event_key)
            DO UPDATE SET url = excluded.url, enabled = excluded.enabled, template = excluded.template
            ''',
            (server_id, key, url, int(enabled), template),
        )

    conn.commit()
    conn.close()


def render_message(event_type, payload, template=None):
    if not event_type:
        return None
    data = payload or {}
    resolved = template or DEFAULT_TEMPLATES.get(event_type, '')
    if not resolved:
        return None

    replacements = {
        '{player}': str(data.get('player', 'Unknown')),
        '{uuid}': str(data.get('uuid', '')),
        '{world}': str(data.get('world', 'unknown')),
        '{cause}': str(data.get('cause', 'unknown')),
        '{message}': str(data.get('message', '')),
        '{tps}': str(data.get('tps', '')),
        '{mspt}': str(data.get('mspt', '')),
        '{timestamp}': str(data.get('timestamp', '')),
    }

    for key, value in replacements.items():
        resolved = resolved.replace(key, value)

    return resolved.strip() or None
