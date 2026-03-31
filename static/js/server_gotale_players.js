const gotalePlayersPanel = document.getElementById('gotalePlayersPanel');
const gotalePlayersConnection = document.getElementById('gotalePlayersConnection');
const gotalePlayersRefresh = document.getElementById('gotalePlayersRefresh');
const gotalePlayerSelect = document.getElementById('gotalePlayerSelect');
const gotaleActionSelect = document.getElementById('gotaleActionSelect');
const gotaleActionValue = document.getElementById('gotaleActionValue');
const gotaleActionBtn = document.getElementById('gotaleActionBtn');
const gotaleActionResult = document.getElementById('gotaleActionResult');
const gotalePlayerCards = document.getElementById('gotalePlayerCards');
const gotalePlayerEmpty = document.getElementById('gotalePlayerEmpty');

let gotalePlayersConfig = null;
const gotaleSocket = window.hsmSocket || io();
window.hsmSocket = gotaleSocket;
const gotalePlayersCsrfHeader = () => ({ 'X-CSRFToken': CSRF_TOKEN });
let gotalePlayersJoined = false;
let gotalePlayersApiHealthy = false;
let gotalePlayersWsHealthy = false;

function setPlayersConnection(state, label) {
    if (!gotalePlayersConnection) return;
    gotalePlayersConnection.classList.remove('online', 'offline', 'warning');
    gotalePlayersConnection.classList.add(state);
    gotalePlayersConnection.textContent = label;
}

function applyConnectionState() {
    if (gotalePlayersWsHealthy) {
        setPlayersConnection('online', 'Live');
        return;
    }
    if (gotalePlayersApiHealthy) {
        setPlayersConnection('warning', 'API only');
        return;
    }
    setPlayersConnection('offline', 'Disconnected');
}

function formatNumber(value) {
    if (value === null || value === undefined || Number.isNaN(value)) return '--';
    return value;
}

function renderPlayerList(players) {
    if (!gotalePlayerCards || !gotalePlayerEmpty || !gotalePlayerSelect) return;
    gotalePlayerCards.innerHTML = '';
    gotalePlayerSelect.innerHTML = '';
    if (!players || !players.length) {
        gotalePlayerEmpty.style.display = 'block';
        return;
    }
    gotalePlayerEmpty.style.display = 'none';
    players.forEach((player) => {
        const option = document.createElement('option');
        option.value = player.name || player.uuid;
        option.textContent = player.name || player.uuid || 'Unknown';
        gotalePlayerSelect.appendChild(option);

        const card = document.createElement('div');
        card.className = 'mini-player-card';
        card.innerHTML = `
            <div class="mini-player-name">${player.name || 'Unknown'}</div>
            <div class="mini-player-sub">${player.world || 'world'}</div>
            <div class="mini-player-coords">${formatNumber(player.position?.x)} / ${formatNumber(player.position?.y)} / ${formatNumber(player.position?.z)}</div>
        `;
        gotalePlayerCards.appendChild(card);
    });
}

async function refreshPlayersPanel() {
    if (!gotalePlayersConfig || !gotalePlayersConfig.enabled) return;
    try {
        const response = await fetch(`/api/server/${SERVER_ID}/gotale/proxy/players`);
        if (!response.ok) {
            gotalePlayersApiHealthy = false;
            applyConnectionState();
            return;
        }
        const data = await response.json();
        renderPlayerList(data.players || []);
        gotalePlayersApiHealthy = true;
        applyConnectionState();
    } catch (error) {
        gotalePlayersApiHealthy = false;
        applyConnectionState();
        console.warn('GoTale players refresh failed', error);
    }
}


async function runPlayerAction() {
    if (!gotalePlayerSelect || !gotaleActionSelect) return;
    const playerName = gotalePlayerSelect.value;
    const action = gotaleActionSelect.value;
    if (!playerName || !action) return;
    let endpoint = `/api/server/${SERVER_ID}/gotale/proxy/players/${encodeURIComponent(playerName)}/${action}`;
    let body = null;

    if (action === 'gamemode') {
        body = { gamemode: (gotaleActionValue?.value || '').trim() };
    }
    if (action === 'teleport') {
        const raw = (gotaleActionValue?.value || '').trim();
        const parts = raw.split(/\s+/).filter(Boolean);
        if (parts.length === 3 && parts.every((num) => !Number.isNaN(Number(num)))) {
            body = { x: Number(parts[0]), y: Number(parts[1]), z: Number(parts[2]) };
        } else if (raw) {
            body = { target: raw };
        }
    }

    try {
        const response = await fetch(endpoint, {
            method: 'POST',
            headers: {
                'Content-Type': 'application/json',
                ...gotalePlayersCsrfHeader()
            },
            body: body ? JSON.stringify(body) : JSON.stringify({})
        });
        const data = await response.json();
        if (gotaleActionResult) {
            gotaleActionResult.textContent = data.message || (data.success ? 'Action executed.' : 'Action failed.');
            gotaleActionResult.classList.toggle('saved', !!data.success);
        }
    } catch (error) {
        if (gotaleActionResult) {
            gotaleActionResult.textContent = 'Action failed.';
        }
    }
}

function joinPlayersRoom() {
    if (gotalePlayersJoined) return;
    gotaleSocket.emit('join_gotale', { server_id: SERVER_ID });
    gotalePlayersJoined = true;
}

async function initPlayersPanel() {
    if (!gotalePlayersPanel) return;
    try {
        const response = await fetch(`/api/server/${SERVER_ID}/gotale/config`);
        const data = await response.json();
        if (!response.ok || !data.success || !data.configured) {
            setPlayersConnection('warning', 'Not configured');
            return;
        }
        gotalePlayersConfig = data;
        if (!gotalePlayersConfig.enabled) {
            setPlayersConnection('warning', 'Disabled');
            return;
        }
        gotalePlayersApiHealthy = false;
        setPlayersConnection('warning', 'Connecting…');
        await refreshPlayersPanel();
        joinPlayersRoom();
        setInterval(refreshPlayersPanel, 15000);
    } catch (error) {
        gotalePlayersApiHealthy = false;
        applyConnectionState();
    }
}

gotaleSocket.on('connect', () => {
    if (gotalePlayersConfig && gotalePlayersConfig.enabled) {
        joinPlayersRoom();
    }
});

gotaleSocket.on('gotale_status', (data) => {
    if (!data || Number(data.server_id) !== Number(SERVER_ID)) return;
    gotalePlayersWsHealthy = !!data.connected;
    applyConnectionState();
});

gotaleSocket.on('gotale_event', (data) => {
    if (!data || Number(data.server_id) !== Number(SERVER_ID)) return;
    const payload = data.event;
    if (!payload || !payload.type) return;
    if (payload.type === 'player_connect' || payload.type === 'player_disconnect') {
        refreshPlayersPanel();
    }
});

if (gotalePlayersRefresh) {
    gotalePlayersRefresh.addEventListener('click', refreshPlayersPanel);
}

if (gotaleActionBtn) {
    gotaleActionBtn.addEventListener('click', runPlayerAction);
}

initPlayersPanel();
