(function () {
    function createAdminStatsDashboardFeature(deps) {
        var _deps = deps || {};

        var REVENUE_RANGE_STORAGE_KEY = 'daralla-admin-revenue-range-v1';
        var REV_PRESET_LABELS = {
            '7d': '7 дней',
            '14d': '14 дней',
            '30d': '30 дней',
            month: 'Этот месяц'
        };

        var revenueControlsInitialized = false;

        function safeParseStoredRange() {
            try {
                var raw = localStorage.getItem(REVENUE_RANGE_STORAGE_KEY);
                if (!raw) return null;
                var o = JSON.parse(raw);
                return o && typeof o === 'object' ? o : null;
            } catch (e) {
                return null;
            }
        }

        function normalizeStoredRange(o) {
            if (!o || typeof o !== 'object') return { preset: '30d' };
            var presets = { '7d': true, '14d': true, '30d': true, month: true, custom: true };
            var p = String(o.preset || '30d').toLowerCase();
            if (!presets[p]) p = '30d';
            if (p === 'custom') {
                var from = typeof o.from === 'string' ? o.from.slice(0, 10) : '';
                var to = typeof o.to === 'string' ? o.to.slice(0, 10) : '';
                if (!/^\d{4}-\d{2}-\d{2}$/.test(from) || !/^\d{4}-\d{2}-\d{2}$/.test(to)) return { preset: '30d' };
                return { preset: 'custom', from: from, to: to };
            }
            return { preset: p };
        }

        function persistRange(o) {
            try {
                localStorage.setItem(REVENUE_RANGE_STORAGE_KEY, JSON.stringify(normalizeStoredRange(o)));
            } catch (e) {}
        }

        function getRevenueRangeForApi() {
            var raw = safeParseStoredRange();
            return normalizeStoredRange(raw || { preset: '30d' });
        }

        function seedCustomDatesIfNeeded() {
            var fromEl = document.getElementById('dash-revenue-from');
            var toEl = document.getElementById('dash-revenue-to');
            if (!fromEl || !toEl) return;
            if (!fromEl.value || !toEl.value) {
                var now = new Date();
                var y = now.getFullYear();
                var m = String(now.getMonth() + 1).padStart(2, '0');
                var day = String(now.getDate()).padStart(2, '0');
                var toStr = y + '-' + m + '-' + day;
                var from = new Date(now.getTime());
                from.setDate(from.getDate() - 29);
                var fy = from.getFullYear();
                var fm = String(from.getMonth() + 1).padStart(2, '0');
                var fd = String(from.getDate()).padStart(2, '0');
                fromEl.value = fy + '-' + fm + '-' + fd;
                toEl.value = toStr;
            }
        }

        function syncRevenuePresetUi() {
            var r = getRevenueRangeForApi();
            document.querySelectorAll('[data-dash-revenue-preset]').forEach(function (btn) {
                var pr = btn.getAttribute('data-dash-revenue-preset');
                btn.classList.toggle('dashboard-revenue-preset--active', pr === r.preset);
            });
            var selectEl = document.getElementById('dash-revenue-preset-select');
            if (selectEl) selectEl.value = r.preset;
            var row = document.getElementById('dash-revenue-custom-row');
            if (row) {
                if (r.preset === 'custom') {
                    row.hidden = false;
                    var fe = document.getElementById('dash-revenue-from');
                    var te = document.getElementById('dash-revenue-to');
                    if (fe && r.from) fe.value = r.from;
                    if (te && r.to) te.value = r.to;
                } else {
                    row.hidden = true;
                }
            }
        }

        function fmtRuShort(iso) {
            if (!iso || iso.length < 10) return iso || '';
            var d = new Date(iso.slice(0, 10) + 'T12:00:00Z');
            if (isNaN(d.getTime())) return iso;
            var opts = { day: 'numeric', month: 'short' };
            var cy = new Date().getFullYear();
            if (d.getUTCFullYear() !== cy) opts.year = 'numeric';
            return d.toLocaleDateString('ru-RU', opts);
        }

        function updateRevenueHeadingFromStats(stats) {
            var el = document.getElementById('dash-revenue-chart-heading');
            if (!el) return;
            if (!stats || !stats.revenue_range) {
                el.textContent = 'Выручка';
                return;
            }
            var rr = stats.revenue_range;
            var label = 'Выручка';
            if (rr.preset === 'custom') {
                el.textContent = label + ' · ' + fmtRuShort(rr.from) + ' — ' + fmtRuShort(rr.to);
            } else {
                var cap = REV_PRESET_LABELS[rr.preset] || 'за период';
                el.textContent = label + ' · ' + cap;
            }
        }

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

            var tickCap = labels.length <= 14 ? 14 : labels.length <= 31 ? 10 : 8;

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
                                maxTicksLimit: tickCap,
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
            var names = { yookassa: 'YooKassa', cryptocloud: 'CryptoCloud', platega: 'Platega' };
            el.textContent = entries.map(function (entry) {
                var k = entry[0];
                var v = entry[1];
                var pct = Math.round(v / total * 100);
                return (names[k] || k) + ': ' + formatRub(v) + ' (' + pct + '%)';
            }).join('  ·  ');
        }

        function applyDashboardPayload(result) {
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

            if (s.revenue_range && s.revenue_range.preset === 'custom') {
                persistRange({
                    preset: 'custom',
                    from: s.revenue_range.from,
                    to: s.revenue_range.to
                });
            }

            updateRevenueHeadingFromStats(s);
            renderRevenueChart(s.daily_revenue || []);
            renderGatewaySplit(s.gateway_split || {});
            syncRevenuePresetUi();
        }

        async function loadAdminStats(opts) {
            opts = opts || {};
            var quiet = !!opts.quiet;

            initDashboardRevenueControls();
            if (!safeParseStoredRange()) persistRange({ preset: '30d' });
            syncRevenuePresetUi();

            var loadingEl = document.getElementById('admin-stats-loading');
            var dashboardEl = document.getElementById('admin-dashboard');

            if (!quiet) {
                if (loadingEl) loadingEl.style.display = 'block';
                if (dashboardEl) dashboardEl.style.display = 'none';
            }

            try {
                var range = getRevenueRangeForApi();
                var response = await _deps.apiFetch('/api/admin/stats', {
                    method: 'POST',
                    headers: { 'Content-Type': 'application/json' },
                    body: JSON.stringify({ revenue_range: range })
                });
                var result = await response.json();
                if (!result.success) throw new Error('API error');

                applyDashboardPayload(result);

                if (!quiet) {
                    if (loadingEl) loadingEl.style.display = 'none';
                    if (dashboardEl) dashboardEl.style.display = 'block';
                    loadDashboardServers();
                    var interval = _deps.getServerLoadChartInterval();
                    if (interval) clearInterval(interval);
                    _deps.setServerLoadChartInterval(setInterval(function () {
                        if (_deps.getCurrentPage() === 'admin-stats') loadDashboardServers();
                    }, 2 * 60 * 1000));
                }
            } catch (err) {
                console.error('Dashboard load error:', err);
                if (!quiet) {
                    if (loadingEl) loadingEl.style.display = 'none';
                    if (dashboardEl) dashboardEl.style.display = 'block';
                }
            }
        }

        function initDashboardRevenueControls() {
            if (revenueControlsInitialized) return;
            var presetsEl = document.querySelector('.dashboard-revenue-presets');
            var selectEl = document.getElementById('dash-revenue-preset-select');
            if (!presetsEl && !selectEl) return;
            revenueControlsInitialized = true;

            function applyPresetSelection(preset) {
                if (!preset) return;
                if (preset === 'custom') {
                    seedCustomDatesIfNeeded();
                    var fromEl = document.getElementById('dash-revenue-from');
                    var toEl = document.getElementById('dash-revenue-to');
                    persistRange({
                        preset: 'custom',
                        from: fromEl ? fromEl.value.slice(0, 10) : '',
                        to: toEl ? toEl.value.slice(0, 10) : ''
                    });
                } else {
                    persistRange({ preset: preset });
                }
                syncRevenuePresetUi();
                loadAdminStats({ quiet: true });
            }

            if (presetsEl) {
                presetsEl.addEventListener('click', function (e) {
                    var btn = e.target.closest('[data-dash-revenue-preset]');
                    if (!btn) return;
                    applyPresetSelection(btn.getAttribute('data-dash-revenue-preset'));
                });
            }

            if (selectEl) {
                selectEl.addEventListener('change', function () {
                    applyPresetSelection(selectEl.value);
                });
            }

            var applyBtn = document.getElementById('dash-revenue-apply-custom');
            if (applyBtn) {
                applyBtn.addEventListener('click', function () {
                    var fromEl = document.getElementById('dash-revenue-from');
                    var toEl = document.getElementById('dash-revenue-to');
                    if (!fromEl || !toEl || !fromEl.value || !toEl.value) return;
                    persistRange({
                        preset: 'custom',
                        from: fromEl.value.slice(0, 10),
                        to: toEl.value.slice(0, 10)
                    });
                    syncRevenuePresetUi();
                    loadAdminStats({ quiet: true });
                });
            }
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
