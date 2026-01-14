"""
Console WebSocket routes for real-time console interaction
"""

from flask_socketio import emit, join_room, leave_room
from flask_login import current_user
from functools import wraps

from models.server import Server
from utils import server_manager

def authenticated_only(f):
    """Decorator to require authentication for SocketIO events"""
    @wraps(f)
    def wrapped(*args, **kwargs):
        if not current_user.is_authenticated:
            emit('error', {'message': 'Authentication required'})
            return
        return f(*args, **kwargs)
    return wrapped

def register_socketio_events(socketio):
    """Register SocketIO event handlers"""

    @socketio.on('join_console')
    @authenticated_only
    def handle_join_console(data):
        """Client joins a server console room"""
        try:
            server_id = data.get('server_id')

            if not server_id:
                emit('error', {'message': 'Server ID required'})
                return

            # Get server from database
            server = Server.get_by_id(server_id)

            if not server:
                emit('error', {'message': 'Server not found'})
                return

            # Join room
            room = f'console_{server_id}'
            join_room(room)

            # Send console history
            history = server_manager.get_console_output(server_id, lines=100)

            emit('console_history', {
                'messages': history,
                'server_id': server_id
            })

            # Send current server status
            is_running = server_manager.is_server_running(server_id)

            emit('server_status', {
                'server_id': server_id,
                'status': server.status,
                'is_running': is_running
            })

            print(f"User {current_user.username} joined console for server {server_id}")

        except Exception as e:
            print(f"Error joining console: {e}")
            emit('error', {'message': 'Failed to join console'})

    @socketio.on('leave_console')
    @authenticated_only
    def handle_leave_console(data):
        """Client leaves a server console room"""
        try:
            server_id = data.get('server_id')

            if not server_id:
                return

            # Leave room
            room = f'console_{server_id}'
            leave_room(room)

            print(f"User {current_user.username} left console for server {server_id}")

        except Exception as e:
            print(f"Error leaving console: {e}")

    @socketio.on('console_command')
    @authenticated_only
    def handle_console_command(data):
        """Client sends a command to server console"""
        try:
            server_id = data.get('server_id')
            command = data.get('command', '').strip()

            if not server_id or not command:
                emit('error', {'message': 'Server ID and command required'})
                return

            # Get server from database
            server = Server.get_by_id(server_id)

            if not server:
                emit('error', {'message': 'Server not found'})
                return

            # Check if server is running
            if not server_manager.is_server_running(server_id):
                emit('error', {'message': 'Server is not running'})
                return

            # Send command
            success = server_manager.send_command(server_id, command)

            if not success:
                emit('error', {'message': 'Failed to send command'})
                return

            # Echo command in console for all viewers
            room = f'console_{server_id}'
            emit('console_output', {
                'server_id': server_id,
                'message': f'> {command}',
                'type': 'command'
            }, room=room)

            print(f"User {current_user.username} sent command to server {server_id}: {command}")

        except Exception as e:
            print(f"Error sending console command: {e}")
            emit('error', {'message': 'Failed to send command'})

    @socketio.on('connect')
    def handle_connect():
        """Client connects to WebSocket"""
        if current_user.is_authenticated:
            print(f"User {current_user.username} connected via WebSocket")
        else:
            print("Unauthenticated user connected via WebSocket")

    @socketio.on('disconnect')
    def handle_disconnect():
        """Client disconnects from WebSocket"""
        if current_user.is_authenticated:
            print(f"User {current_user.username} disconnected from WebSocket")
        else:
            print("User disconnected from WebSocket")
