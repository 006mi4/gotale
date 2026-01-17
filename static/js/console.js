// Console JavaScript
// Handles server control buttons and status updates

const socket = io();
const csrfHeader = () => ({ 'X-CSRFToken': CSRF_TOKEN });
const startBtn = document.getElementById('startBtn');
const stopBtn = document.getElementById('stopBtn');
const restartBtn = document.getElementById('restartBtn');
const statusBadge = document.getElementById('statusBadge');
const statusBadges = document.querySelectorAll('.status-badge');
const statusValues = document.querySelectorAll('[data-status-value]');
const statusTexts = document.querySelectorAll('[data-status-text]');
const consoleOutput = document.getElementById('consoleOutput');
const consoleInput = document.getElementById('consoleInput');
const authModal = document.getElementById('authModal');
const authUrl = document.getElementById('authUrl');
const authCode = document.getElementById('authCode');
const authCloseBtn = document.getElementById('authCloseBtn');
const startupModal = document.getElementById('startupModal');
const startupCloseBtn = document.getElementById('startupCloseBtn');
const startupAuthUrl = document.getElementById('startupAuthUrl');
const startupAuthCode = document.getElementById('startupAuthCode');
const startupProgressBar = document.getElementById('startupProgressBar');
const startupProgressText = document.getElementById('startupProgressText');
const startupSteps = {
    'start': document.querySelector('[data-step="start"]'),
    'auth-check': document.querySelector('[data-step="auth-check"]'),
    'auth-device': document.querySelector('[data-step="auth-device"]'),
    'auth-wait': document.querySelector('[data-step="auth-wait"]'),
    'auth-save': document.querySelector('[data-step="auth-save"]'),
    'done': document.querySelector('[data-step="done"]')
};

let commandHistory = [];
let historyIndex = -1;
let authPoller = null;
const SERVER_ID_VALUE = Number(SERVER_ID);
let consolePoller = null;
let lastConsoleSnapshot = [];
let startupFlowActive = false;
let lastAuthPending = false;
let authCompleted = false;
let startupError = false;
let awaitingAuth = false;
let startupOpenedAt = 0;
let stepTimes = {};
let authProbeCount = 0;
let authPollStartedAt = 0;

// Join console room on connect (for status updates)
socket.on('connect', () => {
    console.log('Connected to WebSocket server');
    socket.emit('join_console', { server_id: SERVER_ID });
    checkAuthStatus();
    startAuthPolling();
    stopConsolePolling();
    startConsolePolling();
});

socket.on('disconnect', () => {
    console.log('Disconnected from server');
    startConsolePolling();
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
    lastConsoleSnapshot = data.messages || [];
});

// Live console output
socket.on('console_output', (data) => {
    if (Number(data.server_id) !== SERVER_ID_VALUE || !consoleOutput) return;
    appendConsoleLine(data.message, data.type);
    scrollConsoleToBottom(true);
    if (lastConsoleSnapshot) {
        lastConsoleSnapshot.push(data.message);
        if (lastConsoleSnapshot.length > 1000) {
            lastConsoleSnapshot = lastConsoleSnapshot.slice(-1000);
        }
    }
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
    if (startupAuthUrl) {
        const url = data.url || '';
        startupAuthUrl.textContent = url;
        startupAuthUrl.setAttribute('href', url || '#');
    }
    if (startupAuthCode) startupAuthCode.textContent = data.code || '';
    setStartupStep('auth-check', 'done');
    setStartupStep('auth-device', 'active');
    setStartupStep('auth-wait', 'active');
    updateStartupProgress(55, 'Auth login device ready. Waiting for completion…');
    lastAuthPending = true;
    awaitingAuth = true;
    startAuthPolling();
});

socket.on('auth_success', (data) => {
    if (Number(data.server_id) !== SERVER_ID_VALUE) return;
    if (authModal) authModal.classList.remove('active');
    authCompleted = true;
    awaitingAuth = false;
    setStartupStep('auth-wait', 'done');
    setStartupStep('auth-save', 'active');
    updateStartupProgress(80, 'Saving auth token…');
    stopAuthPolling();
});

if (authCloseBtn) {
    authCloseBtn.addEventListener('click', () => {
        if (authModal) authModal.classList.remove('active');
    });
}

if (startupCloseBtn) {
    startupCloseBtn.addEventListener('click', () => {
        if (startupModal) startupModal.classList.remove('active');
    });
}

// Start server
startBtn.addEventListener('click', async () => {
    try {
        startBtn.disabled = true;
        startBtn.textContent = 'Starting...';
        openStartupModal();

        const response = await fetch(`/api/server/${SERVER_ID}/start`, {
            method: 'POST',
            headers: csrfHeader()
        });

        const data = await response.json();

        if (data.success) {
            updateStatus('starting', true);
            triggerAuthStatus();
            checkAuthStatus();
            startAuthPolling();
        } else {
            alert(data.error || 'Failed to start server');
            startBtn.disabled = false;
            startBtn.textContent = 'Start';
            closeStartupModal();
            updateStartupProgress(0, 'Startup failed.', true);
        }
    } catch (error) {
        console.error('Error starting server:', error);
        alert('An error occurred while starting the server');
        startBtn.disabled = false;
        startBtn.textContent = 'Start';
        closeStartupModal();
        updateStartupProgress(0, 'Startup failed.', true);
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
            method: 'POST',
            headers: csrfHeader()
        });

        const data = await response.json();

        if (data.success) {
            updateStatus('stopping');
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
        openStartupModal();

        const response = await fetch(`/api/server/${SERVER_ID}/restart`, {
            method: 'POST',
            headers: csrfHeader()
        });

        const data = await response.json();

        if (data.success) {
            updateStatus('restarting');
            triggerAuthStatus();
        } else {
            alert(data.error || 'Failed to restart server');
            restartBtn.disabled = false;
            restartBtn.textContent = 'Restart';
            closeStartupModal();
            updateStartupProgress(0, 'Restart failed.', true);
        }
    } catch (error) {
        console.error('Error restarting server:', error);
        alert('An error occurred while restarting the server');
        restartBtn.disabled = false;
        restartBtn.textContent = 'Restart';
        closeStartupModal();
        updateStartupProgress(0, 'Restart failed.', true);
    }
});

// Helper functions
function updateStatus(status, isRunning) {
    statusBadge.setAttribute('data-status', status);
    statusBadge.textContent = status;
    statusBadges.forEach((badge) => {
        badge.setAttribute('data-status', status);
        badge.textContent = status;
    });
    statusValues.forEach((value) => {
        value.textContent = status;
    });
    statusTexts.forEach((text) => {
        text.textContent = status;
    });

    const busy = status === 'starting' || status === 'stopping' || status === 'restarting';

    // Update buttons based on status
    if (status === 'online' || (isRunning !== undefined && isRunning)) {
        startBtn.style.display = 'none';
        stopBtn.style.display = 'inline-flex';
        restartBtn.style.display = 'inline-flex';
        startBtn.disabled = false;
        stopBtn.disabled = false;
        restartBtn.disabled = false;
        stopBtn.textContent = 'Stop';
        restartBtn.textContent = 'Restart';
        if (startupFlowActive && !awaitingAuth) {
            if (!authCompleted) {
                setStartupStep('auth-check', 'done');
                setStartupStep('auth-device', 'done');
                setStartupStep('auth-wait', 'done');
                setStartupStep('auth-save', 'done');
            } else {
                setStartupStep('auth-save', 'done');
            }
            setStartupStep('done', 'done');
            updateStartupProgress(100, 'Server started successfully.');
            closeStartupModal(true);
        }
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
        stopBtn.textContent = 'Stop';
        restartBtn.textContent = 'Restart';
    } else if (busy) {
        startBtn.disabled = true;
        stopBtn.disabled = true;
        restartBtn.disabled = true;
        if (status === 'starting') {
            startBtn.style.display = 'inline-flex';
            stopBtn.style.display = 'none';
            restartBtn.style.display = 'none';
            startBtn.textContent = 'Starting...';
            if (startupFlowActive) {
                setStartupStep('start', 'active');
                setStartupStep('auth-check', 'active');
                updateStartupProgress(25, 'Server is starting…');
            }
        } else if (status === 'stopping') {
            startBtn.style.display = 'none';
            stopBtn.style.display = 'inline-flex';
            restartBtn.style.display = 'none';
            stopBtn.textContent = 'Stopping...';
        } else if (status === 'restarting') {
            startBtn.style.display = 'none';
            stopBtn.style.display = 'none';
            restartBtn.style.display = 'inline-flex';
            restartBtn.textContent = 'Restarting...';
            if (startupFlowActive) {
                setStartupStep('start', 'active');
                setStartupStep('auth-check', 'active');
                updateStartupProgress(25, 'Server is restarting…');
            }
        }
    }
}

function openStartupModal() {
    if (!startupModal) return;
    startupFlowActive = true;
    authCompleted = false;
    lastAuthPending = false;
    startupError = false;
    awaitingAuth = true;
    startupOpenedAt = Date.now();
    stepTimes = {};
    authProbeCount = 0;
    authPollStartedAt = Date.now();
    resetStartupSteps();
    setStartupStep('start', 'active');
    setTimeout(() => {
        setStartupStep('auth-check', 'active');
    }, 800);
    updateStartupProgress(15, 'Server is starting…');
    startupModal.classList.add('active');
}

function closeStartupModal(auto = false) {
    if (!startupModal) return;
    if (auto) {
        const elapsed = Date.now() - startupOpenedAt;
        const delay = Math.max(1500, 4000 - elapsed);
        setTimeout(() => {
            startupModal.classList.remove('active');
        }, delay);
    } else {
        startupModal.classList.remove('active');
    }
    startupFlowActive = false;
}

function resetStartupSteps() {
    Object.values(startupSteps).forEach((step) => {
        if (!step) return;
        step.classList.remove('active', 'done');
    });
}

function setStartupStep(key, state) {
    const step = startupSteps[key];
    if (!step) return;
    if (state === 'active') {
        step.classList.add('active');
        step.classList.remove('done');
        stepTimes[key] = Date.now();
    } else if (state === 'done') {
        const startedAt = stepTimes[key] || Date.now();
        const elapsed = Date.now() - startedAt;
        const minVisible = 900;
        if (elapsed < minVisible) {
            setTimeout(() => {
                step.classList.remove('active');
                step.classList.add('done');
            }, minVisible - elapsed);
        } else {
            step.classList.remove('active');
            step.classList.add('done');
        }
    }
}

function updateStartupProgress(value, text, isError = false) {
    if (startupProgressBar) {
        startupProgressBar.style.width = `${value}%`;
    }
    if (startupProgressText) {
        startupProgressText.textContent = text;
        startupProgressText.classList.toggle('error', isError);
    }
}

async function triggerAuthStatus() {
    try {
        await fetch(`/api/server/${SERVER_ID}/auth-trigger`, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json', ...csrfHeader() },
            body: JSON.stringify({ action: 'status' })
        });
    } catch (error) {
        console.error('Auth status trigger failed:', error);
    }
}

async function triggerAuthLoginDevice() {
    try {
        await fetch(`/api/server/${SERVER_ID}/auth-trigger`, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json', ...csrfHeader() },
            body: JSON.stringify({ action: 'login_device' })
        });
    } catch (error) {
        console.error('Auth login device trigger failed:', error);
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
            if (startupAuthUrl) {
                startupAuthUrl.textContent = url;
                startupAuthUrl.setAttribute('href', url || '#');
            }
            if (startupAuthCode) startupAuthCode.textContent = data.auth_code || '';
            setStartupStep('auth-check', 'done');
            setStartupStep('auth-device', 'active');
            setStartupStep('auth-wait', 'active');
            updateStartupProgress(55, 'Auth login device ready. Waiting for completion…');
            lastAuthPending = true;
            awaitingAuth = true;
        } else if (!data.auth_pending) {
            if (authModal) authModal.classList.remove('active');
            awaitingAuth = false;
            if (lastAuthPending) {
                authCompleted = true;
                awaitingAuth = false;
                setStartupStep('auth-wait', 'done');
                setStartupStep('auth-save', 'active');
                updateStartupProgress(80, 'Saving auth token…');
            } else if (startupFlowActive) {
                setStartupStep('auth-check', 'done');
                setStartupStep('auth-device', 'done');
                setStartupStep('auth-wait', 'done');
                setStartupStep('auth-save', 'active');
                updateStartupProgress(70, 'No auth required. Finalizing…');
            }
            if (!startupFlowActive) {
                stopAuthPolling();
            }
        } else if (startupFlowActive) {
            awaitingAuth = true;
            authProbeCount += 1;
            if (authProbeCount >= 2) {
                triggerAuthLoginDevice();
            }
        }
    } catch (error) {
        console.error('Auth status check error:', error);
        updateStartupProgress(0, 'Auth check failed.', true);
    }
}

function startAuthPolling() {
    if (authPoller) return;
    authPollStartedAt = Date.now();
    authPoller = setInterval(checkAuthStatus, 3000);
}

function stopAuthPolling() {
    if (!authPoller) return;
    clearInterval(authPoller);
    authPoller = null;
}

async function pollConsoleOutput() {
    try {
        const response = await fetch(`/api/server/${SERVER_ID}/console?lines=200`);
        if (!response.ok) return;
        const data = await response.json();
        if (!data.success || !Array.isArray(data.lines)) return;

        if (!consoleOutput) return;
        const lines = data.lines;

        if (!lastConsoleSnapshot.length) {
            consoleOutput.innerHTML = '';
            lines.forEach((line) => appendConsoleLine(line));
            scrollConsoleToBottom();
            lastConsoleSnapshot = lines.slice();
            return;
        }

        const lastLine = lastConsoleSnapshot[lastConsoleSnapshot.length - 1];
        let startIndex = lines.lastIndexOf(lastLine);
        if (startIndex === -1) {
            consoleOutput.innerHTML = '';
            lines.forEach((line) => appendConsoleLine(line));
            scrollConsoleToBottom();
            lastConsoleSnapshot = lines.slice();
            return;
        }

        startIndex += 1;
        if (startIndex < lines.length) {
            for (let i = startIndex; i < lines.length; i++) {
                appendConsoleLine(lines[i]);
            }
            scrollConsoleToBottom(true);
        }
        lastConsoleSnapshot = lines.slice();
    } catch (error) {
        console.error('Console poll error:', error);
    }
}

function startConsolePolling() {
    if (consolePoller) return;
    consolePoller = setInterval(pollConsoleOutput, 2000);
    pollConsoleOutput();
}

function stopConsolePolling() {
    if (!consolePoller) return;
    clearInterval(consolePoller);
    consolePoller = null;
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

    if (!startupFlowActive) return;
    const lower = message.toLowerCase();
    const urlMatch = message.match(/https?:\/\/[^\s]+/);
    const codeMatch = message.match(/Enter code:\\s*([A-Za-z0-9-]+)/i);
    const userCodeMatch = message.match(/user_code=([A-Za-z0-9-]+)/i);

    if (urlMatch) {
        const url = urlMatch[0].replace(/\)$/, '');
        if (startupAuthUrl) {
            startupAuthUrl.textContent = url;
            startupAuthUrl.setAttribute('href', url);
        }
        setStartupStep('auth-check', 'done');
        setStartupStep('auth-device', 'active');
        setStartupStep('auth-wait', 'active');
        updateStartupProgress(55, 'Auth login device ready. Waiting for completion…');
        awaitingAuth = true;
    }

    if (userCodeMatch && startupAuthUrl) {
        const url = `https://oauth.accounts.hytale.com/oauth2/device/verify?user_code=${userCodeMatch[1]}`;
        startupAuthUrl.textContent = url;
        startupAuthUrl.setAttribute('href', url);
    }

    if (codeMatch && startupAuthCode) {
        startupAuthCode.textContent = codeMatch[1];
        setStartupStep('auth-check', 'done');
        setStartupStep('auth-device', 'active');
        setStartupStep('auth-wait', 'active');
        updateStartupProgress(55, 'Auth login device ready. Waiting for completion…');
        awaitingAuth = true;
    }

    if (lower.includes('auth login device')) {
        setStartupStep('auth-check', 'done');
        setStartupStep('auth-device', 'active');
        setStartupStep('auth-wait', 'active');
        updateStartupProgress(55, 'Auth login device ready. Waiting for completion…');
        awaitingAuth = true;
    }
    if (lower.includes('no server tokens configured') || lower.includes('tokenmissing')) {
        setStartupStep('auth-check', 'active');
        triggerAuthLoginDevice();
    }
    if (lower.includes('auth persistence') || lower.includes('auth save')) {
        setStartupStep('auth-wait', 'done');
        setStartupStep('auth-save', 'active');
        updateStartupProgress(80, 'Saving auth token…');
    }
    if (lower.includes('auth success') || lower.includes('auth saved')) {
        authCompleted = true;
        awaitingAuth = false;
        setStartupStep('auth-save', 'done');
        setStartupStep('done', 'done');
        updateStartupProgress(100, 'Server started successfully.');
        closeStartupModal(true);
    }
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
