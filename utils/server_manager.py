"""
Server Manager - Manages Hytale server processes
Handles starting, stopping, console I/O, and authentication
"""

import subprocess
import threading
import os
import shutil
import zipfile
import time
import re
from queue import Queue, Empty
from pathlib import Path

# Global dictionary to store running server processes
_running_servers = {}

# Global dictionary to store console output buffers
_console_buffers = {}

# Maximum lines to keep in console buffer
MAX_BUFFER_LINES = 1000

def get_server_path(server_id):
    """Get the directory path for a server"""
    base_path = Path(__file__).parent.parent.parent
    return os.path.join(base_path, 'servers', f'server_{server_id}')

def get_assets_path(server_id):
    """Get the Assets.zip path for a server"""
    return os.path.join(get_server_path(server_id), 'Assets.zip')

def get_jar_path(server_id):
    """Get the HytaleServer.jar path for a server"""
    return os.path.join(get_server_path(server_id), 'HytaleServer.jar')

def create_server_directory(server_id, name):
    """
    Create server directory structure

    Args:
        server_id (int): Server ID
        name (str): Server name

    Returns:
        bool: True if successful, False otherwise
    """
    try:
        server_path = get_server_path(server_id)

        # Create server directory
        os.makedirs(server_path, exist_ok=True)

        # Create subdirectories
        os.makedirs(os.path.join(server_path, 'logs'), exist_ok=True)

        return True
    except Exception as e:
        print(f"Error creating server directory: {e}")
        return False

def copy_game_files(server_id):
    """
    Copy game files to server directory
    First checks if files exist in other servers, otherwise needs download

    Args:
        server_id (int): Server ID

    Returns:
        tuple: (success: bool, needs_download: bool)
    """
    try:
        server_path = get_server_path(server_id)

        # Look for game files in other servers
        base_path = Path(__file__).parent.parent.parent
        servers_dir = os.path.join(base_path, 'servers')

        source_jar = None
        source_aot = None
        source_assets = None

        # Search for files in existing servers
        if os.path.exists(servers_dir):
            for server_dir in os.listdir(servers_dir):
                if server_dir == f'server_{server_id}':
                    continue

                potential_path = os.path.join(servers_dir, server_dir)

                if os.path.isdir(potential_path):
                    jar_path = os.path.join(potential_path, 'HytaleServer.jar')
                    aot_path = os.path.join(potential_path, 'HytaleServer.aot')
                    assets_path = os.path.join(potential_path, 'Assets.zip')

                    if os.path.exists(jar_path) and not source_jar:
                        source_jar = jar_path
                    if os.path.exists(aot_path) and not source_aot:
                        source_aot = aot_path
                    if os.path.exists(assets_path) and not source_assets:
                        source_assets = assets_path

                    if source_jar and source_aot and source_assets:
                        break

        # If files found, copy them
        if source_jar and source_assets:
            shutil.copy2(source_jar, os.path.join(server_path, 'HytaleServer.jar'))
            if source_aot:
                shutil.copy2(source_aot, os.path.join(server_path, 'HytaleServer.aot'))
            shutil.copy2(source_assets, os.path.join(server_path, 'Assets.zip'))
            return (True, False)

        # Files not found, need to download
        return (False, True)

    except Exception as e:
        print(f"Error copying game files: {e}")
        return (False, False)

def enqueue_output(stream, queue, server_id, stream_type):
    """
    Read output from stream and put it in queue
    Runs in a separate thread
    """
    try:
        for line in iter(stream.readline, ''):
            if line:
                queue.put((stream_type, line.rstrip()))
    except Exception as e:
        queue.put(('error', f'Error reading {stream_type}: {str(e)}'))
    finally:
        stream.close()

def start_server(server_id, port, socketio=None, java_args=None):
    """
    Start a Hytale server

    Args:
        server_id (int): Server ID
        port (int): Port to bind server to
        socketio: SocketIO instance for broadcasting console output
        java_args (str): Additional Java arguments

    Returns:
        bool: True if started successfully, False otherwise
    """
    try:
        # Check if server is already running
        if server_id in _running_servers:
            return False

        server_path = get_server_path(server_id)
        jar_path = get_jar_path(server_id)
        assets_path = get_assets_path(server_id)

        # Verify files exist
        if not os.path.exists(jar_path):
            return False
        if not os.path.exists(assets_path):
            return False

        # Build command
        cmd = ['java']

        # Add AOT cache if available
        aot_path = os.path.join(server_path, 'HytaleServer.aot')
        if os.path.exists(aot_path):
            cmd.extend(['-XX:AOTCache=HytaleServer.aot'])

        # Add custom Java args if provided
        if java_args:
            cmd.extend(java_args.split())

        # Add server jar and arguments
        cmd.extend([
            '-jar', 'HytaleServer.jar',
            '--assets', 'Assets.zip',
            '--bind', f'0.0.0.0:{port}'
        ])

        # Start process
        process = subprocess.Popen(
            cmd,
            cwd=server_path,
            stdin=subprocess.PIPE,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            bufsize=1,
            universal_newlines=True
        )

        # Store process
        _running_servers[server_id] = {
            'process': process,
            'socketio': socketio,
            'port': port,
            'output_queue': Queue(),
            'auth_pending': False
        }

        # Initialize console buffer
        _console_buffers[server_id] = []

        # Start output reading threads
        stdout_thread = threading.Thread(
            target=enqueue_output,
            args=(process.stdout, _running_servers[server_id]['output_queue'], server_id, 'stdout'),
            daemon=True
        )
        stderr_thread = threading.Thread(
            target=enqueue_output,
            args=(process.stderr, _running_servers[server_id]['output_queue'], server_id, 'stderr'),
            daemon=True
        )

        stdout_thread.start()
        stderr_thread.start()

        # Start console monitoring thread
        monitor_thread = threading.Thread(
            target=monitor_console_output,
            args=(server_id,),
            daemon=True
        )
        monitor_thread.start()

        return True

    except Exception as e:
        print(f"Error starting server {server_id}: {e}")
        return False

def stop_server(server_id):
    """
    Stop a Hytale server

    Args:
        server_id (int): Server ID

    Returns:
        bool: True if stopped successfully, False otherwise
    """
    try:
        if server_id not in _running_servers:
            return False

        server_info = _running_servers[server_id]
        process = server_info['process']

        # Try graceful shutdown first with /stop command
        try:
            process.stdin.write('/stop\n')
            process.stdin.flush()
        except:
            pass

        # Wait for process to terminate (max 30 seconds)
        try:
            process.wait(timeout=30)
        except subprocess.TimeoutExpired:
            # Force kill if not terminated
            process.kill()
            process.wait()

        # Remove from running servers
        del _running_servers[server_id]

        return True

    except Exception as e:
        print(f"Error stopping server {server_id}: {e}")
        return False

def send_command(server_id, command):
    """
    Send a command to a running server

    Args:
        server_id (int): Server ID
        command (str): Command to send

    Returns:
        bool: True if command sent successfully, False otherwise
    """
    try:
        if server_id not in _running_servers:
            return False

        process = _running_servers[server_id]['process']

        # Send command
        process.stdin.write(command + '\n')
        process.stdin.flush()

        return True

    except Exception as e:
        print(f"Error sending command to server {server_id}: {e}")
        return False

def get_console_output(server_id, lines=100):
    """
    Get recent console output for a server

    Args:
        server_id (int): Server ID
        lines (int): Number of recent lines to return

    Returns:
        list: List of console output lines
    """
    if server_id in _console_buffers:
        return _console_buffers[server_id][-lines:]
    return []

def is_server_running(server_id):
    """Check if a server is currently running"""
    return server_id in _running_servers

def monitor_console_output(server_id):
    """
    Monitor console output for a server
    Detects authentication requests and broadcasts output via WebSocket
    """
    if server_id not in _running_servers:
        return

    server_info = _running_servers[server_id]
    queue = server_info['output_queue']
    socketio = server_info['socketio']

    # Pattern to detect auth request
    auth_pattern = re.compile(r'Visit:\s*(https://accounts\.hytale\.com/device\S*)')
    code_pattern = re.compile(r'Enter code:\s*([A-Z0-9-]+)')

    while server_id in _running_servers:
        try:
            # Get output from queue (with timeout)
            stream_type, line = queue.get(timeout=0.1)

            # Add to buffer
            if server_id in _console_buffers:
                _console_buffers[server_id].append(line)

                # Trim buffer if too large
                if len(_console_buffers[server_id]) > MAX_BUFFER_LINES:
                    _console_buffers[server_id] = _console_buffers[server_id][-MAX_BUFFER_LINES:]

            # Broadcast to WebSocket clients
            if socketio:
                socketio.emit('console_output', {
                    'server_id': server_id,
                    'message': line,
                    'type': stream_type
                }, room=f'console_{server_id}')

            # Check for authentication request
            auth_match = auth_pattern.search(line)
            code_match = code_pattern.search(line)

            if auth_match and not server_info['auth_pending']:
                url = auth_match.group(1)
                code = code_match.group(1) if code_match else None

                # Mark auth as pending
                server_info['auth_pending'] = True

                # Broadcast auth required event
                if socketio:
                    socketio.emit('auth_required', {
                        'server_id': server_id,
                        'url': url,
                        'code': code
                    }, room=f'console_{server_id}')

            # Check for successful authentication
            if 'Authentication successful' in line and server_info['auth_pending']:
                server_info['auth_pending'] = False

                # Send persistence command
                time.sleep(1)
                send_command(server_id, '/auth persistence encrypted')

                # Broadcast auth success
                if socketio:
                    socketio.emit('auth_success', {
                        'server_id': server_id
                    }, room=f'console_{server_id}')

        except Empty:
            # Queue timeout, continue
            continue
        except Exception as e:
            print(f"Error monitoring console for server {server_id}: {e}")
            break

def delete_server_files(server_id):
    """
    Delete all files for a server

    Args:
        server_id (int): Server ID

    Returns:
        bool: True if deleted successfully, False otherwise
    """
    try:
        # Make sure server is stopped first
        if server_id in _running_servers:
            stop_server(server_id)

        # Delete directory
        server_path = get_server_path(server_id)
        if os.path.exists(server_path):
            shutil.rmtree(server_path)

        # Remove from buffers
        if server_id in _console_buffers:
            del _console_buffers[server_id]

        return True

    except Exception as e:
        print(f"Error deleting server files for server {server_id}: {e}")
        return False
