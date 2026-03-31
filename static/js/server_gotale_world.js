const gotaleWorldsPanel = document.getElementById('gotaleWorldsPanel');
const gotaleWorldsConnection = document.getElementById('gotaleWorldsConnection');
const gotaleWorldsRefresh = document.getElementById('gotaleWorldsRefresh');
const gotaleWorldCards = document.getElementById('gotaleWorldCards');
const gotaleWorldsEmpty = document.getElementById('gotaleWorldsEmpty');

let gotaleWorldsConfig = null;
const gotaleSocket = window.hsmSocket || io();
window.hsmSocket = gotaleSocket;
let gotaleWorldsJoined = false;
let gotaleWorldsApiHealthy = false;
let gotaleWorldsWsHealthy = false;

function setWorldsConnection(state, label) {
    if (!gotaleWorldsConnection) return;
    gotaleWorldsConnection.classList.remove('online', 'offline', 'warning');
    gotaleWorldsConnection.classList.add(state);
    gotaleWorldsConnection.textContent = label;
}

function applyConnectionState() {
    if (gotaleWorldsWsHealthy) {
        setWorldsConnection('online', 'Live');
        return;
    }
    if (gotaleWorldsApiHealthy) {
        setWorldsConnection('warning', 'API only');
        return;
    }
    setWorldsConnection('offline', 'Disconnected');
}

function formatNumber(value) {
    if (value === null || value === undefined || Number.isNaN(value)) return '--';
    return value;
}

function renderWorldCards(worlds, statsMap) {
    if (!gotaleWorldCards || !gotaleWorldsEmpty) return;
    gotaleWorldCards.innerHTML = '';
    if (!worlds || !worlds.length) {
        gotaleWorldsEmpty.style.display = 'block';
        return;
    }
    gotaleWorldsEmpty.style.display = 'none';
    worlds.forEach((world) => {
        const stats = statsMap?.[world.name] || {};
        const card = document.createElement('div');
        card.className = 'world-card';
        card.innerHTML = `
            <div class="world-card-title">${world.name}</div>
            <div class="world-card-meta">
                <span>Players: <strong>${formatNumber(world.playerCount)}</strong></span>
                <span>Ticking: <strong>${world.isTicking ? 'Yes' : 'No'}</strong></span>
            </div>
            <div class="world-card-stats">
                <div><span>TPS</span><strong>${formatNumber(stats.tps)}</strong></div>
                <div><span>Chunks</span><strong>${formatNumber(stats.loadedChunks)}</strong></div>
                <div><span>Entities</span><strong>${formatNumber(stats.entityCount)}</strong></div>
            </div>
        `;
        gotaleWorldCards.appendChild(card);
    });
}

async function refreshWorlds() {
    if (!gotaleWorldsConfig || !gotaleWorldsConfig.enabled) return;
    try {
        let apiOk = false;
        const response = await fetch(`/api/server/${SERVER_ID}/gotale/proxy/worlds`);
        if (!response.ok) {
            gotaleWorldsApiHealthy = false;
            applyConnectionState();
            return;
        }
        apiOk = true;
        const data = await response.json();
        const worlds = data.worlds || [];
        const statsMap = {};
        await Promise.all(
            worlds.map(async (world) => {
                try {
                    const res = await fetch(`/api/server/${SERVER_ID}/gotale/proxy/worlds/${encodeURIComponent(world.name)}/stats`);
                    if (res.ok) {
                        apiOk = true;
                        statsMap[world.name] = await res.json();
                    }
                } catch (error) {
                    console.warn('World stats fetch failed', error);
                }
            })
        );
        renderWorldCards(worlds, statsMap);
        gotaleWorldsApiHealthy = apiOk;
        applyConnectionState();
    } catch (error) {
        gotaleWorldsApiHealthy = false;
        applyConnectionState();
        console.warn('GoTale worlds refresh failed', error);
    }
}

function joinWorldsRoom() {
    if (gotaleWorldsJoined) return;
    gotaleSocket.emit('join_gotale', { server_id: SERVER_ID });
    gotaleWorldsJoined = true;
}

async function initWorldsPanel() {
    if (!gotaleWorldsPanel) return;
    try {
        const response = await fetch(`/api/server/${SERVER_ID}/gotale/config`);
        const data = await response.json();
        if (!response.ok || !data.success || !data.configured) {
            setWorldsConnection('warning', 'Not configured');
            return;
        }
        gotaleWorldsConfig = data;
        if (!gotaleWorldsConfig.enabled) {
            setWorldsConnection('warning', 'Disabled');
            return;
        }
        gotaleWorldsApiHealthy = false;
        setWorldsConnection('warning', 'Connecting…');
        await refreshWorlds();
        joinWorldsRoom();
        setInterval(refreshWorlds, 20000);
    } catch (error) {
        gotaleWorldsApiHealthy = false;
        applyConnectionState();
    }
}

gotaleSocket.on('connect', () => {
    if (gotaleWorldsConfig && gotaleWorldsConfig.enabled) {
        joinWorldsRoom();
    }
});

gotaleSocket.on('gotale_status', (data) => {
    if (!data || Number(data.server_id) !== Number(SERVER_ID)) return;
    gotaleWorldsWsHealthy = !!data.connected;
    applyConnectionState();
});

if (gotaleWorldsRefresh) {
    gotaleWorldsRefresh.addEventListener('click', refreshWorlds);
}

initWorldsPanel();
