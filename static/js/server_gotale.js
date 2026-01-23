const gotalePanel = document.getElementById('gotalePanel');
const gotaleConnection = document.getElementById('gotaleConnection');
const gotaleRefresh = document.getElementById('gotaleRefresh');
const gotaleServerInfo = document.getElementById('gotaleServerInfo');
const gotalePerf = document.getElementById('gotalePerf');
const gotaleMemory = document.getElementById('gotaleMemory');
const gotalePlayers = document.getElementById('gotalePlayers');
const gotalePlayersEmpty = document.getElementById('gotalePlayersEmpty');
const gotaleEvents = document.getElementById('gotaleEvents');
const gotaleEventsEmpty = document.getElementById('gotaleEventsEmpty');

let gotaleConfig = null;
let gotalePlayersRefreshTimer = null;
const eventBuffer = [];
let gotaleApiHealthy = false;
let gotaleWsHealthy = false;
let gotaleWsRetryAt = 0;
let gotaleWsRetryTimer = null;

const gotaleSocket = window.hsmSocket || io();
window.hsmSocket = gotaleSocket;
let gotaleJoined = false;

function updateConnection(state, label) {
    if (!gotaleConnection) return;
    gotaleConnection.classList.remove('online', 'offline', 'warning');
    gotaleConnection.classList.add(state);
    gotaleConnection.textContent = label;
}

function applyConnectionState() {
    if (gotaleWsHealthy) {
        updateConnection('online', 'Live');
        return;
    }
    if (gotaleApiHealthy) {
        const now = Date.now();
        if (gotaleWsRetryAt && now < gotaleWsRetryAt) {
            updateConnection('warning', 'API only (WS retrying…)');
        } else {
            updateConnection('warning', 'API only');
        }
        return;
    }
    updateConnection('offline', 'Disconnected');
}

function formatUptime(seconds) {
    if (typeof seconds !== 'number') return '--';
    const hrs = Math.floor(seconds / 3600);
    const mins = Math.floor((seconds % 3600) / 60);
    return `${hrs}h ${mins}m`;
}

function formatNumber(value, suffix = '') {
    if (value === null || value === undefined || Number.isNaN(value)) return '--';
    return `${value}${suffix}`;
}

function renderInfo(info) {
    if (!gotaleServerInfo) return;
    const online = info?.online ? 'Yes' : 'No';
    const players = `${formatNumber(info?.onlinePlayers)} / ${formatNumber(info?.maxPlayers)}`;
    const worlds = formatNumber(info?.worldCount);
    const uptime = formatUptime(info?.uptimeSeconds);
    const version = info?.version ? `${info?.version} (${info?.patchline || '-'})` : '--';
    gotaleServerInfo.innerHTML = `
        <div class="stat-row"><span>Online</span><strong>${online}</strong></div>
        <div class="stat-row"><span>Players</span><strong>${players}</strong></div>
        <div class="stat-row"><span>Worlds</span><strong>${worlds}</strong></div>
        <div class="stat-row"><span>Uptime</span><strong>${uptime}</strong></div>
        <div class="stat-row"><span>Version</span><strong>${version}</strong></div>
    `;
}

function renderPerformance(perf) {
    if (!gotalePerf) return;
    gotalePerf.innerHTML = `
        <div class="stat-row"><span>TPS</span><strong>${formatNumber(perf?.tps)}</strong></div>
        <div class="stat-row"><span>MSPT</span><strong>${formatNumber(perf?.mspt)}</strong></div>
        <div class="stat-row"><span>CPU</span><strong>${formatNumber(perf?.cpuUsage, '%')}</strong></div>
        <div class="stat-row"><span>Threads</span><strong>${formatNumber(perf?.threadCount)}</strong></div>
    `;
}

function renderMemory(mem) {
    if (!gotaleMemory) return;
    const heap = `${formatNumber(mem?.heapUsedMB, 'MB')} / ${formatNumber(mem?.heapMaxMB, 'MB')}`;
    const committed = formatNumber(mem?.heapCommittedMB, 'MB');
    const total = formatNumber(mem?.totalMemoryMB, 'MB');
    const free = formatNumber(mem?.freeMemoryMB, 'MB');
    gotaleMemory.innerHTML = `
        <div class="stat-row"><span>Heap</span><strong>${heap}</strong></div>
        <div class="stat-row"><span>Committed</span><strong>${committed}</strong></div>
        <div class="stat-row"><span>Total</span><strong>${total}</strong></div>
        <div class="stat-row"><span>Free</span><strong>${free}</strong></div>
    `;
}

function renderPlayers(players) {
    if (!gotalePlayers || !gotalePlayersEmpty) return;
    gotalePlayers.innerHTML = '';
    if (!players || !players.length) {
        gotalePlayersEmpty.style.display = 'block';
        return;
    }
    gotalePlayersEmpty.style.display = 'none';
    players.forEach((player) => {
        const row = document.createElement('div');
        row.className = 'player-row';
        row.innerHTML = `
            <div>
                <div class="player-name">${player.name || player.uuid || 'Unknown'}</div>
                <div class="player-sub">${player.world || 'world'} • ${formatNumber(player.position?.x)} / ${formatNumber(player.position?.y)} / ${formatNumber(player.position?.z)}</div>
            </div>
            <span class="player-chip">${player.uuid ? player.uuid.slice(0, 8) : '--'}</span>
        `;
        gotalePlayers.appendChild(row);
    });
}

function pushEvent(event) {
    if (!gotaleEvents || !gotaleEventsEmpty) return;
    eventBuffer.unshift(event);
    if (eventBuffer.length > 40) {
        eventBuffer.pop();
    }
    gotaleEvents.innerHTML = '';
    eventBuffer.forEach((item) => {
        const row = document.createElement('div');
        row.className = 'event-row';
        row.innerHTML = `
            <span class="event-dot ${item.variant}"></span>
            <div>
                <div class="event-title">${item.title}</div>
                <div class="event-sub">${item.subtitle}</div>
            </div>
            <span class="event-time">${item.time}</span>
        `;
        gotaleEvents.appendChild(row);
    });
    gotaleEventsEmpty.style.display = eventBuffer.length ? 'none' : 'block';
}

function formatTimestamp(ts) {
    if (!ts) return 'now';
    try {
        const date = new Date(ts);
        return date.toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' });
    } catch (e) {
        return 'now';
    }
}

function eventToRow(evt) {
    switch (evt.type) {
        case 'player_connect':
            return {
                title: `${evt.player} joined`,
                subtitle: 'Player connected',
                time: formatTimestamp(evt.timestamp),
                variant: 'success'
            };
        case 'player_disconnect':
            return {
                title: `${evt.player} left`,
                subtitle: 'Player disconnected',
                time: formatTimestamp(evt.timestamp),
                variant: 'muted'
            };
        case 'player_chat':
            return {
                title: `${evt.player}`,
                subtitle: evt.message || 'Chat message',
                time: formatTimestamp(evt.timestamp),
                variant: 'info'
            };
        case 'player_death':
            return {
                title: `${evt.player} died`,
                subtitle: evt.cause ? `Cause: ${evt.cause}` : 'Player death',
                time: formatTimestamp(evt.timestamp),
                variant: 'danger'
            };
        case 'performance_update':
            return {
                title: `TPS ${formatNumber(evt.tps)} • MSPT ${formatNumber(evt.mspt)}`,
                subtitle: 'Performance update',
                time: formatTimestamp(evt.timestamp),
                variant: 'info'
            };
        default:
            return null;
    }
}

function schedulePlayersRefresh() {
    if (gotalePlayersRefreshTimer) return;
    gotalePlayersRefreshTimer = setTimeout(() => {
        gotalePlayersRefreshTimer = null;
        refreshPlayers();
    }, 1500);
}

async function refreshPlayers() {
    try {
        const response = await fetch(`/api/server/${SERVER_ID}/gotale/proxy/players`);
        if (!response.ok) return;
        const data = await response.json();
        renderPlayers(data.players || []);
    } catch (error) {
        console.warn('Player refresh failed', error);
    }
}

async function refreshGotale() {
    if (!gotaleConfig || !gotaleConfig.enabled) {
        updateConnection('warning', 'Not configured');
        return;
    }
    try {
        let apiOk = false;
        const [infoRes, perfRes, memRes, playerRes] = await Promise.all([
            fetch(`/api/server/${SERVER_ID}/gotale/proxy/server/info`),
            fetch(`/api/server/${SERVER_ID}/gotale/proxy/server/performance`),
            fetch(`/api/server/${SERVER_ID}/gotale/proxy/server/memory`),
            fetch(`/api/server/${SERVER_ID}/gotale/proxy/players`)
        ]);
        if (infoRes.ok) {
            apiOk = true;
            renderInfo(await infoRes.json());
        }
        if (perfRes.ok) {
            apiOk = true;
            renderPerformance(await perfRes.json());
        }
        if (memRes.ok) {
            apiOk = true;
            renderMemory(await memRes.json());
        }
        if (playerRes.ok) {
            apiOk = true;
            const data = await playerRes.json();
            renderPlayers(data.players || []);
        }
        gotaleApiHealthy = apiOk;
        applyConnectionState();
    } catch (error) {
        gotaleApiHealthy = false;
        applyConnectionState();
        console.warn('GoTale refresh failed', error);
    }
}

function joinGotaleRoom() {
    if (gotaleJoined) return;
    gotaleSocket.emit('join_gotale', { server_id: SERVER_ID });
    gotaleJoined = true;
}

function scheduleWsRetry(delayMs) {
    if (gotaleWsRetryTimer) return;
    gotaleWsRetryAt = Date.now() + delayMs;
    console.warn(`[GoTale] WS offline for server ${SERVER_ID}; retrying in ${Math.round(delayMs / 1000)}s`);
    gotaleWsRetryTimer = setTimeout(() => {
        gotaleWsRetryTimer = null;
        gotaleWsRetryAt = 0;
        gotaleJoined = false;
        console.info(`[GoTale] Retrying WS join for server ${SERVER_ID}`);
        joinGotaleRoom();
        applyConnectionState();
    }, delayMs);
}

async function initGotale() {
    if (!gotalePanel) return;
    try {
        const response = await fetch(`/api/server/${SERVER_ID}/gotale/config`);
        const data = await response.json();
        if (!response.ok || !data.success || !data.configured) {
            updateConnection('warning', 'Not configured');
            return;
        }
        gotaleConfig = data;
        if (!gotaleConfig.enabled) {
            updateConnection('warning', 'Disabled');
            return;
        }
        gotaleApiHealthy = false;
        updateConnection('warning', 'Connecting…');
        await refreshGotale();
        joinGotaleRoom();
        setInterval(refreshGotale, 12000);
    } catch (error) {
        gotaleApiHealthy = false;
        applyConnectionState();
        console.warn('GoTale init failed', error);
    }
}

gotaleSocket.on('connect', () => {
    if (gotaleConfig && gotaleConfig.enabled) {
        joinGotaleRoom();
    }
});

gotaleSocket.on('gotale_status', (data) => {
    if (!data || Number(data.server_id) !== Number(SERVER_ID)) return;
    gotaleWsHealthy = !!data.connected;
    if (gotaleWsHealthy) {
        console.info(`[GoTale] WS connected for server ${SERVER_ID}`);
    } else {
        console.warn(`[GoTale] WS disconnected for server ${SERVER_ID}`);
    }
    applyConnectionState();
    if (!gotaleWsHealthy) {
        scheduleWsRetry(4000);
    }
});

gotaleSocket.on('gotale_event', (data) => {
    if (!data || Number(data.server_id) !== Number(SERVER_ID)) return;
    const payload = data.event;
    if (!payload || !payload.type) return;
    const row = eventToRow(payload);
    if (row) {
        pushEvent(row);
    }
    if (payload.type === 'performance_update') {
        renderPerformance(payload);
    }
    if (payload.type === 'player_connect' || payload.type === 'player_disconnect') {
        schedulePlayersRefresh();
    }
});

if (gotaleRefresh) {
    gotaleRefresh.addEventListener('click', () => {
        refreshGotale();
    });
}

initGotale();
