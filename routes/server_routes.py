"""
Server control routes for start, stop, restart operations
"""

from flask import Blueprint, render_template, request, jsonify, current_app
from flask_login import login_required, current_user
import time

from models.server import Server
from utils import server_manager, java_checker

# Import socketio from app (will be set during initialization)
_socketio = None

bp = Blueprint('server', __name__)

def get_socketio():
    """Get the SocketIO instance from the current app"""
    from flask import current_app
    return getattr(current_app, 'socketio', None)

@bp.route('/server/<int:server_id>')
@login_required
def console_view(server_id):
    """Console view page for a specific server"""

    # Get server from database
    server = Server.get_by_id(server_id)

    if not server:
        return render_template('404.html'), 404

    # Get console history
    console_history = server_manager.get_console_output(server_id, lines=100)

    # Check if server is running
    is_running = server_manager.is_server_running(server_id)

    # Check Java
    java_info = java_checker.check_java()
    java_info['download_url'] = java_checker.get_java_download_url()

    return render_template('server_console.html',
                         server=server,
                         console_history=console_history,
                         is_running=is_running,
                         java_info=java_info,
                         user=current_user)

@bp.route('/api/server/<int:server_id>/start', methods=['POST'])
@login_required
def start_server(server_id):
    """API endpoint to start a server"""

    try:
        # Get server from database
        server = Server.get_by_id(server_id)

        if not server:
            return jsonify({'success': False, 'error': 'Server not found'}), 404

        # Check if already running
        if server_manager.is_server_running(server_id):
            return jsonify({'success': False, 'error': 'Server is already running'}), 400

        # Check Java installation
        java_info = java_checker.check_java()
        if not java_info['installed']:
            return jsonify({
                'success': False,
                'error': 'Java 25 or higher is not installed',
                'java_download_url': java_checker.get_java_download_url()
            }), 400

        # Check if game files exist
        if not server_manager.get_jar_path(server_id) or not server_manager.get_assets_path(server_id):
            return jsonify({
                'success': False,
                'error': 'Server files are missing. Please download Hytale server files.'
            }), 400

        # Update status to starting
        Server.update_status(server_id, 'starting')

        # Get SocketIO instance
        from app import socketio

        # Start server in new terminal window
        success = server_manager.start_server(
            server_id,
            server.port,
            socketio=socketio,
            java_args=server.java_args,
            server_name=server.name
        )

        if not success:
            Server.update_status(server_id, 'offline')
            return jsonify({'success': False, 'error': 'Failed to start server'}), 500

        # Update status to online
        Server.update_status(server_id, 'online')

        return jsonify({'success': True, 'message': 'Server started successfully'})

    except Exception as e:
        print(f"Error starting server: {e}")
        Server.update_status(server_id, 'offline')
        return jsonify({'success': False, 'error': 'An unexpected error occurred'}), 500

@bp.route('/api/server/<int:server_id>/stop', methods=['POST'])
@login_required
def stop_server(server_id):
    """API endpoint to stop a server"""

    try:
        # Get server from database
        server = Server.get_by_id(server_id)

        if not server:
            return jsonify({'success': False, 'error': 'Server not found'}), 404

        # Check if running
        if not server_manager.is_server_running(server_id):
            return jsonify({'success': False, 'error': 'Server is not running'}), 400

        # Update status to stopping
        Server.update_status(server_id, 'stopping')

        # Stop server
        success = server_manager.stop_server(server_id)

        if not success:
            Server.update_status(server_id, 'online')
            return jsonify({'success': False, 'error': 'Failed to stop server'}), 500

        # Update status to offline
        Server.update_status(server_id, 'offline')

        return jsonify({'success': True, 'message': 'Server stopped successfully'})

    except Exception as e:
        print(f"Error stopping server: {e}")
        return jsonify({'success': False, 'error': 'An unexpected error occurred'}), 500

@bp.route('/api/server/<int:server_id>/restart', methods=['POST'])
@login_required
def restart_server(server_id):
    """API endpoint to restart a server"""

    try:
        # Get server from database
        server = Server.get_by_id(server_id)

        if not server:
            return jsonify({'success': False, 'error': 'Server not found'}), 404

        # Stop if running
        if server_manager.is_server_running(server_id):
            Server.update_status(server_id, 'stopping')
            server_manager.stop_server(server_id)

        # Wait a moment
        time.sleep(2)

        # Start server
        Server.update_status(server_id, 'starting')

        from app import socketio

        success = server_manager.start_server(
            server_id,
            server.port,
            socketio=socketio,
            java_args=server.java_args,
            server_name=server.name
        )

        if not success:
            Server.update_status(server_id, 'offline')
            return jsonify({'success': False, 'error': 'Failed to start server'}), 500

        Server.update_status(server_id, 'online')

        return jsonify({'success': True, 'message': 'Server restarted successfully'})

    except Exception as e:
        print(f"Error restarting server: {e}")
        Server.update_status(server_id, 'offline')
        return jsonify({'success': False, 'error': 'An unexpected error occurred'}), 500

@bp.route('/api/server/<int:server_id>/status')
@login_required
def get_status(server_id):
    """API endpoint to get server status"""

    try:
        # Get server from database
        server = Server.get_by_id(server_id)

        if not server:
            return jsonify({'success': False, 'error': 'Server not found'}), 404

        # Check if actually running
        is_running = server_manager.is_server_running(server_id)

        return jsonify({
            'success': True,
            'status': server.status,
            'is_running': is_running,
            'port': server.port
        })

    except Exception as e:
        print(f"Error getting server status: {e}")
        return jsonify({'success': False, 'error': 'An unexpected error occurred'}), 500

@bp.route('/api/server/<int:server_id>/auth-status')
@login_required
def get_auth_status(server_id):
    """API endpoint to get server authentication status"""
    try:
        server = Server.get_by_id(server_id)

        if not server:
            return jsonify({'success': False, 'error': 'Server not found'}), 404

        auth_status = server_manager.get_server_auth_status(server_id)

        return jsonify({
            'success': True,
            'auth_pending': auth_status['auth_pending'],
            'auth_url': auth_status['auth_url'],
            'auth_code': auth_status['auth_code']
        })

    except Exception as e:
        print(f"Error getting auth status: {e}")
        return jsonify({'success': False, 'error': 'An unexpected error occurred'}), 500
