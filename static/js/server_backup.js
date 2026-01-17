const backupModeInputs = Array.from(document.querySelectorAll('input[name="backupMode"]'));
const worldSelectWrap = document.getElementById('worldSelectWrap');
const worldList = document.getElementById('worldList');
const scheduleToggle = document.getElementById('scheduleToggle');
const scheduleValue = document.getElementById('scheduleValue');
const scheduleUnit = document.getElementById('scheduleUnit');
const startupToggle = document.getElementById('startupToggle');
const saveSettingsBtn = document.getElementById('saveSettingsBtn');
const runBackupBtn = document.getElementById('runBackupBtn');
const backupList = document.getElementById('backupList');
const backupStatus = document.getElementById('backupStatus');
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

function setMode(mode) {
    backupModeInputs.forEach((input) => {
        input.checked = input.value === mode;
    });
    worldSelectWrap.style.display = mode === 'world' ? 'block' : 'none';
}

function getMode() {
    const selected = backupModeInputs.find((input) => input.checked);
    return selected ? selected.value : 'worlds';
}

function formatBytes(bytes) {
    if (!bytes && bytes !== 0) return '';
    const sizes = ['B', 'KB', 'MB', 'GB'];
    let value = bytes;
    let index = 0;
    while (value >= 1024 && index < sizes.length - 1) {
        value /= 1024;
        index += 1;
    }
    return `${value.toFixed(value >= 10 || index === 0 ? 0 : 1)} ${sizes[index]}`;
}

function formatTimestamp(timestamp) {
    if (!timestamp) return 'Unknown';
    const parts = timestamp.split('-');
    if (parts.length !== 5) return timestamp;
    const [day, month, year, hour, minute] = parts;
    return `${day}.${month}.${year} ${hour}:${minute}`;
}

function updateBackupStatus(settings) {
    if (!settings) return;
    const last = settings.last_backup_at ? new Date(settings.last_backup_at * 1000) : null;
    if (!last) {
        backupStatus.textContent = 'No backups recorded yet.';
        return;
    }
    const formatted = `${last.toLocaleDateString()} ${last.toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' })}`;
    backupStatus.textContent = `Last backup: ${formatted}`;
}

function renderWorlds(worlds, selectedWorlds) {
    worldList.innerHTML = '';
    if (!worlds.length) {
        worldList.innerHTML = '<div class="muted">No worlds found.</div>';
        return;
    }
    worlds.forEach((world) => {
        const wrapper = document.createElement('label');
        wrapper.className = 'backup-world';
        const checkbox = document.createElement('input');
        checkbox.type = 'checkbox';
        checkbox.value = world;
        checkbox.checked = selectedWorlds.includes(world);
        const label = document.createElement('span');
        label.textContent = world;
        wrapper.appendChild(checkbox);
        wrapper.appendChild(label);
        worldList.appendChild(wrapper);
    });
}

function getSelectedWorlds() {
    return Array.from(worldList.querySelectorAll('input[type="checkbox"]:checked')).map((input) => input.value);
}

async function loadSettings() {
    const response = await fetch(`/api/server/${SERVER_ID}/backup-settings`);
    const data = await response.json();
    if (!data.success) {
        showToast('Failed to load backup settings.', 'error');
        return;
    }
    const settings = data.settings || {};
    setMode(settings.mode || 'worlds');
    renderWorlds(data.worlds || [], settings.selected_worlds || []);
    scheduleToggle.checked = Boolean(settings.schedule_enabled);
    scheduleValue.value = settings.interval_value || 24;
    scheduleUnit.value = settings.interval_unit || 'hours';
    startupToggle.checked = Boolean(settings.backup_on_start);
    updateBackupStatus(settings);
}

async function saveSettings() {
    const payload = {
        mode: getMode(),
        selected_worlds: getSelectedWorlds(),
        schedule_enabled: scheduleToggle.checked,
        interval_value: Number(scheduleValue.value || 1),
        interval_unit: scheduleUnit.value,
        backup_on_start: startupToggle.checked
    };
    const response = await fetch(`/api/server/${SERVER_ID}/backup-settings`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json', ...csrfHeader() },
        body: JSON.stringify(payload)
    });
    const data = await response.json();
    if (!data.success) {
        showToast('Saving settings failed.', 'error');
        return;
    }
    updateBackupStatus(data.settings);
    showToast('Backup settings saved.');
}

async function runBackup() {
    const payload = {
        mode: getMode(),
        selected_worlds: getSelectedWorlds()
    };
    runBackupBtn.disabled = true;
    runBackupBtn.textContent = 'Running...';
    const response = await fetch(`/api/server/${SERVER_ID}/backups/run`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json', ...csrfHeader() },
        body: JSON.stringify(payload)
    });
    const data = await response.json();
    runBackupBtn.disabled = false;
    runBackupBtn.textContent = 'Run backup now';
    if (!data.success) {
        showToast(data.error || 'Backup failed.', 'error');
        return;
    }
    showToast('Backup created.');
    await loadBackups();
    await loadSettings();
}

async function restoreBackup(path) {
    if (!confirm('Restore this backup? This will overwrite existing data.')) {
        return;
    }
    const response = await fetch(`/api/server/${SERVER_ID}/backups/restore`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json', ...csrfHeader() },
        body: JSON.stringify({ path })
    });
    const data = await response.json();
    if (!data.success) {
        showToast(data.error || 'Restore failed.', 'error');
        return;
    }
    showToast('Backup restored.');
}

function renderBackups(backups) {
    backupList.innerHTML = '';
    if (!backups.length) {
        backupList.innerHTML = '<div class="muted">No backups yet.</div>';
        return;
    }
    backups.forEach((backup) => {
        const row = document.createElement('div');
        row.className = 'server-row';

        const info = document.createElement('div');
        info.className = 'server-info';
        const title = document.createElement('div');
        title.style.color = 'white';
        title.style.fontWeight = '700';
        const typeLabel = backup.type === 'universe' ? 'Universe' : (backup.type === 'worlds' ? 'Worlds folder' : 'World');
        const name = backup.label || typeLabel;
        const timestamp = backup.timestamp ? formatTimestamp(backup.timestamp) : 'Unknown time';
        title.textContent = `${name} (${typeLabel})`;
        const meta = document.createElement('div');
        meta.className = 'muted';
        meta.textContent = `${timestamp} · ${formatBytes(backup.size)}`;
        info.appendChild(title);
        info.appendChild(meta);

        const actions = document.createElement('div');
        actions.style.display = 'flex';
        actions.style.gap = '10px';
        const restoreBtn = document.createElement('button');
        restoreBtn.className = 'btn btn-ghost btn-small';
        restoreBtn.textContent = 'Restore';
        restoreBtn.addEventListener('click', () => restoreBackup(backup.path));
        actions.appendChild(restoreBtn);

        row.appendChild(info);
        row.appendChild(actions);
        backupList.appendChild(row);
    });
}

async function loadBackups() {
    const response = await fetch(`/api/server/${SERVER_ID}/backups`);
    const data = await response.json();
    if (!data.success) {
        showToast('Failed to load backups.', 'error');
        return;
    }
    renderBackups(data.backups || []);
}

backupModeInputs.forEach((input) => {
    input.addEventListener('change', () => {
        setMode(getMode());
    });
});

saveSettingsBtn.addEventListener('click', saveSettings);
runBackupBtn.addEventListener('click', runBackup);

setMode(getMode());
loadSettings();
loadBackups();
