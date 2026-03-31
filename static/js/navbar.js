document.addEventListener('DOMContentLoaded', () => {
    const navRoot = document.querySelector('[data-nav-root]');
    if (!navRoot) return;

    const menu = navRoot.querySelector('[data-nav-menu]');
    const toggle = navRoot.querySelector('[data-nav-toggle]');
    const dropdowns = navRoot.querySelectorAll('[data-nav-dropdown]');

    function closeDropdowns(except = null) {
        dropdowns.forEach((dropdown) => {
            if (dropdown !== except) {
                dropdown.classList.remove('is-open');
            }
        });
    }

    if (toggle && menu) {
        toggle.addEventListener('click', () => {
            menu.classList.toggle('is-open');
        });
    }

    dropdowns.forEach((dropdown) => {
        const trigger = dropdown.querySelector('[data-nav-trigger]');
        if (!trigger) return;
        trigger.addEventListener('click', (event) => {
            event.stopPropagation();
            const isOpen = dropdown.classList.contains('is-open');
            closeDropdowns(dropdown);
            dropdown.classList.toggle('is-open', !isOpen);
        });
    });

    document.addEventListener('click', () => {
        closeDropdowns();
    });

    const serverId = window.SERVER_ID ?? (typeof SERVER_ID !== 'undefined' ? SERVER_ID : null);

    function syncServerButtons(status) {
        const startBtn = document.getElementById('startBtn');
        const stopBtn = document.getElementById('stopBtn');
        const restartBtn = document.getElementById('restartBtn');
        if (!startBtn && !stopBtn && !restartBtn) return;

        const normalized = String(status || '').toLowerCase();
        const states = {
            online: { start: false, stop: true, restart: true },
            starting: { start: false, stop: true, restart: false },
            stopping: { start: false, stop: false, restart: false },
            offline: { start: true, stop: false, restart: false },
        };
        const fallback = { start: true, stop: true, restart: true };
        const state = states[normalized] || fallback;

        if (startBtn) {
            startBtn.disabled = !state.start;
            startBtn.hidden = !state.start;
        }
        if (stopBtn) {
            stopBtn.disabled = !state.stop;
            stopBtn.hidden = !state.stop;
        }
        if (restartBtn) {
            restartBtn.disabled = !state.restart;
            restartBtn.hidden = !state.restart;
        }
    }

    const statusBadge = document.getElementById('statusBadge');
    if (statusBadge) {
        syncServerButtons(statusBadge.getAttribute('data-status') || statusBadge.textContent);
        const observer = new MutationObserver(() => {
            syncServerButtons(statusBadge.getAttribute('data-status') || statusBadge.textContent);
        });
        observer.observe(statusBadge, { attributes: true, attributeFilter: ['data-status'], childList: true, subtree: true });
    }

    if (!window.NAV_SERVER_CONTROLS_LOCK && serverId) {
        const startBtn = document.getElementById('startBtn');
        const stopBtn = document.getElementById('stopBtn');
        const restartBtn = document.getElementById('restartBtn');

        const callAction = async (action, button, busyLabel) => {
            if (!button) return;
            const original = button.textContent;
            button.disabled = true;
            button.textContent = busyLabel;
            try {
                const response = await fetch(`/api/server/${serverId}/${action}`, {
                    method: 'POST',
                    headers: {
                        'Content-Type': 'application/json',
                        'X-CSRFToken': window.CSRF_TOKEN || '',
                    },
                    body: JSON.stringify({}),
                });
                const data = await response.json();
                if (!response.ok || !data.success) {
                    alert(data.error || 'Action failed.');
                } else {
                    try {
                        const statusResponse = await fetch(`/api/server/${serverId}/status`);
                        if (statusResponse.ok) {
                            const statusData = await statusResponse.json();
                            if (statusData.success) {
                                syncServerButtons(statusData.status);
                            }
                        }
                    } catch (error) {
                        console.error(error);
                    }
                }
            } catch (error) {
                console.error(error);
                alert('Action failed.');
            } finally {
                button.disabled = false;
                button.textContent = original;
            }
        };

        if (startBtn) {
            startBtn.addEventListener('click', () => callAction('start', startBtn, 'Starting...'));
        }
        if (stopBtn) {
            stopBtn.addEventListener('click', () => callAction('stop', stopBtn, 'Stopping...'));
        }
        if (restartBtn) {
            restartBtn.addEventListener('click', () => callAction('restart', restartBtn, 'Restarting...'));
        }
    }
});
