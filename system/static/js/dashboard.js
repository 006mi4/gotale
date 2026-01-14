// Dashboard JavaScript
// Handles server creation, deletion, and real-time status updates

const socket = io();

// Create Server Form
document.getElementById('createServerForm').addEventListener('submit', async (e) => {
    e.preventDefault();

    const name = document.getElementById('serverName').value.trim();
    const port = document.getElementById('serverPort').value;

    if (!name) {
        alert('Please enter a server name');
        return;
    }

    const formData = new FormData();
    formData.append('name', name);
    formData.append('port', port);

    try {
        const response = await fetch('/api/server/create', {
            method: 'POST',
            body: formData
        });

        const data = await response.json();

        if (data.success) {
            alert('Server created successfully!');
            location.reload();
        } else {
            if (data.suggested_port) {
                alert(`${data.error}\n\nSuggested port: ${data.suggested_port}`);
                document.getElementById('serverPort').value = data.suggested_port;
            } else {
                alert(data.error || 'Failed to create server');
            }
        }
    } catch (error) {
        console.error('Error creating server:', error);
        alert('An error occurred while creating the server');
    }
});

// Port checker
let portCheckTimeout;
document.getElementById('serverPort').addEventListener('input', (e) => {
    clearTimeout(portCheckTimeout);

    const port = parseInt(e.target.value);
    const statusDiv = document.getElementById('portStatus');

    if (!port || port < 1024 || port > 65535) {
        statusDiv.textContent = '';
        return;
    }

    portCheckTimeout = setTimeout(async () => {
        try {
            const response = await fetch(`/api/port-check/${port}`);
            const data = await response.json();

            if (data.available) {
                statusDiv.style.color = 'var(--success)';
                statusDiv.textContent = `✓ Port ${port} is available`;
            } else {
                statusDiv.style.color = 'var(--error)';
                statusDiv.textContent = `✗ Port ${port} is in use`;
                if (data.suggested_port) {
                    statusDiv.textContent += ` (suggested: ${data.suggested_port})`;
                }
            }
        } catch (error) {
            console.error('Error checking port:', error);
        }
    }, 500);
});

// Start Server
document.querySelectorAll('.server-start').forEach(btn => {
    btn.addEventListener('click', async (e) => {
        const serverId = e.target.dataset.serverId;

        try {
            const response = await fetch(`/api/server/${serverId}/start`, {
                method: 'POST'
            });

            const data = await response.json();

            if (data.success) {
                updateServerStatus(serverId, 'starting');
            } else {
                alert(data.error || 'Failed to start server');
            }
        } catch (error) {
            console.error('Error starting server:', error);
            alert('An error occurred while starting the server');
        }
    });
});

// Stop Server
document.querySelectorAll('.server-stop').forEach(btn => {
    btn.addEventListener('click', async (e) => {
        const serverId = e.target.dataset.serverId;

        try {
            const response = await fetch(`/api/server/${serverId}/stop`, {
                method: 'POST'
            });

            const data = await response.json();

            if (data.success) {
                updateServerStatus(serverId, 'stopping');
            } else {
                alert(data.error || 'Failed to stop server');
            }
        } catch (error) {
            console.error('Error stopping server:', error);
            alert('An error occurred while stopping the server');
        }
    });
});

// Delete Server
document.querySelectorAll('.server-delete').forEach(btn => {
    btn.addEventListener('click', async (e) => {
        const serverId = e.target.dataset.serverId;

        if (!confirm('Are you sure you want to delete this server? All data will be lost!')) {
            return;
        }

        try {
            const response = await fetch(`/api/server/${serverId}/delete`, {
                method: 'DELETE'
            });

            const data = await response.json();

            if (data.success) {
                location.reload();
            } else {
                alert(data.error || 'Failed to delete server');
            }
        } catch (error) {
            console.error('Error deleting server:', error);
            alert('An error occurred while deleting the server');
        }
    });
});

// WebSocket status updates
socket.on('server_status_change', (data) => {
    updateServerStatus(data.server_id, data.status);
});

function updateServerStatus(serverId, status) {
    const serverRow = document.querySelector(`.server-row[data-server-id="${serverId}"]`);
    if (!serverRow) return;

    const statusDot = serverRow.querySelector('.server-status');
    const statusText = serverRow.querySelector('.status-text');

    if (statusDot) {
        statusDot.setAttribute('data-status', status);
    }

    if (statusText) {
        statusText.textContent = status;
    }

    // Update buttons
    const actionsDiv = serverRow.querySelector('div:last-child');
    if (actionsDiv && (status === 'online' || status === 'offline')) {
        location.reload(); // Reload to update buttons
    }
}

// Connection status
socket.on('connect', () => {
    console.log('Connected to server');
});

socket.on('disconnect', () => {
    console.log('Disconnected from server');
});
