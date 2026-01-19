const editorPage = document.getElementById('jsonEditorPage');
const endpoint = editorPage.dataset.endpoint;
const fileSelect = document.getElementById('fileSelect');
const fileDescription = document.getElementById('fileDescription');
const fileSelectTrigger = document.getElementById('fileSelectTrigger');
const fileSelectMenu = document.getElementById('fileSelectMenu');
const fileSelectSearchId = 'fileSelectSearch';
const unsavedPopup = document.getElementById('unsavedPopup');
const saveBtn = document.getElementById('saveBtn');
const saveBtnInline = document.getElementById('saveBtnInline');
const unsavedInline = document.getElementById('unsavedInline');
const autosaveToggle = document.getElementById('autosaveToggle');
const saveToast = document.getElementById('saveToast');

let editor;
let currentFile = null;
let isDirty = false;
let isLoading = false;
let autosaveTimer = null;
const csrfHeader = () => ({ 'X-CSRFToken': CSRF_TOKEN });

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

function initEditor() {
    if (!editor) {
        const container = document.getElementById('jsonEditor');
        editor = new JSONEditor(container, editorOptions);
    }
}

async function loadFiles() {
    const response = await fetch(`/api/server/${SERVER_ID}/${endpoint}-files`);
    const result = await response.json();

    if (!result.success) {
        showToast('Files could not be loaded.', 'error');
        return;
    }

    fileSelect.innerHTML = '';
    if (fileSelectMenu) {
        fileSelectMenu.innerHTML = '';
        const search = document.createElement('input');
        search.type = 'search';
        search.id = fileSelectSearchId;
        search.className = 'form-input custom-select-search';
        search.placeholder = 'Search players...';
        search.addEventListener('input', () => {
            filterCustomOptions(search.value);
        });
        fileSelectMenu.appendChild(search);
    }

    if (!result.files.length) {
        const option = document.createElement('option');
        option.textContent = 'No JSON files found';
        option.value = '';
        fileSelect.appendChild(option);
        if (fileSelectTrigger) {
            fileSelectTrigger.textContent = 'No JSON files found';
        }
        fileSelect.disabled = true;
        return;
    }

    fileSelect.disabled = false;
    result.files.forEach((file) => {
        const option = document.createElement('option');
        option.value = file.value;
        const primary = file.label || file.value;
        const secondary = file.fileLabel ? `\\n${file.fileLabel}` : '';
        option.textContent = `${primary}${secondary}`;
        option.dataset.description = file.description || '';
        fileSelect.appendChild(option);
        if (fileSelectMenu) {
            const entry = document.createElement('button');
            entry.type = 'button';
            entry.className = 'custom-select-option';
            entry.dataset.value = file.value;
            entry.innerHTML = `<span class="option-title">${primary}</span><span class="option-sub censor-target">${file.fileLabel || file.value}</span>`;
            entry.addEventListener('click', () => {
                fileSelect.value = file.value;
                updateCustomSelect(primary, file.fileLabel || file.value);
                closeCustomSelect();
                fileSelect.dispatchEvent(new Event('change'));
            });
            fileSelectMenu.appendChild(entry);
        }
    });

    fileSelect.value = result.files[0].value;
    if (fileSelectTrigger) {
        const first = result.files[0];
        updateCustomSelect(first.label || first.value, first.fileLabel || first.value);
    }
    await loadFile(result.files[0].value);
}

async function loadFile(name) {
    if (!name) return;

    if (isDirty && name !== currentFile) {
        const confirmSwitch = window.confirm('You have unsaved changes. Switch anyway?');
        if (!confirmSwitch) {
            fileSelect.value = currentFile;
            return;
        }
    }

    currentFile = name;
    setDirty(false);
    if (saveBtnInline) {
        saveBtnInline.disabled = true;
    }
    const response = await fetch(`/api/server/${SERVER_ID}/${endpoint}-file?name=${encodeURIComponent(name)}`);
    const result = await response.json();

    if (!result.success) {
        showToast('File could not be loaded.', 'error');
        return;
    }

    initEditor();
    isLoading = true;
    editor.set(result.data || {});
    isLoading = false;

    const selectedOption = fileSelect.options[fileSelect.selectedIndex];
    const descriptionText = selectedOption ? selectedOption.dataset.description : '';
    fileDescription.textContent = descriptionText ? descriptionText : `File: ${name}`;
    fileDescription.classList.add('censor-target');
}

async function saveCurrent() {
    if (!currentFile) return;

    let payload;
    try {
        payload = { data: editor.get() };
    } catch (error) {
        showToast('JSON is not valid.', 'error');
        return;
    }

    const response = await fetch(`/api/server/${SERVER_ID}/${endpoint}-file?name=${encodeURIComponent(currentFile)}`,
        {
            method: 'POST',
            headers: { 'Content-Type': 'application/json', ...csrfHeader() },
            body: JSON.stringify(payload)
        }
    );

    const result = await response.json();
    if (result.success) {
        setDirty(false);
        showToast('Saved.');
    } else {
        showToast(result.error || 'Save failed.', 'error');
    }
}

fileSelect.addEventListener('change', (event) => {
    loadFile(event.target.value);
});

function updateCustomSelect(title, subtitle) {
    if (!fileSelectTrigger) return;
    fileSelectTrigger.innerHTML = `<span class="option-title">${title}</span><span class="option-sub censor-target">${subtitle}</span>`;
}

function filterCustomOptions(query) {
    if (!fileSelectMenu) return;
    const normalized = query.trim().toLowerCase();
    fileSelectMenu.querySelectorAll('.custom-select-option').forEach((option) => {
        const text = option.textContent.toLowerCase();
        option.classList.toggle('hidden', normalized && !text.includes(normalized));
    });
}

if (fileSelectTrigger && fileSelectMenu) {
    fileSelectTrigger.addEventListener('click', () => {
        fileSelectMenu.classList.toggle('hidden');
        if (!fileSelectMenu.classList.contains('hidden')) {
            const search = document.getElementById(fileSelectSearchId);
            if (search) {
                search.focus();
            }
        }
    });
    document.addEventListener('click', (event) => {
        if (!event.target.closest('[data-custom-select]')) {
            fileSelectMenu.classList.add('hidden');
        }
    });
}

document.addEventListener('censorModeChange', () => {
    // no-op, CSS handles the blur
});

function closeCustomSelect() {
    if (!fileSelectMenu) return;
    fileSelectMenu.classList.add('hidden');
}

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

window.addEventListener('beforeunload', (event) => {
    if (!isDirty) return;
    event.preventDefault();
    event.returnValue = '';
});

loadFiles();
