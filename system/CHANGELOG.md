# Changelog

All notable changes to this project will be documented in this file.

## [1.0.0] - 2026-01-14

### Added
- Initial release of Hytale Server Manager
- Web-based dashboard for server management
- Support for up to 100 Hytale servers
- Live console with WebSocket support
- Real-time server status updates
- Automatic Hytale account authentication
- Port availability checking
- Server creation, deletion, start, stop, restart
- Command input with history (arrow keys)
- Secure authentication with bcrypt
- Session management with Flask-Login
- SQLite database for persistence
- Automatic system updates via Git
- Windows batch scripts for easy management:
  - install.bat - Complete system installation
  - start.bat - Start the web interface
  - stop.bat - Stop all servers and web interface
  - restart.bat - Restart the system
  - update.bat - Update from Git repository
- Modern dark theme UI with gold accents
- Responsive design
- Java 25 detection and warnings
- Server file management
- Console output buffering (1000 lines)
- Background server monitoring thread

### Features
- **Multi-Server Support**: Create and manage up to 100 Hytale servers
- **Web Interface**: Accessible at http://localhost:5000
- **Live Console**: Real-time console output via WebSockets
- **Command History**: Navigate command history with arrow keys
- **Status Updates**: Real-time server status via WebSocket broadcasts
- **Hytale Auth**: Automatic OAuth device flow authentication
- **Port Management**: Automatic port availability checking
- **Security**: Bcrypt password hashing, secure sessions
- **Auto-Updates**: Git-based system updates with backup

### Technical Stack
- Python 3.9+
- Flask 3.0.0
- Flask-SocketIO 5.3.5
- SQLite database
- HTML/CSS/JavaScript frontend
- WebSocket for real-time communication

### Requirements
- Windows 10 or higher
- Python 3.9 or higher
- Java 25 or higher (for Hytale servers)
- Git for updates
- Internet connection for setup

---

## Future Releases

### [Planned]
- Multi-user support with permissions
- Server backups and restore functionality
- Scheduled server restarts
- Resource monitoring (CPU, RAM per server)
- Plugin management
- RCON integration
- Mobile-responsive design improvements
- Dark/light theme toggle
- Server templates (pre-configured setups)
- Automatic update notifications
- Server groups/categories
- Bulk server operations
- Advanced logging and analytics
- Email notifications
- Discord webhook integration
