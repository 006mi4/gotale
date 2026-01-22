const statusBadges = document.querySelectorAll('.status-badge');
const statusValue = document.querySelector('[data-status-value]');
const statusText = document.querySelector('[data-status-text]');
const SERVER_ID_VALUE = Number(SERVER_ID);

const socket = window.hsmSocket || io();
window.hsmSocket = socket;

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

function insertGotaleAlert() {
    const main = document.querySelector('.server-main');
    if (!main) return null;
    const alert = document.createElement('div');
    alert.className = 'alert alert-warning gotale-plugin-alert';
    alert.style.marginBottom = '18px';
    alert.style.display = 'flex';
    alert.style.alignItems = 'center';
    alert.style.justifyContent = 'space-between';
    alert.style.gap = '12px';
    alert.innerHTML = `
        <span>Um alle Funktionen gut nutzen zu können muss man das GoTaleManager Plugin installieren.</span>
        <div style="display:flex; gap:10px; align-items:center;">
            <button class="btn btn-ghost btn-small gotale-install-btn" type="button">Installieren</button>
            <button class="btn btn-ghost btn-small gotale-dismiss-btn" type="button">Schließen</button>
        </div>
    `;
    main.insertBefore(alert, main.firstChild);
    return alert;
}

async function initGotalePluginAlert() {
    if (typeof SERVER_ID === 'undefined') return;
    const dismissedKey = `gotale_plugin_dismissed_${SERVER_ID}`;
    if (localStorage.getItem(dismissedKey) === '1') {
        return;
    }
    let alert = document.querySelector('.gotale-plugin-alert');
    try {
        const response = await fetch(`/api/server/${SERVER_ID}/gotale/plugin-status`);
        if (!response.ok) return;
        const data = await response.json();
        if (!data.success || data.installed) return;
        if (!alert) {
            alert = insertGotaleAlert();
        }
    } catch (error) {
        return;
    }
    if (!alert) return;
    const installBtn = alert.querySelector('.gotale-install-btn');
    const dismissBtn = alert.querySelector('.gotale-dismiss-btn');
    if (dismissBtn) {
        dismissBtn.addEventListener('click', () => {
            localStorage.setItem(dismissedKey, '1');
            alert.remove();
        });
    }
    if (installBtn) {
        installBtn.addEventListener('click', async () => {
            installBtn.disabled = true;
            installBtn.textContent = 'Installiere...';
            try {
                const response = await fetch(`/api/server/${SERVER_ID}/gotale/install-plugin`, {
                    method: 'POST',
                    headers: { 'X-CSRFToken': CSRF_TOKEN }
                });
                const data = await response.json();
                if (response.ok && data.success) {
                    alert.remove();
                    localStorage.removeItem(dismissedKey);
                } else {
                    installBtn.disabled = false;
                    installBtn.textContent = 'Installieren';
                }
            } catch (error) {
                installBtn.disabled = false;
                installBtn.textContent = 'Installieren';
            }
        });
    }
}

initGotalePluginAlert();
