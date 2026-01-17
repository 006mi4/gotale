# Hytale Server Manager

This project is a Windows and Linux web system for running and managing multiple Hytale servers from a single dashboard.

## Features

- 🎮 **Multi-server management** - Run up to 100 Hytale servers at once
- 🌐 **Web dashboard** - Clean interface for control and monitoring
- 📊 **Live console** - Real-time output and command input
- 🔒 **Secure login** - Password-protected access with bcrypt
- 🔄 **One-command updates** - Update the system via Git
- ⚡ **Live status** - WebSocket updates for server states
- 🔑 **Hytale auth flow** - Device-code authentication built in

## Requirements

- **Windows** 10 or higher or **Linux** (modern distro)
- **Python** 3.9 or higher
- **Java** 25 or higher (for running Hytale servers)
- **Git** (for system updates)
- **Internet connection** (for initial setup and updates)

## Installation

This repository contains only the `system/` folder. The installer scripts (`install.bat`, `start.bat`, `install.sh`, `start.sh`, etc.) are distributed separately.

1. Join the Discord to download the installer files and data:
   https://discord.com/invite/MGpDcfEVkg
2. Download the installer that matches your OS:
   - Windows: `install.bat`
   - Linux: `install.sh`
3. Run the installer:
   - Windows: `install.bat` (Administrator)
   - Linux: `chmod +x install.sh && ./install.sh`
4. Follow the on-screen instructions
5. The installer will:
   - Check required dependencies
   - Download Hytale Downloader
   - Clone the system from Git
   - Install Python dependencies
   - Initialize the database

## Usage

### Starting the System

Windows:
```batch
start.bat
```

Linux:
```bash
./start.sh
```

The web interface will be available at `http://localhost:5000`.

### First-Time Setup

1. Open `http://localhost:5000/setup` (opens automatically)
2. Create your administrator account:
   - Username (3-20 characters)
   - Email address
   - Password (minimum 8 characters)
3. Select your Host OS
4. Click "Complete Setup"

### Creating a Server

1. Log in to the dashboard
2. Enter a server name
3. Choose a port (default: 5520)
4. Click "Create Server"
5. The system will:
   - Create the server directory
   - Copy game files (or prompt for download)
   - Add the server to the database

### Managing Servers

- **Start Server**: Click "Start" button
- **Stop Server**: Click "Stop" button
- **View Console**: Click "Console" to access live output
- **Send Commands**: Type in console input and press Enter
- **Delete Server**: Click "Delete" (requires confirmation)

### Server Console

The console view provides:
- **Live Output**: Real-time server logs
- **Command Input**: Send commands directly to the server
- **Command History**: Use Up/Down arrow keys to navigate
- **Status Controls**: Start, Stop, Restart buttons
- **Authentication Flow**: Automatic Hytale account authentication

### Hytale Authentication

First-time server start requires Hytale account authentication:

1. Start the server
2. A modal will appear with:
   - Authentication URL
   - Device code
3. Open the URL in your browser
4. Enter the code
5. Complete authentication
6. The system automatically sends `/auth persistence encrypted`
7. Future starts won't require authentication

### Stopping the System

Windows:
```batch
stop.bat
```

Linux:
```bash
./stop.sh
```

Stops the web interface and all running servers.

### Restarting the System

Windows:
```batch
restart.bat
```

Linux:
```bash
./restart.sh
```

Stops everything, waits 3 seconds, then starts again.

### Updating the System

Windows:
```batch
update.bat
```

Linux:
```bash
./update.sh
```

The update script will:
1. Check for updates from Git
2. Display number of available updates
3. Ask for confirmation
4. Create a backup
5. Pull updates from Git
6. Update Python dependencies
7. Display changelog (if available)
8. Ask to restart

## Configuration

### Database Location

`system/database.db` - SQLite database containing:
- User accounts
- Server configurations
- System settings

### Server Locations

Each server has its own directory:
```
servers/
├── server_1/
│   ├── HytaleServer.jar
│   ├── HytaleServer.aot
│   ├── Assets.zip
│   ├── universe/
│   └── logs/
├── server_2/
└── ...
```

### System Configuration

`system/config.json` - System configuration:
```json
{
    "version": "1.0.0",
    "git_repo_url": "https://github.com/006mi4/gotale.git",
    "web_interface": {
        "host": "0.0.0.0",
        "port": 5000
    },
    ...
}
```

## Port Management

- **Default Port**: 5520 (Hytale default)
- **Port Range**: 1024-65535
- **Protocol**: UDP (QUIC)
- **Automatic Checking**: System verifies port availability before creating servers
- **Suggestions**: If port is in use, system suggests next available port

## Troubleshooting

### Java Not Found

**Problem**: "Java 25 or higher is not installed"

**Solution**:
1. Download Java 25 from [Adoptium](https://adoptium.net/temurin/releases/?version=25)
2. Install Java
3. Restart the system

### Port Already in Use

**Problem**: "Port XXXX is already in use"

**Solution**:
1. Use the suggested port
2. Or choose a different port manually
3. Check for other applications using the port

### Server Won't Start

**Problem**: Server status stuck on "starting"

**Solution**:
1. Check Java installation
2. Verify game files exist
3. Check console for error messages
4. Ensure port is not blocked by firewall

### Authentication Timeout

**Problem**: "Device code expired"

**Solution**:
1. Restart the server
2. A new code will be generated
3. Complete authentication within 15 minutes

### Web Interface Not Loading

**Problem**: Can't access `http://localhost:5000`

**Solution**:
1. Check if system is running (`start.bat` or `./start.sh`)
2. Verify Python is installed
3. Check firewall settings
4. Try `http://127.0.0.1:5000` instead

## Security

- **Password Hashing**: Bcrypt with salt
- **Session Management**: Secure Flask sessions
- **Input Validation**: All user inputs are validated
- **Port Binding**: Web interface binds to localhost by default
- **File Restrictions**: Server operations limited to designated directories

## API Endpoints

### Authentication
- `GET /setup` - Initial setup page
- `POST /setup` - Create administrator account
- `GET /login` - Login page
- `POST /login` - Authenticate user
- `GET /logout` - Log out user

### Dashboard
- `GET /dashboard` - Server list
- `POST /api/server/create` - Create new server
- `DELETE /api/server/<id>/delete` - Delete server
- `GET /api/port-check/<port>` - Check port availability

### Server Control
- `GET /server/<id>` - Console view
- `POST /api/server/<id>/start` - Start server
- `POST /api/server/<id>/stop` - Stop server
- `POST /api/server/<id>/restart` - Restart server
- `GET /api/server/<id>/status` - Get server status

### WebSocket Events
- `join_console` - Join console room
- `leave_console` - Leave console room
- `console_command` - Send command to server
- `console_output` - Receive console output (broadcast)
- `auth_required` - Authentication needed (broadcast)
- `server_status_change` - Status update (broadcast)

## File Structure

```
Hytaleserver/
├── install.bat           # Installer (distributed via Discord)
├── install.sh            # Linux installer (distributed via Discord)
├── start.bat            # Start system (distributed via Discord)
├── start.sh             # Start system (Linux)
├── stop.bat             # Stop system (distributed via Discord)
├── stop.sh              # Stop system (Linux)
├── restart.bat          # Restart system (distributed via Discord)
├── restart.sh           # Restart system (Linux)
├── update.bat           # Update system (distributed via Discord)
├── update.sh            # Update system (Linux)
├── system/              # System files (this Git repo)
│   ├── app.py
│   ├── init_db.py
│   ├── requirements.txt
│   ├── config.json
│   ├── database.db
│   ├── routes/
│   ├── models/
│   ├── utils/
│   ├── static/
│   └── templates/
├── servers/             # Server instances
├── downloads/           # Downloaded files
└── logs/                # System logs
```

## Development

### Adding Features

1. Modify files in `system/` directory
2. Test locally
3. Commit changes to Git
4. Users update via `update.bat`

### Database Schema

See `system/init_db.py` for complete schema.

Tables:
- `users` - User accounts
- `servers` - Server configurations
- `server_logs` - Console history
- `settings` - System settings

### WebSocket Events

See `system/routes/console.py` for WebSocket event handlers.

## Credits

- **Hytale** - Hypixel Studios
- **Flask** - Web framework
- **Flask-SocketIO** - WebSocket support
- **Adoptium** - Java distribution

## License

This is a community project for managing Hytale servers. Not affiliated with Hypixel Studios.

## Support

Join the Discord for downloads, support, and to share feature requests:
https://discord.com/invite/MGpDcfEVkg

## Version History

### v1.0.0 (Current)
- Initial release
- Multi-server management
- Web-based dashboard
- Live console with WebSocket
- Hytale authentication integration
- Automatic updates via Git
