"""
Port availability checker utility
Checks if UDP ports are available (Hytale uses UDP/QUIC)
"""

import socket

def is_port_available(port, host='0.0.0.0'):
    """
    Check if a UDP port is available

    Args:
        port (int): Port number to check
        host (str): Host address (default: 0.0.0.0)

    Returns:
        bool: True if port is available, False otherwise
    """
    try:
        # Create UDP socket (Hytale uses QUIC over UDP)
        sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        sock.bind((host, port))
        sock.close()
        return True
    except OSError:
        return False
    except Exception:
        return False

def get_next_available_port(start_port=5520, max_attempts=1000):
    """
    Find the next available port starting from start_port

    Args:
        start_port (int): Port to start checking from (default: 5520)
        max_attempts (int): Maximum number of ports to try (default: 1000)

    Returns:
        int or None: Next available port number, or None if no port found
    """
    port = start_port
    attempts = 0

    while attempts < max_attempts:
        if is_port_available(port):
            return port
        port += 1
        attempts += 1

    return None

def get_available_ports_in_range(start_port=5520, end_port=5620):
    """
    Get all available ports in a range

    Args:
        start_port (int): Start of port range
        end_port (int): End of port range

    Returns:
        list: List of available port numbers
    """
    available_ports = []

    for port in range(start_port, end_port + 1):
        if is_port_available(port):
            available_ports.append(port)

    return available_ports

if __name__ == '__main__':
    # Test the checker
    print(f"Port 5520 available: {is_port_available(5520)}")
    print(f"Next available port from 5520: {get_next_available_port(5520)}")

    # Test first 10 ports
    print("\nFirst 10 ports starting from 5520:")
    for i in range(10):
        port = 5520 + i
        status = "available" if is_port_available(port) else "in use"
        print(f"  Port {port}: {status}")
