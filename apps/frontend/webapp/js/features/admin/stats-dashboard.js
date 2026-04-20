(function () {
    function createAdminStatsDashboardFeature(deps) {
        var _deps = deps || {};

        function formatRub(v) {
            return Math.round(v).toLocaleString('ru-RU') + ' ₽';
        }

        function renderRevenueChart(data) {
            var ctx = document.getElementById('dash-revenue-chart');
            if (!ctx) return;

            var chart = _deps.getDashRevenueChart();
            if (chart) {
                chart.destroy();
                _deps.setDashRevenueChart(null);
            }

            var labels = data.map(function (d) {
                var parts = d.date.split('-');
                return parts[2] + '.' + parts[1];
            });
            var values = data.map(function (d) { return d.revenue || 0; });
            var isDark = document.body.classList.contains('dark')
                || getComputedStyle(document.documentElement).getPropertyValue('--bg-primary').trim().startsWith('#1');

            _deps.setDashRevenueChart(new Chart(ctx, {
                type: 'bar',
                data: {
                    labels: labels,
                    datasets: [{
                        data: values,
                        backgroundColor: isDark ? 'rgba(99,132,255,0.6)' : 'rgba(54,120,220,0.7)',
                        borderRadius: 4,
                        maxBarThickness: 18
                    }]
                },
                options: {
                    responsive: true,
                    maintainAspectRatio: false,
                    plugins: {
                        legend: { display: false },
                        tooltip: { callbacks: { label: function (c) { return formatRub(c.raw); } } }
                    },
                    scales: {
                        x: {
                            grid: { display: false },
                            ticks: {
                                maxRotation: 0,
                                autoSkip: true,
                                maxTicksLimit: 7,
                                color: isDark ? '#888' : '#666',
                                font: { size: 11 }
                            }
                        },
                        y: {
                            grid: { color: isDark ? 'rgba(255,255,255,0.06)' : 'rgba(0,0,0,0.06)' },
                            ticks: {
                                callback: function (v) { return v >= 1000 ? (v / 1000) + 'k' : v; },
                                color: isDark ? '#888' : '#666',
                                font: { size: 11 }
                            },
                            beginAtZero: true
                        }
                    }
                }
            }));
        }

        function renderGatewaySplit(gw) {
            var el = document.getElementById('dash-gateway-split');
            if (!el) return;
            var entries = Object.entries(gw);
            if (entries.length === 0) {
                el.textContent = '';
                return;
            }
            var total = entries.reduce(function (s, entry) { return s + entry[1]; }, 0);
            if (total === 0) {
                el.textContent = '';
                return;
            }
            var names = { yookassa: 'YooKassa', cryptocloud: 'CryptoCloud' };
            el.textContent = entries.map(function (entry) {
                var k = entry[0];
                var v = entry[1];
                var pct = Math.round(v / total * 100);
                return (names[k] || k) + ': ' + formatRub(v) + ' (' + pct + '%)';
            }).join('  ·  ');
        }

        async function loadDashboardServers() {
            var container = document.getElementById('dash-servers-load');
            if (!container) return;
            if (!container.querySelector('.server-load-card')) {
                container.innerHTML = '<p class="empty-hint">Загрузка нагрузки серверов…</p>';
            }
            try {
                var response = await _deps.apiFetch('/api/admin/charts/server-load', {
                    method: 'POST',
                    headers: { 'Content-Type': 'application/json' }
                });
                if (!response.ok) throw new Error('Ошибка загрузки данных');
                var result = await response.json();
                if (!result.success || !result.data) {
                    container.innerHTML = '<p class="empty-hint">Нет данных</p>';
                    return;
                }
                var serverData = result.data.servers || [];
                if (serverData.length === 0) {
                    container.innerHTML = '<p class="empty-hint">Нет данных о нагрузке</p>';
                    return;
                }
                var getLoadClass = function (p) { return p >= 80 ? 'high' : p >= 50 ? 'medium' : 'low'; };
                container.innerHTML = serverData.map(function (item) {
                    var pct = item.load_percentage != null ? item.load_percentage : 0;
                    var online = item.online_clients != null ? item.online_clients : 0;
                    var total = item.total_active != null ? item.total_active : 0;
                    var name = _deps.escapeHtml(item.display_name || item.server_name);
                    var cls = getLoadClass(pct);
                    var details = [];
                    if (total > 0) details.push(online + ' онлайн / ' + total + ' всего');
                    if (item.avg_online_24h != null || item.max_online_24h != null) {
                        var parts = [];
                        if (item.avg_online_24h != null) parts.push('среднее: ' + item.avg_online_24h);
                        if (item.max_online_24h != null) parts.push('пик: ' + item.max_online_24h);
                        if (parts.length) details.push(parts.join(' · '));
                    }
                    return '\n'
                        + '                <div class="server-load-card" title="' + (item.location ? 'Локация: ' + _deps.escapeHtml(item.location) : '') + '">\n'
                        + '                    <div class="server-load-card-header">\n'
                        + '                        <span class="server-load-card-name">' + name + '</span>\n'
                        + '                        <span class="server-load-card-percent ' + cls + '">' + Math.round(pct) + '%</span>\n'
                        + '                    </div>\n'
                        + '                    <div class="server-load-progress-track">\n'
                        + '                        <div class="server-load-progress-fill ' + cls + '" style="width: ' + Math.min(100, pct) + '%;"></div>\n'
                        + '                    </div>\n'
                        + (details.length ? ('<div class="server-load-card-details">' + _deps.escapeHtml(details.join(' · ')) + '</div>') : '')
                        + '\n                </div>\n'
                        + '            ';
                }).join('');
            } catch (error) {
                console.error('Ошибка загрузки нагрузки серверов:', error);
                container.innerHTML = '<p class="error-text">Ошибка загрузки данных</p>';
            }
        }

        async function loadAdminStats() {
            var loadingEl = document.getElementById('admin-stats-loading');
            var dashboardEl = document.getElementById('admin-dashboard');
            if (loadingEl) loadingEl.style.display = 'block';
            if (dashboardEl) dashboardEl.style.display = 'none';

            try {
                var response = await _deps.apiFetch('/api/admin/stats', {
                    method: 'POST',
                    headers: { 'Content-Type': 'application/json' }
                });
                var result = await response.json();
                if (!result.success) throw new Error('API error');
                var s = result.stats;

                document.getElementById('dash-mrr').textContent = formatRub(s.mrr || 0);
                var mrrPct = s.mrr_change_percent || 0;
                var mrrTrendEl = document.getElementById('dash-mrr-trend');
                if (mrrPct > 0) {
                    mrrTrendEl.textContent = '+' + mrrPct.toFixed(1) + '%';
                    mrrTrendEl.className = 'dashboard-card-trend trend-up';
                } else if (mrrPct < 0) {
                    mrrTrendEl.textContent = mrrPct.toFixed(1) + '%';
                    mrrTrendEl.className = 'dashboard-card-trend trend-down';
                } else {
                    mrrTrendEl.textContent = '';
                }

                document.getElementById('dash-active-subs').textContent = s.subscriptions.active;
                document.getElementById('dash-users').textContent = s.users.total;
                var usersTrendEl = document.getElementById('dash-users-trend');
                if (s.users.new_30d > 0) {
                    usersTrendEl.textContent = '+' + s.users.new_30d + ' за 30д';
                    usersTrendEl.className = 'dashboard-card-trend trend-up';
                } else {
                    usersTrendEl.textContent = '';
                }
                document.getElementById('dash-conversion').textContent = (s.conversion_rate || 0) + '%';

                renderRevenueChart(s.daily_revenue || []);
                renderGatewaySplit(s.gateway_split || {});

                if (loadingEl) loadingEl.style.display = 'none';
                if (dashboardEl) dashboardEl.style.display = 'block';

                loadDashboardServers();
                var interval = _deps.getServerLoadChartInterval();
                if (interval) clearInterval(interval);
                _deps.setServerLoadChartInterval(setInterval(function () {
                    if (_deps.getCurrentPage() === 'admin-stats') loadDashboardServers();
                }, 2 * 60 * 1000));
            } catch (err) {
                console.error('Dashboard load error:', err);
                if (loadingEl) loadingEl.style.display = 'none';
                if (dashboardEl) dashboardEl.style.display = 'block';
            }
        }

        return {
            loadAdminStats: loadAdminStats,
            formatRub: formatRub,
            renderRevenueChart: renderRevenueChart,
            renderGatewaySplit: renderGatewaySplit,
            loadDashboardServers: loadDashboardServers
        };
    }

    window.DarallaAdminStatsDashboardFeature = window.DarallaAdminStatsDashboardFeature || {};
    window.DarallaAdminStatsDashboardFeature.create = createAdminStatsDashboardFeature;
})();
