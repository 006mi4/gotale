const statusBadges = document.querySelectorAll('.status-badge');
const statusValue = document.querySelector('[data-status-value]');
const statusText = document.querySelector('[data-status-text]');
const SERVER_ID_VALUE = Number(SERVER_ID);

const socket = io();

function applyStatus(status) {
    statusBadges.forEach((badge) => {
        badge.setAttribute('data-status', status);
        badge.textContent = status;
    });
    if (statusValue) {
        statusValue.textContent = status;
    }
    if (statusText) {
        statusText.textContent = status;
    }
}

socket.on('server_status_change', (data) => {
    if (Number(data.server_id) !== SERVER_ID_VALUE) return;
    applyStatus(data.status);
});

socket.on('server_status', (data) => {
    if (Number(data.server_id) !== SERVER_ID_VALUE) return;
    applyStatus(data.status);
});

setInterval(async () => {
    try {
        const response = await fetch(`/api/server/${SERVER_ID}/status`);
        if (!response.ok) return;
        const data = await response.json();
        if (data.success) {
            applyStatus(data.status);
        }
    } catch (error) {
        console.error('Status poll error:', error);
    }
}, 5000);
