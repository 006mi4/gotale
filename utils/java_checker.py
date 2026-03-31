"""
Java version checker utility
Checks if Java 25 or higher is installed
"""

import subprocess
import re

def check_java():
    """
    Check if Java is installed and get version information

    Returns:
        dict: {
            'installed': bool,
            'version': int or None,
            'version_string': str or None,
            'path': str or None
        }
    """
    try:
        result = subprocess.run(
            ['java', '--version'],
            capture_output=True,
            text=True,
            timeout=5
        )

        output = result.stdout

        # Parse version number - supports both OpenJDK and Oracle Java
        # Patterns:
        # - "openjdk 25.0.1" (OpenJDK)
        # - "java 25.0.1 2025-10-21" (Oracle Java)
        match = re.search(r'(?:openjdk|java)\s+(\d+)\.', output, re.IGNORECASE)
        if match:
            version = int(match.group(1))
            return {
                'installed': version >= 25,
                'version': version,
                'version_string': output.split('\n')[0] if output else None,
                'path': 'java'
            }

        return {
            'installed': False,
            'version': None,
            'version_string': None,
            'path': None
        }

    except FileNotFoundError:
        return {
            'installed': False,
            'version': None,
            'version_string': None,
            'path': None
        }
    except subprocess.TimeoutExpired:
        return {
            'installed': False,
            'version': None,
            'version_string': 'Timeout',
            'path': None
        }
    except Exception as e:
        return {
            'installed': False,
            'version': None,
            'version_string': f'Error: {str(e)}',
            'path': None
        }

def get_java_download_url():
    """
    Get the download URL for Java 25

    Returns:
        str: Download URL for Oracle Java 25
    """
    return "https://www.oracle.com/de/java/technologies/downloads/#jdk25-windows"

if __name__ == '__main__':
    # Test the checker
    result = check_java()
    print(f"Java installed: {result['installed']}")
    if result['version']:
        print(f"Version: {result['version']}")
        print(f"Version string: {result['version_string']}")
    else:
        print("Java not found or version too old (< 25)")
        print(f"Download from: {get_java_download_url()}")
