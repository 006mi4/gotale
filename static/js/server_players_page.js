const playerEditorSection = document.getElementById('playerEditorSection');
const jsonEditorSection = document.getElementById('jsonEditorPage');
const modeButtons = document.querySelectorAll('[data-player-mode]');
const playersModeTitle = document.getElementById('playersModeTitle');
const playersModeSubtitle = document.getElementById('playersModeSubtitle');

const playerSearch = document.getElementById('playerSearch');
const playerCards = document.getElementById('playerCards');
const playerCardsEmpty = document.getElementById('playerCardsEmpty');
const playersPrev = document.getElementById('playersPrev');
const playersNext = document.getElementById('playersNext');
const playersPageInfo = document.getElementById('playersPageInfo');
const censorToggle = document.getElementById('censorToggle');

const playerDetail = document.getElementById('playerDetail');
const playerDetailName = document.getElementById('playerDetailName');
const playerDetailUuid = document.getElementById('playerDetailUuid');
const playerDirtyState = document.getElementById('playerDirtyState');
const playerSaveBtn = document.getElementById('playerSaveBtn');
const inventoryMeta = document.getElementById('inventoryMeta');
const inventoryShell = document.getElementById('inventoryShell');

const armorGrid = document.getElementById('armorGrid');
const utilityRadial = document.getElementById('utilityRadial');
const storageGrid = document.getElementById('storageGrid');
const hotbarGrid = document.getElementById('hotbarGrid');
const toolGrid = document.getElementById('toolGrid');
const entityStatsPanel = document.getElementById('entityStatsPanel');
const worldDataPanel = document.getElementById('worldDataPanel');

const stackModal = document.getElementById('stackModal');
const stackModalTitle = document.getElementById('stackModalTitle');
const stackModalSubtitle = document.getElementById('stackModalSubtitle');
const stackModalAmount = document.getElementById('stackModalAmount');
const stackModalCancel = document.getElementById('stackModalCancel');
const stackModalConfirm = document.getElementById('stackModalConfirm');
const deleteModal = document.getElementById('deleteModal');
const deleteModalAmount = document.getElementById('deleteModalAmount');
const deleteModalCancel = document.getElementById('deleteModalCancel');
const deleteModalAll = document.getElementById('deleteModalAll');
const deleteModalConfirm = document.getElementById('deleteModalConfirm');

const ITEM_API_URL = '/api/items/';
const ITEM_IMAGE_URL = '/api/item-image/';
const PAGE_SIZE = 50;

const itemMetaCache = new Map();
const playerDetailRow = document.createElement('div');
playerDetailRow.className = 'player-detail-row';

const STAT_ICONS = {
    Health: 'HP',
    Mana: 'MP',
    Oxygen: 'O2',
    Stamina: 'ST',
    Ammo: 'AM',
    Immunity: 'IM',
    SignatureEnergy: 'SE',
    SignatureCharges: 'SC',
    MagicCharges: 'MC',
};

const STAT_DEFAULT_MAX = {
    Health: 100,
    Mana: 100,
    Oxygen: 100,
    Stamina: 100,
    SignatureEnergy: 100,
    Ammo: 100,
    MagicCharges: 100,
};

const playerState = {
    allPlayers: [],
    filteredPlayers: [],
    page: 1,
    currentFile: null,
    currentData: null,
    inventoryState: null,
    dirty: false,
    dragSource: null,
    activeCard: null,
    activeButton: null,
    pendingSplit: null,
    activeModal: null,
    lastHoveredSlot: null,
};

function showPlayerToast(message, type = 'success') {
    const toast = document.getElementById('saveToast');
    if (!toast) return;
    toast.textContent = message;
    toast.classList.remove('error');
    if (type === 'error') {
        toast.classList.add('error');
    }
    toast.classList.add('visible');
    setTimeout(() => {
        toast.classList.remove('visible');
    }, 2800);
}

function openModal(modal) {
    if (!modal) return;
    modal.classList.remove('hidden');
}

function closeModal(modal) {
    if (!modal) return;
    modal.classList.add('hidden');
}

function openStackSplitModal(item, sectionName, index) {
    if (!stackModal || !stackModalAmount || !stackModalTitle || !stackModalConfirm) return;
    const quantity = item.Quantity || 1;
    stackModalTitle.textContent = 'Stack teilen';
    stackModalSubtitle.textContent = `Verfügbar: ${quantity}x ${item.Id}`;
    stackModalAmount.max = Math.max(1, quantity - 1);
    stackModalAmount.value = Math.max(1, Math.floor(quantity / 2));
    playerState.activeModal = { type: 'split', sectionName, index, itemId: item.Id };
    openModal(stackModal);
}

function openDeleteModal(item, sectionName, index) {
    if (!deleteModal || !deleteModalAmount) return;
    const quantity = item.Quantity || 1;
    deleteModalAmount.max = quantity;
    deleteModalAmount.value = quantity;
    playerState.activeModal = { type: 'delete', sectionName, index, itemId: item.Id };
    openModal(deleteModal);
}

function setPlayerMode(mode) {
    const isPlayerMode = mode === 'player';
    document.body.dataset.playersMode = mode;
    if (playerEditorSection) {
        playerEditorSection.classList.toggle('hidden', !isPlayerMode);
    }
    if (jsonEditorSection) {
        jsonEditorSection.classList.toggle('hidden', isPlayerMode);
    }
    modeButtons.forEach((button) => {
        button.classList.toggle('active', button.dataset.playerMode === mode);
    });
    if (playersModeTitle && playersModeSubtitle) {
        if (isPlayerMode) {
            playersModeTitle.textContent = 'Player Editor';
            playersModeSubtitle.textContent = 'Browse players, edit inventories, and save changes instantly.';
        } else {
            playersModeTitle.textContent = 'JSON Editor';
            playersModeSubtitle.textContent = 'Edit player JSON files directly with full control.';
        }
    }
    localStorage.setItem('playersEditorMode', mode);
    document.dispatchEvent(new CustomEvent('playersModeChange', { detail: { mode } }));
}

function setCensorMode(enabled) {
    document.body.classList.toggle('censor-on', enabled);
    if (censorToggle) {
        censorToggle.checked = enabled;
    }
    localStorage.setItem('censorIds', enabled ? '1' : '0');
    document.dispatchEvent(new CustomEvent('censorModeChange', { detail: { enabled } }));
}

modeButtons.forEach((button) => {
    button.addEventListener('click', () => {
        setPlayerMode(button.dataset.playerMode);
    });
});

const initialMode = localStorage.getItem('playersEditorMode') || 'player';
setPlayerMode(initialMode);
setCensorMode(localStorage.getItem('censorIds') === '1');

function setPlayerDirty(value) {
    playerState.dirty = value;
    if (playerDirtyState) {
        if (value) {
            playerDirtyState.textContent = 'Unsaved changes.';
            playerDirtyState.classList.add('dirty');
            playerDirtyState.classList.remove('saved');
        } else {
            playerDirtyState.textContent = 'All changes saved.';
            playerDirtyState.classList.remove('dirty');
            playerDirtyState.classList.add('saved');
        }
    }
    if (playerSaveBtn) {
        playerSaveBtn.disabled = !value;
    }
}

async function loadPlayers() {
    const response = await fetch(`/api/server/${SERVER_ID}/player-summaries`);
    const result = await response.json();
    if (!result.success) {
        showPlayerToast(result.error || 'Players could not be loaded.', 'error');
        return;
    }
    playerState.allPlayers = result.players || [];
    renderPlayerCards();
}

function setActiveCard(card, button) {
    if (playerState.activeButton) {
        playerState.activeButton.textContent = 'Edit';
    }
    if (playerState.activeCard) {
        playerState.activeCard.classList.remove('active');
    }
    playerState.activeCard = card;
    playerState.activeButton = button;
    if (card && button) {
        card.classList.add('active');
        button.textContent = 'Stop Editing';
    }
}

function getPlayerGridColumns() {
    if (!playerCards) return 1;
    const template = window.getComputedStyle(playerCards).gridTemplateColumns || '';
    const columns = template.split(' ').filter(Boolean).length;
    return Math.max(1, columns || 1);
}

function attachDetailRow(cardElement) {
    if (!playerCards) return;

    const wrapper = cardElement?.closest?.('.player-card-wrapper');
    const wrappers = Array.from(playerCards.querySelectorAll(':scope > .player-card-wrapper'));
    let anchor = null;

    if (wrapper) {
        const wrapperIndex = wrappers.indexOf(wrapper);
        if (wrapperIndex >= 0) {
            const columns = getPlayerGridColumns();
            const rowStart = Math.floor(wrapperIndex / columns) * columns;
            const rowEnd = Math.min(rowStart + columns - 1, wrappers.length - 1);
            anchor = wrappers[rowEnd];
        }
    }

    if (!anchor) {
        playerCards.appendChild(playerDetailRow);
    } else if (anchor.nextElementSibling) {
        playerCards.insertBefore(playerDetailRow, anchor.nextElementSibling);
    } else {
        playerCards.appendChild(playerDetailRow);
    }

    if (!playerDetailRow.contains(playerDetail)) {
        playerDetailRow.appendChild(playerDetail);
    }
}

async function closePlayerDetail({ promptSave = true } = {}) {
    if (!playerDetailRow.isConnected) return true;
    if (playerState.dirty && promptSave) {
        const confirmSave = window.confirm('Änderungen speichern?');
        if (confirmSave) {
            const saved = await savePlayer();
            if (!saved) return false;
        } else {
            setPlayerDirty(false);
        }
    }
    playerState.currentFile = null;
    playerState.currentData = null;
    playerState.inventoryState = null;
    setPendingSplit(null);
    playerState.lastHoveredSlot = null;
    playerDetail.classList.add('hidden');
    if (playerDetailRow.parentNode) {
        playerDetailRow.parentNode.removeChild(playerDetailRow);
    }
    setActiveCard(null, null);
    return true;
}

async function renderPlayerCards() {
    const query = playerSearch.value.trim().toLowerCase();
    const filtered = playerState.allPlayers.filter((player) => {
        const name = (player.name || '').toLowerCase();
        const uuid = (player.uuid || '').toLowerCase();
        return name.includes(query) || uuid.includes(query);
    });

    playerState.filteredPlayers = filtered;

    const totalPages = Math.max(1, Math.ceil(filtered.length / PAGE_SIZE));
    if (playerState.page > totalPages) {
        playerState.page = totalPages;
    }
    const startIndex = (playerState.page - 1) * PAGE_SIZE;
    const pagePlayers = filtered.slice(startIndex, startIndex + PAGE_SIZE);

    if (playerDetailRow.isConnected) {
        const stillVisible = pagePlayers.some((player) => player.file === playerState.currentFile);
        if (!stillVisible) {
            const closed = await closePlayerDetail({ promptSave: true });
            if (!closed) {
                return;
            }
        }
    }

    playerCards.innerHTML = '';
    if (!pagePlayers.length) {
        playerCardsEmpty.classList.remove('hidden');
    } else {
        playerCardsEmpty.classList.add('hidden');
    }

    const cardElements = [];

    pagePlayers.forEach((player, index) => {
        const wrapper = document.createElement('div');
        wrapper.className = 'player-card-wrapper';

        const card = document.createElement('div');
        card.className = 'player-card';
        card.dataset.file = player.file;

        const avatar = document.createElement('img');
        avatar.className = 'player-card-avatar';
        const avatarKey = player.name || player.uuid || player.file;
        if (avatarKey) {
            avatar.src = `/api/server/${SERVER_ID}/avatar/${encodeURIComponent(avatarKey)}`;
        }
        avatar.alt = `${player.name || 'Player'} avatar`;
        avatar.loading = 'lazy';
        avatar.decoding = 'async';

        const name = document.createElement('div');
        name.className = 'player-card-name';
        name.textContent = player.name || 'Unknown';

        const uuid = document.createElement('div');
        uuid.className = 'player-card-uuid censor-target';
        uuid.textContent = player.uuid || player.file || 'Unknown';

        const meta = document.createElement('div');
        meta.className = 'player-card-meta';
        meta.textContent = 'Player UUID';

        const actions = document.createElement('div');
        actions.className = 'player-card-actions';
        const editBtn = document.createElement('button');
        editBtn.type = 'button';
        editBtn.className = 'btn btn-ghost btn-small';
        editBtn.textContent = 'Edit';
        editBtn.addEventListener('click', async () => {
            await openPlayer(player, {
                card,
                button: editBtn,
                index,
                cardElements,
                pagePlayers,
            });
        });
        actions.appendChild(editBtn);

        card.appendChild(avatar);
        card.appendChild(meta);
        card.appendChild(name);
        card.appendChild(uuid);
        card.appendChild(actions);
        wrapper.appendChild(card);
        playerCards.appendChild(wrapper);
        cardElements.push(card);
    });

    if (playerDetailRow.isConnected && playerState.currentFile) {
        const currentIndex = pagePlayers.findIndex((player) => player.file === playerState.currentFile);
        if (currentIndex >= 0) {
            attachDetailRow(cardElements[currentIndex]);
            const activeCard = cardElements[currentIndex];
            const activeButton = activeCard.querySelector('.player-card-actions .btn');
            setActiveCard(activeCard, activeButton);
        }
    }

    if (playersPageInfo) {
        playersPageInfo.textContent = `Page ${playerState.page} of ${totalPages}`;
    }
    if (playersPrev) {
        playersPrev.disabled = playerState.page <= 1;
    }
    if (playersNext) {
        playersNext.disabled = playerState.page >= totalPages;
    }
}

async function openPlayer(player, context) {
    if (playerState.currentFile === player.file && playerDetailRow.isConnected) {
        await closePlayerDetail({ promptSave: true });
        return;
    }

    if (playerDetailRow.isConnected && playerState.currentFile !== player.file) {
        const closed = await closePlayerDetail({ promptSave: true });
        if (!closed) return;
    }

    playerDetail.classList.remove('hidden');
    playerDetailName.textContent = 'Loading player...';
    playerDetailUuid.textContent = '';
    inventoryMeta.textContent = '';

    if (context?.cardElements) {
        attachDetailRow(context.card);
        setActiveCard(context.card, context.button);
    }

    const response = await fetch(`/api/server/${SERVER_ID}/player-file?name=${encodeURIComponent(player.file)}`);
    const result = await response.json();
    if (!result.success) {
        showPlayerToast(result.error || 'Player could not be loaded.', 'error');
        await closePlayerDetail({ promptSave: false });
        return;
    }

    playerState.currentFile = player.file;
    playerState.currentData = result.data || {};
    setPlayerDirty(false);

    const displayName = getPlayerDisplayName(playerState.currentData, player.uuid);
    playerDetailName.textContent = displayName;
    playerDetailUuid.textContent = `UUID: ${player.uuid}`;
    playerDetailUuid.classList.add('censor-target');
    inventoryMeta.textContent = `File: ${player.file}`;
    inventoryMeta.classList.add('censor-target');

    hydrateInventoryState();
    renderInventory();
}

function getPlayerDisplayName(data, fallback) {
    const components = data?.Components || {};
    const rawText = components?.DisplayName?.DisplayName?.RawText;
    if (rawText && typeof rawText === 'string') {
        return rawText.trim();
    }
    const nameplate = components?.Nameplate?.Text;
    if (nameplate && typeof nameplate === 'string') {
        return nameplate.trim();
    }
    return fallback || 'Unknown';
}

function hydrateInventoryState() {
    if (!playerState.currentData.Components) {
        playerState.currentData.Components = {};
    }
    if (!playerState.currentData.Components.Player) {
        playerState.currentData.Components.Player = {};
    }
    if (!playerState.currentData.Components.Player.Inventory) {
        playerState.currentData.Components.Player.Inventory = {};
    }

    const inventory = playerState.currentData.Components.Player.Inventory;
    const ensureSection = (section, capacityFallback) => {
        const data = inventory[section] || {};
        if (!data.Items) {
            data.Items = {};
        }
        if (!data.Capacity && capacityFallback) {
            data.Capacity = capacityFallback;
        }
        inventory[section] = data;
        return {
            items: data.Items,
            capacity: data.Capacity || 0,
        };
    };

    playerState.inventoryState = {
        Armor: ensureSection('Armor', 4),
        Utility: ensureSection('Utility', 4),
        Storage: ensureSection('Storage', 36),
        HotBar: ensureSection('HotBar', 9),
        Tool: ensureSection('Tool', 23),
    };
}

function renderInventory() {
    if (!playerState.inventoryState) return;

    renderSection(armorGrid, 'Armor', { columns: 1, slotLabels: ['H', 'C', 'L', 'F'] });
    renderUtilityRadial();
    renderSection(storageGrid, 'Storage', { columns: 9 });
    renderSection(hotbarGrid, 'HotBar', { columns: 9, hotkeys: true });
    renderSection(toolGrid, 'Tool', { columns: 9 });

    const activeSlot = playerState.currentData?.Components?.Player?.Inventory?.ActiveHotbarSlot;
    if (typeof activeSlot === 'number') {
        const slot = hotbarGrid.querySelector(`[data-index="${activeSlot}"]`);
        if (slot) {
            slot.classList.add('active-slot');
        }
    }

    renderStatsPanel();
    renderWorldData();
}

function clearSlot(slot) {
    while (slot.firstChild) {
        slot.removeChild(slot.firstChild);
    }
}

function renderUtilityRadial() {
    if (!utilityRadial) return;
    const radialSlots = utilityRadial.querySelectorAll('.radial-slot');
    const section = playerState.inventoryState?.Utility;
    if (!section) return;

    radialSlots.forEach((slot) => {
        const index = Number(slot.dataset.index);
        clearSlot(slot);
        const item = section.items[String(index)];
        if (item) {
            slot.appendChild(buildItemElement(item, 'Utility', index));
        }
        addSlotListeners(slot);
    });

    const center = utilityRadial.querySelector('.utility-center');
    if (center && !center.dataset.bound) {
        center.dataset.bound = 'true';
        const openRadial = () => {
            if (playerState.dragSource) {
                utilityRadial.classList.add('force-open');
            }
        };
        center.addEventListener('dragenter', openRadial);
        center.addEventListener('dragover', (event) => {
            event.preventDefault();
            openRadial();
        });
        utilityRadial.addEventListener('dragleave', (event) => {
            if (!utilityRadial.contains(event.relatedTarget)) {
                utilityRadial.classList.remove('force-open');
            }
        });
    }
}

function renderSection(container, sectionName, options) {
    if (!container) return;
    const section = playerState.inventoryState[sectionName];
    if (!section) return;

    container.innerHTML = '';
    container.style.setProperty('--columns', options.columns || 1);

    for (let i = 0; i < section.capacity; i += 1) {
        const slot = document.createElement('div');
        slot.className = 'inventory-slot';
        slot.dataset.section = sectionName;
        slot.dataset.index = i;

        if (options.slotLabels && options.slotLabels[i]) {
            const label = document.createElement('span');
            label.className = 'slot-label';
            label.textContent = options.slotLabels[i];
            slot.appendChild(label);
        }

        if (options.hotkeys) {
            const hotkey = document.createElement('span');
            hotkey.className = 'slot-hotkey';
            hotkey.textContent = i + 1;
            slot.appendChild(hotkey);
        }

        const item = section.items[String(i)];
        if (item) {
            slot.appendChild(buildItemElement(item, sectionName, i));
        }

        addSlotListeners(slot);
        container.appendChild(slot);
    }
}

function renderStatsPanel() {
    if (!entityStatsPanel) return;
    entityStatsPanel.innerHTML = '';

    const stats = playerState.currentData?.Components?.EntityStats?.Stats;
    if (!stats || typeof stats !== 'object') {
        const empty = document.createElement('div');
        empty.className = 'empty-state';
        empty.textContent = 'No stats available.';
        entityStatsPanel.appendChild(empty);
        return;
    }

    Object.keys(stats).forEach((statId) => {
        const stat = stats[statId] || {};
        const value = Number(stat.Value ?? 0);
        const defaultMax = STAT_DEFAULT_MAX[statId] || 100;
        let currentMax = Math.max(defaultMax, value || 0);
        const percent = currentMax ? Math.min(100, Math.max(0, (value / currentMax) * 100)) : 0;

        const card = document.createElement('div');
        card.className = 'stat-card';

        const header = document.createElement('div');
        header.className = 'stat-header';
        const icon = document.createElement('div');
        icon.className = 'stat-icon';
        icon.textContent = STAT_ICONS[statId] || statId.slice(0, 2).toUpperCase();
        const meta = document.createElement('div');
        const name = document.createElement('div');
        name.className = 'stat-name';
        name.textContent = statId;
        const sub = document.createElement('div');
        sub.className = 'stat-sub';
        sub.textContent = stat.Id || statId;
        meta.appendChild(name);
        meta.appendChild(sub);
        header.appendChild(icon);
        header.appendChild(meta);

        const controls = document.createElement('div');
        controls.className = 'stat-controls';
        const range = document.createElement('input');
        range.type = 'range';
        range.min = 0;
        range.max = currentMax;
        range.value = value;
        const number = document.createElement('input');
        number.type = 'number';
        number.min = 0;
        number.value = value;

        const bar = document.createElement('div');
        bar.className = 'stat-bar';
        const fill = document.createElement('div');
        fill.className = 'stat-bar-fill';
        fill.style.width = `${percent}%`;
        bar.appendChild(fill);

        range.addEventListener('input', () => {
            const nextValue = Number(range.value);
            number.value = nextValue;
            fill.style.width = `${Math.min(100, Math.max(0, (nextValue / currentMax) * 100))}%`;
        });
        range.addEventListener('change', () => {
            updateStatValue(statId, Number(range.value));
        });
        number.addEventListener('change', () => {
            const nextValue = Number(number.value);
            if (nextValue > currentMax) {
                currentMax = nextValue;
                range.max = currentMax;
            }
            range.value = nextValue;
            fill.style.width = `${Math.min(100, Math.max(0, (nextValue / currentMax) * 100))}%`;
            updateStatValue(statId, nextValue);
        });

        controls.appendChild(range);
        controls.appendChild(number);

        card.appendChild(header);
        card.appendChild(controls);
        card.appendChild(bar);
        entityStatsPanel.appendChild(card);
    });
}

function updateStatValue(statId, value) {
    if (!playerState.currentData.Components) {
        playerState.currentData.Components = {};
    }
    if (!playerState.currentData.Components.EntityStats) {
        playerState.currentData.Components.EntityStats = { Stats: {}, Version: 1 };
    }
    if (!playerState.currentData.Components.EntityStats.Stats) {
        playerState.currentData.Components.EntityStats.Stats = {};
    }
    if (!playerState.currentData.Components.EntityStats.Stats[statId]) {
        playerState.currentData.Components.EntityStats.Stats[statId] = { Id: statId, Value: 0 };
    }
    playerState.currentData.Components.EntityStats.Stats[statId].Value = value;
    setPlayerDirty(true);
}

function renderWorldData() {
    if (!worldDataPanel) return;
    worldDataPanel.innerHTML = '';

    const perWorld = playerState.currentData?.Components?.Player?.PlayerData?.PerWorldData;
    if (!perWorld || typeof perWorld !== 'object') {
        const empty = document.createElement('div');
        empty.className = 'empty-state';
        empty.textContent = 'No world data available.';
        worldDataPanel.appendChild(empty);
        return;
    }

    Object.keys(perWorld).forEach((worldKey) => {
        const world = perWorld[worldKey] || {};
        const card = document.createElement('div');
        card.className = 'world-card';

        const title = document.createElement('div');
        title.className = 'world-title';
        title.textContent = worldKey;

        const toggles = document.createElement('div');
        toggles.className = 'world-toggles';
        const firstSpawn = document.createElement('label');
        firstSpawn.className = 'toggle-row';
        const firstSpawnInput = document.createElement('input');
        firstSpawnInput.type = 'checkbox';
        firstSpawnInput.checked = !!world.FirstSpawn;
        const firstSpawnText = document.createElement('span');
        firstSpawnText.textContent = 'First Spawn';
        firstSpawn.appendChild(firstSpawnInput);
        firstSpawn.appendChild(firstSpawnText);
        const flying = document.createElement('label');
        flying.className = 'toggle-row';
        const flyingInput = document.createElement('input');
        flyingInput.type = 'checkbox';
        flyingInput.checked = !!world.LastMovementStates?.Flying;
        const flyingText = document.createElement('span');
        flyingText.textContent = 'Flying';
        flying.appendChild(flyingInput);
        flying.appendChild(flyingText);
        toggles.appendChild(firstSpawn);
        toggles.appendChild(flying);

        const position = world.LastPosition || {};
        const positionGrid = document.createElement('div');
        positionGrid.className = 'world-position-grid';
        const fields = [
            { key: 'X', label: 'X' },
            { key: 'Y', label: 'Y' },
            { key: 'Z', label: 'Z' },
            { key: 'Yaw', label: 'Yaw' },
            { key: 'Pitch', label: 'Pitch' },
            { key: 'Roll', label: 'Roll' },
        ];
        fields.forEach((field) => {
            const wrapper = document.createElement('label');
            wrapper.className = 'world-input';
            const text = document.createElement('span');
            text.textContent = field.label;
            const input = document.createElement('input');
            input.type = 'number';
            input.step = '0.01';
            input.value = position[field.key] ?? 0;
            input.addEventListener('change', () => {
                ensureWorldData(worldKey);
                const nextValue = Number(input.value);
                playerState.currentData.Components.Player.PlayerData.PerWorldData[worldKey].LastPosition[field.key] = nextValue;
                setPlayerDirty(true);
            });
            wrapper.appendChild(text);
            wrapper.appendChild(input);
            positionGrid.appendChild(wrapper);
        });

        const deathList = document.createElement('div');
        deathList.className = 'death-list';
        const deaths = Array.isArray(world.DeathPositions) ? world.DeathPositions : [];
        if (!deaths.length) {
            const empty = document.createElement('div');
            empty.className = 'empty-state';
            empty.textContent = 'No death positions.';
            deathList.appendChild(empty);
        } else {
            deaths.forEach((death, deathIndex) => {
                const row = document.createElement('div');
                row.className = 'death-row';
                const label = document.createElement('div');
                label.className = 'death-meta';
                const transform = death.Transform || {};
                label.textContent = `Day ${death.Day ?? 0} • X ${transform.X ?? 0} Y ${transform.Y ?? 0} Z ${transform.Z ?? 0}`;
                const removeBtn = document.createElement('button');
                removeBtn.type = 'button';
                removeBtn.className = 'btn btn-ghost btn-small';
                removeBtn.textContent = 'Loeschen';
                removeBtn.addEventListener('click', () => {
                    ensureWorldData(worldKey);
                    const list = playerState.currentData.Components.Player.PlayerData.PerWorldData[worldKey].DeathPositions || [];
                    list.splice(deathIndex, 1);
                    playerState.currentData.Components.Player.PlayerData.PerWorldData[worldKey].DeathPositions = list;
                    setPlayerDirty(true);
                    renderWorldData();
                });
                row.appendChild(label);
                row.appendChild(removeBtn);
                deathList.appendChild(row);
            });
        }

        firstSpawnInput.addEventListener('change', () => {
            ensureWorldData(worldKey);
            playerState.currentData.Components.Player.PlayerData.PerWorldData[worldKey].FirstSpawn = firstSpawnInput.checked;
            setPlayerDirty(true);
        });
        flyingInput.addEventListener('change', () => {
            ensureWorldData(worldKey);
            if (!playerState.currentData.Components.Player.PlayerData.PerWorldData[worldKey].LastMovementStates) {
                playerState.currentData.Components.Player.PlayerData.PerWorldData[worldKey].LastMovementStates = {};
            }
            playerState.currentData.Components.Player.PlayerData.PerWorldData[worldKey].LastMovementStates.Flying = flyingInput.checked;
            setPlayerDirty(true);
        });

        card.appendChild(title);
        card.appendChild(toggles);
        card.appendChild(positionGrid);
        card.appendChild(deathList);
        worldDataPanel.appendChild(card);
    });
}

function ensureWorldData(worldKey) {
    if (!playerState.currentData.Components) {
        playerState.currentData.Components = {};
    }
    if (!playerState.currentData.Components.Player) {
        playerState.currentData.Components.Player = {};
    }
    if (!playerState.currentData.Components.Player.PlayerData) {
        playerState.currentData.Components.Player.PlayerData = {};
    }
    if (!playerState.currentData.Components.Player.PlayerData.PerWorldData) {
        playerState.currentData.Components.Player.PlayerData.PerWorldData = {};
    }
    if (!playerState.currentData.Components.Player.PlayerData.PerWorldData[worldKey]) {
        playerState.currentData.Components.Player.PlayerData.PerWorldData[worldKey] = {
            DeathPositions: [],
            FirstSpawn: false,
            LastMovementStates: { Flying: false },
            LastPosition: { X: 0, Y: 0, Z: 0, Pitch: 0, Roll: 0, Yaw: 0 },
        };
    }
    if (!playerState.currentData.Components.Player.PlayerData.PerWorldData[worldKey].LastPosition) {
        playerState.currentData.Components.Player.PlayerData.PerWorldData[worldKey].LastPosition = { X: 0, Y: 0, Z: 0, Pitch: 0, Roll: 0, Yaw: 0 };
    }
}

function buildItemElement(item, sectionName, index) {
    const wrapper = document.createElement('div');
    wrapper.className = 'inventory-item';
    wrapper.draggable = true;
    wrapper.dataset.section = sectionName;
    wrapper.dataset.index = index;

    const img = document.createElement('img');
    img.className = 'inventory-item-img loading';
    img.src = `${ITEM_IMAGE_URL}${encodeURIComponent(item.Id)}`;
    img.alt = item.Id;
    img.title = item.Id;

    img.onload = () => {
        img.classList.remove('loading');
    };
    img.onerror = () => {
        img.classList.remove('loading');
        img.src = `https://placehold.co/64x64/2a3442/ffffff?text=${item.Id.substring(0, 3)}`;
    };

    ensureItemMetadata(item.Id, img);

    wrapper.appendChild(img);

    const quantity = item.Quantity || 1;
    if (quantity > 1) {
        const count = document.createElement('span');
        count.className = 'inventory-count';
        count.textContent = quantity;
        wrapper.appendChild(count);
    }

    if (item.MaxDurability && item.MaxDurability > 0) {
        const bar = document.createElement('div');
        bar.className = 'inventory-durability';
        const fill = document.createElement('div');
        fill.className = 'inventory-durability-fill';
        const percent = Math.min(100, Math.max(0, (item.Durability / item.MaxDurability) * 100));
        fill.style.width = `${percent}%`;
        if (percent < 20) {
            fill.classList.add('low');
        }
        bar.appendChild(fill);
        wrapper.appendChild(bar);
    }

    if (quantity > 1) {
        const splitBtn = document.createElement('button');
        splitBtn.type = 'button';
        splitBtn.className = 'inventory-split';
        splitBtn.textContent = '÷';
        splitBtn.addEventListener('click', (event) => {
            event.stopPropagation();
            openStackSplitModal(item, sectionName, index);
        });
        wrapper.appendChild(splitBtn);
    }

    const removeBtn = document.createElement('button');
    removeBtn.type = 'button';
    removeBtn.className = 'inventory-remove';
    removeBtn.textContent = 'x';
    removeBtn.addEventListener('click', (event) => {
        event.stopPropagation();
        openDeleteModal(item, sectionName, index);
    });

    wrapper.appendChild(removeBtn);

    wrapper.addEventListener('dragstart', handleDragStart);
    wrapper.addEventListener('dragend', handleDragEnd);

    return wrapper;
}

function ensureItemMetadata(itemId, img) {
    if (itemMetaCache.has(itemId)) {
        const meta = itemMetaCache.get(itemId);
        if (meta?.name) {
            img.title = `${meta.name} (${itemId})`;
        }
        return;
    }

    fetch(`${ITEM_API_URL}${encodeURIComponent(itemId)}`)
        .then((response) => response.json())
        .then((data) => {
            const item = data?.item;
            if (item) {
                itemMetaCache.set(itemId, item);
                img.title = `${item.name || itemId} (${itemId})`;
            }
        })
        .catch(() => {
            itemMetaCache.set(itemId, { name: itemId });
        });
}

function addSlotListeners(slot) {
    slot.addEventListener('dragover', (event) => event.preventDefault());
    slot.addEventListener('dragenter', (event) => {
        event.preventDefault();
        slot.classList.add('drag-over');
    });
    slot.addEventListener('dragleave', (event) => {
        if (!slot.contains(event.relatedTarget)) {
            slot.classList.remove('drag-over');
        }
    });
    slot.addEventListener('drop', (event) => {
        event.preventDefault();
        slot.classList.remove('drag-over');
        handleDrop(slot);
    });
    slot.addEventListener('click', () => {
        handleSlotClick(slot);
    });
    slot.addEventListener('mouseenter', () => {
        playerState.lastHoveredSlot = slot;
    });
    slot.addEventListener('contextmenu', (event) => {
        if (!playerState.dragSource) return;
        event.preventDefault();
        handleRightClickSplit(slot);
    });
}

function handleDragStart(event) {
    const target = event.currentTarget;
    playerState.dragSource = {
        section: target.dataset.section,
        index: Number(target.dataset.index),
    };
    event.dataTransfer.effectAllowed = 'move';
    event.dataTransfer.setData('text/plain', 'move');
    setTimeout(() => {
        target.classList.add('dragging');
    }, 0);
}

function handleDragEnd(event) {
    event.currentTarget.classList.remove('dragging');
    playerState.dragSource = null;
    document.querySelectorAll('.inventory-slot.drag-over').forEach((slot) => {
        slot.classList.remove('drag-over');
    });
    if (utilityRadial) {
        utilityRadial.classList.remove('force-open');
    }
}

function handleDrop(slot) {
    if (!playerState.dragSource) return;
    const targetSection = slot.dataset.section;
    const targetIndex = Number(slot.dataset.index);
    moveItem(playerState.dragSource, { section: targetSection, index: targetIndex });
}

function handleRightClickSplit(slot) {
    const targetSection = slot.dataset.section;
    const targetIndex = Number(slot.dataset.index);
    if (!targetSection || Number.isNaN(targetIndex)) return;

    const source = playerState.dragSource;
    const sourceItems = playerState.inventoryState?.[source.section]?.items;
    const targetItems = playerState.inventoryState?.[targetSection]?.items;
    if (!sourceItems || !targetItems) return;

    const sourceKey = String(source.index);
    const targetKey = String(targetIndex);
    const sourceItem = sourceItems[sourceKey];
    if (!sourceItem) return;

    const sourceQuantity = sourceItem.Quantity || 1;
    if (sourceQuantity <= 1) {
        moveItem(source, { section: targetSection, index: targetIndex });
        return;
    }

    const targetItem = targetItems[targetKey];
    if (targetItem && targetItem.Id !== sourceItem.Id) {
        showPlayerToast('Slot hat ein anderes Item.', 'error');
        return;
    }

    if (targetItem) {
        const targetQuantity = targetItem.Quantity || 1;
        targetItem.Quantity = targetQuantity + 1;
    } else {
        targetItems[targetKey] = { ...sourceItem, Quantity: 1 };
    }

    sourceItem.Quantity = sourceQuantity - 1;
    if (sourceItem.Quantity <= 0) {
        delete sourceItems[sourceKey];
    }

    setPlayerDirty(true);
    renderInventory();
}

function setPendingSplit(data) {
    playerState.pendingSplit = data;
    document.querySelectorAll('.inventory-slot').forEach((slot) => {
        const section = slot.dataset.section;
        const index = Number(slot.dataset.index);
        const items = playerState.inventoryState?.[section]?.items;
        const hasItem = items && items[String(index)];
        slot.classList.toggle('split-target', !!data && !hasItem);
    });
}

function handleSlotClick(slot) {
    if (!playerState.pendingSplit) return;
    const targetSection = slot.dataset.section;
    const targetIndex = Number(slot.dataset.index);
    if (!targetSection || Number.isNaN(targetIndex)) return;

    const targetItems = playerState.inventoryState?.[targetSection]?.items;
    if (!targetItems) return;
    const targetKey = String(targetIndex);
    if (targetItems[targetKey]) {
        showPlayerToast('Slot ist belegt.', 'error');
        return;
    }

    const source = playerState.pendingSplit;
    const sourceItems = playerState.inventoryState?.[source.section]?.items;
    if (!sourceItems) return;
    const sourceKey = String(source.index);
    const sourceItem = sourceItems[sourceKey];
    if (!sourceItem) {
        setPendingSplit(null);
        return;
    }

    const quantity = sourceItem.Quantity || 1;
    if (source.amount >= quantity || source.amount <= 0) {
        showPlayerToast('Ungültige Menge.', 'error');
        setPendingSplit(null);
        return;
    }

    sourceItem.Quantity = quantity - source.amount;
    if (sourceItem.Quantity <= 0) {
        delete sourceItems[sourceKey];
    }
    const newItem = { ...sourceItem, Quantity: source.amount };
    targetItems[targetKey] = newItem;

    setPlayerDirty(true);
    setPendingSplit(null);
    renderInventory();
}

function moveItem(source, target) {
    if (source.section === target.section && source.index === target.index) return;

    const sourceItems = playerState.inventoryState[source.section]?.items;
    const targetItems = playerState.inventoryState[target.section]?.items;
    if (!sourceItems || !targetItems) return;

    const sourceKey = String(source.index);
    const targetKey = String(target.index);

    const sourceItem = sourceItems[sourceKey];
    if (!sourceItem) return;

    const targetItem = targetItems[targetKey];

    if (targetItem) {
        sourceItems[sourceKey] = targetItem;
    } else {
        delete sourceItems[sourceKey];
    }

    targetItems[targetKey] = sourceItem;

    setPlayerDirty(true);
    renderInventory();
}

function removeItem(sectionName, index) {
    const items = playerState.inventoryState[sectionName]?.items;
    if (!items) return;
    delete items[String(index)];
    setPlayerDirty(true);
    renderInventory();
}

function getInventoryItem(sectionName, index) {
    const items = playerState.inventoryState?.[sectionName]?.items;
    if (!items) return null;
    return items[String(index)] || null;
}

function handleSplitConfirm() {
    if (!playerState.activeModal || playerState.activeModal.type !== 'split') return;
    const { sectionName, index } = playerState.activeModal;
    const item = getInventoryItem(sectionName, index);
    if (!item) {
        closeModal(stackModal);
        playerState.activeModal = null;
        return;
    }
    const quantity = item.Quantity || 1;
    const amount = Number(stackModalAmount.value);
    if (!Number.isFinite(amount) || amount <= 0 || amount >= quantity) {
        showPlayerToast('Ungültige Menge.', 'error');
        return;
    }
    setPendingSplit({ section: sectionName, index, amount });
    closeModal(stackModal);
    playerState.activeModal = null;
    showPlayerToast('Wähle ein leeres Slot für den Split.', 'success');
}

function handleDeleteAll() {
    if (!playerState.activeModal || playerState.activeModal.type !== 'delete') return;
    const { sectionName, index } = playerState.activeModal;
    removeItem(sectionName, index);
    closeModal(deleteModal);
    playerState.activeModal = null;
}

function handleDeleteConfirm() {
    if (!playerState.activeModal || playerState.activeModal.type !== 'delete') return;
    const { sectionName, index } = playerState.activeModal;
    const item = getInventoryItem(sectionName, index);
    if (!item) {
        closeModal(deleteModal);
        playerState.activeModal = null;
        return;
    }
    const quantity = item.Quantity || 1;
    const amount = Number(deleteModalAmount.value);
    if (!Number.isFinite(amount) || amount <= 0) {
        showPlayerToast('Ungültige Menge.', 'error');
        return;
    }
    if (amount >= quantity) {
        removeItem(sectionName, index);
    } else {
        item.Quantity = quantity - amount;
        setPlayerDirty(true);
        renderInventory();
    }
    closeModal(deleteModal);
    playerState.activeModal = null;
}

async function savePlayer() {
    if (!playerState.currentFile || !playerState.currentData) return false;

    const response = await fetch(`/api/server/${SERVER_ID}/player-file?name=${encodeURIComponent(playerState.currentFile)}`,
        {
            method: 'POST',
            headers: { 'Content-Type': 'application/json', 'X-CSRFToken': CSRF_TOKEN },
            body: JSON.stringify({ data: playerState.currentData })
        }
    );

    const result = await response.json();
    if (result.success) {
        setPlayerDirty(false);
        showPlayerToast('Saved.');
        refreshCurrentPlayerSummary();
        return true;
    } else {
        showPlayerToast(result.error || 'Save failed.', 'error');
        return false;
    }
}

function refreshCurrentPlayerSummary() {
    if (!playerState.currentFile) return;
    const uuid = playerState.currentFile.replace(/\.json$/, '');
    const displayName = getPlayerDisplayName(playerState.currentData, uuid);
    const player = playerState.allPlayers.find((entry) => entry.file === playerState.currentFile);
    if (player) {
        player.name = displayName;
    }
    renderPlayerCards();
}

playerSearch.addEventListener('input', async () => {
    playerState.page = 1;
    await renderPlayerCards();
});

if (playersPrev) {
    playersPrev.addEventListener('click', async () => {
        if (playerState.page > 1) {
            playerState.page -= 1;
            await renderPlayerCards();
        }
    });
}

if (playersNext) {
    playersNext.addEventListener('click', async () => {
        const totalPages = Math.max(1, Math.ceil(playerState.filteredPlayers.length / PAGE_SIZE));
        if (playerState.page < totalPages) {
            playerState.page += 1;
            await renderPlayerCards();
        }
    });
}

if (playerSaveBtn) {
    playerSaveBtn.addEventListener('click', () => {
        savePlayer();
    });
}

if (censorToggle) {
    censorToggle.addEventListener('change', () => {
        setCensorMode(censorToggle.checked);
    });
}

if (inventoryShell) {
    inventoryShell.addEventListener('contextmenu', (event) => {
        if (!playerState.dragSource) return;
        if (!playerState.lastHoveredSlot || !inventoryShell.contains(playerState.lastHoveredSlot)) return;
        event.preventDefault();
        handleRightClickSplit(playerState.lastHoveredSlot);
    });
}

if (stackModalCancel) {
    stackModalCancel.addEventListener('click', () => {
        closeModal(stackModal);
        playerState.activeModal = null;
    });
}

if (stackModalConfirm) {
    stackModalConfirm.addEventListener('click', () => {
        handleSplitConfirm();
    });
}

if (deleteModalCancel) {
    deleteModalCancel.addEventListener('click', () => {
        closeModal(deleteModal);
        playerState.activeModal = null;
    });
}

if (deleteModalAll) {
    deleteModalAll.addEventListener('click', () => {
        handleDeleteAll();
    });
}

if (deleteModalConfirm) {
    deleteModalConfirm.addEventListener('click', () => {
        handleDeleteConfirm();
    });
}

window.addEventListener('beforeunload', (event) => {
    if (!playerState.dirty) return;
    event.preventDefault();
    event.returnValue = '';
});

loadPlayers();
