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
const previewCmd = document.getElementById('startupPreviewCmd');
const previewEnv = document.getElementById('startupPreviewEnv');
const previewNote = document.getElementById('startupPreviewNote');

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
    renderPreview(getFormSettings());
}

function getFormSettings() {
    return {
        min_ram_mb: toOptionalInt(minRamInput.value),
        max_ram_mb: toOptionalInt(maxRamInput.value),
        game_profile: gameProfileInput.value.trim(),
        auth_mode: authModeSelect.value,
        automatic_update: automaticUpdateToggle.checked,
        allow_op: allowOpToggle.checked,
        accept_early_plugins: acceptEarlyPluginsToggle.checked,
        asset_pack: assetPackInput.value.trim() || 'Assets.zip',
        enable_backups: enableBackupsToggle.checked,
        backup_directory: backupDirectoryInput.value.trim(),
        backup_frequency: toOptionalInt(backupFrequencyInput.value) || 30,
        disable_sentry: disableSentryToggle.checked,
        leverage_aot_cache: leverageAotCacheToggle.checked,
        jvm_args: jvmArgsInput.value.trim()
    };
}

function renderPreview(settings) {
    if (!previewCmd || !previewEnv) return;

    const args = [];
    const combinedArgs = settings.jvm_args || '';
    const hasXms = /(^|\s)-Xms\S+/.test(combinedArgs);
    const hasXmx = /(^|\s)-Xmx\S+/.test(combinedArgs);

    if (settings.leverage_aot_cache) {
        args.push('-XX:AOTCache=HytaleServer.aot');
    }
    if (settings.min_ram_mb && !hasXms) {
        args.push(`-Xms${settings.min_ram_mb}M`);
    }
    if (settings.max_ram_mb && !hasXmx) {
        args.push(`-Xmx${settings.max_ram_mb}M`);
    }
    if (combinedArgs) {
        args.push(combinedArgs);
    }

    const assetPack = settings.asset_pack || 'Assets.zip';
    const cmd = [
        'java',
        ...args,
        '-jar',
        'HytaleServer.jar',
        '--assets',
        assetPack,
        '--bind',
        `0.0.0.0:${SERVER_PORT}`
    ].filter(Boolean);
    previewCmd.textContent = cmd.join(' ');

    const env = [];
    if (settings.game_profile) env.push(`GAME_PROFILE=${settings.game_profile}`);
    env.push(`AUTH_MODE=${settings.auth_mode || 'authenticated'}`);
    env.push(`AUTOMATIC_UPDATE=${settings.automatic_update ? 'true' : 'false'}`);
    env.push(`ALLOW_OP=${settings.allow_op ? 'true' : 'false'}`);
    env.push(`ACCEPT_EARLY_PLUGINS=${settings.accept_early_plugins ? 'true' : 'false'}`);
    env.push(`ASSET_PACK=${assetPack}`);
    env.push(`ENABLE_BACKUPS=${settings.enable_backups ? 'true' : 'false'}`);
    if (settings.backup_directory) env.push(`BACKUP_DIRECTORY=${settings.backup_directory}`);
    env.push(`BACKUP_FREQUENCY=${settings.backup_frequency || 30}`);
    env.push(`DISABLE_SENTRY=${settings.disable_sentry ? 'true' : 'false'}`);
    if (settings.jvm_args) env.push(`JVM_ARGS=${settings.jvm_args}`);
    env.push(`LEVERAGE_AHEAD_OF_TIME_CACHE=${settings.leverage_aot_cache ? 'true' : 'false'}`);
    previewEnv.textContent = env.join('\n');

    if (previewNote) {
        previewNote.textContent = settings.leverage_aot_cache
            ? 'AOT cache flag is shown when enabled (requires HytaleServer.aot to exist).'
            : '';
    }
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
    const payload = getFormSettings();

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

[
    minRamInput,
    maxRamInput,
    gameProfileInput,
    authModeSelect,
    automaticUpdateToggle,
    allowOpToggle,
    acceptEarlyPluginsToggle,
    assetPackInput,
    enableBackupsToggle,
    backupDirectoryInput,
    backupFrequencyInput,
    disableSentryToggle,
    leverageAotCacheToggle,
    jvmArgsInput
].forEach((element) => {
    if (!element) return;
    element.addEventListener('input', () => {
        renderPreview(getFormSettings());
    });
    element.addEventListener('change', () => {
        renderPreview(getFormSettings());
    });
});

loadSettings();
