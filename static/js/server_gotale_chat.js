const chatConnection = document.getElementById('chatConnection');
const chatRefresh = document.getElementById('chatRefresh');
const chatLog = document.getElementById('chatLog');
const chatEmpty = document.getElementById('chatEmpty');
const chatLoadedStatus = document.getElementById('chatLoadedStatus');
const chatSearchForm = document.getElementById('chatSearchForm');
const chatSearchInput = document.getElementById('chatSearchInput');
const chatSearchClear = document.getElementById('chatSearchClear');
const chatSearchResults = document.getElementById('chatSearchResults');
const chatSearchList = document.getElementById('chatSearchList');
const chatSearchEmpty = document.getElementById('chatSearchEmpty');

const gotaleSocket = window.hsmSocket || io();
window.hsmSocket = gotaleSocket;
let chatJoined = false;

function setConnection(state, label) {
    if (!chatConnection) return;
    chatConnection.classList.remove('online', 'offline', 'warning');
    chatConnection.classList.add(state);
    chatConnection.textContent = label;
}

function formatTime(value) {
    if (!value) return '--';
    try {
        const date = new Date(value);
        return date.toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' });
    } catch (error) {
        return '--';
    }
}

function createChatRow(message) {
    const row = document.createElement('div');
    row.className = 'chat-row';
    row.innerHTML = `
        <div class="chat-meta">
            <span class="chat-time">${formatTime(message.timestamp)}</span>
            <span class="chat-player">${message.player || 'Unknown'}</span>
        </div>
        <div class="chat-message">${message.message || ''}</div>
    `;
    return row;
}

function renderChat(messages) {
    if (!chatLog || !chatEmpty) return;
    chatLog.innerHTML = '';
    if (!messages || !messages.length) {
        chatEmpty.style.display = 'block';
        return;
    }
    chatEmpty.style.display = 'none';
    messages.forEach((message) => {
        chatLog.appendChild(createChatRow(message));
    });
    chatLog.scrollTop = chatLog.scrollHeight;
}

function appendChatMessage(message) {
    if (!chatLog || !chatEmpty) return;
    if (chatEmpty.style.display !== 'none') {
        chatEmpty.style.display = 'none';
    }
    chatLog.appendChild(createChatRow(message));
    chatLog.scrollTop = chatLog.scrollHeight;
}

function renderSearchResults(messages) {
    if (!chatSearchResults || !chatSearchList || !chatSearchEmpty) return;
    chatSearchResults.classList.remove('hidden');
    chatSearchList.innerHTML = '';
    if (!messages || !messages.length) {
        chatSearchEmpty.style.display = 'block';
        return;
    }
    chatSearchEmpty.style.display = 'none';
    messages.forEach((message) => {
        chatSearchList.appendChild(createChatRow(message));
    });
}

function clearSearchResults() {
    if (!chatSearchResults) return;
    chatSearchResults.classList.add('hidden');
    if (chatSearchList) chatSearchList.innerHTML = '';
    if (chatSearchEmpty) chatSearchEmpty.style.display = 'none';
}

async function fetchChatLogs() {
    if (chatLoadedStatus) {
        chatLoadedStatus.textContent = 'Loading…';
        chatLoadedStatus.classList.remove('saved');
    }
    try {
        const response = await fetch(`/api/server/${SERVER_ID}/gotale/chat/logs?limit=200`);
        if (!response.ok) return;
        const data = await response.json();
        if (!data.success) return;
        renderChat(data.messages || []);
        if (chatLoadedStatus) {
            chatLoadedStatus.textContent = 'Loaded';
            chatLoadedStatus.classList.add('saved');
        }
    } catch (error) {
        console.warn('Chat log fetch failed', error);
        if (chatLoadedStatus) {
            chatLoadedStatus.textContent = 'Failed';
            chatLoadedStatus.classList.remove('saved');
        }
    }
}

function joinChatRoom() {
    if (chatJoined) return;
    gotaleSocket.emit('join_gotale', { server_id: SERVER_ID });
    chatJoined = true;
}

async function searchChat(query) {
    if (!query) {
        clearSearchResults();
        return;
    }
    try {
        const response = await fetch(`/api/server/${SERVER_ID}/gotale/chat/search?q=${encodeURIComponent(query)}&limit=200`);
        if (!response.ok) return;
        const data = await response.json();
        if (!data.success) return;
        renderSearchResults(data.messages || []);
    } catch (error) {
        console.warn('Chat search failed', error);
    }
}

gotaleSocket.on('connect', () => {
    joinChatRoom();
});

gotaleSocket.on('gotale_status', (data) => {
    if (!data || Number(data.server_id) !== Number(SERVER_ID)) return;
    setConnection(data.connected ? 'online' : 'offline', data.connected ? 'Live' : 'Disconnected');
});

gotaleSocket.on('gotale_event', (data) => {
    if (!data || Number(data.server_id) !== Number(SERVER_ID)) return;
    const payload = data.event;
    if (!payload || payload.type !== 'player_chat') return;
    appendChatMessage({
        player: payload.player,
        message: payload.message,
        timestamp: payload.timestamp
    });
});

if (chatRefresh) {
    chatRefresh.addEventListener('click', () => {
        fetchChatLogs();
    });
}

if (chatSearchForm) {
    chatSearchForm.addEventListener('submit', (event) => {
        event.preventDefault();
        const query = (chatSearchInput?.value || '').trim();
        searchChat(query);
    });
}

if (chatSearchClear) {
    chatSearchClear.addEventListener('click', () => {
        if (chatSearchInput) chatSearchInput.value = '';
        clearSearchResults();
    });
}

fetchChatLogs();
joinChatRoom();
