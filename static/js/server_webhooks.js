const webhookStatus = document.getElementById('webhookStatus');
const saveWebhooksBtn = document.getElementById('saveWebhooksBtn');
const refreshWebhookDiagBtn = document.getElementById('refreshWebhookDiagBtn');

const diagBridge = document.getElementById('webhookDiagBridge');
const diagWorker = document.getElementById('webhookDiagWorker');
const diagQueue = document.getElementById('webhookDiagQueue');
const diagSent = document.getElementById('webhookDiagSent');
const diagFailed = document.getElementById('webhookDiagFailed');
const diagDropped = document.getElementById('webhookDiagDropped');
const diagRateLimited = document.getElementById('webhookDiagRateLimited');
const diagLastEvent = document.getElementById('webhookDiagLastEvent');
const diagLastSuccess = document.getElementById('webhookDiagLastSuccess');
const diagLastFailure = document.getElementById('webhookDiagLastFailure');
const diagLastError = document.getElementById('webhookDiagLastError');
const diagUpdated = document.getElementById('webhookDiagUpdated');

const webhookFields = {
    player_connect: document.getElementById('webhookConnect'),
    player_disconnect: document.getElementById('webhookDisconnect'),
    player_death: document.getElementById('webhookDeath'),
    player_chat: document.getElementById('webhookChat'),
};

const webhookTemplates = {
    player_connect: document.getElementById('webhookConnectTemplate'),
    player_disconnect: document.getElementById('webhookDisconnectTemplate'),
    player_death: document.getElementById('webhookDeathTemplate'),
    player_chat: document.getElementById('webhookChatTemplate'),
};

const webhookToggles = {
    player_connect: document.querySelector('[data-webhook-toggle="player_connect"]'),
    player_disconnect: document.querySelector('[data-webhook-toggle="player_disconnect"]'),
    player_death: document.querySelector('[data-webhook-toggle="player_death"]'),
    player_chat: document.querySelector('[data-webhook-toggle="player_chat"]'),
};

const csrfHeader = () => ({ 'X-CSRFToken': CSRF_TOKEN });

function setStatus(message, isSaved = true) {
    if (!webhookStatus) return;
    webhookStatus.textContent = message;
    webhookStatus.classList.toggle('saved', isSaved);
}

function formatEpoch(seconds) {
    if (!seconds) return '-';
    const date = new Date(seconds * 1000);
    if (Number.isNaN(date.getTime())) return '-';
    return date.toLocaleString();
}

function updateDiagText(element, value) {
    if (!element) return;
    element.textContent = value;
}

function renderDiagnostics(diag) {
    updateDiagText(diagBridge, diag.connected ? 'Connected' : 'Disconnected');
    updateDiagText(diagWorker, diag.worker_alive ? 'Running' : 'Stopped');
    updateDiagText(diagQueue, `${diag.queue_size || 0}/${diag.queue_maxsize || 0}`);
    updateDiagText(diagSent, String(diag.sent_total || 0));
    updateDiagText(diagFailed, String(diag.failed_total || 0));
    updateDiagText(diagDropped, String(diag.dropped_total || 0));
    updateDiagText(diagRateLimited, String(diag.rate_limited_total || 0));
    updateDiagText(diagLastEvent, diag.last_event_type || '-');
    updateDiagText(diagLastSuccess, `${formatEpoch(diag.last_success_at)} (${diag.last_success_event_type || '-'})`);
    updateDiagText(diagLastFailure, `${formatEpoch(diag.last_failure_at)} (${diag.last_failure_event_type || '-'})`);
    updateDiagText(diagLastError, diag.last_error || '-');
    updateDiagText(diagUpdated, formatEpoch(diag.updated_at));
}

async function loadWebhookDiagnostics() {
    try {
        const response = await fetch(`/api/server/${SERVER_ID}/gotale/webhooks/diagnostics`);
        const data = await response.json();
        if (!response.ok || !data.success) return;
        renderDiagnostics(data.diagnostics || {});
    } catch (error) {
        updateDiagText(diagUpdated, 'Failed to refresh diagnostics.');
    }
}

async function loadWebhooks() {
    try {
        const response = await fetch(`/api/server/${SERVER_ID}/gotale/webhooks`);
        const data = await response.json();
        if (!response.ok || !data.success) {
            setStatus('Failed to load webhooks.', false);
            return;
        }
        const webhooks = data.webhooks || {};
        Object.keys(webhookFields).forEach((key) => {
            if (webhookFields[key]) {
                webhookFields[key].value = webhooks[key]?.url || '';
            }
            if (webhookToggles[key]) {
                webhookToggles[key].checked = !!webhooks[key]?.enabled;
            }
            if (webhookTemplates[key]) {
                const template = webhooks[key]?.template || '';
                const fallback = webhooks[key]?.default_template || '';
                webhookTemplates[key].value = template || fallback;
            }
        });
        setStatus('All changes saved.', true);
    } catch (error) {
        setStatus('Failed to load webhooks.', false);
    }
}

async function saveWebhooks() {
    const payload = {};
    Object.keys(webhookFields).forEach((key) => {
        payload[key] = {
            url: webhookFields[key]?.value || '',
            enabled: !!webhookToggles[key]?.checked,
            template: webhookTemplates[key]?.value || ''
        };
    });

    try {
        const response = await fetch(`/api/server/${SERVER_ID}/gotale/webhooks`, {
            method: 'POST',
            headers: {
                'Content-Type': 'application/json',
                ...csrfHeader()
            },
            body: JSON.stringify(payload)
        });
        const data = await response.json();
        if (!response.ok || !data.success) {
            setStatus('Failed to save webhooks.', false);
            return;
        }
        setStatus('All changes saved.', true);
    } catch (error) {
        setStatus('Failed to save webhooks.', false);
    }
}

if (saveWebhooksBtn) {
    saveWebhooksBtn.addEventListener('click', saveWebhooks);
}

if (refreshWebhookDiagBtn) {
    refreshWebhookDiagBtn.addEventListener('click', loadWebhookDiagnostics);
}

loadWebhooks();
loadWebhookDiagnostics();
setInterval(loadWebhookDiagnostics, 10000);
