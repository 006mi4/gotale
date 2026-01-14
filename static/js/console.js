// Console JavaScript
// Handles server control buttons and status updates

const socket = io();
const startBtn = document.getElementById('startBtn');
const stopBtn = document.getElementById('stopBtn');
const restartBtn = document.getElementById('restartBtn');
const statusBadge = document.getElementById('statusBadge');

// Join console room on connect (for status updates)
socket.on('connect', () => {
    console.log('Connected to WebSocket server');
});

socket.on('disconnect', () => {
    console.log('Disconnected from server');
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
