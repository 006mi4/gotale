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
import shlex
import sys
import json
import uuid
from queue import Queue, Empty
from pathlib import Path

# Supported persistence types to try in order if the server rejects one.
AUTH_PERSISTENCE_TYPES = [
    'Encrypted'
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
    'success': False,
    'attempt': 0,
    'max_attempts': 0,
    'last_error': None
}

VERSION_FILENAME = 'hytale_version.txt'

MAX_DOWNLOAD_ATTEMPTS = 30
DOWNLOAD_RETRY_DELAY = 10
AUTH_LOGIN_COOLDOWN = 20

AUTH_TOKEN_FILENAMES = (
    'auth.enc',
    'credentials.enc',
    'oauth_credentials.json',
    'credentials.json',
    '.hytale_token'
)

DOWNLOADER_CREDENTIALS_FILENAMES = (
    '.hytale-downloader-credentials.json',
    'oauth_credentials.json',
    'credentials.json'
)

DEFAULT_STARTUP_SETTINGS = {
    'min_ram_mb': None,
    'max_ram_mb': None,
    'game_profile': '',
    'auth_mode': 'authenticated',
    'automatic_update': False,
    'allow_op': True,
    'accept_early_plugins': False,
    'asset_pack': 'Assets.zip',
    'enable_backups': False,
    'backup_directory': '',
    'backup_frequency': 30,
    'disable_sentry': False,
    'jvm_args': '',
    'leverage_aot_cache': True
}

def _read_version_file(path):
    if not os.path.exists(path):
        return None
    try:
        with open(path, 'r', encoding='utf-8') as handle:
            version = handle.read().strip()
        return version or None
    except Exception as e:
        print(f"Error reading version file {path}: {e}")
        return None

def _write_version_file(path, version):
    if not version:
        return False
    try:
        with open(path, 'w', encoding='utf-8') as handle:
            handle.write(str(version).strip() + '\n')
        return True
    except Exception as e:
        print(f"Error writing version file {path}: {e}")
        return False

def get_template_version():
    base_path = Path(__file__).parent.parent.parent
    version_path = os.path.join(base_path, 'servertemplate', VERSION_FILENAME)
    return _read_version_file(version_path)

def get_server_version(server_id):
    version_path = os.path.join(get_server_path(server_id), VERSION_FILENAME)
    return _read_version_file(version_path)

def _copy_version_file(source_dir, dest_dir):
    source_path = os.path.join(source_dir, VERSION_FILENAME)
    if os.path.exists(source_path):
        try:
            shutil.copy2(source_path, os.path.join(dest_dir, VERSION_FILENAME))
            return True
        except Exception as e:
            print(f"Error copying version file: {e}")
    return False

def _normalize_host_os(host_os=None):
    if host_os:
        host_os = host_os.strip().lower()
    if host_os not in ('linux', 'windows'):
        return 'linux' if sys.platform.startswith('linux') else 'windows'
    return host_os

def _get_downloader_path(host_os=None):
    base_path = Path(__file__).parent.parent.parent
    normalized = _normalize_host_os(host_os)
    filename = 'hytale-downloader-linux-amd64' if normalized == 'linux' else 'hytale-downloader-windows-amd64.exe'
    return os.path.join(base_path, 'downloads', filename)

def _ensure_downloader_executable(path, host_os=None):
    normalized = _normalize_host_os(host_os)
    if normalized == 'linux':
        try:
            os.chmod(path, 0o755)
        except Exception:
            pass

def get_latest_game_version(host_os=None):
    downloader_path = _get_downloader_path(host_os)
    if not os.path.exists(downloader_path):
        return None, f'Hytale downloader not found at {downloader_path}'

    _ensure_downloader_executable(downloader_path, host_os)

    download_dir = os.path.dirname(downloader_path)
    try:
        result = subprocess.run(
            [downloader_path, '-print-version'],
            check=False,
            capture_output=True,
            text=True,
            timeout=20,
            cwd=download_dir
        )
    except Exception as e:
        return None, str(e)

    if result.returncode != 0:
        stderr = (result.stderr or '').strip()
        stdout = (result.stdout or '').strip()
        return None, stderr or stdout or f'Failed to read version (code {result.returncode})'

    output = (result.stdout or result.stderr or '').strip()
    if not output:
        return None, 'No version output'

    lines = [line.strip() for line in output.splitlines() if line.strip()]
    if not lines:
        return None, 'No version output'

    return lines[-1], None

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
        'success': False,
        'attempt': 0,
        'max_attempts': 0,
        'last_error': None
    }

def _read_machine_id(path):
    try:
        with open(path, 'r', encoding='utf-8') as handle:
            value = handle.read().strip()
        if re.fullmatch(r'[0-9a-fA-F]{32}', value):
            return value.lower()
    except Exception:
        return None
    return None

def _write_machine_id(path, value):
    try:
        with open(path, 'w', encoding='utf-8') as handle:
            handle.write(value + '\n')
        return True
    except Exception:
        return False

def _ensure_persistent_machine_id(server_path):
    """Ensure a stable machine-id for auth persistence when possible."""
    if not sys.platform.startswith('linux'):
        return None

    system_machine_id = _read_machine_id('/etc/machine-id')
    if system_machine_id:
        return None

    local_path = os.path.join(server_path, '.machine-id')
    machine_id = _read_machine_id(local_path)
    if not machine_id:
        machine_id = uuid.uuid4().hex
        _write_machine_id(local_path, machine_id)

    if os.access('/etc/machine-id', os.W_OK):
        if _write_machine_id('/etc/machine-id', machine_id):
            if os.path.isdir('/var/lib/dbus') and os.access('/var/lib/dbus', os.W_OK):
                _write_machine_id('/var/lib/dbus/machine-id', machine_id)
            return None

    return local_path

def _find_auth_token_path(server_path):
    candidates = [
        os.path.join(server_path, name) for name in AUTH_TOKEN_FILENAMES
    ]
    candidates.extend([
        os.path.join(server_path, '.auth', name) for name in AUTH_TOKEN_FILENAMES
    ])
    candidates.extend([
        os.path.join(server_path, 'auth', name) for name in AUTH_TOKEN_FILENAMES
    ])
    for path in candidates:
        if os.path.exists(path):
            return path
    return None

def _downloader_credential_candidates():
    base_path = Path(__file__).parent.parent.parent
    download_dir = os.path.join(base_path, 'downloads')
    home_dir = os.path.expanduser('~')
    candidates = []
    for filename in DOWNLOADER_CREDENTIALS_FILENAMES:
        candidates.append(os.path.join(download_dir, filename))
        candidates.append(os.path.join(home_dir, filename))
    return [path for path in candidates if os.path.exists(path)]

def _mirror_downloader_credentials(destination_dir):
    candidates = _downloader_credential_candidates()
    if not candidates:
        return None

    os.makedirs(destination_dir, exist_ok=True)
    auth_dir = os.path.join(destination_dir, '.auth')
    os.makedirs(auth_dir, exist_ok=True)

    copied_paths = []
    for source_path in candidates:
        for filename in DOWNLOADER_CREDENTIALS_FILENAMES:
            if os.path.basename(source_path) != filename:
                continue
            target_paths = [
                os.path.join(destination_dir, filename),
                os.path.join(auth_dir, filename)
            ]
            for target_path in target_paths:
                try:
                    shutil.copy2(source_path, target_path)
                    copied_paths.append(target_path)
                except Exception:
                    continue

    return copied_paths or None

def _template_files_present():
    base_path = Path(__file__).parent.parent.parent
    template_dir = os.path.join(base_path, 'servertemplate')
    return (
        os.path.exists(os.path.join(template_dir, 'HytaleServer.jar')) and
        os.path.exists(os.path.join(template_dir, 'Assets.zip'))
    )

def _should_request_auth_login(server_info):
    if not server_info:
        return False, 'server_not_ready'
    if server_info.get('auth_pending') and server_info.get('auth_url'):
        return False, 'already_pending'
    last_request = server_info.get('auth_login_requested_at', 0) or 0
    if time.time() - last_request < AUTH_LOGIN_COOLDOWN:
        return False, 'cooldown'
    return True, None

def request_auth_login(server_id, reason=None):
    if server_id not in _running_servers:
        return False, 'not_running'

    server_info = _running_servers[server_id]
    allowed, message = _should_request_auth_login(server_info)
    if not allowed:
        return False, message or 'not_allowed'

    ok = send_command(server_id, '/auth login device')
    if ok:
        server_info['auth_login_requested_at'] = time.time()
        server_info['auth_pending'] = True
        if reason:
            print(f"[Server {server_id}] Auth login device requested ({reason})")
    return ok, None if ok else 'send_failed'

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
        source_version_dir = None

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
            source_version_dir = template_dir

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
                            source_version_dir = potential_path
                            break

        # If files found, copy them
        if source_jar and source_assets:
            shutil.copy2(source_jar, os.path.join(server_path, 'HytaleServer.jar'))
            if source_aot:
                shutil.copy2(source_aot, os.path.join(server_path, 'HytaleServer.aot'))
            shutil.copy2(source_assets, os.path.join(server_path, 'Assets.zip'))
            if source_version_dir:
                _copy_version_file(source_version_dir, server_path)
            _mirror_downloader_credentials(server_path)
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
        startup_settings = read_startup_settings(server_id)

        if startup_settings.get('automatic_update'):
            if not copy_downloaded_files_to_server(server_id):
                print(f"Error applying automatic update for server {server_id}")

        # Verify files exist
        if not os.path.exists(jar_path):
            return False
        if not os.path.exists(assets_path):
            return False

        # Build Java command parts
        java_cmd_parts = ['java']

        # Add AOT cache if available
        aot_path = os.path.join(server_path, 'HytaleServer.aot')
        if startup_settings.get('leverage_aot_cache', True) and os.path.exists(aot_path):
            java_cmd_parts.extend(['-XX:AOTCache=HytaleServer.aot'])

        combined_args = " ".join([arg for arg in (java_args, startup_settings.get('jvm_args')) if arg])
        has_xms = bool(re.search(r'(^|\s)-Xms\S+', combined_args))
        has_xmx = bool(re.search(r'(^|\s)-Xmx\S+', combined_args))

        if startup_settings.get('min_ram_mb') and not has_xms:
            java_cmd_parts.append(f"-Xms{startup_settings['min_ram_mb']}M")
        if startup_settings.get('max_ram_mb') and not has_xmx:
            java_cmd_parts.append(f"-Xmx{startup_settings['max_ram_mb']}M")

        # Add custom Java args if provided
        if combined_args:
            java_cmd_parts.extend(shlex.split(combined_args))

        assets_file = startup_settings.get('asset_pack') or 'Assets.zip'
        if assets_file and not os.path.exists(os.path.join(server_path, assets_file)):
            assets_file = 'Assets.zip'

        # Add server jar and arguments
        java_cmd_parts.extend([
            '-jar', 'HytaleServer.jar',
            '--assets', assets_file,
            '--bind', f'0.0.0.0:{port}'
        ])

        machine_id_path = _ensure_persistent_machine_id(server_path)
        _mirror_downloader_credentials(server_path)

        auth_token_path = _find_auth_token_path(server_path)

        env = os.environ.copy()
        if machine_id_path:
            env['DBUS_MACHINE_ID_FILE'] = machine_id_path
        if startup_settings.get('game_profile'):
            env['GAME_PROFILE'] = startup_settings['game_profile']
        if startup_settings.get('auth_mode'):
            env['AUTH_MODE'] = startup_settings['auth_mode']
        env['AUTOMATIC_UPDATE'] = 'true' if startup_settings.get('automatic_update') else 'false'
        env['ALLOW_OP'] = 'true' if startup_settings.get('allow_op') else 'false'
        env['ACCEPT_EARLY_PLUGINS'] = 'true' if startup_settings.get('accept_early_plugins') else 'false'
        if startup_settings.get('asset_pack'):
            env['ASSET_PACK'] = startup_settings['asset_pack']
        env['ENABLE_BACKUPS'] = 'true' if startup_settings.get('enable_backups') else 'false'
        if startup_settings.get('backup_directory'):
            env['BACKUP_DIRECTORY'] = startup_settings['backup_directory']
        env['BACKUP_FREQUENCY'] = str(startup_settings.get('backup_frequency', 30))
        env['DISABLE_SENTRY'] = 'true' if startup_settings.get('disable_sentry') else 'false'
        if startup_settings.get('jvm_args'):
            env['JVM_ARGS'] = startup_settings['jvm_args']
        env['LEVERAGE_AHEAD_OF_TIME_CACHE'] = 'true' if startup_settings.get('leverage_aot_cache', True) else 'false'

        # Start server process with pipes for live console
        process = subprocess.Popen(
            java_cmd_parts,
            cwd=server_path,
            stdin=subprocess.PIPE,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            bufsize=1,
            universal_newlines=True,
            env=env
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
            'auth_persistence_index': 0,
            'auth_persistence_exhausted': False,
            'last_auth_payload': None,
            'auth_token_path': auth_token_path,
            'auth_persistence_verified': bool(auth_token_path),
            'auth_login_requested_at': 0
        }

        _running_servers[server_id] = server_info

        if auth_token_path:
            try:
                from models.server import Server
                Server.update_authentication(server_id, True, auth_token_path)
            except Exception as exc:
                print(f"[Server {server_id}] Failed to update auth status: {exc}")

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
        server_info['auth_persistence_exhausted'] = True
        return False

    persistence_type = types[index]
    server_info['auth_persistence_last'] = persistence_type
    server_info['auth_persistence_attempted'] = True
    print(f"[Server {server_id}] Setting auth persistence to '{persistence_type}'")
    send_command(server_id, f'/auth persistence {persistence_type}')
    return True

def _verify_auth_persistence(server_id):
    server_info = _running_servers.get(server_id)
    if not server_info:
        return

    server_path = server_info.get('server_path')
    if not server_path:
        return

    token_path = _find_auth_token_path(server_path)
    if not token_path:
        return

    server_info['auth_persistence_verified'] = True
    server_info['auth_token_path'] = token_path

    try:
        from models.server import Server
        Server.update_authentication(server_id, True, token_path)
    except Exception as exc:
        print(f"[Server {server_id}] Failed to update auth status: {exc}")

def _schedule_auth_verification(server_id, delay=3):
    timer = threading.Timer(delay, _verify_auth_persistence, args=(server_id,))
    timer.daemon = True
    timer.start()

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
    auth_success_pattern = re.compile(
        r'authentication\s+successful|successfully authenticated|logged in|successfully created game session',
        re.IGNORECASE
    )
    auth_ok_pattern = re.compile(
        r'(Mode:\s*(OAUTH|AUTHENTICATED|EXTERNAL_SESSION))|'
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
            if no_tokens_pattern.search(clean_line) and not auth_command_sent:
                auth_command_sent = True
                print(f"[Server {server_id}] No auth tokens detected, automatically running '/auth login device'")

                # Wait a moment for server to be ready
                time.sleep(1)

                # Send auth login device command
                ok, _ = request_auth_login(server_id, 'no_tokens')
                if not ok:
                    auth_command_sent = False

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
                if not server_info.get('auth_url') and not pending_auth_url:
                    pending_auth_url = f'https://accounts.hytale.com/device?user_code={pending_auth_code}'
                    server_info['auth_url'] = pending_auth_url
                    server_info['auth_pending'] = True

            # If we have URL, broadcast auth required event
            if pending_auth_url and server_info['auth_pending']:
                payload = {
                    'server_id': server_id,
                    'server_name': server_info.get('server_name', f'Server {server_id}'),
                    'url': pending_auth_url,
                    'code': pending_auth_code or 'See URL'
                }
                if payload != server_info.get('last_auth_payload'):
                    print(f"[WS] Emitting auth_required event for server {server_id}")
                    if socketio:
                        try:
                            socketio.emit('auth_required', payload)
                        except Exception as emit_error:
                            print(f"[WS] Error emitting auth_required: {emit_error}")
                    server_info['last_auth_payload'] = payload

                # Clear pending values after sending
                pending_auth_url = None
                pending_auth_code = None
            elif pending_auth_code and server_info['auth_pending'] and server_info.get('auth_url'):
                payload = {
                    'server_id': server_id,
                    'server_name': server_info.get('server_name', f'Server {server_id}'),
                    'url': server_info.get('auth_url'),
                    'code': pending_auth_code
                }
                if payload != server_info.get('last_auth_payload'):
                    print(f"[WS] Emitting auth_required event for server {server_id} (code update)")
                    if socketio:
                        try:
                            socketio.emit('auth_required', payload)
                        except Exception as emit_error:
                            print(f"[WS] Error emitting auth_required: {emit_error}")
                    server_info['last_auth_payload'] = payload
                pending_auth_code = None

            # Check for successful authentication
            if auth_success_pattern.search(clean_line) and server_info['auth_pending']:
                server_info['auth_pending'] = False
                server_info['auth_url'] = None
                server_info['auth_code'] = None
                auth_command_sent = False
                server_info['auth_checked'] = True
                server_info['last_auth_payload'] = None

                print(f"[Server {server_id}] Authentication successful, setting auth persistence")

                # Send persistence command
                time.sleep(1)
                if not server_info.get('auth_persistence_done'):
                    send_auth_persistence(server_id, server_info)
                    _schedule_auth_verification(server_id)

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
                server_info['auth_url'] = None
                server_info['auth_code'] = None
                server_info['last_auth_payload'] = None
                if not server_info.get('auth_checked'):
                    server_info['auth_checked'] = True
                    if socketio:
                        try:
                            socketio.emit('auth_success', {
                                'server_id': server_id
                            })
                        except Exception as emit_error:
                            print(f"[WS] Error emitting auth_success: {emit_error}")
                _schedule_auth_verification(server_id)
            elif auth_bad_pattern.search(clean_line) and not auth_command_sent:
                auth_command_sent = True
                print(f"[Server {server_id}] Auth status not valid, running '/auth login device'")
                time.sleep(1)
                ok, _ = request_auth_login(server_id, 'auth_status')
                if not ok:
                    auth_command_sent = False

            # Handle persistence errors and retries
            if persistence_unknown_pattern.search(clean_line) and server_info.get('auth_persistence_attempted') and not server_info.get('auth_persistence_done') and not server_info.get('auth_persistence_exhausted'):
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

def download_game_files(socketio=None, host_os=None):
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
        downloader_path = _get_downloader_path(host_os)
        download_dir = os.path.join(base_path, 'downloads')
        template_dir = os.path.join(base_path, 'servertemplate')
        download_zip_path = os.path.join(download_dir, 'hytale-download.zip')

        try:
            if os.path.exists(download_zip_path):
                os.remove(download_zip_path)
        except Exception:
            pass

        # Check if downloader exists
        if not os.path.exists(downloader_path):
            print("Error: Hytale downloader not found!")
            _download_status['complete'] = True
            _download_status['success'] = False
            _download_status['active'] = False
            _download_status['last_error'] = 'Hytale downloader not found'
            if socketio:
                socketio.emit('download_error', {
                    'error': 'Hytale downloader not found. Please reinstall the system.'
                })
            return False

        _ensure_downloader_executable(downloader_path, host_os)

        # Patterns to detect auth request and progress
        auth_url_pattern = re.compile(r'(https://oauth\.accounts\.hytale\.com/oauth2/device/verify\?user_code=\S+)')
        auth_code_pattern = re.compile(r'Authorization code:\s*([A-Za-z0-9]+)')
        progress_pattern = re.compile(r'\[([=\s]*)\]\s*([\d.]+)%\s*\(([^)]+)\)')
        version_pattern = re.compile(r'successfully downloaded.*\(version\s+([^)]+)\)')

        downloaded_version = None
        _download_status['max_attempts'] = MAX_DOWNLOAD_ATTEMPTS

        for attempt in range(1, MAX_DOWNLOAD_ATTEMPTS + 1):
            _download_status['attempt'] = attempt
            _download_status['details'] = f'Starting download attempt {attempt} of {MAX_DOWNLOAD_ATTEMPTS}...'
            _download_status['last_error'] = None

            cmd = [downloader_path, '-download-path', download_zip_path]

            process = subprocess.Popen(
                cmd,
                cwd=download_dir,
                stdout=subprocess.PIPE,
                stderr=subprocess.STDOUT,
                stdin=subprocess.PIPE,
                text=True,
                bufsize=1,
                universal_newlines=True
            )

            # Monitor output
            while True:
                line = process.stdout.readline()

                if not line:
                    break

                line = line.strip()
                if not line:
                    continue

                print(f"Downloader: {line}")

                url_match = auth_url_pattern.search(line)
                if url_match:
                    _download_status['auth_url'] = url_match.group(1)

                code_match = auth_code_pattern.search(line)
                if code_match:
                    _download_status['auth_code'] = code_match.group(1)

                if len(_download_status['messages']) < 100:
                    _download_status['messages'].append(line)

                progress_match = progress_pattern.search(line)
                if progress_match:
                    _download_status['percentage'] = float(progress_match.group(2))
                    _download_status['details'] = progress_match.group(3)
                    _download_status['auth_url'] = None
                    _download_status['auth_code'] = None

                version_match = version_pattern.search(line)
                if version_match:
                    downloaded_version = version_match.group(1)
                    print(f"Detected version: {downloaded_version}")

                if 'validating checksum' in line.lower():
                    _download_status['percentage'] = 99
                    _download_status['details'] = 'Almost done...'

            exit_code = process.wait()

            if exit_code == 0:
                break

            if exit_code == 3 and _template_files_present():
                _download_status['messages'].append('Server files already up to date.')
                _download_status['complete'] = True
                _download_status['success'] = True
                _download_status['active'] = False
                return True

            _download_status['last_error'] = f'Download failed (exit code {exit_code})'
            _download_status['messages'].append(_download_status['last_error'])

            if attempt < MAX_DOWNLOAD_ATTEMPTS:
                _download_status['details'] = f'Retrying in {DOWNLOAD_RETRY_DELAY}s...'
                time.sleep(DOWNLOAD_RETRY_DELAY)
                continue

            _download_status['details'] = 'Max attempts reached. Waiting for manual files...'
            _download_status['messages'].append('Waiting for manual file placement...')
            while not _template_files_present():
                time.sleep(10)
            _download_status['complete'] = True
            _download_status['success'] = True
            _download_status['active'] = False
            return True

        # Find the downloaded ZIP file
        zip_file_path = None

        if os.path.exists(download_zip_path):
            zip_file_path = download_zip_path

        if not zip_file_path and downloaded_version:
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
            _download_status['complete'] = True
            _download_status['success'] = False
            _download_status['active'] = False
            _download_status['last_error'] = 'Downloaded ZIP file not found'
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
            _download_status['complete'] = True
            _download_status['success'] = False
            _download_status['active'] = False
            _download_status['last_error'] = 'Required server files not found in ZIP'
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

        if not downloaded_version:
            downloaded_version, _ = get_latest_game_version(host_os)
        if downloaded_version:
            _write_version_file(os.path.join(template_dir, VERSION_FILENAME), downloaded_version)

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
        _download_status['last_error'] = None
        _download_status['auth_url'] = None
        _download_status['auth_code'] = None

        return True

    except Exception as e:
        print(f"Error downloading game files: {e}")
        _download_status['complete'] = True
        _download_status['success'] = False
        _download_status['active'] = False
        _download_status['last_error'] = str(e)
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
        _copy_version_file(template_dir, server_path)
        _mirror_downloader_credentials(server_path)

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

def _get_startup_settings_path(server_id):
    return os.path.join(get_server_path(server_id), 'startup_settings.json')

def _coerce_int(value):
    if value is None:
        return None
    if isinstance(value, bool):
        return None
    if isinstance(value, (int, float)):
        return int(value)
    if isinstance(value, str):
        cleaned = value.strip()
        if not cleaned:
            return None
        try:
            return int(float(cleaned))
        except ValueError:
            return None
    return None

def _merge_startup_settings(settings):
    merged = DEFAULT_STARTUP_SETTINGS.copy()
    if isinstance(settings, dict):
        merged.update(settings)

    min_ram = _coerce_int(merged.get('min_ram_mb'))
    max_ram = _coerce_int(merged.get('max_ram_mb'))
    if min_ram is not None and min_ram <= 0:
        min_ram = None
    if max_ram is not None and max_ram <= 0:
        max_ram = None
    if min_ram is not None and max_ram is not None and max_ram < min_ram:
        max_ram = min_ram
    merged['min_ram_mb'] = min_ram
    merged['max_ram_mb'] = max_ram

    auth_mode = str(merged.get('auth_mode', '')).strip().lower()
    if auth_mode not in ('authenticated', 'offline'):
        auth_mode = DEFAULT_STARTUP_SETTINGS['auth_mode']
    merged['auth_mode'] = auth_mode

    merged['game_profile'] = str(merged.get('game_profile', '') or '').strip()
    merged['asset_pack'] = str(merged.get('asset_pack', '') or '').strip() or DEFAULT_STARTUP_SETTINGS['asset_pack']
    merged['backup_directory'] = str(merged.get('backup_directory', '') or '').strip()
    merged['jvm_args'] = str(merged.get('jvm_args', '') or '').strip()

    try:
        merged['backup_frequency'] = max(1, int(merged.get('backup_frequency', DEFAULT_STARTUP_SETTINGS['backup_frequency'])))
    except (TypeError, ValueError):
        merged['backup_frequency'] = DEFAULT_STARTUP_SETTINGS['backup_frequency']

    for key in (
        'automatic_update',
        'allow_op',
        'accept_early_plugins',
        'enable_backups',
        'disable_sentry',
        'leverage_aot_cache'
    ):
        merged[key] = bool(merged.get(key, DEFAULT_STARTUP_SETTINGS[key]))

    return merged

def read_startup_settings(server_id):
    path = _get_startup_settings_path(server_id)
    if not os.path.isfile(path):
        return _merge_startup_settings({})
    try:
        with open(path, 'r', encoding='utf-8') as handle:
            data = json.load(handle)
        return _merge_startup_settings(data)
    except Exception as exc:
        print(f"Error reading startup settings for server {server_id}: {exc}")
        return _merge_startup_settings({})

def write_startup_settings(server_id, settings):
    path = _get_startup_settings_path(server_id)
    merged = _merge_startup_settings(settings or {})
    try:
        with open(path, 'w', encoding='utf-8') as handle:
            json.dump(merged, handle, indent=2, ensure_ascii=True)
            handle.write('\n')
        return merged
    except Exception as exc:
        print(f"Error writing startup settings for server {server_id}: {exc}")
        return None

DEFAULT_BACKUP_SETTINGS = {
    'mode': 'worlds',
    'selected_worlds': [],
    'schedule_enabled': False,
    'interval_value': 24,
    'interval_unit': 'hours',
    'backup_on_start': False,
    'last_backup_at': None
}

def _get_backup_root(server_id):
    return os.path.join(get_server_path(server_id), 'Backup')

def _ensure_backup_dirs(server_id):
    root = _get_backup_root(server_id)
    for folder in ('Universe', 'World', 'Worlds'):
        os.makedirs(os.path.join(root, folder), exist_ok=True)
    return root

def _get_backup_settings_path(server_id):
    return os.path.join(get_server_path(server_id), 'backup_settings.json')

def _sanitize_name(name):
    cleaned = re.sub(r'[^A-Za-z0-9_-]+', '_', name.strip())
    return cleaned or 'world'

def _format_backup_timestamp(ts=None):
    return time.strftime('%d-%m-%Y-%H-%M', time.localtime(ts or time.time()))

def _zip_directory(source_dir, root_dir, output_path):
    with zipfile.ZipFile(output_path, 'w', compression=zipfile.ZIP_DEFLATED) as zipf:
        for root, _, files in os.walk(source_dir):
            for filename in files:
                file_path = os.path.join(root, filename)
                arcname = os.path.relpath(file_path, root_dir)
                zipf.write(file_path, arcname)

def _merge_backup_settings(settings):
    merged = DEFAULT_BACKUP_SETTINGS.copy()
    if isinstance(settings, dict):
        merged.update(settings)
    if merged['interval_unit'] not in ('hours', 'days'):
        merged['interval_unit'] = 'hours'
    try:
        merged['interval_value'] = max(1, int(merged['interval_value']))
    except (TypeError, ValueError):
        merged['interval_value'] = DEFAULT_BACKUP_SETTINGS['interval_value']
    merged['schedule_enabled'] = bool(merged.get('schedule_enabled', False))
    merged['backup_on_start'] = bool(merged.get('backup_on_start', False))
    if not isinstance(merged.get('selected_worlds'), list):
        merged['selected_worlds'] = []
    return merged

def read_backup_settings(server_id):
    path = _get_backup_settings_path(server_id)
    if not os.path.isfile(path):
        return _merge_backup_settings({})
    try:
        with open(path, 'r', encoding='utf-8') as handle:
            data = json.load(handle)
        return _merge_backup_settings(data)
    except Exception as exc:
        print(f"Error reading backup settings for server {server_id}: {exc}")
        return _merge_backup_settings({})

def write_backup_settings(server_id, settings):
    path = _get_backup_settings_path(server_id)
    merged = _merge_backup_settings(settings or {})
    try:
        with open(path, 'w', encoding='utf-8') as handle:
            json.dump(merged, handle, indent=2, ensure_ascii=True)
            handle.write('\n')
        return merged
    except Exception as exc:
        print(f"Error writing backup settings for server {server_id}: {exc}")
        return None

def list_worlds(server_id):
    worlds_root = os.path.join(get_server_path(server_id), 'universe', 'worlds')
    if not os.path.isdir(worlds_root):
        return []
    worlds = []
    for entry in sorted(os.listdir(worlds_root)):
        full_path = os.path.join(worlds_root, entry)
        if os.path.isdir(full_path):
            worlds.append(entry)
    return worlds

def create_backup(server_id, backup_type, selected_worlds=None, update_last=False):
    server_path = get_server_path(server_id)
    universe_dir = os.path.join(server_path, 'universe')
    worlds_dir = os.path.join(universe_dir, 'worlds')
    backup_root = _ensure_backup_dirs(server_id)
    timestamp = _format_backup_timestamp()
    created = []

    if backup_type == 'universe':
        if not os.path.isdir(universe_dir):
            raise FileNotFoundError('Universe directory not found.')
        dest_dir = os.path.join(backup_root, 'Universe')
        filename = f'universe-{timestamp}.zip'
        output_path = os.path.join(dest_dir, filename)
        _zip_directory(universe_dir, server_path, output_path)
        created.append(output_path)
    elif backup_type == 'worlds':
        if not os.path.isdir(worlds_dir):
            raise FileNotFoundError('Worlds directory not found.')
        dest_dir = os.path.join(backup_root, 'World')
        filename = f'worlds-{timestamp}.zip'
        output_path = os.path.join(dest_dir, filename)
        _zip_directory(worlds_dir, server_path, output_path)
        created.append(output_path)
    elif backup_type == 'world':
        if not selected_worlds:
            raise ValueError('No worlds selected for backup.')
        if not os.path.isdir(worlds_dir):
            raise FileNotFoundError('Worlds directory not found.')
        dest_dir = os.path.join(backup_root, 'Worlds')
        for world_name in selected_worlds:
            world_dir = os.path.join(worlds_dir, world_name)
            if not os.path.isdir(world_dir):
                continue
            safe_name = _sanitize_name(world_name)
            filename = f'{safe_name}-{timestamp}.zip'
            output_path = os.path.join(dest_dir, filename)
            _zip_directory(world_dir, server_path, output_path)
            created.append(output_path)
        if not created:
            raise FileNotFoundError('Selected worlds not found.')
    else:
        raise ValueError('Invalid backup type.')

    if update_last and created:
        settings = read_backup_settings(server_id)
        settings['last_backup_at'] = time.time()
        write_backup_settings(server_id, settings)

    return created

def _parse_backup_name(name):
    if not name.endswith('.zip'):
        return None, None
    base = name[:-4]
    parts = base.split('-')
    if len(parts) < 6:
        return base, None
    timestamp = '-'.join(parts[-5:])
    label = '-'.join(parts[:-5])
    return label, timestamp

def list_backups(server_id):
    backup_root = _ensure_backup_dirs(server_id)
    results = []
    for folder, backup_type in (('Universe', 'universe'), ('World', 'worlds'), ('Worlds', 'world')):
        folder_path = os.path.join(backup_root, folder)
        if not os.path.isdir(folder_path):
            continue
        for entry in sorted(os.listdir(folder_path)):
            if not entry.endswith('.zip'):
                continue
            full_path = os.path.join(folder_path, entry)
            label, timestamp = _parse_backup_name(entry)
            results.append({
                'path': os.path.join(folder, entry),
                'type': backup_type,
                'label': label,
                'timestamp': timestamp,
                'created_at': os.path.getmtime(full_path),
                'size': os.path.getsize(full_path)
            })
    results.sort(key=lambda item: item['created_at'], reverse=True)
    return results

def _safe_extract(zip_file, destination):
    dest_root = os.path.abspath(destination)
    for member in zip_file.infolist():
        target_path = os.path.abspath(os.path.join(dest_root, member.filename))
        if not target_path.startswith(dest_root + os.sep):
            raise ValueError('Invalid archive entry.')
    zip_file.extractall(dest_root)

def _infer_world_from_zip(zip_file):
    for name in zip_file.namelist():
        parts = name.replace('\\', '/').split('/')
        if len(parts) >= 3 and parts[0] == 'universe' and parts[1] == 'worlds':
            if parts[2]:
                return parts[2]
    return None

def restore_backup(server_id, relative_path):
    backup_root = _get_backup_root(server_id)
    clean_rel = relative_path.replace('\\', os.sep).replace('/', os.sep)
    full_path = os.path.abspath(os.path.join(backup_root, clean_rel))
    if not full_path.startswith(os.path.abspath(backup_root) + os.sep):
        raise ValueError('Invalid backup path.')
    if not os.path.isfile(full_path):
        raise FileNotFoundError('Backup file not found.')

    parts = clean_rel.split(os.sep)
    category = parts[0] if parts else ''
    server_path = get_server_path(server_id)
    universe_dir = os.path.join(server_path, 'universe')
    worlds_dir = os.path.join(universe_dir, 'worlds')

    target_dir = None
    with zipfile.ZipFile(full_path, 'r') as zipf:
        if category == 'Universe':
            target_dir = universe_dir
        elif category == 'World':
            target_dir = worlds_dir
        elif category == 'Worlds':
            world_name = _infer_world_from_zip(zipf)
            if not world_name:
                raise ValueError('World name not found in backup.')
            target_dir = os.path.join(worlds_dir, world_name)
        else:
            raise ValueError('Unknown backup category.')

        if target_dir and os.path.exists(target_dir):
            shutil.rmtree(target_dir)

        _safe_extract(zipf, server_path)

    return True

def _backup_due(settings):
    if not settings.get('schedule_enabled'):
        return False
    interval_value = settings.get('interval_value', 24)
    interval_unit = settings.get('interval_unit', 'hours')
    seconds = interval_value * 3600 if interval_unit == 'hours' else interval_value * 86400
    last_backup = settings.get('last_backup_at')
    if not last_backup:
        return True
    return (time.time() - float(last_backup)) >= seconds

def process_scheduled_backup(server_id):
    settings = read_backup_settings(server_id)
    if not _backup_due(settings):
        return []
    created = create_backup(
        server_id,
        settings.get('mode', 'worlds'),
        settings.get('selected_worlds', []),
        update_last=True
    )
    return created

def run_startup_backup(server_id):
    settings = read_backup_settings(server_id)
    if not settings.get('backup_on_start'):
        return []
    try:
        created = create_backup(
            server_id,
            settings.get('mode', 'worlds'),
            settings.get('selected_worlds', []),
            update_last=True
        )
        return created
    except FileNotFoundError as exc:
        print(f"Startup backup skipped: {exc}")
        return []
