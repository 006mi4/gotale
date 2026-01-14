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
        if socketio:
            socketio.emit('download_progress', {
                'message': 'Extracting ZIP file...'
            })

        extract_dir = os.path.join(download_dir, 'extracted')
        os.makedirs(extract_dir, exist_ok=True)

        with zipfile.ZipFile(zip_file_path, 'r') as zip_ref:
            zip_ref.extractall(extract_dir)

        print(f"Extracted ZIP to: {extract_dir}")

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
