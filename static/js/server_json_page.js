const editorPage = document.getElementById('jsonEditorPage');
const endpoint = editorPage.dataset.endpoint;
const fileSelect = document.getElementById('fileSelect');
const fileDescription = document.getElementById('fileDescription');
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

    if (!result.files.length) {
        const option = document.createElement('option');
        option.textContent = 'No JSON files found';
        option.value = '';
        fileSelect.appendChild(option);
        fileSelect.disabled = true;
        return;
    }

    fileSelect.disabled = false;
    result.files.forEach((file) => {
        const option = document.createElement('option');
        option.value = file.value;
        option.textContent = file.label;
        option.dataset.description = file.description || '';
        fileSelect.appendChild(option);
    });

    fileSelect.value = result.files[0].value;
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
            headers: { 'Content-Type': 'application/json' },
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
