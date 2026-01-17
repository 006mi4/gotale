"""
Console WebSocket routes for real-time console interaction
"""

from flask_socketio import emit, join_room, leave_room
from flask_login import current_user
from functools import wraps

from models.server import Server
from utils import server_manager
from utils.authz import has_permission
from models.user import User

def authenticated_only(f):
    """Decorator to require authentication for SocketIO events"""
    @wraps(f)
    def wrapped(*args, **kwargs):
        try:
            if not current_user.is_authenticated:
                print(f"[WebSocket] Authentication failed for event")
                emit('error', {'message': 'Authentication required. Please refresh the page.'})
                return
        except Exception as e:
            print(f"[WebSocket] Error checking authentication: {e}")
            # Allow the request to proceed if we can't check auth (edge case)
            pass
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
            if not has_permission('view_servers'):
                emit('error', {'message': 'Forbidden'})
                return
            if not current_user.is_superadmin and not User.has_server_access(current_user.id, server_id):
                emit('error', {'message': 'Forbidden'})
                return

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

            # Check if there's a pending auth request
            auth_status = server_manager.get_server_auth_status(server_id)
            if auth_status['auth_pending'] and auth_status['auth_url']:
                print(f"[Console] Sending pending auth_required for server {server_id}")
                emit('auth_required', {
                    'server_id': server_id,
                    'url': auth_status['auth_url'],
                    'code': auth_status['auth_code'] or 'See URL'
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

            print(f"[Console] Received command for server {server_id}: {command}")

            if not server_id or not command:
                print(f"[Console] Error: Missing server_id or command")
                emit('error', {'message': 'Server ID and command required'})
                return

            # Get server from database
            server = Server.get_by_id(server_id)

            if not server:
                print(f"[Console] Error: Server {server_id} not found in database")
                emit('error', {'message': 'Server not found'})
                return

            # Check if server is running
            if not server_manager.is_server_running(server_id):
                print(f"[Console] Error: Server {server_id} is not running")
                emit('error', {'message': 'Server is not running'})
                return

            # Send command
            print(f"[Console] Sending command to server process...")
            success = server_manager.send_command(server_id, command)

            if not success:
                print(f"[Console] Error: Failed to send command to server process")
                emit('error', {'message': 'Failed to send command'})
                return

            print(f"[Console] Command sent successfully")

            # Command echo is now handled locally in the frontend

            try:
                print(f"[Console] User {current_user.username} sent command to server {server_id}: {command}")
            except:
                print(f"[Console] Command sent to server {server_id}: {command}")

        except Exception as e:
            print(f"[Console] Error sending console command: {e}")
            import traceback
            traceback.print_exc()
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
