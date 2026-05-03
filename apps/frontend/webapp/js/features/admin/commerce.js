(function () {
    function createAdminCommerceFeature(deps) {
        var _deps = deps || {};
        var tariffCounter = 0;
        var ttCounter = 0;

        function escapeHtml(value) {
            return String(value == null ? '' : value)
                .replace(/&/g, '&amp;')
                .replace(/</g, '&lt;')
                .replace(/>/g, '&gt;')
                .replace(/"/g, '&quot;')
                .replace(/'/g, '&#039;');
        }

        function normalizeTariffList(raw) {
            var list = Array.isArray(raw) ? raw : [];
            var out = [];
            var used = {};
            list.forEach(function (item) {
                if (!item || typeof item !== 'object') return;
                var period = String(item.period || '').trim().toLowerCase();
                if (!period || used[period]) return;
                used[period] = true;
                var title = String(item.title || '').trim() || period;
                var days = parseInt(item.days, 10);
                var price = parseInt(item.price, 10);
                var badge = String(item.badge || '').trim().toLowerCase();
                if (badge !== 'best' && badge !== 'hit') badge = '';
                if (isNaN(days) || days < 1) days = 30;
                if (isNaN(price) || price < 1) price = 150;
                out.push({
                    period: period,
                    title: title,
                    days: days,
                    price: price,
                    badge: badge
                });
            });
            out.sort(function (a, b) { return a.days - b.days; });
            return out;
        }

        function fallbackTariffsFromLegacy(data) {
            return normalizeTariffList([
                { period: 'month', title: '1 месяц', days: 30, price: data && data.price_month != null ? data.price_month : 150, badge: '' },
                { period: '3month', title: '3 месяца', days: 90, price: data && data.price_3month != null ? data.price_3month : 350, badge: 'best' }
            ]);
        }

        function createTariffRowHtml(tariff, canRemove) {
            var key = 'tariff_' + (tariffCounter++);
            var badge = String(tariff.badge || '').trim().toLowerCase();
            if (badge !== 'best' && badge !== 'hit') badge = '';
            var sid = key.replace(/[^a-zA-Z0-9_-]/g, '_');
            return [
                '<div class="admin-commerce-tariff-row" data-row-key="', key, '">',
                '<div class="admin-commerce-tariff-fields">',
                '<div class="form-group admin-commerce-field">',
                '<label for="', sid, '_period">Ключ периода</label>',
                '<input id="', sid, '_period" type="text" class="admin-commerce-tariff-period" value="', escapeHtml(tariff.period), '" ',
                'maxlength="32" required placeholder="month, 6month…" spellcheck="false" autocomplete="off">',
                '</div>',
                '<div class="form-group admin-commerce-field">',
                '<label for="', sid, '_title">Название в приложении</label>',
                '<input id="', sid, '_title" type="text" class="admin-commerce-tariff-title" value="', escapeHtml(tariff.title), '" ',
                'maxlength="60" required placeholder="Например: 6 месяцев">',
                '</div>',
                '<div class="form-group admin-commerce-field">',
                '<label for="', sid, '_days">Срок (дней)</label>',
                '<input id="', sid, '_days" type="number" class="admin-commerce-tariff-days" min="1" max="3650" step="1" value="', escapeHtml(tariff.days), '" required inputmode="numeric">',
                '</div>',
                '<div class="form-group admin-commerce-field">',
                '<label for="', sid, '_price">Цена (₽)</label>',
                '<input id="', sid, '_price" type="number" class="admin-commerce-tariff-price" min="1" max="2000000" step="1" value="', escapeHtml(tariff.price), '" required inputmode="numeric">',
                '</div>',
                '<div class="form-group admin-commerce-field">',
                '<label for="', sid, '_badge">Бейдж</label>',
                '<select id="', sid, '_badge" class="admin-commerce-tariff-badge">',
                '<option value=""', badge === '' ? ' selected' : '', '>Без бейджа</option>',
                '<option value="best"', badge === 'best' ? ' selected' : '', '>Выгодно</option>',
                '<option value="hit"', badge === 'hit' ? ' selected' : '', '>Хит</option>',
                '</select>',
                '</div>',
                '</div>',
                '<div class="admin-commerce-tariff-actions">',
                canRemove ? '<button type="button" class="btn-secondary admin-commerce-remove-tariff">Удалить тариф</button>' : '<span class="hint admin-commerce-tariff-hint">Нужен минимум один тариф</span>',
                '</div>',
                '</div>'
            ].join('');
        }

        function renderTariffEditor(tariffs) {
            var container = document.getElementById('admin-commerce-tariffs');
            if (!container) return;
            var rows = Array.isArray(tariffs) && tariffs.length ? tariffs : fallbackTariffsFromLegacy({});
            container.innerHTML = rows.map(function (tariff, idx) {
                return createTariffRowHtml(tariff, rows.length > 1 && idx > 0);
            }).join('');
        }

        function normalizeTrafficTopupList(raw) {
            var list = Array.isArray(raw) ? raw : [];
            var out = [];
            var used = {};
            list.forEach(function (item) {
                if (!item || typeof item !== 'object') return;
                var pid = String(item.id || '').trim().toLowerCase();
                if (!pid || used[pid]) return;
                used[pid] = true;
                var title = String(item.title || '').trim() || pid;
                var gib = parseFloat(item.gib);
                var price = parseInt(item.price, 10);
                var badge = String(item.badge || '').trim().toLowerCase();
                if (badge !== 'best' && badge !== 'hit') badge = '';
                var enabled = item.enabled !== false && item.enabled !== 0 && item.enabled !== '0';
                var sortOrder = parseInt(item.sort_order, 10);
                if (isNaN(gib) || gib < 0.001) gib = 1;
                if (isNaN(price) || price < 1) price = 50;
                if (isNaN(sortOrder)) sortOrder = 0;
                out.push({
                    id: pid,
                    title: title,
                    gib: gib,
                    price: price,
                    badge: badge,
                    enabled: !!enabled,
                    sort_order: sortOrder
                });
            });
            out.sort(function (a, b) {
                if (a.sort_order !== b.sort_order) return a.sort_order - b.sort_order;
                return String(a.id).localeCompare(String(b.id));
            });
            return out;
        }

        function createTrafficTopupRowHtml(pkg, canRemove) {
            var key = 'tt_' + (ttCounter++);
            var sid = key.replace(/[^a-zA-Z0-9_-]/g, '_');
            var badge = String(pkg.badge || '').trim().toLowerCase();
            if (badge !== 'best' && badge !== 'hit') badge = '';
            var enabled = pkg.enabled !== false && pkg.enabled !== 0 && pkg.enabled !== '0';
            return [
                '<div class="admin-commerce-tariff-row admin-commerce-topup-row" data-row-key="', key, '">',
                '<div class="admin-commerce-tariff-fields">',
                '<div class="form-group admin-commerce-field">',
                '<label for="', sid, '_id">Ключ пакета</label>',
                '<input id="', sid, '_id" type="text" class="admin-commerce-topup-id" value="', escapeHtml(pkg.id), '" ',
                'maxlength="40" required placeholder="topup_50gb" spellcheck="false" autocomplete="off">',
                '</div>',
                '<div class="form-group admin-commerce-field">',
                '<label for="', sid, '_title">Название</label>',
                '<input id="', sid, '_title" type="text" class="admin-commerce-topup-title" value="', escapeHtml(pkg.title), '" ',
                'maxlength="80" required>',
                '</div>',
                '<div class="form-group admin-commerce-field">',
                '<label for="', sid, '_gib">ГиБ (двоичных)</label>',
                '<input id="', sid, '_gib" type="number" class="admin-commerce-topup-gib" min="0.001" max="4096" step="0.001" value="', escapeHtml(pkg.gib), '" required>',
                '</div>',
                '<div class="form-group admin-commerce-field">',
                '<label for="', sid, '_price">Цена (₽)</label>',
                '<input id="', sid, '_price" type="number" class="admin-commerce-topup-price" min="1" max="2000000" step="1" value="', escapeHtml(pkg.price), '" required>',
                '</div>',
                '<div class="form-group admin-commerce-field">',
                '<label for="', sid, '_badge">Бейдж</label>',
                '<select id="', sid, '_badge" class="admin-commerce-topup-badge">',
                '<option value=""', badge === '' ? ' selected' : '', '>Без бейджа</option>',
                '<option value="best"', badge === 'best' ? ' selected' : '', '>Выгодно</option>',
                '<option value="hit"', badge === 'hit' ? ' selected' : '', '>Хит</option>',
                '</select>',
                '</div>',
                '<div class="form-group admin-commerce-field">',
                '<label for="', sid, '_sort">Порядок</label>',
                '<input id="', sid, '_sort" type="number" class="admin-commerce-topup-sort" step="1" value="', escapeHtml(pkg.sort_order != null ? pkg.sort_order : 0), '">',
                '</div>',
                '<div class="form-group admin-commerce-field admin-commerce-field--toggle">',
                '<label><input type="checkbox" class="admin-commerce-topup-enabled"', enabled ? ' checked' : '', '> Включён</label>',
                '</div>',
                '</div>',
                '<div class="admin-commerce-tariff-actions">',
                canRemove ? '<button type="button" class="btn-secondary admin-commerce-remove-traffic-topup">Удалить пакет</button>' : '',
                '</div>',
                '</div>'
            ].join('');
        }

        function renderTrafficTopupEditor(packages) {
            var container = document.getElementById('admin-commerce-traffic-topups');
            if (!container) return;
            var rows = Array.isArray(packages) ? normalizeTrafficTopupList(packages) : [];
            if (!rows.length) {
                container.innerHTML = '<p class="hint">Пакетов нет — пользователи не увидят докупку трафика.</p>';
                return;
            }
            container.innerHTML = rows.map(function (pkg) {
                return createTrafficTopupRowHtml(pkg, rows.length > 1);
            }).join('');
        }

        function bindTrafficTopupEditorActions() {
            var addBtn = document.getElementById('admin-commerce-add-traffic-topup');
            var container = document.getElementById('admin-commerce-traffic-topups');
            if (addBtn && !addBtn._ttAddBound) {
                addBtn._ttAddBound = true;
                addBtn.addEventListener('click', function () {
                    var hint = container && container.querySelector('.hint');
                    if (hint) hint.remove();
                    var html = createTrafficTopupRowHtml({
                        id: 'topup_' + Math.floor(Math.random() * 9000 + 1000),
                        title: 'Докупка',
                        gib: 10,
                        price: 100,
                        badge: '',
                        enabled: true,
                        sort_order: 0
                    }, true);
                    if (container) container.insertAdjacentHTML('beforeend', html);
                });
            }
            if (container && !container._ttRemoveBound) {
                container._ttRemoveBound = true;
                container.addEventListener('click', function (event) {
                    var btn = event.target && event.target.closest ? event.target.closest('.admin-commerce-remove-traffic-topup') : null;
                    if (!btn) return;
                    var row = btn.closest('.admin-commerce-topup-row');
                    if (!row) return;
                    row.remove();
                    if (container && !container.querySelector('.admin-commerce-topup-row')) {
                        container.innerHTML = '<p class="hint">Пакетов нет — пользователи не увидят докупку трафика.</p>';
                    }
                });
            }
        }

        function collectTrafficTopupsFromForm() {
            var container = document.getElementById('admin-commerce-traffic-topups');
            var rows = container ? container.querySelectorAll('.admin-commerce-topup-row') : [];
            var packages = [];
            var usedIds = {};
            for (var i = 0; i < rows.length; i++) {
                var row = rows[i];
                var pid = String(row.querySelector('.admin-commerce-topup-id').value || '').trim().toLowerCase();
                var title = String(row.querySelector('.admin-commerce-topup-title').value || '').trim();
                var gib = parseFloat(row.querySelector('.admin-commerce-topup-gib').value);
                var price = parseInt(row.querySelector('.admin-commerce-topup-price').value, 10);
                var badge = String((row.querySelector('.admin-commerce-topup-badge') || {}).value || '').trim().toLowerCase();
                if (badge !== 'best' && badge !== 'hit') badge = '';
                var sortEl = row.querySelector('.admin-commerce-topup-sort');
                var sortOrder = sortEl ? parseInt(sortEl.value, 10) : 0;
                var enabledCb = row.querySelector('.admin-commerce-topup-enabled');
                var enabled = !!(enabledCb && enabledCb.checked);
                if (!/^[a-z0-9_-]{2,40}$/.test(pid)) throw new Error('Ключ пакета докупки: только a-z, 0-9, _, - (2-40 символов)');
                if (usedIds[pid]) throw new Error('Ключ пакета "' + pid + '" дублируется');
                usedIds[pid] = true;
                if (!title) throw new Error('Название пакета докупки обязательно');
                if (isNaN(gib) || gib < 0.001 || gib > 4096) throw new Error('Обём пакета: от 0.001 до 4096 ГиБ');
                if (isNaN(price) || price < 1 || price > 2000000) throw new Error('Цена пакета вне допустимого диапазона');
                if (isNaN(sortOrder)) sortOrder = 0;
                packages.push({
                    id: pid,
                    title: title,
                    gib: gib,
                    price: price,
                    badge: badge,
                    enabled: enabled,
                    sort_order: sortOrder
                });
            }
            packages.sort(function (a, b) {
                if (a.sort_order !== b.sort_order) return a.sort_order - b.sort_order;
                return String(a.id).localeCompare(String(b.id));
            });
            return packages;
        }

        function bindTariffEditorActions() {
            var addBtn = document.getElementById('admin-commerce-add-tariff');
            var container = document.getElementById('admin-commerce-tariffs');
            if (addBtn && !addBtn._commerceAddBound) {
                addBtn._commerceAddBound = true;
                addBtn.addEventListener('click', function () {
                    var currentRows = container ? container.querySelectorAll('.admin-commerce-tariff-row').length : 0;
                    var html = createTariffRowHtml({
                        period: 'custom_' + (currentRows + 1),
                        title: 'Новый тариф',
                        days: 30,
                        price: 150,
                        badge: ''
                    }, true);
                    if (container) container.insertAdjacentHTML('beforeend', html);
                });
            }
            if (container && !container._commerceRemoveBound) {
                container._commerceRemoveBound = true;
                container.addEventListener('click', function (event) {
                    var btn = event.target && event.target.closest ? event.target.closest('.admin-commerce-remove-tariff') : null;
                    if (!btn) return;
                    var row = btn.closest('.admin-commerce-tariff-row');
                    if (!row) return;
                    var rowsCount = container.querySelectorAll('.admin-commerce-tariff-row').length;
                    if (rowsCount <= 1) return;
                    row.remove();
                });
            }
        }

        function collectTariffsFromForm() {
            var container = document.getElementById('admin-commerce-tariffs');
            var rows = container ? container.querySelectorAll('.admin-commerce-tariff-row') : [];
            var tariffs = [];
            var usedPeriods = {};
            for (var i = 0; i < rows.length; i++) {
                var row = rows[i];
                var period = String(row.querySelector('.admin-commerce-tariff-period').value || '').trim().toLowerCase();
                var title = String(row.querySelector('.admin-commerce-tariff-title').value || '').trim();
                var days = parseInt(row.querySelector('.admin-commerce-tariff-days').value, 10);
                var price = parseInt(row.querySelector('.admin-commerce-tariff-price').value, 10);
                var badge = String((row.querySelector('.admin-commerce-tariff-badge') || {}).value || '').trim().toLowerCase();
                if (badge !== 'best' && badge !== 'hit') badge = '';
                if (!/^[a-z0-9_-]{2,32}$/.test(period)) throw new Error('Ключ периода: только a-z, 0-9, _, - (2-32 символа)');
                if (usedPeriods[period]) throw new Error('Ключ периода "' + period + '" дублируется');
                usedPeriods[period] = true;
                if (!title) throw new Error('Название тарифа обязательно');
                if (isNaN(days) || days < 1 || days > 3650) throw new Error('Срок тарифа: от 1 до 3650 дней');
                if (isNaN(price) || price < 1 || price > 2000000) throw new Error('Цена тарифа вне допустимого диапазона');
                tariffs.push({ period: period, title: title, days: days, price: price, badge: badge });
            }
            if (!tariffs.length) throw new Error('Добавьте хотя бы один тариф');
            tariffs.sort(function (a, b) { return a.days - b.days; });
            return tariffs;
        }

        async function loadAdminCommercePage() {
            var loadingEl = document.getElementById('admin-commerce-loading');
            var formEl = document.getElementById('admin-commerce-form');
            var errEl = document.getElementById('admin-commerce-error');
            var msgEl = document.getElementById('admin-commerce-form-message');
            if (msgEl) {
                msgEl.style.display = 'none';
                msgEl.textContent = '';
                msgEl.className = 'form-message';
            }
            if (errEl) {
                errEl.style.display = 'none';
                errEl.textContent = '';
            }
            if (loadingEl) loadingEl.style.display = 'block';
            if (formEl) formEl.style.display = 'none';
            try {
                var res = await _deps.apiFetch('/api/admin/commerce', { method: 'GET', headers: { 'Content-Type': 'application/json' } });
                var data = await window.DarallaApiClient.responseJson(res);
                if (!res.ok || !data.success) throw new Error(data.error || 'Не удалось загрузить настройки');
                var dl = document.getElementById('admin-commerce-device-limit');
                var tariffs = normalizeTariffList(data.tariffs);
                if (!tariffs.length) tariffs = fallbackTariffsFromLegacy(data);
                renderTariffEditor(tariffs);
                bindTariffEditorActions();
                var ttList = normalizeTrafficTopupList(data.traffic_topup_packages || []);
                renderTrafficTopupEditor(ttList);
                bindTrafficTopupEditorActions();
                if (dl) dl.value = String(data.default_device_limit != null ? data.default_device_limit : 1);
            } catch (e) {
                console.error('loadAdminCommercePage', e);
                if (errEl) {
                    errEl.textContent = e.message || String(e);
                    errEl.style.display = 'block';
                }
            } finally {
                if (loadingEl) loadingEl.style.display = 'none';
                if (formEl) formEl.style.display = 'block';
            }
        }

        async function saveAdminCommerce(event) {
            event.preventDefault();
            var dl = parseInt(document.getElementById('admin-commerce-device-limit').value, 10);
            var msgEl = document.getElementById('admin-commerce-form-message');
            if (msgEl) {
                msgEl.style.display = 'none';
                msgEl.textContent = '';
            }
            if (isNaN(dl)) {
                if (msgEl) {
                    msgEl.className = 'form-message form-message--error';
                    msgEl.textContent = 'Введите корректный лимит устройств';
                    msgEl.style.display = 'block';
                }
                return;
            }
            try {
                var tariffs = collectTariffsFromForm();
                var trafficTopups = collectTrafficTopupsFromForm();
                var res = await _deps.apiFetch('/api/admin/commerce', {
                    method: 'POST',
                    headers: { 'Content-Type': 'application/json' },
                    body: JSON.stringify({
                        tariffs: tariffs,
                        traffic_topup_packages: trafficTopups,
                        default_device_limit: dl
                    })
                });
                var data = await window.DarallaApiClient.responseJson(res);
                if (!res.ok || !data.success) throw new Error(data.error || 'Ошибка сохранения');
                var normalized = normalizeTariffList(data.tariffs);
                if (normalized.length) renderTariffEditor(normalized);
                renderTrafficTopupEditor(normalizeTrafficTopupList(data.traffic_topup_packages || []));
                bindTrafficTopupEditorActions();
                if (msgEl) {
                    msgEl.className = 'form-message form-message--success';
                    msgEl.textContent = 'Сохранено. Тарифы, пакеты докупки и лимит устройств применены.';
                    msgEl.style.display = 'block';
                }
                _deps.loadPrices();
            } catch (e) {
                console.error('saveAdminCommerce', e);
                if (msgEl) {
                    msgEl.className = 'form-message form-message--error';
                    msgEl.textContent = e.message || String(e);
                    msgEl.style.display = 'block';
                }
            }
        }

        return {
            loadAdminCommercePage: loadAdminCommercePage,
            saveAdminCommerce: saveAdminCommerce
        };
    }

    window.DarallaAdminCommerceFeature = window.DarallaAdminCommerceFeature || {};
    window.DarallaAdminCommerceFeature.create = createAdminCommerceFeature;
})();
