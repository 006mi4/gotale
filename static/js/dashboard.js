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

// Download Server Files
let authMessageShown = false;
const downloadBtn = document.getElementById('downloadGameFilesBtn');
if (downloadBtn) {
    downloadBtn.addEventListener('click', async () => {
        const modal = document.getElementById('downloadModal');
        const progressDiv = document.getElementById('downloadProgress');
        const authSection = document.getElementById('downloadAuthSection');
        const authWaiting = document.getElementById('downloadAuthWaiting');
        const authDetails = document.getElementById('downloadAuthDetails');
        const progressBarContainer = document.getElementById('downloadProgressBarContainer');

        // Show modal (use flex for centering)
        modal.style.display = 'flex';

        // Reset content
        progressDiv.innerHTML = '<div>Starting download...</div>';
        authSection.style.display = 'block';
        authWaiting.style.display = 'block';
        authDetails.style.display = 'none';
        progressBarContainer.style.display = 'none';

        // Reset auth message flag for new download
        authMessageShown = false;

        console.log('Download modal opened, starting download...');

        try {
            const response = await fetch('/api/download-game-files', {
                method: 'POST'
            });

            const data = await response.json();
            console.log('Download API response:', data);

            if (!data.success) {
                addDownloadMessage(data.error || 'Failed to start download', 'error');
            }
        } catch (error) {
            console.error('Error starting download:', error);
            addDownloadMessage('An error occurred while starting the download', 'error');
        }
    });
}

// Close download modal
const closeModalBtn = document.getElementById('closeDownloadModal');
if (closeModalBtn) {
    closeModalBtn.addEventListener('click', () => {
        const modal = document.getElementById('downloadModal');
        modal.style.display = 'none';
    });
}

// WebSocket events for download
socket.on('download_progress', (data) => {
    addDownloadMessage(data.message);

    // Check if this is a progress update with percentage
    if (data.percentage !== undefined) {
        const progressBarContainer = document.getElementById('downloadProgressBarContainer');
        const progressBar = document.getElementById('downloadProgressBar');
        const progressPercent = document.getElementById('downloadProgressPercent');
        const progressDetails = document.getElementById('downloadProgressDetails');
        const authSection = document.getElementById('downloadAuthSection');

        // Hide auth section, show progress bar
        authSection.style.display = 'none';
        progressBarContainer.style.display = 'block';

        // Update progress bar
        progressBar.style.width = data.percentage + '%';
        progressPercent.textContent = data.percentage + '%';

        // Show download details if available
        if (data.details) {
            progressDetails.textContent = data.details;
        }
    }
});

socket.on('download_auth_required', (data) => {
    console.log('Received download_auth_required event:', data);

    const authSection = document.getElementById('downloadAuthSection');
    const authWaiting = document.getElementById('downloadAuthWaiting');
    const authDetails = document.getElementById('downloadAuthDetails');
    const authUrl = document.getElementById('downloadAuthUrl');
    const authCode = document.getElementById('downloadAuthCode');

    if (!authSection || !authWaiting || !authDetails || !authUrl || !authCode) {
        console.error('Auth modal elements not found!');
        return;
    }

    // Show auth details, hide waiting message
    authWaiting.style.display = 'none';
    authDetails.style.display = 'block';

    authUrl.href = data.url;
    authUrl.textContent = data.url;
    authCode.textContent = data.code || 'N/A';

    authSection.style.display = 'block';

    // Only show the message once
    if (!authMessageShown) {
        authMessageShown = true;
        console.log('Auth details displayed - URL:', data.url, 'Code:', data.code);
        addDownloadMessage('Authentication required! Please follow the instructions above.', 'warning');
    }
});

socket.on('download_success', (data) => {
    addDownloadMessage(data.message, 'success');
});

socket.on('download_error', (data) => {
    addDownloadMessage('Error: ' + data.error, 'error');
});

socket.on('download_complete', (data) => {
    const progressBar = document.getElementById('downloadProgressBar');
    const progressPercent = document.getElementById('downloadProgressPercent');

    if (data.success) {
        // Set progress to 100%
        if (progressBar) {
            progressBar.style.width = '100%';
        }
        if (progressPercent) {
            progressPercent.textContent = '100%';
        }

        addDownloadMessage('Download completed successfully!', 'success');
        addDownloadMessage('Reloading page in 3 seconds...', 'info');

        setTimeout(() => {
            location.reload();
        }, 3000);
    } else {
        addDownloadMessage('Download failed. Please try again.', 'error');
    }
});

function addDownloadMessage(message, type = 'info') {
    const progressDiv = document.getElementById('downloadProgress');
    const messageDiv = document.createElement('div');

    messageDiv.textContent = message;
    messageDiv.style.marginTop = '5px';

    if (type === 'error') {
        messageDiv.style.color = 'var(--error)';
    } else if (type === 'success') {
        messageDiv.style.color = 'var(--success)';
    } else if (type === 'warning') {
        messageDiv.style.color = '#ffc107';
    }

    progressDiv.appendChild(messageDiv);

    // Auto-scroll to bottom
    progressDiv.scrollTop = progressDiv.scrollHeight;
}
