// Console JavaScript
// Handles WebSocket connection, console output, and command input

const socket = io();
const consoleOutput = document.getElementById('consoleOutput');
const commandInput = document.getElementById('commandInput');
const sendBtn = document.getElementById('sendBtn');
const startBtn = document.getElementById('startBtn');
const stopBtn = document.getElementById('stopBtn');
const restartBtn = document.getElementById('restartBtn');
const statusBadge = document.getElementById('statusBadge');
const authModal = document.getElementById('authModal');

// Command history
const commandHistory = [];
let historyIndex = -1;

// Join console room on connect
socket.on('connect', () => {
    console.log('Connected to server');
    socket.emit('join_console', { server_id: SERVER_ID });
});

socket.on('disconnect', () => {
    console.log('Disconnected from server');
});

// Console history
socket.on('console_history', (data) => {
    consoleOutput.innerHTML = '';
    if (data.messages && data.messages.length > 0) {
        data.messages.forEach(msg => {
            appendConsoleMessage(msg, 'stdout');
        });
    } else {
        appendConsoleMessage('Console output will appear here...', 'system');
    }
    scrollToBottom();
});

// Console output
socket.on('console_output', (data) => {
    if (data.server_id === SERVER_ID) {
        appendConsoleMessage(data.message, data.type);
        scrollToBottom();
    }
});

// Server status updates
socket.on('server_status', (data) => {
    if (data.server_id === SERVER_ID) {
        updateStatus(data.status, data.is_running);
    }
});

socket.on('server_status_change', (data) => {
    if (data.server_id === SERVER_ID) {
        updateStatus(data.status);
    }
});

// Authentication required
socket.on('auth_required', (data) => {
    if (data.server_id === SERVER_ID) {
        showAuthModal(data.url, data.code);
    }
});

// Authentication success
socket.on('auth_success', (data) => {
    if (data.server_id === SERVER_ID) {
        hideAuthModal();
        appendConsoleMessage('✓ Authentication successful', 'system');
    }
});

// Send command
function sendCommand() {
    const command = commandInput.value.trim();
    if (!command) return;

    socket.emit('console_command', {
        server_id: SERVER_ID,
        command: command
    });

    // Add to history
    commandHistory.push(command);
    historyIndex = commandHistory.length;

    // Clear input
    commandInput.value = '';
}

// Event listeners
sendBtn.addEventListener('click', sendCommand);

commandInput.addEventListener('keydown', (e) => {
    if (e.key === 'Enter') {
        e.preventDefault();
        sendCommand();
    } else if (e.key === 'ArrowUp') {
        e.preventDefault();
        if (historyIndex > 0) {
            historyIndex--;
            commandInput.value = commandHistory[historyIndex];
        }
    } else if (e.key === 'ArrowDown') {
        e.preventDefault();
        if (historyIndex < commandHistory.length - 1) {
            historyIndex++;
            commandInput.value = commandHistory[historyIndex];
        } else {
            historyIndex = commandHistory.length;
            commandInput.value = '';
        }
    }
});

// Start server
startBtn.addEventListener('click', async () => {
    try {
        const response = await fetch(`/api/server/${SERVER_ID}/start`, {
            method: 'POST'
        });

        const data = await response.json();

        if (data.success) {
            updateStatus('starting');
        } else {
            alert(data.error || 'Failed to start server');
        }
    } catch (error) {
        console.error('Error starting server:', error);
        alert('An error occurred while starting the server');
    }
});

// Stop server
stopBtn.addEventListener('click', async () => {
    try {
        const response = await fetch(`/api/server/${SERVER_ID}/stop`, {
            method: 'POST'
        });

        const data = await response.json();

        if (data.success) {
            updateStatus('stopping');
        } else {
            alert(data.error || 'Failed to stop server');
        }
    } catch (error) {
        console.error('Error stopping server:', error);
        alert('An error occurred while stopping the server');
    }
});

// Restart server
restartBtn.addEventListener('click', async () => {
    try {
        const response = await fetch(`/api/server/${SERVER_ID}/restart`, {
            method: 'POST'
        });

        const data = await response.json();

        if (data.success) {
            updateStatus('restarting');
        } else {
            alert(data.error || 'Failed to restart server');
        }
    } catch (error) {
        console.error('Error restarting server:', error);
        alert('An error occurred while restarting the server');
    }
});

// Helper functions
function appendConsoleMessage(message, type) {
    const line = document.createElement('div');
    line.className = 'console-line';

    if (type === 'error' || type === 'stderr') {
        line.classList.add('error');
    } else if (type === 'system') {
        line.classList.add('system');
    } else if (type === 'command') {
        line.classList.add('command');
    }

    line.textContent = message;
    consoleOutput.appendChild(line);
}

function scrollToBottom() {
    consoleOutput.scrollTop = consoleOutput.scrollHeight;
}

function updateStatus(status, isRunning) {
    statusBadge.setAttribute('data-status', status);
    statusBadge.textContent = status;

    // Update buttons
    if (status === 'online' || (isRunning !== undefined && isRunning)) {
        startBtn.style.display = 'none';
        stopBtn.style.display = 'inline-flex';
        restartBtn.style.display = 'inline-flex';
        commandInput.disabled = false;
        sendBtn.disabled = false;
    } else {
        startBtn.style.display = 'inline-flex';
        stopBtn.style.display = 'none';
        restartBtn.style.display = 'none';
        commandInput.disabled = true;
        sendBtn.disabled = true;
    }
}

function showAuthModal(url, code) {
    document.getElementById('authUrl').href = url;
    document.getElementById('authUrl').textContent = url;
    document.getElementById('authCode').textContent = code;
    authModal.classList.add('active');
}

function hideAuthModal() {
    authModal.classList.remove('active');
}

// Initialize button states
if (!IS_RUNNING) {
    startBtn.style.display = 'inline-flex';
    stopBtn.style.display = 'none';
    restartBtn.style.display = 'none';
    commandInput.disabled = true;
    sendBtn.disabled = true;
} else {
    startBtn.style.display = 'none';
    stopBtn.style.display = 'inline-flex';
    restartBtn.style.display = 'inline-flex';
    commandInput.disabled = false;
    sendBtn.disabled = false;
}

// Leave console on page unload
window.addEventListener('beforeunload', () => {
    socket.emit('leave_console', { server_id: SERVER_ID });
});
