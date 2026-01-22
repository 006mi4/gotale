const webhookStatus = document.getElementById('webhookStatus');
const saveWebhooksBtn = document.getElementById('saveWebhooksBtn');

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

loadWebhooks();
