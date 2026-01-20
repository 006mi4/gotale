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

let installedMods = [];

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

searchInput.addEventListener('input', applyFilter);
refreshBtn.addEventListener('click', () => fetchInstalledMods(true));

fetchInstalledMods();
