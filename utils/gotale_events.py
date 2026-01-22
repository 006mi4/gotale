"""
Helpers for storing and reading GoTaleManager events.
"""

import json
import sqlite3
from datetime import datetime, timedelta, date

ALLOWED_TYPES = {
    'player_connect',
    'player_disconnect',
    'player_chat',
}


def store_event(db_path, server_id, payload):
    if not isinstance(payload, dict):
        return False
    event_type = payload.get('type')
    if event_type not in ALLOWED_TYPES:
        return False
    player = payload.get('player') or None
    message = payload.get('message') if event_type == 'player_chat' else None
    try:
        payload_json = json.dumps(payload, ensure_ascii=True)
    except Exception:
        payload_json = None
    try:
        conn = sqlite3.connect(db_path)
        cursor = conn.cursor()
        cursor.execute(
            '''
            INSERT INTO gotale_events (server_id, event_type, player, message, payload_json, created_at)
            VALUES (?, ?, ?, ?, ?, CURRENT_TIMESTAMP)
            ''',
            (server_id, event_type, player, message, payload_json)
        )
        conn.commit()
        conn.close()
        return True
    except Exception as exc:
        print(f"Error storing GoTale event for server {server_id}: {exc}")
        return False


def _normalize_days(days):
    try:
        days = int(days)
    except (TypeError, ValueError):
        days = 7
    if days < 1:
        days = 1
    if days > 365:
        days = 365
    return days


def get_stats(db_path, server_id, days=7):
    days = _normalize_days(days)
    today = date.today()
    start_day = today - timedelta(days=days - 1)
    start_timestamp = datetime.combine(start_day, datetime.min.time()).strftime('%Y-%m-%d %H:%M:%S')

    labels = []
    join_counts = []
    leave_counts = []
    chat_counts = []
    day_cursor = start_day
    while day_cursor <= today:
        labels.append(day_cursor.strftime('%Y-%m-%d'))
        join_counts.append(0)
        leave_counts.append(0)
        chat_counts.append(0)
        day_cursor += timedelta(days=1)

    index_by_day = {label: idx for idx, label in enumerate(labels)}

    try:
        conn = sqlite3.connect(db_path)
        cursor = conn.cursor()
        cursor.execute(
            '''
            SELECT date(created_at) as day, event_type, COUNT(*)
            FROM gotale_events
            WHERE server_id = ? AND created_at >= ?
            GROUP BY day, event_type
            ORDER BY day ASC
            ''',
            (server_id, start_timestamp)
        )
        rows = cursor.fetchall()
        conn.close()
    except Exception as exc:
        print(f"Error reading GoTale stats for server {server_id}: {exc}")
        rows = []

    for day, event_type, count in rows:
        if not day or day not in index_by_day:
            continue
        idx = index_by_day[day]
        if event_type == 'player_connect':
            join_counts[idx] = count
        elif event_type == 'player_disconnect':
            leave_counts[idx] = count
        elif event_type == 'player_chat':
            chat_counts[idx] = count

    return {
        'days': days,
        'labels': labels,
        'joins': join_counts,
        'leaves': leave_counts,
        'chats': chat_counts,
    }


def get_chat_messages(db_path, server_id, limit=200, offset=0):
    try:
        limit = int(limit)
        offset = int(offset)
    except (TypeError, ValueError):
        limit = 200
        offset = 0
    limit = max(1, min(limit, 500))
    offset = max(0, offset)

    try:
        conn = sqlite3.connect(db_path)
        cursor = conn.cursor()
        cursor.execute(
            '''
            SELECT id, event_type, player, message, created_at
            FROM gotale_events
            WHERE server_id = ? AND event_type = 'player_chat'
            ORDER BY created_at DESC, id DESC
            LIMIT ? OFFSET ?
            ''',
            (server_id, limit, offset)
        )
        rows = cursor.fetchall()
        conn.close()
    except Exception as exc:
        print(f"Error reading GoTale chat for server {server_id}: {exc}")
        rows = []

    items = [
        {
            'id': row[0],
            'type': row[1],
            'player': row[2],
            'message': row[3],
            'timestamp': row[4],
        }
        for row in rows
    ]
    items.reverse()
    return items


def search_chat_messages(db_path, server_id, query, limit=200):
    if not query:
        return []
    try:
        limit = int(limit)
    except (TypeError, ValueError):
        limit = 200
    limit = max(1, min(limit, 500))

    pattern = f"%{query.strip()}%"
    try:
        conn = sqlite3.connect(db_path)
        cursor = conn.cursor()
        cursor.execute(
            '''
            SELECT id, event_type, player, message, created_at
            FROM gotale_events
            WHERE server_id = ? AND event_type = 'player_chat'
            AND (message LIKE ? OR player LIKE ?)
            ORDER BY created_at DESC, id DESC
            LIMIT ?
            ''',
            (server_id, pattern, pattern, limit)
        )
        rows = cursor.fetchall()
        conn.close()
    except Exception as exc:
        print(f"Error searching GoTale chat for server {server_id}: {exc}")
        rows = []

    return [
        {
            'id': row[0],
            'type': row[1],
            'player': row[2],
            'message': row[3],
            'timestamp': row[4],
        }
        for row in rows
    ]
