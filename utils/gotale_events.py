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
    conn = None
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

    rows = []
    overview = {
        'total_events_all_time': 0,
        'unique_players_seen': 0,
        'joins_today': 0,
        'joins_yesterday': 0,
        'new_players_today': 0,
        'new_players_yesterday': 0,
    }
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

        cursor.execute(
            '''
            SELECT COUNT(*)
            FROM gotale_events
            WHERE server_id = ?
            ''',
            (server_id,)
        )
        overview['total_events_all_time'] = int((cursor.fetchone() or [0])[0] or 0)

        cursor.execute(
            '''
            SELECT COUNT(DISTINCT player)
            FROM gotale_events
            WHERE server_id = ?
              AND player IS NOT NULL
              AND TRIM(player) != ''
            ''',
            (server_id,)
        )
        overview['unique_players_seen'] = int((cursor.fetchone() or [0])[0] or 0)

        today_label = today.strftime('%Y-%m-%d')
        yesterday_label = (today - timedelta(days=1)).strftime('%Y-%m-%d')

        cursor.execute(
            '''
            SELECT date(created_at) as day, COUNT(*)
            FROM gotale_events
            WHERE server_id = ?
              AND event_type = 'player_connect'
              AND date(created_at) IN (?, ?)
            GROUP BY day
            ''',
            (server_id, today_label, yesterday_label)
        )
        for day, count in cursor.fetchall():
            if day == today_label:
                overview['joins_today'] = int(count or 0)
            elif day == yesterday_label:
                overview['joins_yesterday'] = int(count or 0)

        cursor.execute(
            '''
            SELECT first_day, COUNT(*)
            FROM (
                SELECT player, MIN(date(created_at)) AS first_day
                FROM gotale_events
                WHERE server_id = ?
                  AND event_type = 'player_connect'
                  AND player IS NOT NULL
                  AND TRIM(player) != ''
                GROUP BY player
            )
            WHERE first_day IN (?, ?)
            GROUP BY first_day
            ''',
            (server_id, today_label, yesterday_label)
        )
        for day, count in cursor.fetchall():
            if day == today_label:
                overview['new_players_today'] = int(count or 0)
            elif day == yesterday_label:
                overview['new_players_yesterday'] = int(count or 0)

    except Exception as exc:
        print(f"Error reading GoTale stats for server {server_id}: {exc}")
    finally:
        if conn:
            conn.close()

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

    join_delta = overview['joins_today'] - overview['joins_yesterday']
    new_player_delta = overview['new_players_today'] - overview['new_players_yesterday']

    def _trend(delta):
        if delta > 0:
            return 'up'
        if delta < 0:
            return 'down'
        return 'equal'

    return {
        'days': days,
        'labels': labels,
        'joins': join_counts,
        'leaves': leave_counts,
        'chats': chat_counts,
        'overview': {
            **overview,
            'join_delta_vs_yesterday': join_delta,
            'new_player_delta_vs_yesterday': new_player_delta,
            'join_trend': _trend(join_delta),
            'new_player_trend': _trend(new_player_delta),
        },
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
