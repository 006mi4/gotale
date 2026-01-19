const minRamInput = document.getElementById('minRam');
const maxRamInput = document.getElementById('maxRam');
const gameProfileInput = document.getElementById('gameProfile');
const authModeSelect = document.getElementById('authMode');
const automaticUpdateToggle = document.getElementById('automaticUpdate');
const allowOpToggle = document.getElementById('allowOp');
const acceptEarlyPluginsToggle = document.getElementById('acceptEarlyPlugins');
const assetPackInput = document.getElementById('assetPack');
const enableBackupsToggle = document.getElementById('enableBackups');
const backupDirectoryInput = document.getElementById('backupDirectory');
const backupFrequencyInput = document.getElementById('backupFrequency');
const disableSentryToggle = document.getElementById('disableSentry');
const leverageAotCacheToggle = document.getElementById('leverageAotCache');
const jvmArgsInput = document.getElementById('jvmArgs');
const saveBtn = document.getElementById('saveStartupSettings');
const saveToast = document.getElementById('saveToast');

const csrfHeader = () => ({ 'X-CSRFToken': CSRF_TOKEN });

function showToast(message, type = 'success') {
    saveToast.textContent = message;
    saveToast.classList.remove('error');
    if (type === 'error') {
        saveToast.classList.add('error');
    }
    saveToast.classList.add('visible');
    setTimeout(() => {
        saveToast.classList.remove('visible');
    }, 2800);
}

function toOptionalInt(value) {
    if (value === null || value === undefined) return null;
    const cleaned = String(value).trim();
    if (!cleaned) return null;
    const parsed = Number(cleaned);
    if (Number.isNaN(parsed) || parsed <= 0) return null;
    return Math.floor(parsed);
}

function applySettings(settings) {
    minRamInput.value = settings.min_ram_mb || '';
    maxRamInput.value = settings.max_ram_mb || '';
    gameProfileInput.value = settings.game_profile || '';
    authModeSelect.value = settings.auth_mode || 'authenticated';
    automaticUpdateToggle.checked = Boolean(settings.automatic_update);
    allowOpToggle.checked = settings.allow_op !== false;
    acceptEarlyPluginsToggle.checked = Boolean(settings.accept_early_plugins);
    assetPackInput.value = settings.asset_pack || 'Assets.zip';
    enableBackupsToggle.checked = Boolean(settings.enable_backups);
    backupDirectoryInput.value = settings.backup_directory || '';
    backupFrequencyInput.value = settings.backup_frequency || 30;
    disableSentryToggle.checked = Boolean(settings.disable_sentry);
    leverageAotCacheToggle.checked = settings.leverage_aot_cache !== false;
    jvmArgsInput.value = settings.jvm_args || '';
}

async function loadSettings() {
    const response = await fetch(`/api/server/${SERVER_ID}/startup-settings`);
    const data = await response.json();
    if (!data.success) {
        showToast('Failed to load startup settings.', 'error');
        return;
    }
    applySettings(data.settings || {});
}

async function saveSettings() {
    const assetPackValue = assetPackInput.value.trim() || 'Assets.zip';
    const payload = {
        min_ram_mb: toOptionalInt(minRamInput.value),
        max_ram_mb: toOptionalInt(maxRamInput.value),
        game_profile: gameProfileInput.value.trim(),
        auth_mode: authModeSelect.value,
        automatic_update: automaticUpdateToggle.checked,
        allow_op: allowOpToggle.checked,
        accept_early_plugins: acceptEarlyPluginsToggle.checked,
        asset_pack: assetPackValue,
        enable_backups: enableBackupsToggle.checked,
        backup_directory: backupDirectoryInput.value.trim(),
        backup_frequency: toOptionalInt(backupFrequencyInput.value) || 30,
        disable_sentry: disableSentryToggle.checked,
        leverage_aot_cache: leverageAotCacheToggle.checked,
        jvm_args: jvmArgsInput.value.trim()
    };

    const response = await fetch(`/api/server/${SERVER_ID}/startup-settings`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json', ...csrfHeader() },
        body: JSON.stringify(payload)
    });
    const data = await response.json();
    if (!data.success) {
        showToast(data.error || 'Saving startup settings failed.', 'error');
        return;
    }
    applySettings(data.settings || {});
    showToast('Startup settings saved.');
}

if (saveBtn) {
    saveBtn.addEventListener('click', () => {
        saveSettings();
    });
}

loadSettings();
