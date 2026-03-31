function showToast(message, type = 'success') {
    const toast = document.getElementById('saveToast');
    if (!toast) return;
    toast.textContent = message;
    toast.className = `save-toast ${type}`;
    toast.style.display = 'block';
    setTimeout(() => {
        toast.style.display = 'none';
    }, 3000);
}

function formatBytes(bytes) {
    if (!bytes && bytes !== 0) return 'N/A';
    const sizes = ['B', 'KB', 'MB', 'GB'];
    let index = 0;
    let value = Number(bytes);
    while (value >= 1024 && index < sizes.length - 1) {
        value /= 1024;
        index += 1;
    }
    return `${value.toFixed(value >= 10 || index === 0 ? 0 : 1)} ${sizes[index]}`;
}

function formatDate(value) {
    if (!value) return 'N/A';
    const date = new Date(value);
    if (Number.isNaN(date.getTime())) return 'N/A';
    return date.toLocaleDateString();
}

const listEl = document.getElementById('installedModsList');
const searchInput = document.getElementById('installedSearchInput');
const refreshBtn = document.getElementById('refreshInstalledBtn');
const checkUpdatesBtn = document.getElementById('checkInstalledUpdatesBtn');
const updateModal = document.getElementById('modUpdateModal');
const updateCloseBtn = document.getElementById('modUpdateCloseBtn');
const updateSelectBtn = document.getElementById('modUpdateSelectBtn');
const updateInput = document.getElementById('modUpdateInput');
const updateDrop = document.getElementById('modUpdateDrop');
const updateStatus = document.getElementById('modUpdateStatus');
const updateSubmitBtn = document.getElementById('modUpdateSubmitBtn');
const updateSubtitle = document.getElementById('modUpdateSubtitle');
const updateHint = document.getElementById('modUpdateHint');
const updateProgress = document.getElementById('modUpdateProgress');
const updateProgressFill = document.getElementById('modUpdateProgressFill');
const updateProgressPercent = document.getElementById('modUpdateProgressPercent');
const restartNotice = document.getElementById('restartNotice');
const restartNoticeText = document.getElementById('restartNoticeText');
const restartNoticeClose = document.getElementById('restartNoticeClose');

let installedMods = [];
let updateTarget = null;
let updateFile = null;

function renderInstalledMods(mods) {
    listEl.innerHTML = '';
    if (!mods.length) {
        listEl.innerHTML = '<div class="mods-empty">No mods installed yet.</div>';
        return;
    }

    mods.forEach((mod) => {
        const row = document.createElement('div');
        row.className = 'mod-installed-row';

        const icon = document.createElement('div');
        icon.className = 'mod-icon';
        if (mod.logo_url) {
            const img = document.createElement('img');
            img.src = mod.logo_url;
            img.alt = mod.name || 'Mod';
            icon.appendChild(img);
        } else {
            icon.textContent = mod.name ? mod.name.charAt(0).toUpperCase() : '?';
        }

        const info = document.createElement('div');
        info.className = 'mod-installed-info';
        const title = document.createElement('div');
        title.className = 'mod-title';
        title.textContent = mod.name || mod.file_name || 'Unknown mod';
        const meta = document.createElement('div');
        meta.className = 'mod-meta';
        const metaParts = [
            `Size ${formatBytes(mod.file_length)}`,
            `Installed ${formatDate(mod.installed_at)}`,
        ];
        if (mod.side_label) {
            metaParts.push(mod.side_label);
        }
        if (mod.auto_installed) {
            metaParts.push('Auto dependency');
        }
        if (mod.auto_update) {
            metaParts.push('Auto update');
        }
        meta.textContent = metaParts.join(' • ');

        const summary = document.createElement('div');
        summary.className = 'mod-summary';
        summary.textContent = mod.summary || mod.file_name || '';

        info.appendChild(title);
        info.appendChild(meta);
        info.appendChild(summary);

        const actions = document.createElement('div');
        actions.className = 'mod-actions';

        const autoUpdateWrap = document.createElement('div');
        autoUpdateWrap.className = 'checkbox-row';
        const autoUpdateInput = document.createElement('input');
        autoUpdateInput.type = 'checkbox';
        autoUpdateInput.checked = Boolean(mod.auto_update);
        autoUpdateInput.disabled = !mod.mod_id;
        autoUpdateInput.addEventListener('change', () => {
            setAutoUpdate(mod, autoUpdateInput.checked, autoUpdateInput);
        });
        const autoUpdateLabel = document.createElement('label');
        autoUpdateLabel.textContent = 'Auto update';
        autoUpdateWrap.appendChild(autoUpdateInput);
        autoUpdateWrap.appendChild(autoUpdateLabel);
        if (!mod.mod_id) {
            autoUpdateWrap.title = 'Only available for CurseForge-installed mods';
        }

        const uninstallBtn = document.createElement('button');
        uninstallBtn.className = 'btn btn-ghost';
        uninstallBtn.textContent = 'Uninstall';
        uninstallBtn.addEventListener('click', () => uninstallMod(mod));
        if (mod.local) {
            const updateBtn = document.createElement('button');
            updateBtn.className = 'btn btn-gold';
            updateBtn.textContent = 'Update';
            updateBtn.addEventListener('click', () => openUpdateModal(mod));
            actions.appendChild(updateBtn);
        }
        actions.appendChild(autoUpdateWrap);
        actions.appendChild(uninstallBtn);

        row.appendChild(icon);
        row.appendChild(info);
        row.appendChild(actions);
        listEl.appendChild(row);
    });
}

function applyFilter() {
    const query = searchInput.value.trim().toLowerCase();
    if (!query) {
        renderInstalledMods(installedMods);
        return;
    }
    const filtered = installedMods.filter((mod) => {
        const name = (mod.name || '').toLowerCase();
        const file = (mod.file_name || '').toLowerCase();
        return name.includes(query) || file.includes(query);
    });
    renderInstalledMods(filtered);
}

async function fetchInstalledMods(checkUpdates = false) {
    listEl.innerHTML = '<div class="mods-empty">Loading installed mods...</div>';
    try {
        const params = checkUpdates ? '?check_updates=1' : '';
        const response = await fetch(`/api/server/${SERVER_ID}/mods/installed${params}`);
        const data = await response.json();
        if (!response.ok || !data.success) {
            listEl.innerHTML = '<div class="mods-empty">Failed to load installed mods.</div>';
            return;
        }
        if (checkUpdates && data.update_error) {
            showToast(data.update_error, 'error');
        } else if (checkUpdates && data.updated_mods && data.updated_mods.length) {
            showToast(`Auto-updated ${data.updated_mods.length} mod(s).`);
        }
        installedMods = data.mods || [];
        applyFilter();
    } catch (error) {
        console.error(error);
        listEl.innerHTML = '<div class="mods-empty">Failed to load installed mods.</div>';
    }
}

async function uninstallMod(mod) {
    if (!mod.file_name) return;
    const confirmed = confirm(`Uninstall ${mod.name || mod.file_name}?`);
    if (!confirmed) return;
    try {
        const response = await fetch(`/api/server/${SERVER_ID}/mods/uninstall`, {
            method: 'POST',
            headers: {
                'Content-Type': 'application/json',
                'X-CSRFToken': CSRF_TOKEN,
            },
            body: JSON.stringify({ file_name: mod.file_name }),
        });
        const data = await response.json();
        if (!response.ok || !data.success) {
            showToast(data.error || 'Uninstall failed.', 'error');
            return;
        }
        showToast('Mod uninstalled.');
        await fetchInstalledMods();
    } catch (error) {
        console.error(error);
        showToast('Uninstall failed.', 'error');
    }
}

async function setAutoUpdate(mod, enabled, inputEl) {
    if (!mod.file_name) return;
    try {
        const response = await fetch(`/api/server/${SERVER_ID}/mods/auto-update`, {
            method: 'POST',
            headers: {
                'Content-Type': 'application/json',
                'X-CSRFToken': CSRF_TOKEN,
            },
            body: JSON.stringify({ file_name: mod.file_name, auto_update: enabled }),
        });
        const data = await response.json();
        if (!response.ok || !data.success) {
            showToast(data.error || 'Failed to update auto update.', 'error');
            if (inputEl) inputEl.checked = !enabled;
            return;
        }
        mod.auto_update = enabled;
        showToast(enabled ? 'Auto update enabled.' : 'Auto update disabled.');
    } catch (error) {
        console.error(error);
        showToast('Failed to update auto update.', 'error');
        if (inputEl) inputEl.checked = !enabled;
    }
}

async function runInstalledUpdateCheck() {
    if (!checkUpdatesBtn) return;
    const originalText = checkUpdatesBtn.textContent;
    checkUpdatesBtn.disabled = true;
    checkUpdatesBtn.textContent = 'Checking...';
    try {
        const response = await fetch(`/api/server/${SERVER_ID}/mods/check-updates`, {
            method: 'POST',
            headers: {
                'X-CSRFToken': CSRF_TOKEN,
            },
        });
        const data = await response.json();
        if (!response.ok || !data.success) {
            showToast(data.error || 'Mod update check failed.', 'error');
            return;
        }
        const updated = data.updated_mods || [];
        if (updated.length) {
            showToast(`Mod/plugin updates installed (${updated.length}). Please restart the server.`);
            const preview = updated
                .slice(0, 10)
                .map((item) => `- ${item.name || item.to_file_name || 'Unknown'} (${item.from_file_name || 'old'} -> ${item.to_file_name || 'new'})`)
                .join('\n');
            const more = updated.length > 10 ? `\n...and ${updated.length - 10} more` : '';
            alert(`Installed updates (${updated.length}):\n\n${preview}${more}`);
        } else {
            showToast('No updates found.');
        }
        await fetchInstalledMods();
    } catch (error) {
        console.error(error);
        showToast('Mod update check failed.', 'error');
    } finally {
        checkUpdatesBtn.disabled = false;
        checkUpdatesBtn.textContent = originalText;
    }
}

searchInput.addEventListener('input', applyFilter);
refreshBtn.addEventListener('click', () => fetchInstalledMods());
if (checkUpdatesBtn) {
    checkUpdatesBtn.addEventListener('click', runInstalledUpdateCheck);
}

fetchInstalledMods();

function resetUpdateModal() {
    updateTarget = null;
    updateFile = null;
    if (updateInput) updateInput.value = '';
    if (updateStatus) updateStatus.textContent = '';
    if (updateHint) updateHint.textContent = '';
    if (updateSubmitBtn) updateSubmitBtn.disabled = true;
    if (updateProgress) updateProgress.style.display = 'none';
    if (updateProgressFill) updateProgressFill.style.width = '0%';
    if (updateProgressPercent) updateProgressPercent.textContent = '0%';
}

function setUpdateStatus(text, type = '') {
    if (!updateStatus) return;
    updateStatus.textContent = text;
    updateStatus.className = type ? `muted ${type}` : 'muted';
}

function handleUpdateFile(file) {
    if (!file) return;
    const name = (file.name || '').toLowerCase();
    if (!name.endsWith('.jar') && !name.endsWith('.zip')) {
        setUpdateStatus('Only .jar or .zip files are allowed.', 'error');
        updateFile = null;
        if (updateSubmitBtn) updateSubmitBtn.disabled = true;
        return;
    }
    updateFile = file;
    setUpdateStatus(`Selected: ${file.name}`);
    if (updateSubmitBtn) updateSubmitBtn.disabled = false;
}

function showRestartNotice(message) {
    if (restartNoticeText) {
        restartNoticeText.textContent = message;
    }
    if (restartNotice) {
        restartNotice.classList.remove('hidden');
    }
}

function openUpdateModal(mod) {
    if (!updateModal) return;
    resetUpdateModal();
    updateTarget = mod;
    if (updateSubtitle) {
        updateSubtitle.textContent = `Replace ${mod.name || mod.file_name} with a new file.`;
    }
    updateModal.classList.add('active');
}

async function submitUpdate() {
    if (!updateTarget || !updateFile) return;
    if (updateSubmitBtn) {
        updateSubmitBtn.disabled = true;
        updateSubmitBtn.textContent = 'Updating...';
    }
    try {
        const formData = new FormData();
        formData.append('old_file', updateTarget.file_name);
        formData.append('file', updateFile);
        if (updateProgress) updateProgress.style.display = 'block';

        const xhr = new XMLHttpRequest();
        xhr.open('POST', `/api/server/${SERVER_ID}/mods/replace`);
        xhr.setRequestHeader('X-CSRFToken', CSRF_TOKEN);
        xhr.upload.onprogress = (event) => {
            if (!event.lengthComputable) return;
            const percent = Math.round((event.loaded / event.total) * 100);
            if (updateProgressFill) updateProgressFill.style.width = `${percent}%`;
            if (updateProgressPercent) updateProgressPercent.textContent = `${percent}%`;
        };
        xhr.onload = async () => {
            let data = null;
            try {
                data = JSON.parse(xhr.responseText);
            } catch (error) {
                data = null;
            }
            if (xhr.status >= 200 && xhr.status < 300 && data && data.success) {
                showToast('Mod updated.');
                showRestartNotice('Server restart required for the mod/plugin to take effect.');
                updateModal.classList.remove('active');
                await fetchInstalledMods();
            } else {
                setUpdateStatus((data && data.error) || 'Update failed.', 'error');
                if (updateSubmitBtn) updateSubmitBtn.disabled = false;
            }
            if (updateSubmitBtn) updateSubmitBtn.textContent = 'Update';
        };
        xhr.onerror = () => {
            setUpdateStatus('Update failed.', 'error');
            if (updateSubmitBtn) updateSubmitBtn.disabled = false;
            if (updateSubmitBtn) updateSubmitBtn.textContent = 'Update';
        };
        xhr.send(formData);
    } catch (error) {
        console.error(error);
        setUpdateStatus('Update failed.', 'error');
        if (updateSubmitBtn) updateSubmitBtn.disabled = false;
    }
}

if (updateCloseBtn && updateModal) {
    updateCloseBtn.addEventListener('click', () => updateModal.classList.remove('active'));
}

if (updateSelectBtn && updateInput) {
    updateSelectBtn.addEventListener('click', () => updateInput.click());
}

if (updateInput) {
    updateInput.addEventListener('change', () => {
        const file = updateInput.files ? updateInput.files[0] : null;
        handleUpdateFile(file);
    });
}

if (updateDrop) {
    ['dragenter', 'dragover'].forEach((eventName) => {
        updateDrop.addEventListener(eventName, (event) => {
            event.preventDefault();
            updateDrop.classList.add('is-dragover');
        });
    });
    ['dragleave', 'drop'].forEach((eventName) => {
        updateDrop.addEventListener(eventName, (event) => {
            event.preventDefault();
            updateDrop.classList.remove('is-dragover');
        });
    });
    updateDrop.addEventListener('drop', (event) => {
        const file = event.dataTransfer?.files?.[0] || null;
        handleUpdateFile(file);
    });
}

if (updateSubmitBtn) {
    updateSubmitBtn.addEventListener('click', submitUpdate);
}

window.addEventListener('click', (event) => {
    if (event.target === updateModal) {
        updateModal.classList.remove('active');
    }
});

if (restartNoticeClose && restartNotice) {
    restartNoticeClose.addEventListener('click', () => {
        restartNotice.classList.add('hidden');
    });
}
