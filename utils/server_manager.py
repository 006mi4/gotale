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

# Supported persistence types to try in order if the server rejects one.
AUTH_PERSISTENCE_TYPES = [
    'encrypted',
    'file',
    'encrypted-file',
    'encrypted_file',
    'plaintext',
    'plain'
]

# Global dictionary to store running server processes
_running_servers = {}

# Global dictionary to store console output buffers
_console_buffers = {}

# Maximum lines to keep in console buffer
MAX_BUFFER_LINES = 1000

# Global variable to store download status (for polling)
_download_status = {
    'active': False,
    'auth_url': None,
    'auth_code': None,
    'percentage': None,
    'details': None,
    'messages': [],
    'complete': False,
    'success': False
}

def get_download_status():
    """Get current download status for polling"""
    return _download_status.copy()

def reset_download_status():
    """Reset download status for a new download"""
    global _download_status
    _download_status = {
        'active': True,
        'auth_url': None,
        'auth_code': None,
        'percentage': None,
        'details': None,
        'messages': [],
        'complete': False,
        'success': False
    }

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
    Copy server files to server directory
    First checks servertemplate folder, then other servers, otherwise needs download

    Args:
        server_id (int): Server ID

    Returns:
        tuple: (success: bool, needs_download: bool)
    """
    try:
        server_path = get_server_path(server_id)
        base_path = Path(__file__).parent.parent.parent

        source_jar = None
        source_aot = None
        source_assets = None

        # First, check servertemplate folder (preferred source)
        template_dir = os.path.join(base_path, 'servertemplate')
        template_jar = os.path.join(template_dir, 'HytaleServer.jar')
        template_aot = os.path.join(template_dir, 'HytaleServer.aot')
        template_assets = os.path.join(template_dir, 'Assets.zip')

        if os.path.exists(template_jar) and os.path.exists(template_assets):
            source_jar = template_jar
            source_assets = template_assets
            if os.path.exists(template_aot):
                source_aot = template_aot

        # If not found in template, search in existing servers
        if not source_jar or not source_assets:
            servers_dir = os.path.join(base_path, 'servers')

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

                        if source_jar and source_assets:
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
        print(f"Error copying server files: {e}")
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

def tail_server_logs(server_id):
    """
    Tail the newest server log file and forward lines into the output queue.
    This is a fallback when the server does not emit live stdout/stderr.
    """
    if server_id not in _running_servers:
        return

    server_info = _running_servers[server_id]
    queue = server_info['output_queue']
    logs_dir = os.path.join(server_info['server_path'], 'logs')
    last_log_path = None
    log_file = None

    while server_id in _running_servers:
        try:
            if not os.path.isdir(logs_dir):
                time.sleep(0.5)
                continue

            # Prefer a known filename, otherwise pick the newest file
            preferred_log = os.path.join(logs_dir, 'latest.log')
            if os.path.isfile(preferred_log):
                newest_log = preferred_log
            else:
                log_candidates = []
                for entry in os.listdir(logs_dir):
                    full_path = os.path.join(logs_dir, entry)
                    if os.path.isfile(full_path) and not entry.endswith('.gz'):
                        log_candidates.append(full_path)

                if not log_candidates:
                    time.sleep(0.5)
                    continue

                newest_log = max(log_candidates, key=os.path.getmtime)

            # If log file changed, reopen and read from start
            if newest_log != last_log_path:
                if log_file:
                    try:
                        log_file.close()
                    except Exception:
                        pass
                last_log_path = newest_log
                log_file = open(newest_log, 'r', encoding='utf-8', errors='replace')
                try:
                    if os.path.getsize(newest_log) > 2 * 1024 * 1024:
                        log_file.seek(0, os.SEEK_END)
                        queue.put(('system', 'Log output is large; tailing from end.'))
                except Exception:
                    pass

            if log_file:
                line = log_file.readline()
                if line:
                    queue.put(('log', line.rstrip('\r\n')))
                else:
                    time.sleep(0.2)
            else:
                time.sleep(0.5)
        except Exception as e:
            queue.put(('error', f'Log tail error: {str(e)}'))
            time.sleep(1)

    if log_file:
        try:
            log_file.close()
        except Exception:
            pass

def start_server(server_id, port, socketio=None, java_args=None, server_name=None):
    """
    Start a Hytale server process with live console I/O

    Args:
        server_id (int): Server ID
        port (int): Port to bind server to
        socketio: SocketIO instance for broadcasting console output
        java_args (str): Additional Java arguments
        server_name (str): Name of the server (for window title)

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

        # Build Java command parts
        java_cmd_parts = ['java']

        # Add AOT cache if available
        aot_path = os.path.join(server_path, 'HytaleServer.aot')
        if os.path.exists(aot_path):
            java_cmd_parts.extend(['-XX:AOTCache=HytaleServer.aot'])

        # Add custom Java args if provided
        if java_args:
            java_cmd_parts.extend(java_args.split())

        # Add server jar and arguments
        java_cmd_parts.extend([
            '-jar', 'HytaleServer.jar',
            '--assets', 'Assets.zip',
            '--bind', f'0.0.0.0:{port}'
        ])

        # Start server process with pipes for live console
        process = subprocess.Popen(
            java_cmd_parts,
            cwd=server_path,
            stdin=subprocess.PIPE,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            bufsize=1,
            universal_newlines=True
        )

        server_info = {
            'process': process,
            'socketio': socketio,
            'port': port,
            'output_queue': Queue(),
            'auth_pending': False,
            'auth_url': None,
            'auth_code': None,
            'server_path': server_path,
            'server_name': server_name or f'Server {server_id}',
            'start_time': time.time(),
            'auth_status_requested': False,
            'auth_checked': False,
            'auth_persistence_attempted': False,
            'auth_persistence_done': False,
            'auth_persistence_index': 0
        }

        _running_servers[server_id] = server_info

        # Initialize console buffer
        _console_buffers[server_id] = ['Starting server process...']

        # Start threads to capture output
        stdout_thread = threading.Thread(
            target=enqueue_output,
            args=(process.stdout, server_info['output_queue'], server_id, 'stdout'),
            daemon=True
        )
        stderr_thread = threading.Thread(
            target=enqueue_output,
            args=(process.stderr, server_info['output_queue'], server_id, 'stderr'),
            daemon=True
        )
        stdout_thread.start()
        stderr_thread.start()

        # Start console monitor thread
        monitor_thread = threading.Thread(
            target=monitor_console_output,
            args=(server_id,),
            daemon=True
        )
        monitor_thread.start()

        # Start log tail thread (fallback for live output)
        log_thread = threading.Thread(
            target=tail_server_logs,
            args=(server_id,),
            daemon=True
        )
        log_thread.start()

        return True

    except Exception as e:
        print(f"Error starting server {server_id}: {e}")
        import traceback
        traceback.print_exc()
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
        process = server_info.get('process')

        if process and process.poll() is None:
            try:
                send_command(server_id, 'stop')
                process.wait(timeout=10)
            except Exception:
                try:
                    process.terminate()
                    process.wait(timeout=5)
                except Exception:
                    try:
                        process.kill()
                    except Exception as e:
                        print(f"[StopServer] Error killing process: {e}")

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
            print(f"[SendCommand] Server {server_id} not in running servers list")
            return False

        process = _running_servers[server_id]['process']

        # Check if process is still running
        if process.poll() is not None:
            print(f"[SendCommand] Server {server_id} process has terminated")
            return False

        if not process.stdin:
            print(f"[SendCommand] Server {server_id} has no stdin attached")
            return False

        # Send command
        print(f"[SendCommand] Writing command to stdin: {command}")
        process.stdin.write(command + '\n')
        process.stdin.flush()
        print(f"[SendCommand] Command flushed successfully")

        return True

    except Exception as e:
        print(f"[SendCommand] Error sending command to server {server_id}: {e}")
        import traceback
        traceback.print_exc()
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
    """Check if a server is currently running by checking the process state"""
    if server_id not in _running_servers:
        return False

    server_info = _running_servers[server_id]
    process = server_info.get('process')

    if not process:
        return False

    if process.poll() is None:
        return True

    # Process has exited, clean up
    if server_id in _running_servers:
        del _running_servers[server_id]

    return False

def get_server_auth_status(server_id):
    """
    Get the current authentication status for a server

    Returns:
        dict: {'auth_pending': bool, 'auth_url': str or None, 'auth_code': str or None}
    """
    if server_id not in _running_servers:
        return {'auth_pending': False, 'auth_url': None, 'auth_code': None}

    server_info = _running_servers[server_id]
    return {
        'auth_pending': server_info.get('auth_pending', False),
        'auth_url': server_info.get('auth_url'),
        'auth_code': server_info.get('auth_code')
    }

def send_auth_persistence(server_id, server_info):
    """Send the next auth persistence command, if available."""
    types = server_info.setdefault('auth_persistence_types', list(AUTH_PERSISTENCE_TYPES))
    index = server_info.get('auth_persistence_index', 0)

    if index >= len(types):
        print(f"[Server {server_id}] No more auth persistence types to try")
        return False

    persistence_type = types[index]
    server_info['auth_persistence_last'] = persistence_type
    server_info['auth_persistence_attempted'] = True
    print(f"[Server {server_id}] Setting auth persistence to '{persistence_type}'")
    send_command(server_id, f'/auth persistence {persistence_type}')
    return True

def monitor_console_output(server_id):
    """
    Monitor console output for a server
    Detects authentication requests and broadcasts output via WebSocket
    Automatically handles 'auth login device' when server needs authentication
    """
    if server_id not in _running_servers:
        return

    server_info = _running_servers[server_id]
    queue = server_info['output_queue']
    socketio = server_info['socketio']

    # Pattern to detect auth request (from auth login device command)
    auth_url_pattern = re.compile(
        r'(https://accounts\.hytale\.com/device(?:\?user_code=\S+)?)|'
        r'(https://oauth\.accounts\.hytale\.com/oauth2/device/verify\?user_code=\S+)'
    )
    auth_code_pattern = re.compile(r'(Authorization code:|Enter code:)\s*([A-Za-z0-9-]+)')

    # Pattern to detect "no tokens configured" message
    no_tokens_pattern = re.compile(r'No server tokens configured|Use /auth login to authenticate', re.IGNORECASE)
    auth_ok_pattern = re.compile(
        r'(Mode:\s*(OAUTH|AUTHENTICATED|EXTERNAL_SESSION))|'
        r'Authentication successful|Successfully authenticated|'
        r'auth\.status\.tokenPresent|tokenPresent',
        re.IGNORECASE
    )
    auth_bad_pattern = re.compile(
        r'Not authenticated|Unauthenticated|Authentication required|'
        r'auth\.status\.tokenMissing|tokenMissing',
        re.IGNORECASE
    )
    persistence_unknown_pattern = re.compile(r'auth\.persistence\.unknownType', re.IGNORECASE)
    persistence_any_pattern = re.compile(r'auth\.persistence\.', re.IGNORECASE)

    # Track if we've already sent the auth command for this session
    auth_command_sent = False
    pending_auth_url = None
    pending_auth_code = None

    while server_id in _running_servers:
        try:
            if not server_info.get('auth_status_requested'):
                start_time = server_info.get('start_time')
                if start_time and time.time() - start_time >= 2:
                    server_info['auth_status_requested'] = True
                    send_command(server_id, '/auth status')

            # Get output from queue (with timeout)
            stream_type, line = queue.get(timeout=0.1)

            # Strip ANSI control sequences to keep output clean
            clean_line = re.sub(r'\x1b\[[0-9;]*[A-Za-z]', '', line)

            # Add to buffer
            if server_id in _console_buffers:
                _console_buffers[server_id].append(clean_line)

                # Trim buffer if too large
                if len(_console_buffers[server_id]) > MAX_BUFFER_LINES:
                    _console_buffers[server_id] = _console_buffers[server_id][-MAX_BUFFER_LINES:]

            # Broadcast to WebSocket clients
            if socketio:
                try:
                    socketio.emit('console_output', {
                        'server_id': server_id,
                        'message': clean_line,
                        'type': stream_type
                    })
                except Exception as emit_error:
                    print(f"[WS] Error emitting console_output: {emit_error}")

            # Check for "no tokens configured" message - auto-run auth login device
            if no_tokens_pattern.search(clean_line) and not auth_command_sent and not server_info['auth_pending']:
                auth_command_sent = True
                print(f"[Server {server_id}] No auth tokens detected, automatically running '/auth login device'")

                # Wait a moment for server to be ready
                time.sleep(1)

                # Send auth login device command
                send_command(server_id, '/auth login device')

                # Mark auth as pending
                server_info['auth_pending'] = True

            # Check for authentication URL (from auth login device)
            url_match = auth_url_pattern.search(clean_line)
            if url_match:
                raw_url = url_match.group(1) or url_match.group(2)
                code_match = re.search(r'user_code=([A-Za-z0-9-]+)', raw_url or '')
                user_code = code_match.group(1) if code_match else None
                if user_code:
                    pending_auth_url = f'https://accounts.hytale.com/device?user_code={user_code}'
                else:
                    pending_auth_url = raw_url
                server_info['auth_url'] = pending_auth_url
                server_info['auth_pending'] = True
                print(f"[Server {server_id}] Found auth URL: {pending_auth_url}")

            # Check for authorization code
            code_match = auth_code_pattern.search(clean_line)
            if code_match:
                pending_auth_code = code_match.group(2)
                server_info['auth_code'] = pending_auth_code
                print(f"[Server {server_id}] Found auth code: {pending_auth_code}")

            # If we have URL, broadcast auth required event
            if pending_auth_url and server_info['auth_pending']:
                print(f"[WS] Emitting auth_required event for server {server_id}")
                if socketio:
                    try:
                        socketio.emit('auth_required', {
                            'server_id': server_id,
                            'server_name': server_info.get('server_name', f'Server {server_id}'),
                            'url': pending_auth_url,
                            'code': pending_auth_code or 'See URL'
                        })
                    except Exception as emit_error:
                        print(f"[WS] Error emitting auth_required: {emit_error}")

                # Clear pending values after sending
                pending_auth_url = None
                pending_auth_code = None
            elif pending_auth_code and server_info['auth_pending'] and server_info.get('auth_url'):
                print(f"[WS] Emitting auth_required event for server {server_id} (code update)")
                if socketio:
                    try:
                        socketio.emit('auth_required', {
                            'server_id': server_id,
                            'server_name': server_info.get('server_name', f'Server {server_id}'),
                            'url': server_info.get('auth_url'),
                            'code': pending_auth_code
                        })
                    except Exception as emit_error:
                        print(f"[WS] Error emitting auth_required: {emit_error}")
                pending_auth_code = None

            # Check for successful authentication
            if ('Authentication successful' in clean_line or 'Successfully authenticated' in clean_line or 'logged in' in clean_line.lower()) and server_info['auth_pending']:
                server_info['auth_pending'] = False
                auth_command_sent = False
                server_info['auth_checked'] = True

                print(f"[Server {server_id}] Authentication successful, setting auth persistence")

                # Send persistence command
                time.sleep(1)
                if not server_info.get('auth_persistence_done'):
                    send_auth_persistence(server_id, server_info)

                # Broadcast auth success
                print(f"[WS] Emitting auth_success event for server {server_id}")
                if socketio:
                    try:
                        socketio.emit('auth_success', {
                            'server_id': server_id
                        })
                    except Exception as emit_error:
                        print(f"[WS] Error emitting auth_success: {emit_error}")

            # Handle /auth status output
            if auth_ok_pattern.search(clean_line):
                server_info['auth_pending'] = False
                if not server_info.get('auth_checked'):
                    server_info['auth_checked'] = True
                    if socketio:
                        try:
                            socketio.emit('auth_success', {
                                'server_id': server_id
                            })
                        except Exception as emit_error:
                            print(f"[WS] Error emitting auth_success: {emit_error}")
            elif auth_bad_pattern.search(clean_line) and not auth_command_sent and not server_info['auth_pending']:
                auth_command_sent = True
                print(f"[Server {server_id}] Auth status not valid, running '/auth login device'")
                time.sleep(1)
                send_command(server_id, '/auth login device')
                server_info['auth_pending'] = True

            # Handle persistence errors and retries
            if persistence_unknown_pattern.search(clean_line) and server_info.get('auth_persistence_attempted') and not server_info.get('auth_persistence_done'):
                server_info['auth_persistence_index'] = server_info.get('auth_persistence_index', 0) + 1
                server_info['auth_persistence_attempted'] = False
                print(f"[Server {server_id}] Persistence type not supported, trying next option")
                send_auth_persistence(server_id, server_info)
            elif persistence_any_pattern.search(clean_line) and not persistence_unknown_pattern.search(clean_line) and server_info.get('auth_persistence_attempted'):
                server_info['auth_persistence_done'] = True

        except Empty:
            # Queue timeout, continue
            continue
        except Exception as e:
            print(f"Error monitoring console for server {server_id}: {e}")
            break

def download_game_files(socketio=None):
    """
    Download Hytale server files using the hytale-downloader
    Handles authentication via device code flow
    Extracts the downloaded ZIP and copies files to servertemplate folder

    Args:
        socketio: SocketIO instance for broadcasting download progress

    Returns:
        bool: True if download successful, False otherwise
    """
    global _download_status

    # Reset download status
    reset_download_status()

    try:
        base_path = Path(__file__).parent.parent.parent
        downloader_path = os.path.join(base_path, 'downloads', 'hytale-downloader-windows-amd64.exe')
        download_dir = os.path.join(base_path, 'downloads')
        template_dir = os.path.join(base_path, 'servertemplate')

        # Check if downloader exists
        if not os.path.exists(downloader_path):
            print("Error: Hytale downloader not found!")
            if socketio:
                socketio.emit('download_error', {
                    'error': 'Hytale downloader not found. Please reinstall the system.'
                })
            return False

        # Start downloader process
        cmd = [downloader_path, 'download', '--output', download_dir, 'server']

        process = subprocess.Popen(
            cmd,
            cwd=download_dir,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            stdin=subprocess.PIPE,
            text=True,
            bufsize=1,
            universal_newlines=True
        )

        # Patterns to detect auth request and progress
        # Pattern for URL with user_code parameter
        auth_url_pattern = re.compile(r'(https://oauth\.accounts\.hytale\.com/oauth2/device/verify\?user_code=\S+)')
        # Pattern for authorization code
        auth_code_pattern = re.compile(r'Authorization code:\s*([A-Za-z0-9]+)')
        # Pattern: [===                                               ] 6.0% (85.5 MB / 1.4 GB)
        progress_pattern = re.compile(r'\[([=\s]*)\]\s*([\d.]+)%\s*\(([^)]+)\)')
        # Pattern to detect version from success message
        version_pattern = re.compile(r'successfully downloaded.*\(version\s+([^)]+)\)')

        auth_url = None
        auth_code = None
        auth_sent = False
        downloaded_version = None

        # Monitor output
        while True:
            line = process.stdout.readline()

            if not line:
                # Process finished
                break

            line = line.strip()
            if not line:
                continue

            print(f"Downloader: {line}")

            # Check for authentication URL (with user_code)
            url_match = auth_url_pattern.search(line)
            if url_match:
                auth_url = url_match.group(1)
                _download_status['auth_url'] = auth_url
                print(f"DEBUG: Found auth URL: {auth_url}")

            # Check for authorization code
            code_match = auth_code_pattern.search(line)
            if code_match:
                auth_code = code_match.group(1)
                _download_status['auth_code'] = auth_code
                print(f"DEBUG: Found auth code: {auth_code}")

            # Add message to status
            if len(_download_status['messages']) < 100:
                _download_status['messages'].append(line)

            # Check for download progress with percentage
            progress_match = progress_pattern.search(line)
            if progress_match:
                percentage = float(progress_match.group(2))
                details = progress_match.group(3)  # e.g., "85.5 MB / 1.4 GB"
                _download_status['percentage'] = percentage
                _download_status['details'] = details
                # Clear auth info once download starts
                _download_status['auth_url'] = None
                _download_status['auth_code'] = None

            # Check for version in success message
            version_match = version_pattern.search(line)
            if version_match:
                downloaded_version = version_match.group(1)
                print(f"Detected version: {downloaded_version}")

            # Check for validating checksum
            if 'validating checksum' in line.lower():
                _download_status['percentage'] = 99
                _download_status['details'] = 'Almost done...'

        # Wait for process to finish
        process.wait()

        # Find the downloaded ZIP file
        zip_file_path = None

        if downloaded_version:
            # Try to find ZIP with version name
            potential_zip = os.path.join(download_dir, f"{downloaded_version}.zip")
            if os.path.exists(potential_zip):
                zip_file_path = potential_zip

        # If not found by version, search for any recent .zip file
        if not zip_file_path:
            for item in os.listdir(download_dir):
                if item.endswith('.zip') and item != 'hytale-downloader.zip':
                    potential_path = os.path.join(download_dir, item)
                    if os.path.isfile(potential_path):
                        zip_file_path = potential_path
                        print(f"Found ZIP file: {item}")
                        break

        if not zip_file_path or not os.path.exists(zip_file_path):
            print("Error: Downloaded ZIP file not found!")
            if socketio:
                socketio.emit('download_error', {
                    'error': 'Downloaded ZIP file not found!'
                })
            return False

        # Extract the ZIP file
        _download_status['percentage'] = 100
        _download_status['details'] = 'Extracting ZIP file...'
        _download_status['messages'].append('Download complete! Extracting files...')

        if socketio:
            socketio.emit('download_progress', {
                'message': 'Extracting ZIP file...'
            })

        extract_dir = os.path.join(download_dir, 'extracted')
        os.makedirs(extract_dir, exist_ok=True)

        with zipfile.ZipFile(zip_file_path, 'r') as zip_ref:
            zip_ref.extractall(extract_dir)

        print(f"Extracted ZIP to: {extract_dir}")
        _download_status['messages'].append('ZIP file extracted successfully')
        _download_status['details'] = 'Finding server files...'

        # Find HytaleServer.jar and Assets.zip in extracted contents
        jar_file = None
        assets_file = None

        # Search in extracted directory (could be in Server subfolder or root)
        for root, dirs, files in os.walk(extract_dir):
            for file in files:
                if file == 'HytaleServer.jar' and not jar_file:
                    jar_file = os.path.join(root, file)
                    print(f"Found HytaleServer.jar: {jar_file}")
                elif file == 'Assets.zip' and not assets_file:
                    assets_file = os.path.join(root, file)
                    print(f"Found Assets.zip: {assets_file}")

        if not jar_file or not assets_file:
            print("Error: Required files not found in ZIP!")
            print(f"JAR found: {jar_file}")
            print(f"Assets found: {assets_file}")
            if socketio:
                socketio.emit('download_error', {
                    'error': 'Required server files not found in downloaded ZIP!'
                })
            return False

        # Create servertemplate directory and copy files
        _download_status['percentage'] = 100
        _download_status['details'] = 'Copying files to server template...'
        _download_status['messages'].append('Copying server files... This may take a moment.')

        if socketio:
            socketio.emit('download_progress', {
                'message': 'Copying files to server template...'
            })

        os.makedirs(template_dir, exist_ok=True)

        # Copy files to servertemplate
        shutil.copy2(jar_file, os.path.join(template_dir, 'HytaleServer.jar'))
        shutil.copy2(assets_file, os.path.join(template_dir, 'Assets.zip'))

        # Also copy AOT file if it exists
        jar_dir = os.path.dirname(jar_file)
        aot_file = os.path.join(jar_dir, 'HytaleServer.aot')
        if os.path.exists(aot_file):
            shutil.copy2(aot_file, os.path.join(template_dir, 'HytaleServer.aot'))
            print("Copied AOT cache file")

        print(f"Server files copied to: {template_dir}")
        _download_status['messages'].append('Server files copied successfully!')
        _download_status['details'] = 'Cleaning up temporary files...'

        # Cleanup: remove extracted folder and ZIP file
        try:
            shutil.rmtree(extract_dir)
            os.remove(zip_file_path)
            print("Cleaned up temporary files")
        except Exception as cleanup_error:
            print(f"Warning: Could not clean up temp files: {cleanup_error}")

        # Mark download as complete and successful
        _download_status['complete'] = True
        _download_status['success'] = True
        _download_status['active'] = False

        return True

    except Exception as e:
        print(f"Error downloading game files: {e}")
        _download_status['complete'] = True
        _download_status['success'] = False
        _download_status['active'] = False
        return False

def copy_downloaded_files_to_server(server_id):
    """
    Copy server files from servertemplate folder to server directory

    Args:
        server_id (int): Server ID to copy files to

    Returns:
        bool: True if successful, False otherwise
    """
    try:
        base_path = Path(__file__).parent.parent.parent
        template_dir = os.path.join(base_path, 'servertemplate')
        server_path = get_server_path(server_id)

        if not os.path.exists(template_dir):
            print(f"Error: Server template directory not found: {template_dir}")
            return False

        # Copy files
        jar_src = os.path.join(template_dir, 'HytaleServer.jar')
        aot_src = os.path.join(template_dir, 'HytaleServer.aot')
        assets_src = os.path.join(template_dir, 'Assets.zip')

        if not os.path.exists(jar_src):
            print(f"Error: HytaleServer.jar not found at {jar_src}")
            return False

        if not os.path.exists(assets_src):
            print(f"Error: Assets.zip not found at {assets_src}")
            return False

        # Copy to server directory
        shutil.copy2(jar_src, os.path.join(server_path, 'HytaleServer.jar'))
        if os.path.exists(aot_src):
            shutil.copy2(aot_src, os.path.join(server_path, 'HytaleServer.aot'))
        shutil.copy2(assets_src, os.path.join(server_path, 'Assets.zip'))

        print(f"Successfully copied server files to server {server_id}")
        return True

    except Exception as e:
        print(f"Error copying server files to server: {e}")
        return False

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
