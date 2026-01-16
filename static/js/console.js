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
let authPoller = null;
const SERVER_ID_VALUE = Number(SERVER_ID);

// Join console room on connect (for status updates)
socket.on('connect', () => {
    console.log('Connected to WebSocket server');
    socket.emit('join_console', { server_id: SERVER_ID });
    checkAuthStatus();
    startAuthPolling();
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
    if (Number(data.server_id) === SERVER_ID_VALUE) {
        updateStatus(data.status, data.is_running);
        if (data.status === 'online' || data.status === 'starting') {
            startAuthPolling();
        }
    }
});

socket.on('server_status_change', (data) => {
    if (Number(data.server_id) === SERVER_ID_VALUE) {
        updateStatus(data.status);
        if (data.status === 'online' || data.status === 'starting') {
            startAuthPolling();
        }
    }
});

// Console history
socket.on('console_history', (data) => {
    if (Number(data.server_id) !== SERVER_ID_VALUE || !consoleOutput) return;
    consoleOutput.innerHTML = '';
    data.messages.forEach((line) => {
        appendConsoleLine(line);
    });
    scrollConsoleToBottom();
});

// Live console output
socket.on('console_output', (data) => {
    if (Number(data.server_id) !== SERVER_ID_VALUE || !consoleOutput) return;
    appendConsoleLine(data.message, data.type);
    scrollConsoleToBottom(true);
});

// Auth modal
socket.on('auth_required', (data) => {
    if (Number(data.server_id) !== SERVER_ID_VALUE) return;
    if (authUrl) {
        const url = data.url || '';
        authUrl.textContent = url;
        authUrl.setAttribute('href', url || '#');
    }
    if (authCode) authCode.textContent = data.code || '';
    if (authModal) authModal.classList.add('active');
    startAuthPolling();
});

socket.on('auth_success', (data) => {
    if (Number(data.server_id) !== SERVER_ID_VALUE) return;
    if (authModal) authModal.classList.remove('active');
    stopAuthPolling();
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
            updateStatus('starting', true);
            checkAuthStatus();
            startAuthPolling();
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
        startBtn.disabled = false;
        stopBtn.disabled = false;
        restartBtn.disabled = false;
    } else if (status === 'offline') {
        startBtn.style.display = 'inline-flex';
        stopBtn.style.display = 'none';
        restartBtn.style.display = 'none';
        startBtn.disabled = false;
        stopBtn.disabled = false;
        restartBtn.disabled = false;
        if (startBtn.textContent !== 'Start') {
            startBtn.textContent = 'Start';
        }
    }
}

async function checkAuthStatus() {
    try {
        const response = await fetch(`/api/server/${SERVER_ID}/auth-status`);
        if (!response.ok) return;
        const data = await response.json();
        if (!data.success) return;
        if (data.auth_pending && data.auth_url) {
            const url = data.auth_url || '';
            if (authUrl) {
                authUrl.textContent = url;
                authUrl.setAttribute('href', url || '#');
            }
            if (authCode) authCode.textContent = data.auth_code || '';
            if (authModal) authModal.classList.add('active');
        } else {
            if (authModal) authModal.classList.remove('active');
            stopAuthPolling();
        }
    } catch (error) {
        console.error('Auth status check error:', error);
    }
}

function startAuthPolling() {
    if (authPoller) return;
    authPoller = setInterval(checkAuthStatus, 3000);
}

function stopAuthPolling() {
    if (!authPoller) return;
    clearInterval(authPoller);
    authPoller = null;
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
