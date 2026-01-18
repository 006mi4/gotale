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

    if (!window.NAV_SERVER_CONTROLS_LOCK && window.SERVER_ID) {
        const startBtn = document.getElementById('startBtn');
        const stopBtn = document.getElementById('stopBtn');
        const restartBtn = document.getElementById('restartBtn');

        const callAction = async (action, button, busyLabel) => {
            if (!button) return;
            const original = button.textContent;
            button.disabled = true;
            button.textContent = busyLabel;
            try {
                const response = await fetch(`/api/server/${window.SERVER_ID}/${action}`, {
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
