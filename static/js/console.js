// Console JavaScript
// Handles server control buttons and status updates

const socket = io();
const startBtn = document.getElementById('startBtn');
const stopBtn = document.getElementById('stopBtn');
const restartBtn = document.getElementById('restartBtn');
const statusBadge = document.getElementById('statusBadge');
const consoleOutput = document.getElementById('consoleOutput');
const consoleInput = document.getElementById('consoleInput');
const authModal = document.getElementById('authModal');
const authUrl = document.getElementById('authUrl');
const authCode = document.getElementById('authCode');
const authCloseBtn = document.getElementById('authCloseBtn');

let commandHistory = [];
let historyIndex = -1;

// Join console room on connect (for status updates)
socket.on('connect', () => {
    console.log('Connected to WebSocket server');
    socket.emit('join_console', { server_id: SERVER_ID });
});

socket.on('disconnect', () => {
    console.log('Disconnected from server');
});

socket.on('error', (data) => {
    if (!data || !data.message) return;
    appendConsoleLine(`[Error] ${data.message}`, 'error');
});

window.addEventListener('beforeunload', () => {
    socket.emit('leave_console', { server_id: SERVER_ID });
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

// Console history
socket.on('console_history', (data) => {
    if (data.server_id !== SERVER_ID || !consoleOutput) return;
    consoleOutput.innerHTML = '';
    data.messages.forEach((line) => {
        appendConsoleLine(line);
    });
    scrollConsoleToBottom();
});

// Live console output
socket.on('console_output', (data) => {
    if (data.server_id !== SERVER_ID || !consoleOutput) return;
    appendConsoleLine(data.message, data.type);
    scrollConsoleToBottom(true);
});

// Auth modal
socket.on('auth_required', (data) => {
    if (data.server_id !== SERVER_ID) return;
    if (authUrl) {
        const url = data.url || '';
        authUrl.textContent = url;
        authUrl.setAttribute('href', url || '#');
    }
    if (authCode) authCode.textContent = data.code || '';
    if (authModal) authModal.classList.add('active');
});

socket.on('auth_success', (data) => {
    if (data.server_id !== SERVER_ID) return;
    if (authModal) authModal.classList.remove('active');
});

if (authCloseBtn) {
    authCloseBtn.addEventListener('click', () => {
        if (authModal) authModal.classList.remove('active');
    });
}

// Start server
startBtn.addEventListener('click', async () => {
    try {
        startBtn.disabled = true;
        startBtn.textContent = 'Starting...';

        const response = await fetch(`/api/server/${SERVER_ID}/start`, {
            method: 'POST'
        });

        const data = await response.json();

        if (data.success) {
            updateStatus('starting');
            // Reload page after a moment to update UI
            setTimeout(() => location.reload(), 2000);
        } else {
            alert(data.error || 'Failed to start server');
            startBtn.disabled = false;
            startBtn.textContent = 'Start';
        }
    } catch (error) {
        console.error('Error starting server:', error);
        alert('An error occurred while starting the server');
        startBtn.disabled = false;
        startBtn.textContent = 'Start';
    }
});

// Stop server
stopBtn.addEventListener('click', async () => {
    if (!confirm('Are you sure you want to stop the server?')) {
        return;
    }

    try {
        stopBtn.disabled = true;
        stopBtn.textContent = 'Stopping...';

        const response = await fetch(`/api/server/${SERVER_ID}/stop`, {
            method: 'POST'
        });

        const data = await response.json();

        if (data.success) {
            updateStatus('stopping');
            // Reload page after a moment to update UI
            setTimeout(() => location.reload(), 2000);
        } else {
            alert(data.error || 'Failed to stop server');
            stopBtn.disabled = false;
            stopBtn.textContent = 'Stop';
        }
    } catch (error) {
        console.error('Error stopping server:', error);
        alert('An error occurred while stopping the server');
        stopBtn.disabled = false;
        stopBtn.textContent = 'Stop';
    }
});

// Restart server
restartBtn.addEventListener('click', async () => {
    if (!confirm('Are you sure you want to restart the server?')) {
        return;
    }

    try {
        restartBtn.disabled = true;
        restartBtn.textContent = 'Restarting...';

        const response = await fetch(`/api/server/${SERVER_ID}/restart`, {
            method: 'POST'
        });

        const data = await response.json();

        if (data.success) {
            updateStatus('restarting');
            // Reload page after a moment to update UI
            setTimeout(() => location.reload(), 3000);
        } else {
            alert(data.error || 'Failed to restart server');
            restartBtn.disabled = false;
            restartBtn.textContent = 'Restart';
        }
    } catch (error) {
        console.error('Error restarting server:', error);
        alert('An error occurred while restarting the server');
        restartBtn.disabled = false;
        restartBtn.textContent = 'Restart';
    }
});

// Helper functions
function updateStatus(status, isRunning) {
    statusBadge.setAttribute('data-status', status);
    statusBadge.textContent = status;

    // Update buttons based on status
    if (status === 'online' || (isRunning !== undefined && isRunning)) {
        startBtn.style.display = 'none';
        stopBtn.style.display = 'inline-flex';
        restartBtn.style.display = 'inline-flex';
    } else if (status === 'offline') {
        startBtn.style.display = 'inline-flex';
        stopBtn.style.display = 'none';
        restartBtn.style.display = 'none';
    }
}

function appendConsoleLine(message, type) {
    if (!consoleOutput) return;
    const line = document.createElement('div');
    line.classList.add('console-line');
    if (type === 'stderr' || type === 'error') {
        line.classList.add('error');
    } else if (type === 'system') {
        line.classList.add('system');
    } else if (type === 'command') {
        line.classList.add('command');
    }
    line.textContent = message;
    consoleOutput.appendChild(line);
}

function scrollConsoleToBottom(onlyIfNearBottom = false) {
    if (!consoleOutput) return;
    if (onlyIfNearBottom) {
        const threshold = 120;
        const nearBottom = consoleOutput.scrollTop + consoleOutput.clientHeight + threshold >= consoleOutput.scrollHeight;
        if (!nearBottom) {
            return;
        }
    }
    consoleOutput.scrollTop = consoleOutput.scrollHeight;
}

if (consoleInput) {
    consoleInput.addEventListener('keydown', (event) => {
        if (event.key === 'Enter') {
            const command = consoleInput.value.trim();
            if (!command) {
                return;
            }

            socket.emit('console_command', { server_id: SERVER_ID, command });
            appendConsoleLine(`> ${command}`, 'command');
            commandHistory.push(command);
            historyIndex = commandHistory.length;
            consoleInput.value = '';
        } else if (event.key === 'ArrowUp') {
            if (commandHistory.length === 0) return;
            historyIndex = Math.max(0, historyIndex - 1);
            consoleInput.value = commandHistory[historyIndex];
            event.preventDefault();
        } else if (event.key === 'ArrowDown') {
            if (commandHistory.length === 0) return;
            historyIndex = Math.min(commandHistory.length, historyIndex + 1);
            if (historyIndex === commandHistory.length) {
                consoleInput.value = '';
            } else {
                consoleInput.value = commandHistory[historyIndex];
            }
            event.preventDefault();
        }
    });
}

// Initialize button states
if (!IS_RUNNING) {
    startBtn.style.display = 'inline-flex';
    stopBtn.style.display = 'none';
    restartBtn.style.display = 'none';
} else {
    startBtn.style.display = 'none';
    stopBtn.style.display = 'inline-flex';
    restartBtn.style.display = 'inline-flex';
}

// Poll server status periodically
setInterval(async () => {
    try {
        const response = await fetch(`/api/server/${SERVER_ID}/status`);
        if (response.ok) {
            const data = await response.json();
            if (data.success) {
                updateStatus(data.status, data.is_running);
            }
        }
    } catch (error) {
        console.error('Status poll error:', error);
    }
}, 5000);
