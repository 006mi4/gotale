const configFileSelect = document.getElementById('configFileSelect');
const mainConfigForm = document.getElementById('mainConfigForm');
const jsonEditorPanel = document.getElementById('jsonEditorPanel');
const selectedFileMeta = document.getElementById('selectedFileMeta');
const unsavedPopup = document.getElementById('unsavedPopup');
const saveBtn = document.getElementById('saveBtn');
const saveBtnInline = document.getElementById('saveBtnInline');
const unsavedInline = document.getElementById('unsavedInline');
const autosaveToggle = document.getElementById('autosaveToggle');
const saveToast = document.getElementById('saveToast');

const formFields = {
    serverName: ['ServerName'],
    motd: ['MOTD'],
    password: ['Password'],
    maxPlayers: ['MaxPlayers'],
    maxViewRadius: ['MaxViewRadius'],
    localCompression: ['LocalCompressionEnabled'],
    displayTmpTags: ['DisplayTmpTagsInStrings'],
    defaultWorld: ['Defaults', 'World'],
    gameMode: ['Defaults', 'GameMode'],
    playerStorageType: ['PlayerStorage', 'Type'],
    authStoreType: ['AuthCredentialStore', 'Type'],
    authStorePath: ['AuthCredentialStore', 'Path']
};

const jsonFields = {
    joinTimeouts: ['ConnectionTimeouts', 'JoinTimeouts'],
    rateLimit: ['RateLimit'],
    modules: ['Modules'],
    logLevels: ['LogLevels'],
    mods: ['Mods']
};

let editor;
let currentFile = null;
let currentFileCategory = null;
let isDirty = false;
let currentConfigData = null;
let isLoading = false;
let autosaveTimer = null;
const csrfHeader = () => ({ 'X-CSRFToken': CSRF_TOKEN });

// All discovered config files from the list endpoint, keyed by path/value
let allConfigFiles = [];

if (unsavedInline) {
    unsavedInline.classList.add('saved');
}

const editorOptions = {
    mode: 'code',
    modes: ['code', 'tree'],
    onChange: () => {
        if (!isLoading) {
            setDirty(true);
            scheduleAutosave();
        }
    }
};

function setDirty(value) {
    isDirty = value;
    if (isDirty) {
        unsavedPopup.classList.add('active');
        if (unsavedInline) {
            unsavedInline.textContent = 'Unsaved changes.';
            unsavedInline.classList.add('dirty');
            unsavedInline.classList.remove('saved');
        }
        if (saveBtnInline) {
            saveBtnInline.disabled = false;
        }
    } else {
        unsavedPopup.classList.remove('active');
        if (unsavedInline) {
            unsavedInline.textContent = 'All changes saved.';
            unsavedInline.classList.remove('dirty');
            unsavedInline.classList.add('saved');
        }
        if (saveBtnInline) {
            saveBtnInline.disabled = true;
        }
    }
}

function scheduleAutosave() {
    if (!autosaveToggle || !autosaveToggle.checked) return;
    if (autosaveTimer) {
        clearTimeout(autosaveTimer);
    }
    autosaveTimer = setTimeout(() => {
        if (isDirty) {
            saveCurrent();
        }
    }, 900);
}

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

function setDeepValue(obj, path, value) {
    let current = obj;
    for (let i = 0; i < path.length - 1; i += 1) {
        const key = path[i];
        if (!current[key] || typeof current[key] !== 'object') {
            current[key] = {};
        }
        current = current[key];
    }
    current[path[path.length - 1]] = value;
}

function getDeepValue(obj, path, fallback = '') {
    let current = obj;
    for (const key of path) {
        if (current && Object.prototype.hasOwnProperty.call(current, key)) {
            current = current[key];
        } else {
            return fallback;
        }
    }
    return current;
}

function initEditor() {
    if (!editor) {
        const container = document.getElementById('jsonEditor');
        editor = new JSONEditor(container, editorOptions);
    }
}

function toggleMode(mode) {
    if (mode === 'form') {
        mainConfigForm.classList.remove('hidden');
        jsonEditorPanel.classList.add('hidden');
    } else {
        mainConfigForm.classList.add('hidden');
        jsonEditorPanel.classList.remove('hidden');
    }
}

function populateForm(data) {
    currentConfigData = data || {};
    Object.entries(formFields).forEach(([id, path]) => {
        const element = document.getElementById(id);
        const value = getDeepValue(currentConfigData, path, '');
        if (!element) return;
        if (element.type === 'checkbox') {
            element.checked = Boolean(value);
        } else if (element.type === 'number') {
            element.value = value !== undefined ? value : '';
        } else {
            element.value = value !== undefined ? value : '';
        }
    });

    Object.entries(jsonFields).forEach(([id, path]) => {
        const element = document.getElementById(id);
        if (!element) return;
        const value = getDeepValue(currentConfigData, path, {});
        element.value = JSON.stringify(value || {}, null, 2);
    });
}

function collectFormData() {
    const data = JSON.parse(JSON.stringify(currentConfigData || {}));

    Object.entries(formFields).forEach(([id, path]) => {
        const element = document.getElementById(id);
        if (!element) return;
        let value = element.value;
        if (element.type === 'number') {
            value = element.value ? Number(element.value) : 0;
        }
        if (element.type === 'checkbox') {
            value = element.checked;
        }
        setDeepValue(data, path, value);
    });

    for (const [id, path] of Object.entries(jsonFields)) {
        const element = document.getElementById(id);
        if (!element) continue;
        try {
            const parsed = element.value.trim() ? JSON.parse(element.value) : {};
            setDeepValue(data, path, parsed);
        } catch (error) {
            return { error: `Invalid JSON in ${id}.` };
        }
    }

    return { data };
}

const LEGACY_FILES = ['config.json', 'permissions.json', 'bans.json', 'whitelist.json'];

const CATEGORY_LABELS = {
    config: 'Server Config',
    GameplayConfigs: 'Gameplay',
    Environments: 'Environments',
    Instances: 'Instances'
};

function filterConfigFiles() {
    const categoryEl = document.getElementById('config-category');
    const selectedCategory = categoryEl ? categoryEl.value : 'all';

    configFileSelect.innerHTML = '';

    const filtered = selectedCategory === 'all'
        ? allConfigFiles
        : allConfigFiles.filter((f) => f.category === selectedCategory);

    if (!filtered.length) {
        const option = document.createElement('option');
        option.textContent = 'No files in this category';
        option.value = '';
        configFileSelect.appendChild(option);
        configFileSelect.disabled = true;
        return;
    }

    configFileSelect.disabled = false;

    // Group by category for optgroups when showing all
    if (selectedCategory === 'all') {
        const groups = {};
        filtered.forEach((f) => {
            if (!groups[f.category]) groups[f.category] = [];
            groups[f.category].push(f);
        });
        Object.entries(groups).forEach(([cat, files]) => {
            const group = document.createElement('optgroup');
            group.label = CATEGORY_LABELS[cat] || cat;
            files.forEach((file) => {
                const option = document.createElement('option');
                option.value = file.value;
                option.textContent = file.label;
                option.dataset.category = file.category;
                group.appendChild(option);
            });
            configFileSelect.appendChild(group);
        });
    } else {
        filtered.forEach((file) => {
            const option = document.createElement('option');
            option.value = file.value;
            option.textContent = file.label;
            option.dataset.category = file.category;
            configFileSelect.appendChild(option);
        });
    }

    const firstFile = filtered[0];
    configFileSelect.value = firstFile.value;
    loadFile(firstFile.value, firstFile.category);
}

async function fetchFiles() {
    // Load legacy config files first
    const legacyResp = await fetch(`/api/server/${SERVER_ID}/config-files`);
    const legacyResult = await legacyResp.json();

    // Load new-layout config files
    const listResp = await fetch(`/api/server/${SERVER_ID}/config-files-list`);
    const listResult = await listResp.json();

    allConfigFiles = [];

    if (legacyResult.success && legacyResult.files.length) {
        legacyResult.files.forEach((f) => {
            allConfigFiles.push({
                value: f.value,
                label: f.label,
                category: 'config',
                legacy: true
            });
        });
    }

    if (listResult.files && listResult.files.length) {
        listResult.files.forEach((f) => {
            // Avoid duplicates with legacy entries
            const alreadyListed = allConfigFiles.some((existing) => existing.value === f.path);
            if (!alreadyListed) {
                allConfigFiles.push({
                    value: f.path,
                    label: f.path,
                    category: f.category,
                    legacy: false
                });
            }
        });
    }

    if (!allConfigFiles.length) {
        configFileSelect.innerHTML = '';
        const option = document.createElement('option');
        option.textContent = 'No config files found';
        option.value = '';
        configFileSelect.appendChild(option);
        configFileSelect.disabled = true;
        showToast('No config files found.', 'error');
        return;
    }

    filterConfigFiles();
}

function _isLegacyFile(name) {
    return LEGACY_FILES.includes(name);
}

async function loadFile(name, category) {
    if (!name) return;
    if (isDirty && name !== currentFile) {
        const confirmSwitch = window.confirm('You have unsaved changes. Switch anyway?');
        if (!confirmSwitch) {
            configFileSelect.value = currentFile;
            return;
        }
    }

    // Resolve category from allConfigFiles if not passed
    if (!category) {
        const entry = allConfigFiles.find((f) => f.value === name);
        category = entry ? entry.category : null;
    }

    currentFile = name;
    currentFileCategory = category;
    setDirty(false);
    if (saveBtnInline) {
        saveBtnInline.disabled = true;
    }

    let response;
    if (_isLegacyFile(name)) {
        response = await fetch(`/api/server/${SERVER_ID}/config-file?name=${encodeURIComponent(name)}`);
    } else {
        response = await fetch(`/api/server/${SERVER_ID}/config-files-list/${encodeURIComponent(name)}`);
    }

    const result = await response.json();

    if (!result.success) {
        showToast('File could not be loaded.', 'error');
        return;
    }

    if (name === 'config.json') {
        toggleMode('form');
        populateForm(result.data);
    } else {
        toggleMode('editor');
        initEditor();
        isLoading = true;
        editor.set(result.data || {});
        isLoading = false;
        selectedFileMeta.textContent = name;
    }
}

async function saveCurrent() {
    if (!currentFile) {
        return;
    }

    let payload;
    if (currentFile === 'config.json') {
        const { data, error } = collectFormData();
        if (error) {
            showToast(error, 'error');
            return;
        }
        payload = { data };
    } else {
        try {
            payload = { data: editor.get() };
        } catch (error) {
            showToast('JSON is not valid.', 'error');
            return;
        }
    }

    let saveUrl;
    if (_isLegacyFile(currentFile)) {
        saveUrl = `/api/server/${SERVER_ID}/config-file?name=${encodeURIComponent(currentFile)}`;
    } else {
        saveUrl = `/api/server/${SERVER_ID}/config-files-list/${encodeURIComponent(currentFile)}`;
    }

    const response = await fetch(saveUrl, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json', ...csrfHeader() },
        body: JSON.stringify(payload)
    });

    const result = await response.json();
    if (result.success) {
        setDirty(false);
        showToast('Saved.');
    } else {
        showToast(result.error || 'Save failed.', 'error');
    }
}

configFileSelect.addEventListener('change', (event) => {
    const selectedOption = event.target.options[event.target.selectedIndex];
    const category = selectedOption ? selectedOption.dataset.category : null;
    loadFile(event.target.value, category);
});

saveBtn.addEventListener('click', () => {
    saveCurrent();
});

if (saveBtnInline) {
    saveBtnInline.addEventListener('click', () => {
        saveCurrent();
    });
}

if (autosaveToggle) {
    autosaveToggle.addEventListener('change', () => {
        if (autosaveToggle.checked && isDirty) {
            scheduleAutosave();
        }
    });
}

const formElements = mainConfigForm.querySelectorAll('input, textarea');
formElements.forEach((element) => {
    element.addEventListener('input', () => {
        setDirty(true);
        scheduleAutosave();
    });
    element.addEventListener('change', () => {
        setDirty(true);
        scheduleAutosave();
    });
});

window.addEventListener('beforeunload', (event) => {
    if (!isDirty) return;
    event.preventDefault();
    event.returnValue = '';
});

fetchFiles();
