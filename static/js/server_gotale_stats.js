const statsRangeToggle = document.getElementById('statsRangeToggle');
const statsRefresh = document.getElementById('statsRefresh');
const statsJoinTotal = document.getElementById('statsJoinTotal');
const statsLeaveTotal = document.getElementById('statsLeaveTotal');
const statsChatTotal = document.getElementById('statsChatTotal');
const statsPlayersTotal = document.getElementById('statsPlayersTotal');
const statsOnlineNow = document.getElementById('statsOnlineNow');
const statsJoinsDelta = document.getElementById('statsJoinsDelta');
const statsJoinsTrend = document.getElementById('statsJoinsTrend');
const statsJoinsToday = document.getElementById('statsJoinsToday');
const statsJoinsYesterday = document.getElementById('statsJoinsYesterday');
const statsNewPlayersDelta = document.getElementById('statsNewPlayersDelta');
const statsNewPlayersTrend = document.getElementById('statsNewPlayersTrend');
const statsNewPlayersToday = document.getElementById('statsNewPlayersToday');
const statsNewPlayersYesterday = document.getElementById('statsNewPlayersYesterday');
const statsTotalEvents = document.getElementById('statsTotalEvents');
const statsUpdated = document.getElementById('statsUpdated');
const statsCanvas = document.getElementById('statsChart');

let statsChart = null;
let currentRange = 7;

function setUpdatedLabel() {
    if (!statsUpdated) return;
    const now = new Date();
    statsUpdated.textContent = now.toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' });
}

function updateTotals(data) {
    const joins = data.joins.reduce((sum, val) => sum + val, 0);
    const leaves = data.leaves.reduce((sum, val) => sum + val, 0);
    const chats = data.chats.reduce((sum, val) => sum + val, 0);
    const overview = data.overview || {};
    if (statsJoinTotal) statsJoinTotal.textContent = joins;
    if (statsLeaveTotal) statsLeaveTotal.textContent = leaves;
    if (statsChatTotal) statsChatTotal.textContent = chats;
    if (statsPlayersTotal) statsPlayersTotal.textContent = overview.total_players_ever ?? '--';
    if (statsOnlineNow) statsOnlineNow.textContent = overview.online_now ?? '--';
    if (statsTotalEvents) {
        const allTimeEvents = overview.total_events_all_time;
        statsTotalEvents.textContent = allTimeEvents ?? (joins + leaves + chats);
    }

    const joinDelta = Number(overview.join_delta_vs_yesterday || 0);
    if (statsJoinsDelta) statsJoinsDelta.textContent = joinDelta > 0 ? `+${joinDelta}` : `${joinDelta}`;
    if (statsJoinsToday) statsJoinsToday.textContent = String(overview.joins_today ?? 0);
    if (statsJoinsYesterday) statsJoinsYesterday.textContent = String(overview.joins_yesterday ?? 0);
    if (statsJoinsTrend) {
        statsJoinsTrend.classList.remove('up', 'down', 'neutral');
        const joinTrend = overview.join_trend || 'equal';
        if (joinTrend === 'up') {
            statsJoinsTrend.textContent = 'More joins than yesterday';
            statsJoinsTrend.classList.add('up');
        } else if (joinTrend === 'down') {
            statsJoinsTrend.textContent = 'Fewer joins than yesterday';
            statsJoinsTrend.classList.add('down');
        } else {
            statsJoinsTrend.textContent = 'Same joins as yesterday';
            statsJoinsTrend.classList.add('neutral');
        }
    }

    const newPlayerDelta = Number(overview.new_player_delta_vs_yesterday || 0);
    if (statsNewPlayersDelta) statsNewPlayersDelta.textContent = newPlayerDelta > 0 ? `+${newPlayerDelta}` : `${newPlayerDelta}`;
    if (statsNewPlayersToday) statsNewPlayersToday.textContent = String(overview.new_players_today ?? 0);
    if (statsNewPlayersYesterday) statsNewPlayersYesterday.textContent = String(overview.new_players_yesterday ?? 0);
    if (statsNewPlayersTrend) {
        statsNewPlayersTrend.classList.remove('up', 'down', 'neutral');
        const newTrend = overview.new_player_trend || 'equal';
        if (newTrend === 'up') {
            statsNewPlayersTrend.textContent = 'More new players than yesterday';
            statsNewPlayersTrend.classList.add('up');
        } else if (newTrend === 'down') {
            statsNewPlayersTrend.textContent = 'Fewer new players than yesterday';
            statsNewPlayersTrend.classList.add('down');
        } else {
            statsNewPlayersTrend.textContent = 'Same new players as yesterday';
            statsNewPlayersTrend.classList.add('neutral');
        }
    }

    setUpdatedLabel();
}

function renderChart(data) {
    if (!statsCanvas) return;
    const chartData = {
        labels: data.labels,
        datasets: [
            {
                label: 'Joins',
                data: data.joins,
                borderColor: '#22c55e',
                backgroundColor: 'rgba(34, 197, 94, 0.15)',
                tension: 0.25,
                fill: true
            },
            {
                label: 'Leaves',
                data: data.leaves,
                borderColor: '#f97316',
                backgroundColor: 'rgba(249, 115, 22, 0.12)',
                tension: 0.25,
                fill: true
            },
            {
                label: 'Chat',
                data: data.chats,
                borderColor: '#60a5fa',
                backgroundColor: 'rgba(96, 165, 250, 0.12)',
                tension: 0.25,
                fill: true
            }
        ]
    };

    if (statsChart) {
        statsChart.data = chartData;
        statsChart.update();
        return;
    }

    statsChart = new Chart(statsCanvas, {
        type: 'line',
        data: chartData,
        options: {
            responsive: true,
            maintainAspectRatio: false,
            plugins: {
                legend: {
                    labels: {
                        color: '#e2e8f0'
                    }
                }
            },
            scales: {
                x: {
                    grid: {
                        color: 'rgba(148, 163, 184, 0.12)'
                    },
                    ticks: {
                        color: '#94a3b8',
                        maxTicksLimit: 12
                    }
                },
                y: {
                    grid: {
                        color: 'rgba(148, 163, 184, 0.12)'
                    },
                    ticks: {
                        color: '#94a3b8'
                    }
                }
            }
        }
    });
}

async function fetchStats() {
    try {
        const response = await fetch(`/api/server/${SERVER_ID}/gotale/stats?days=${currentRange}`);
        if (!response.ok) return;
        const data = await response.json();
        if (!data.success) return;
        updateTotals(data);
        renderChart(data);
    } catch (error) {
        console.warn('Stats fetch failed', error);
    }
}

function setActiveRange(button) {
    if (!statsRangeToggle) return;
    statsRangeToggle.querySelectorAll('.range-btn').forEach((btn) => {
        btn.classList.toggle('active', btn === button);
    });
}

if (statsRangeToggle) {
    statsRangeToggle.addEventListener('click', (event) => {
        const target = event.target.closest('.range-btn');
        if (!target) return;
        const range = Number(target.dataset.range || 7);
        currentRange = Number.isNaN(range) ? 7 : range;
        setActiveRange(target);
        fetchStats();
    });
}

if (statsRefresh) {
    statsRefresh.addEventListener('click', () => {
        fetchStats();
    });
}

fetchStats();
setInterval(fetchStats, 15000);
