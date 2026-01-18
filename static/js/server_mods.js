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

function formatNumber(value) {
    if (value === null || value === undefined) return '0';
    return Number(value).toLocaleString();
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

const searchInput = document.getElementById('modSearchInput');
const sortSelect = document.getElementById('modSortSelect');
const grid = document.getElementById('modsGrid');
const statusEl = document.getElementById('modsStatus');
const prevBtn = document.getElementById('modsPrevBtn');
const nextBtn = document.getElementById('modsNextBtn');
const pageInfo = document.getElementById('modsPageInfo');

const modal = document.getElementById('modInstallModal');
const modalCloseBtn = document.getElementById('modModalCloseBtn');
const modalTitle = document.getElementById('modModalTitle');
const modalSubtitle = document.getElementById('modModalSubtitle');
const modalHint = document.getElementById('modModalHint');
const modalList = document.getElementById('modFilesList');
const modalInstallBtn = document.getElementById('modInstallBtn');

let currentQuery = '';
let currentSort = 'relevancy';
let pageIndex = 0;
const pageSize = 12;
let totalCount = 0;
let activeModId = null;
let activeModName = '';
let activeFiles = [];
let selectedFileId = null;
let activeInstallButton = null;

function setStatus(message, type = 'warning') {
    statusEl.textContent = message;
    statusEl.className = `alert alert-${type}`;
    statusEl.style.display = 'block';
}

function clearStatus() {
    statusEl.style.display = 'none';
}

function renderMods(mods) {
    grid.innerHTML = '';
    if (!mods.length) {
        grid.innerHTML = '<div class="mods-empty">No mods found.</div>';
        return;
    }

    mods.forEach((mod) => {
        const card = document.createElement('div');
        card.className = 'mod-card';

        const header = document.createElement('div');
        header.className = 'mod-card-header';

        const iconWrap = document.createElement('div');
        iconWrap.className = 'mod-icon';
        if (mod.logo_url) {
            const img = document.createElement('img');
            img.src = mod.logo_url;
            img.alt = mod.name;
            iconWrap.appendChild(img);
        } else {
            iconWrap.textContent = mod.name ? mod.name.charAt(0).toUpperCase() : '?';
        }

        const titleWrap = document.createElement('div');
        const title = document.createElement('div');
        title.className = 'mod-title';
        title.textContent = mod.name;
        const meta = document.createElement('div');
        meta.className = 'mod-meta';
        const fileName = (mod.latest_file_name || '').toLowerCase();
        if (fileName.endsWith('.jar')) {
            meta.textContent = 'Plugin';
        } else {
            meta.textContent = mod.type_label || 'Mod';
        }
        titleWrap.appendChild(title);
        titleWrap.appendChild(meta);

        header.appendChild(iconWrap);
        header.appendChild(titleWrap);

        const summary = document.createElement('div');
        summary.className = 'mod-summary';
        summary.textContent = mod.summary || 'No description provided.';

        const chips = document.createElement('div');
        chips.className = 'mod-chip-row';
        const downloads = document.createElement('span');
        downloads.className = 'chip chip-info';
        downloads.textContent = `${formatNumber(mod.download_count)} downloads`;
        const updated = document.createElement('span');
        updated.className = 'chip';
        updated.textContent = `Updated ${formatDate(mod.date_modified)}`;
        const created = document.createElement('span');
        created.className = 'chip';
        created.textContent = `Uploaded ${formatDate(mod.date_created)}`;
        const size = document.createElement('span');
        size.className = 'chip';
        size.textContent = `Size ${formatBytes(mod.latest_file_size)}`;
        chips.appendChild(downloads);
        chips.appendChild(updated);
        chips.appendChild(created);
        chips.appendChild(size);

        if (mod.side_label) {
            const sideChip = document.createElement('span');
            sideChip.className = 'chip chip-warning';
            sideChip.textContent = mod.side_label;
            chips.appendChild(sideChip);
        }

        const actions = document.createElement('div');
        actions.className = 'mod-actions';
        const installBtn = document.createElement('button');
        if (mod.installed) {
            installBtn.className = 'btn btn-ghost';
            installBtn.textContent = 'Installed';
            installBtn.disabled = true;
        } else {
            installBtn.className = 'btn btn-gold';
            installBtn.textContent = 'Install';
            installBtn.addEventListener('click', () => {
                activeInstallButton = installBtn;
                openInstallModal(mod);
            });
        }
        actions.appendChild(installBtn);

        card.appendChild(header);
        card.appendChild(summary);
        card.appendChild(chips);
        card.appendChild(actions);

        grid.appendChild(card);
    });
}

function updatePagination() {
    const currentPage = Math.floor(pageIndex / pageSize) + 1;
    const totalPages = totalCount ? Math.ceil(totalCount / pageSize) : 1;
    pageInfo.textContent = `Page ${currentPage} of ${totalPages}`;
    prevBtn.disabled = pageIndex === 0;
    nextBtn.disabled = pageIndex + pageSize >= totalCount;
}

async function fetchMods() {
    if (!CURSEFORGE_READY) {
        setStatus('CurseForge API key is missing. Set it in Admin > Settings.');
        grid.innerHTML = '';
        return;
    }

    clearStatus();
    grid.innerHTML = '<div class="mods-empty">Loading mods...</div>';

    const params = new URLSearchParams({
        query: currentQuery,
        sort: currentSort,
        index: String(pageIndex),
        page_size: String(pageSize),
    });

    try {
        const response = await fetch(`/api/server/${SERVER_ID}/mods/search?${params.toString()}`);
        const data = await response.json();
        if (!response.ok || !data.success) {
            setStatus(data.error || 'Failed to load mods.', 'error');
            return;
        }
        totalCount = data.pagination ? data.pagination.total_count : 0;
        renderMods(data.mods || []);
        updatePagination();
    } catch (error) {
        console.error(error);
        setStatus('Failed to load mods.', 'error');
    }
}

function openInstallModal(mod) {
    activeModId = mod.id;
    activeModName = mod.name;
    modalTitle.textContent = `Install ${mod.name}`;
    modalSubtitle.textContent = 'Select the version you want to install.';
    modalHint.textContent = '';
    modalList.innerHTML = '<div class="mods-empty">Loading versions...</div>';
    modalInstallBtn.disabled = true;
    selectedFileId = null;
    modal.classList.add('active');
    loadModFiles(mod.id);
}

async function loadModFiles(modId) {
    try {
        const response = await fetch(`/api/server/${SERVER_ID}/mods/${modId}/files`);
        const data = await response.json();
        if (!response.ok || !data.success) {
            modalList.innerHTML = '<div class="mods-empty">Failed to load versions.</div>';
            modalHint.textContent = data.error || 'Unable to load versions.';
            return;
        }
        activeFiles = data.files || [];
        renderModFiles(activeFiles, data.server_version);
    } catch (error) {
        console.error(error);
        modalList.innerHTML = '<div class="mods-empty">Failed to load versions.</div>';
    }
}

function renderModFiles(files, serverVersion) {
    modalList.innerHTML = '';
    if (!files.length) {
        modalList.innerHTML = '<div class="mods-empty">No files found.</div>';
        return;
    }

    files.forEach((file) => {
        const row = document.createElement('label');
        row.className = 'mod-file-row';
        if (file.matches_server) {
            row.classList.add('mod-file-match');
        }

        const input = document.createElement('input');
        input.type = 'radio';
        input.name = 'modFile';
        input.value = file.id;
        input.addEventListener('change', () => {
            selectedFileId = Number(file.id);
            modalInstallBtn.disabled = false;
            modalHint.textContent = `Selected ${file.display_name}`;
        });

        const info = document.createElement('div');
        info.className = 'mod-file-info';
        const title = document.createElement('div');
        title.className = 'mod-file-title';
        title.textContent = file.display_name;
        const meta = document.createElement('div');
        meta.className = 'mod-file-meta';
        const metaParts = [
            formatDate(file.file_date),
            formatBytes(file.file_length),
            file.release_label || '',
        ].filter(Boolean);
        meta.textContent = metaParts.join(' • ');
        const versionLine = document.createElement('div');
        versionLine.className = 'mod-file-versions';
        versionLine.textContent = file.game_versions ? file.game_versions.join(', ') : '';

        info.appendChild(title);
        info.appendChild(meta);
        if (versionLine.textContent) {
            info.appendChild(versionLine);
        }

        const badge = document.createElement('div');
        badge.className = 'mod-file-badge';
        if (file.matches_server && serverVersion) {
            badge.textContent = `Matches ${serverVersion}`;
        } else if (file.side_label) {
            badge.textContent = file.side_label;
        } else {
            badge.textContent = 'N/A';
        }

        row.appendChild(input);
        row.appendChild(info);
        row.appendChild(badge);
        modalList.appendChild(row);
    });
}

async function installSelectedFile() {
    if (!activeModId || !selectedFileId) return;
    modalInstallBtn.disabled = true;
    modalInstallBtn.textContent = 'Installing...';
    try {
        const response = await fetch(`/api/server/${SERVER_ID}/mods/install`, {
            method: 'POST',
            headers: {
                'Content-Type': 'application/json',
                'X-CSRFToken': CSRF_TOKEN,
            },
            body: JSON.stringify({
                mod_id: activeModId,
                file_id: selectedFileId,
            }),
        });
        let data = null;
        let errorMessage = 'Install failed.';
        try {
            data = await response.json();
            if (data && data.error) {
                errorMessage = data.error;
            }
        } catch (error) {
            try {
                const text = await response.text();
                if (text) {
                    errorMessage = text;
                }
            } catch (innerError) {
                // Ignore parsing failures.
            }
        }
        if (!response.ok || (data && !data.success)) {
            showToast(errorMessage, 'error');
            modalInstallBtn.disabled = false;
            modalInstallBtn.textContent = 'Install selected';
            return;
        }
        showToast(`Installed ${activeModName}.`);
        if (activeInstallButton) {
            activeInstallButton.className = 'btn btn-ghost';
            activeInstallButton.textContent = 'Installiert';
            activeInstallButton.disabled = true;
        }
        modal.classList.remove('active');
        modalInstallBtn.textContent = 'Install selected';
    } catch (error) {
        console.error(error);
        showToast('Install failed.', 'error');
        modalInstallBtn.disabled = false;
        modalInstallBtn.textContent = 'Install selected';
    }
}

function debounce(fn, delay = 300) {
    let timer;
    return (...args) => {
        clearTimeout(timer);
        timer = setTimeout(() => fn(...args), delay);
    };
}

const debouncedSearch = debounce(() => {
    currentQuery = searchInput.value.trim();
    pageIndex = 0;
    fetchMods();
}, 350);

searchInput.addEventListener('input', debouncedSearch);
sortSelect.addEventListener('change', () => {
    currentSort = sortSelect.value;
    pageIndex = 0;
    fetchMods();
});

prevBtn.addEventListener('click', () => {
    pageIndex = Math.max(0, pageIndex - pageSize);
    fetchMods();
});

nextBtn.addEventListener('click', () => {
    pageIndex += pageSize;
    fetchMods();
});

modalCloseBtn.addEventListener('click', () => {
    modal.classList.remove('active');
});

modalInstallBtn.addEventListener('click', installSelectedFile);

window.addEventListener('click', (event) => {
    if (event.target === modal) {
        modal.classList.remove('active');
    }
});

fetchMods();
