(function () {
    function createAdminSubscriptionEditFeature(deps) {
        var _deps = deps || {};
        var _currentBucketSnapshot = null;
        var _trafficCreateFormBound = false;
        var _GIB = Math.pow(1024, 3);

        function _bytesFromGib(gib) {
            var g = parseFloat(gib);
            if (isNaN(g) || g < 0) return 0;
            return Math.round(g * _GIB);
        }

        function _gibFromBytes(bytes) {
            var b = Number(bytes) || 0;
            if (b <= 0) return '';
            var g = b / _GIB;
            return (Math.round(g * 1000) / 1000).toString();
        }

        function _ensureTrafficCreateFormBinding() {
            if (_trafficCreateFormBound) return;
            var u = document.getElementById('new-bucket-unlimited');
            var lim = document.getElementById('new-bucket-limit-gib');
            if (!u || !lim) return;
            _trafficCreateFormBound = true;
            function sync() {
                lim.disabled = !!u.checked;
            }
            u.addEventListener('change', sync);
            sync();
        }

        async function showAdminSubscriptionEdit(subId) {
            try {
                if (_deps.getCurrentPage() === 'admin-subscriptions') {
                    _deps.setPreviousAdminPage('admin-subscriptions');
                } else {
                    _deps.setPreviousAdminPage('admin-user-detail');
                }
                _deps.setCurrentEditingSubscriptionId(subId);
                _deps.showPage('admin-subscription-edit', { id: String(subId) });

                document.getElementById('admin-subscription-edit-loading').style.display = 'block';
                document.getElementById('admin-subscription-edit-content').style.display = 'none';

                var response = await _deps.apiFetch('/api/admin/subscription/' + subId, {
                    method: 'POST',
                    headers: { 'Content-Type': 'application/json' }
                });
                if (!response.ok) throw new Error('Ошибка загрузки подписки');

                var data = await response.json();
                var sub = data.subscription;
                var servers = data.servers || [];

                _deps.setOriginalSubscriptionData({
                    name: sub.name || '',
                    device_limit: sub.device_limit || 1,
                    status: sub.status || 'active',
                    expires_at: sub.expires_at
                });
                _deps.setCurrentSubscriptionServers(servers);

                document.getElementById('admin-subscription-edit-loading').style.display = 'none';
                document.getElementById('admin-subscription-edit-content').style.display = 'block';

                var form = document.getElementById('admin-subscription-edit-form');
                if (form) {
                    var submitBtn = form.querySelector('button[type="submit"]');
                    if (submitBtn) {
                        submitBtn.disabled = false;
                        submitBtn.textContent = 'Сохранить';
                    }
                }

                document.getElementById('sub-name').value = sub.name || '';
                document.getElementById('sub-device-limit').value = sub.device_limit || 1;

                var statusDisplayGroup = document.getElementById('sub-status-display-group');
                var statusDisplay = document.getElementById('sub-status-display');
                var statusHint = document.getElementById('sub-status-hint');
                var statusNames = { active: 'Активна', expired: 'Истекла', deleted: 'Удалена' };
                var currentStatusName = statusNames[sub.status] || sub.status;
                if (sub.status === 'deleted') {
                    statusDisplay.textContent = 'Текущий статус: ' + currentStatusName;
                    statusDisplay.className = 'sub-status-display sub-status-expired';
                    statusHint.textContent = 'Финальный статус, нельзя изменить';
                    statusDisplayGroup.style.display = 'block';
                } else {
                    statusDisplay.textContent = 'Текущий статус: ' + currentStatusName;
                    var isSubActive = sub.status === 'active' || (sub.status === 'trial' && sub.expires_at && new Date(sub.expires_at * 1000) > new Date());
                    statusDisplay.className = 'sub-status-display ' + (isSubActive ? 'sub-status-active' : 'sub-status-expired');
                    statusHint.textContent = 'Управляется автоматически через дату истечения';
                    statusDisplayGroup.style.display = 'block';
                }

                var expiresDate = new Date(sub.expires_at * 1000);
                var year = expiresDate.getFullYear();
                var month = String(expiresDate.getMonth() + 1).padStart(2, '0');
                var day = String(expiresDate.getDate()).padStart(2, '0');
                var hours = String(expiresDate.getHours()).padStart(2, '0');
                var minutes = String(expiresDate.getMinutes()).padStart(2, '0');
                document.getElementById('sub-expires-at').value = year + '-' + month + '-' + day + 'T' + hours + ':' + minutes;

                loadSubscriptionKeys(servers);
                await loadTrafficBuckets();
                _ensureTrafficCreateFormBinding();
            } catch (error) {
                console.error('Ошибка загрузки подписки:', error);
                document.getElementById('admin-subscription-edit-loading').style.display = 'none';
                await _deps.appShowAlert('Не удалось загрузить подписку.', { title: 'Ошибка', variant: 'error' });
            }
        }

        async function saveSubscriptionChanges(event) {
            event.preventDefault();

            var currentEditingSubscriptionId = _deps.getCurrentEditingSubscriptionId();
            var originalSubscriptionData = _deps.getOriginalSubscriptionData();
            if (!currentEditingSubscriptionId || !originalSubscriptionData) {
                await _deps.appShowAlert('Данные подписки не загружены.', { title: 'Ошибка', variant: 'error' });
                return;
            }

            var form = event.target;
            var newData = {
                name: form.name.value,
                device_limit: parseInt(form.device_limit.value, 10),
                expires_at: Math.floor(new Date(form.expires_at.value).getTime() / 1000)
            };

            var changes = [];
            if (newData.name !== originalSubscriptionData.name) {
                changes.push({
                    field: 'Название',
                    old: originalSubscriptionData.name || '(не указано)',
                    new: newData.name || '(не указано)'
                });
            }
            if (newData.device_limit !== originalSubscriptionData.device_limit) {
                changes.push({
                    field: 'Лимит устройств',
                    old: originalSubscriptionData.device_limit,
                    new: newData.device_limit
                });
            }
            if (newData.expires_at !== originalSubscriptionData.expires_at) {
                var oldDate = new Date(originalSubscriptionData.expires_at * 1000).toLocaleString('ru-RU');
                var newDate = new Date(newData.expires_at * 1000).toLocaleString('ru-RU');
                changes.push({ field: 'Дата истечения', old: oldDate, new: newDate });
            }

            if (changes.length > 0) {
                window.pendingSubscriptionUpdate = newData;
                var changesList = document.getElementById('subscription-changes-list');
                changesList.innerHTML = changes.map(function (change) {
                    return '\n'
                        + '            <div class="subscription-change-item">\n'
                        + '                <div class="subscription-change-field">' + _deps.escapeHtml(change.field) + '</div>\n'
                        + '                <div class="subscription-change-old">Было: ' + _deps.escapeHtml(String(change.old)) + '</div>\n'
                        + '                <div class="subscription-change-new">Станет: ' + _deps.escapeHtml(String(change.new)) + '</div>\n'
                        + '            </div>\n'
                        + '        ';
                }).join('');
                document.getElementById('subscription-confirm-modal').style.display = 'flex';
            } else {
                await _deps.appShowAlert('Нет изменений для сохранения.', { title: 'Сообщение' });
            }
        }

        function closeSubscriptionConfirmModal() {
            var confirmBtn = document.querySelector('#subscription-confirm-modal .btn-primary');
            if (confirmBtn) {
                confirmBtn.textContent = 'Подтвердить и сохранить';
                confirmBtn.disabled = false;
            }
            document.getElementById('subscription-confirm-modal').style.display = 'none';
            window.pendingSubscriptionUpdate = null;
        }

        async function confirmSaveSubscriptionChanges() {
            if (!window.pendingSubscriptionUpdate) {
                closeSubscriptionConfirmModal();
                return;
            }
            var confirmBtn = document.querySelector('#subscription-confirm-modal .btn-primary');
            var originalText = confirmBtn ? confirmBtn.textContent : 'Подтвердить и сохранить';
            try {
                if (confirmBtn) {
                    confirmBtn.textContent = 'Сохранение...';
                    confirmBtn.disabled = true;
                }
                var response = await _deps.apiFetch('/api/admin/subscription/' + _deps.getCurrentEditingSubscriptionId() + '/update', {
                    method: 'POST',
                    headers: { 'Content-Type': 'application/json' },
                    body: JSON.stringify(window.pendingSubscriptionUpdate)
                });
                if (!response.ok) {
                    var error = await response.json();
                    throw new Error(error.error || 'Ошибка сохранения');
                }
                if (confirmBtn) {
                    confirmBtn.textContent = originalText;
                    confirmBtn.disabled = false;
                }
                closeSubscriptionConfirmModal();
                await _deps.appShowAlert('Изменения сохранены и синхронизированы с серверами.', { title: 'Готово', variant: 'success' });
                goBackFromSubscriptionEdit();
            } catch (error) {
                console.error('Ошибка сохранения подписки:', error);
                await _deps.appShowAlert('Ошибка сохранения: ' + error.message, { title: 'Ошибка', variant: 'error' });
                if (confirmBtn) {
                    confirmBtn.textContent = originalText;
                    confirmBtn.disabled = false;
                }
            }
        }

        async function syncSubscription() {
            try {
                var currentEditingSubscriptionId = _deps.getCurrentEditingSubscriptionId();
                if (!currentEditingSubscriptionId) {
                    await _deps.appShowAlert('ID подписки не найден.', { title: 'Ошибка', variant: 'error' });
                    return;
                }
                var syncBtn = document.querySelector('.btn-sync');
                syncBtn.disabled = true;
                syncBtn.textContent = 'Синхронизация...';
                var response = await _deps.apiFetch('/api/admin/subscription/' + currentEditingSubscriptionId + '/sync', {
                    method: 'POST',
                    headers: { 'Content-Type': 'application/json' }
                });
                if (!response.ok) throw new Error('Ошибка синхронизации');
                var data = await response.json();
                var resultsEl = document.getElementById('sync-results');
                resultsEl.style.display = 'block';
                resultsEl.innerHTML = '<h4>Результаты синхронизации:</h4>' + data.sync_results.map(function (result) {
                    return '\n'
                        + '                <div class="sync-result-item">\n'
                        + '                    <span>' + _deps.escapeHtml(result.server) + ': </span>\n'
                        + '                    <span class="' + (result.status === 'success' ? 'sync-result-success' : 'sync-result-error') + '">\n'
                        + '                        ' + (result.status === 'success' ? '✓ Успешно' : '✗ Ошибка: ' + _deps.escapeHtml(result.error || 'Неизвестная ошибка')) + '\n'
                        + '                    </span>\n'
                        + '                </div>\n'
                        + '            ';
                }).join('');
                syncBtn.disabled = false;
                syncBtn.textContent = 'Синхронизировать';
            } catch (error) {
                console.error('Ошибка синхронизации:', error);
                await _deps.appShowAlert('Ошибка синхронизации: ' + error.message, { title: 'Ошибка', variant: 'error' });
                var syncBtn = document.querySelector('.btn-sync');
                if (syncBtn) {
                    syncBtn.disabled = false;
                    syncBtn.textContent = 'Синхронизировать';
                }
            }
        }

        function switchSubscriptionTab(tabName) {
            var tabButtons = document.querySelectorAll('#page-admin-subscription-edit .tab-button');
            tabButtons.forEach(function (btn) { return btn.classList.remove('active'); });
            var tabContents = document.querySelectorAll('#page-admin-subscription-edit .tab-content');
            tabContents.forEach(function (content) { return content.classList.remove('active'); });

            if (tabName === 'params') {
                var paramsBtn = document.querySelector('#page-admin-subscription-edit .tab-button[data-arg="params"]');
                if (paramsBtn) paramsBtn.classList.add('active');
                var paramsContent = document.getElementById('subscription-tab-params');
                if (paramsContent) paramsContent.classList.add('active');
            } else if (tabName === 'keys') {
                var keysBtn = document.querySelector('#page-admin-subscription-edit .tab-button[data-arg="keys"]');
                if (keysBtn) keysBtn.classList.add('active');
                var keysContent = document.getElementById('subscription-tab-keys');
                if (keysContent) keysContent.classList.add('active');
                var currentSubscriptionServers = _deps.getCurrentSubscriptionServers();
                if (currentSubscriptionServers && currentSubscriptionServers.length >= 0) {
                    loadSubscriptionKeys(currentSubscriptionServers);
                }
            } else if (tabName === 'traffic') {
                var trafficBtn = document.querySelector('#page-admin-subscription-edit .tab-button[data-arg="traffic"]');
                if (trafficBtn) trafficBtn.classList.add('active');
                var trafficContent = document.getElementById('subscription-tab-traffic');
                if (trafficContent) trafficContent.classList.add('active');
                _ensureTrafficCreateFormBinding();
                loadTrafficBuckets();
            }
        }

        function _formatBytes(num) {
            var n = Number(num || 0);
            if (!isFinite(n) || n <= 0) return '0 B';
            var units = ['B', 'KB', 'MB', 'GB', 'TB'];
            var i = 0;
            while (n >= 1024 && i < units.length - 1) {
                n /= 1024;
                i++;
            }
            return (i === 0 ? Math.round(n) : n.toFixed(2)) + ' ' + units[i];
        }

        async function _trafficBucketApi(action, payload) {
            var currentEditingSubscriptionId = _deps.getCurrentEditingSubscriptionId();
            if (!currentEditingSubscriptionId) throw new Error('ID подписки не найден');
            var body = Object.assign({ action: action }, payload || {});
            var response = await _deps.apiFetch('/api/admin/subscription/' + currentEditingSubscriptionId + '/traffic-buckets', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify(body)
            });
            var data = await response.json().catch(function () { return {}; });
            if (!response.ok) throw new Error(data.error || 'Ошибка запроса buckets');
            return data;
        }

        function _renderTrafficAssignmentMatrix(snapshot) {
            var host = document.getElementById('subscription-traffic-assignment-matrix');
            if (!host) return;
            var servers = _deps.getCurrentSubscriptionServers() || [];
            var buckets = (snapshot && snapshot.buckets) || [];
            var mapping = (snapshot && snapshot.server_bucket_map) || {};
            var defaultBid = '';
            buckets.forEach(function (b) {
                if (b.is_unlimited) defaultBid = String(b.id);
            });
            if (!defaultBid && buckets.length) defaultBid = String(buckets[0].id);

            if (!buckets.length) {
                host.innerHTML = '<p class="hint">Сначала создайте хотя бы один пакет трафика.</p>';
                return;
            }
            if (!servers.length) {
                host.innerHTML = '<p class="hint">Нет привязанных серверов к этой подписке — назначение нод недоступно.</p>';
                return;
            }

            function optionsForServer(selectedId) {
                return buckets.map(function (b) {
                    var sel = String(b.id) === String(selectedId) ? ' selected' : '';
                    var label = _deps.escapeHtml(b.name || ('Пакет #' + b.id));
                    var suffix = b.is_unlimited ? ' — без лимита' : '';
                    return '<option value="' + String(b.id) + '"' + sel + '>' + label + suffix + '</option>';
                }).join('');
            }

            var rows = servers.map(function (s) {
                var name = String(s.server_name || '');
                var cur = mapping[name];
                if (cur == null || cur === '') cur = defaultBid;
                cur = String(cur);
                var esc = _deps.escapeHtml(name);
                return '<tr class="traffic-assign-row" data-server-name="' + esc + '">'
                    + '<th scope="row" class="traffic-assign-server">' + esc + '</th>'
                    + '<td class="traffic-assign-cell-packet"><select class="traffic-assign-select" aria-label="Пакет для ноды ' + esc + '">'
                    + optionsForServer(cur)
                    + '</select></td></tr>';
            }).join('');

            host.innerHTML = ''
                + '<div class="traffic-assign-matrix-shell">'
                + '<table class="traffic-assign-table" aria-label="Назначение нод на пакеты трафика">'
                + '<thead><tr><th scope="col">Нода</th><th scope="col">Пакет трафика</th></tr></thead>'
                + '<tbody>' + rows + '</tbody>'
                + '</table></div>';
        }

        function _renderTrafficPeriodQuota(snapshot) {
            var host = document.getElementById('subscription-traffic-period-quota');
            if (!host) return;
            var q = snapshot && snapshot.traffic_quota;
            if (!q) {
                host.setAttribute('hidden', '');
                host.innerHTML = '';
                return;
            }
            host.removeAttribute('hidden');
            var allowance = Number(q.included_allowance_bytes || 0);
            var incUsed = Number(q.included_used_bytes || 0);
            var purchased = Number(q.purchased_remaining_bytes || 0);
            var incRemain = Math.max(0, allowance - incUsed);
            var ver = Number(q.traffic_period_version || 0);
            host.innerHTML = ''
                + '<h3 id="traffic-quota-title" class="traffic-panel-title">Квота оплаченного периода</h3>'
                + '<p class="traffic-panel-hint">Включённый объём пересчитывается при успешной оплате продления; докупленный не сгорает при продлении.</p>'
                + '<div class="traffic-metric-grid" role="region" aria-label="Периодная квота">'
                + '  <div class="traffic-metric"><span class="traffic-metric-label">Включено на период</span><span class="traffic-metric-value">' + _formatBytes(allowance) + '</span></div>'
                + '  <div class="traffic-metric"><span class="traffic-metric-label">Из включённого израсходовано</span><span class="traffic-metric-value">' + _formatBytes(incUsed) + '</span></div>'
                + '  <div class="traffic-metric"><span class="traffic-metric-label">Остаток включённого</span><span class="traffic-metric-value">' + _formatBytes(incRemain) + '</span></div>'
                + '  <div class="traffic-metric"><span class="traffic-metric-label">Докупленный остаток</span><span class="traffic-metric-value">' + _formatBytes(purchased) + '</span></div>'
                + '  <div class="traffic-metric"><span class="traffic-metric-label">Версия периода</span><span class="traffic-metric-value">' + ver + '</span></div>'
                + '</div>'
                + '<div class="traffic-quota-admin-actions">'
                + '  <label class="traffic-field">'
                + '    <span class="traffic-field-label">Начислить докупку, ГиБ</span>'
                + '    <input type="number" min="0.001" step="0.001" id="traffic-quota-add-gib-input" value="">'
                + '  </label>'
                + '  <button type="button" class="btn-secondary" id="traffic-quota-add-btn">Начислить докупку</button>'
                + '</div>';
            var qBtn = document.getElementById('traffic-quota-add-btn');
            if (qBtn) {
                qBtn.addEventListener('click', function () {
                    addPurchasedTrafficBytes();
                });
            }
        }

        function _bindTrafficBucketActions() {
            document.querySelectorAll('[data-action="saveTrafficBucketUpdate"]').forEach(function (btn) {
                btn.addEventListener('click', function () {
                    var bucketId = btn.getAttribute('data-bucket-id');
                    saveTrafficBucketUpdate(bucketId);
                });
            });
            document.querySelectorAll('[data-action="adjustTrafficBucketUsage"]').forEach(function (btn) {
                btn.addEventListener('click', function () {
                    var bucketId = btn.getAttribute('data-bucket-id');
                    adjustTrafficBucketUsage(bucketId);
                });
            });
            document.querySelectorAll('[data-action="deleteTrafficBucket"]').forEach(function (btn) {
                btn.addEventListener('click', function () {
                    var bucketId = btn.getAttribute('data-bucket-id');
                    deleteTrafficBucket(bucketId);
                });
            });
            document.querySelectorAll('.traffic-bucket-card .traffic-bucket-unlimited-cb').forEach(function (cb) {
                cb.addEventListener('change', function () {
                    var id = cb.getAttribute('data-bucket-id');
                    if (!id) return;
                    var lim = document.getElementById('bucket-limit-gib-' + id);
                    if (lim) lim.disabled = !!cb.checked;
                });
            });
        }

        function renderTrafficBuckets(snapshot) {
            _currentBucketSnapshot = snapshot || { buckets: [], server_bucket_map: {} };
            _renderTrafficAssignmentMatrix(_currentBucketSnapshot);
            _renderTrafficPeriodQuota(_currentBucketSnapshot);
            var root = document.getElementById('subscription-traffic-buckets-list');
            if (!root) return;
            var buckets = _currentBucketSnapshot.buckets || [];
            if (!buckets.length) {
                root.innerHTML = '<div class="empty-state"><p>Пакеты трафика ещё не созданы. Заполните форму выше или нажмите «Обновить список».</p></div>';
                return;
            }
            var html = buckets.map(function (b) {
                var id = String(b.id);
                var isUnlimited = !!b.is_unlimited;
                var used = Number(b.used_bytes_window || 0);
                var limit = Number(b.limit_bytes || 0);
                var winDays = Number(b.window_days || 30);
                var creditTotal = Number(b.credit_periods_total || 1);
                var exhausted = !!b.is_exhausted;
                var statusText = exhausted ? 'Лимит исчерпан' : 'В пределах лимита';
                var statusClass = exhausted ? 'traffic-status-exhausted' : 'traffic-status-active';
                var typeRu = isUnlimited ? 'Без лимита' : 'Лимит по трафику';
                var limitRu = isUnlimited ? '—' : _formatBytes(limit);
                var remainRu = isUnlimited ? '—' : _formatBytes(Math.max(0, limit - used));
                var gibVal = isUnlimited ? '' : _gibFromBytes(limit);
                var canDeleteBucket = buckets.length > 1 && !isUnlimited;
                var limitFieldHtml = isUnlimited
                    ? ''
                    : ''
                    + '      <label class="traffic-field">'
                    + '        <span class="traffic-field-label">Лимит, ГиБ</span>'
                    + '        <input type="number" class="bucket-limit-gib-input" id="bucket-limit-gib-' + id + '" min="0" step="0.001" value="' + _deps.escapeHtml(gibVal) + '">'
                    + '      </label>';
                var toggleBlockHtml = isUnlimited
                    ? ''
                    + '    <div class="traffic-bucket-toggles">'
                    + '      <p class="hint traffic-unlimited-hint">Безлимитный пакет.</p>'
                    + '      <label class="traffic-toggle">'
                    + '        <input type="checkbox" id="bucket-enabled-' + id + '" ' + (b.is_enabled ? 'checked' : '') + '>'
                    + '        <span>Учёт включён</span>'
                    + '      </label>'
                    + '    </div>'
                    : ''
                    + '    <div class="traffic-bucket-toggles">'
                    + '      <label class="traffic-toggle">'
                    + '        <input type="checkbox" class="traffic-bucket-unlimited-cb" data-bucket-id="' + id + '" id="bucket-unlimited-' + id + '" ' + (isUnlimited ? 'checked' : '') + '>'
                    + '        <span>Без лимита трафика</span>'
                    + '      </label>'
                    + '      <label class="traffic-toggle">'
                    + '        <input type="checkbox" id="bucket-enabled-' + id + '" ' + (b.is_enabled ? 'checked' : '') + '>'
                    + '        <span>Учёт включён</span>'
                    + '      </label>'
                    + '    </div>';
                var deleteBtnHtml = canDeleteBucket
                    ? '      <button type="button" class="btn-danger" data-action="deleteTrafficBucket" data-bucket-id="' + id + '">Удалить пакет</button>'
                    : '';
                return ''
                    + '<article class="traffic-bucket-card" data-bucket-id="' + id + '">'
                    + '  <header class="traffic-bucket-head">'
                    + '    <h4 class="traffic-bucket-title">' + _deps.escapeHtml(b.name || ('Пакет #' + id)) + '</h4>'
                    + '    <span class="traffic-bucket-status ' + statusClass + '" role="status">' + statusText + '</span>'
                    + '  </header>'
                    + '  <div class="traffic-metric-grid" aria-label="Сводка по трафику">'
                    + '    <div class="traffic-metric"><span class="traffic-metric-label">Окно учёта</span><span class="traffic-metric-value">' + winDays + ' дн.</span></div>'
                    + '    <div class="traffic-metric"><span class="traffic-metric-label">Слотов кредита</span><span class="traffic-metric-value">' + creditTotal + '</span></div>'
                    + '    <div class="traffic-metric"><span class="traffic-metric-label">Тип</span><span class="traffic-metric-value">' + typeRu + '</span></div>'
                    + '    <div class="traffic-metric"><span class="traffic-metric-label">Лимит пакета</span><span class="traffic-metric-value">' + limitRu + '</span></div>'
                    + '    <div class="traffic-metric"><span class="traffic-metric-label">Использовано</span><span class="traffic-metric-value">' + _formatBytes(used) + '</span></div>'
                    + '    <div class="traffic-metric"><span class="traffic-metric-label">Остаток</span><span class="traffic-metric-value">' + remainRu + '</span></div>'
                    + '  </div>'
                    + '  <section class="traffic-bucket-block" aria-labelledby="bucket-params-' + id + '">'
                    + '    <h5 class="traffic-bucket-block-title" id="bucket-params-' + id + '">Настройки пакета</h5>'
                    + '    <div class="traffic-bucket-fields">'
                    + '      <label class="traffic-field traffic-field--span2">'
                    + '        <span class="traffic-field-label">Название</span>'
                    + '        <input type="text" id="bucket-name-' + id + '" value="' + _deps.escapeHtml(b.name || '') + '">'
                    + '      </label>'
                    + limitFieldHtml
                    + '      <label class="traffic-field">'
                    + '        <span class="traffic-field-label">Окно, дн.</span>'
                    + '        <input type="number" id="bucket-window-' + id + '" min="1" value="' + winDays + '">'
                    + '      </label>'
                    + '      <label class="traffic-field">'
                    + '        <span class="traffic-field-label">Слотов кредита</span>'
                    + '        <input type="number" id="bucket-credit-' + id + '" min="1" value="' + creditTotal + '">'
                    + '      </label>'
                    + '    </div>'
                    + toggleBlockHtml
                    + '    <div class="traffic-bucket-block-actions">'
                    + '      <button type="button" class="btn-primary" data-action="saveTrafficBucketUpdate" data-bucket-id="' + id + '">Сохранить настройки</button>'
                    + deleteBtnHtml
                    + '    </div>'
                    + '  </section>'
                    + '  <section class="traffic-bucket-block traffic-bucket-block--adjust" aria-labelledby="bucket-adjust-' + id + '">'
                    + '    <h5 class="traffic-bucket-block-title" id="bucket-adjust-' + id + '">Корректировка учёта</h5>'
                    + '    <div class="traffic-bucket-adjust-fields">'
                    + '      <label class="traffic-field">'
                    + '        <span class="traffic-field-label">Дельта, ГиБ (+ или −)</span>'
                    + '        <input type="number" step="0.001" id="bucket-adjust-gib-' + id + '" value="0">'
                    + '      </label>'
                    + '      <label class="traffic-field traffic-field--grow">'
                    + '        <span class="traffic-field-label">Комментарий</span>'
                    + '        <input type="text" id="bucket-adjust-reason-' + id + '" placeholder="Например: компенсация">'
                    + '      </label>'
                    + '    </div>'
                    + '    <div class="traffic-bucket-block-actions">'
                    + '      <button type="button" class="btn-secondary" data-action="adjustTrafficBucketUsage" data-bucket-id="' + id + '">Применить корректировку</button>'
                    + '    </div>'
                    + '  </section>'
                    + '</article>';
            }).join('');
            root.innerHTML = html;
            _bindTrafficBucketActions();
        }

        async function loadTrafficBuckets() {
            var root = document.getElementById('subscription-traffic-buckets-list');
            if (root) root.innerHTML = '<div class="loading"><div class="spinner"></div><p>Загрузка настроек трафика...</p></div>';
            try {
                var data = await _trafficBucketApi('list');
                renderTrafficBuckets(data);
            } catch (error) {
                console.error('Ошибка загрузки buckets:', error);
                var qh = document.getElementById('subscription-traffic-period-quota');
                if (qh) {
                    qh.setAttribute('hidden', '');
                    qh.innerHTML = '';
                }
                var mh = document.getElementById('subscription-traffic-assignment-matrix');
                if (mh) mh.innerHTML = '<p class="hint">Не удалось загрузить назначения нод: ' + _deps.escapeHtml(error.message) + '</p>';
                if (root) root.innerHTML = '<div class="empty-state"><p>Не удалось загрузить настройки трафика: ' + _deps.escapeHtml(error.message) + '</p></div>';
            }
        }

        async function createTrafficBucket() {
            try {
                var name = (document.getElementById('new-bucket-name').value || '').trim();
                var isUnlimited = !!document.getElementById('new-bucket-unlimited').checked;
                var gib = parseFloat(document.getElementById('new-bucket-limit-gib').value || '0');
                var limitBytes = isUnlimited ? 0 : _bytesFromGib(gib);
                var creditPeriods = parseInt(document.getElementById('new-bucket-credit-periods').value || '1', 10);
                var windowDays = parseInt(document.getElementById('new-bucket-window-days').value || '30', 10);
                if (!name) throw new Error('Укажите название пакета');
                if (!isUnlimited && (!limitBytes || limitBytes <= 0)) throw new Error('Укажите положительный лимит в ГиБ или включите «без лимита»');
                var data = await _trafficBucketApi('create', {
                    name: name,
                    is_unlimited: isUnlimited,
                    limit_bytes: limitBytes,
                    window_days: Math.max(1, windowDays),
                    credit_periods_total: Math.max(1, creditPeriods)
                });
                document.getElementById('new-bucket-name').value = '';
                document.getElementById('new-bucket-limit-gib').value = '';
                document.getElementById('new-bucket-credit-periods').value = '1';
                var wd = document.getElementById('new-bucket-window-days');
                if (wd) wd.value = '30';
                renderTrafficBuckets(data);
                await _deps.appShowAlert('Пакет трафика создан.', { title: 'Готово', variant: 'success' });
            } catch (error) {
                await _deps.appShowAlert('Ошибка создания пакета: ' + error.message, { title: 'Ошибка', variant: 'error' });
            }
        }

        async function saveTrafficBucketUpdate(bucketId) {
            try {
                var id = String(bucketId);
                var nameEl = document.getElementById('bucket-name-' + id);
                var limitGibEl = document.getElementById('bucket-limit-gib-' + id);
                var windowEl = document.getElementById('bucket-window-' + id);
                var creditEl = document.getElementById('bucket-credit-' + id);
                var unlimitedEl = document.getElementById('bucket-unlimited-' + id);
                var enabledEl = document.getElementById('bucket-enabled-' + id);
                var isUnl = unlimitedEl ? !!unlimitedEl.checked : true;
                var gib = parseFloat((limitGibEl && limitGibEl.value) || '0');
                var limitBytes = isUnl ? 0 : _bytesFromGib(gib);
                if (!isUnl && (!limitBytes || limitBytes <= 0)) throw new Error('Укажите положительный лимит в ГиБ или отметьте «без лимита»');
                var payload = {
                    name: (nameEl && nameEl.value || '').trim(),
                    is_unlimited: isUnl,
                    is_enabled: !!(enabledEl && enabledEl.checked),
                    limit_bytes: limitBytes,
                    window_days: Math.max(1, parseInt((windowEl && windowEl.value) || '30', 10)),
                    credit_periods_total: Math.max(1, parseInt((creditEl && creditEl.value) || '1', 10))
                };
                var data = await _trafficBucketApi('update', Object.assign({ bucket_id: Number(id) }, payload));
                renderTrafficBuckets(data);
                await _deps.appShowAlert('Параметры пакета сохранены.', { title: 'Готово', variant: 'success' });
            } catch (error) {
                await _deps.appShowAlert('Ошибка сохранения: ' + error.message, { title: 'Ошибка', variant: 'error' });
            }
        }

        async function saveAllTrafficAssignments() {
            try {
                var host = document.getElementById('subscription-traffic-assignment-matrix');
                if (!host) return;
                var snap = _currentBucketSnapshot || { buckets: [] };
                var buckets = snap.buckets || [];
                if (!buckets.length) throw new Error('Нет пакетов для назначения');

                var rows = host.querySelectorAll('tbody .traffic-assign-row[data-server-name]');
                if (!rows.length) throw new Error('Нет строк назначения');

                var bucketToServers = {};
                rows.forEach(function (row) {
                    var serverName = row.getAttribute('data-server-name');
                    var sel = row.querySelector('.traffic-assign-select');
                    if (!serverName || !sel) return;
                    var bid = String(sel.value);
                    if (!bucketToServers[bid]) bucketToServers[bid] = [];
                    bucketToServers[bid].push(serverName);
                });

                var ordered = buckets.slice().sort(function (a, b) {
                    return (a.is_unlimited ? 1 : 0) - (b.is_unlimited ? 1 : 0);
                });

                var lastData = null;
                for (var i = 0; i < ordered.length; i++) {
                    var b = ordered[i];
                    var bid = String(b.id);
                    var names = bucketToServers[bid] || [];
                    if (names.length > 0) {
                        lastData = await _trafficBucketApi('assign_servers', {
                            bucket_id: Number(b.id),
                            server_names: names
                        });
                    } else if (!b.is_unlimited) {
                        lastData = await _trafficBucketApi('clear_servers', { bucket_id: Number(b.id) });
                    }
                }
                if (lastData) renderTrafficBuckets(lastData);
                await _deps.appShowAlert('Назначения нод сохранены.', { title: 'Готово', variant: 'success' });
            } catch (error) {
                await _deps.appShowAlert('Ошибка сохранения назначений: ' + error.message, { title: 'Ошибка', variant: 'error' });
            }
        }

        async function deleteTrafficBucket(bucketId) {
            var id = String(bucketId);
            var ok = await _deps.appShowConfirm(
                'Удалить этот пакет трафика? Ноды из него будут переназначены на безлимитный пакет по умолчанию. Данные учёта по удаляемому пакету будут удалены.',
                { title: 'Удаление пакета', confirmText: 'Удалить' }
            );
            if (!ok) return;
            try {
                var data = await _trafficBucketApi('delete', { bucket_id: Number(id) });
                renderTrafficBuckets(data);
                await _deps.appShowAlert('Пакет удалён.', { title: 'Готово', variant: 'success' });
            } catch (error) {
                await _deps.appShowAlert('Ошибка удаления: ' + error.message, { title: 'Ошибка', variant: 'error' });
            }
        }

        async function addPurchasedTrafficBytes() {
            try {
                var el = document.getElementById('traffic-quota-add-gib-input');
                var gib = parseFloat((el && el.value) || '0');
                var bytes = Math.round(gib * _GIB);
                if (!bytes || bytes <= 0) throw new Error('Укажите положительный объём в ГиБ');
                var data = await _trafficBucketApi('add_purchased_bytes', { add_bytes: bytes });
                if (el) el.value = '';
                renderTrafficBuckets(data);
                await _deps.appShowAlert('Докупленный трафик начислен.', { title: 'Готово', variant: 'success' });
            } catch (error) {
                await _deps.appShowAlert('Ошибка: ' + error.message, { title: 'Ошибка', variant: 'error' });
            }
        }

        async function adjustTrafficBucketUsage(bucketId) {
            try {
                var id = String(bucketId);
                var gibRaw = document.getElementById('bucket-adjust-gib-' + id);
                var gib = parseFloat((gibRaw && gibRaw.value) || '0');
                var delta = Math.round(gib * _GIB);
                var reason = (document.getElementById('bucket-adjust-reason-' + id).value || '').trim();
                if (!delta) throw new Error('Укажите ненулевую корректировку в ГиБ (можно с дробью)');
                var data = await _trafficBucketApi('adjust_usage', {
                    bucket_id: Number(id),
                    bytes_delta: delta,
                    reason: reason || 'admin_adjust'
                });
                if (gibRaw) gibRaw.value = '0';
                renderTrafficBuckets(data);
                await _deps.appShowAlert('Корректировка учёта применена.', { title: 'Готово', variant: 'success' });
            } catch (error) {
                await _deps.appShowAlert('Ошибка корректировки: ' + error.message, { title: 'Ошибка', variant: 'error' });
            }
        }

        function loadSubscriptionKeys(servers) {
            var keysListEl = document.getElementById('subscription-keys-list');
            if (!keysListEl) return;
            if (!servers || servers.length === 0) {
                keysListEl.innerHTML = '\n            <div class="empty-state">\n                <p>У этой подписки нет привязанных серверов</p>\n            </div>\n        ';
                return;
            }
            var html = '<div class="keys-list">';
            html += '<div class="keys-header"><h3>Ключи подписки</h3></div>';
            html += '<div class="keys-items">';
            servers.forEach(function (server) {
                var serverName = _deps.escapeHtml(server.server_name || 'Неизвестный сервер');
                var clientEmail = _deps.escapeHtml(server.client_email || 'Не указан');
                html += '\n'
                    + '            <div class="key-item">\n'
                    + '                <div class="key-server">' + serverName + '</div>\n'
                    + '                <div class="key-email">\n'
                    + '                    <code class="key-email-code">' + clientEmail + '</code>\n'
                    + '                    <button class="btn-copy-key" onclick="copyToClipboard(\'' + clientEmail.replace(/'/g, "\\'") + '\', this)" title="Копировать">\n'
                    + '                        📋\n'
                    + '                    </button>\n'
                    + '                </div>\n'
                    + '            </div>\n'
                    + '        ';
            });
            html += '</div>';
            html += '<div class="keys-summary">Всего ключей: ' + servers.length + '</div>';
            html += '</div>';
            keysListEl.innerHTML = html;
        }

        async function copyToClipboard(text, button) {
            if (!button) return;
            var ok = await _deps.copyTextToClipboard(text);
            if (ok) {
                var originalText = button.textContent;
                button.textContent = '✓';
                button.style.color = '#4caf50';
                setTimeout(function () {
                    button.textContent = originalText;
                    button.style.color = '';
                }, 2000);
            } else {
                var el = document.getElementById('generic-copy-manual-url');
                var h = document.getElementById('generic-copy-manual-heading');
                if (el) el.value = text;
                if (h) h.textContent = 'Скопируйте вручную';
                _deps.showModal('generic-copy-manual-modal');
            }
        }

        function goBackFromSubscriptionEdit() {
            switchSubscriptionTab('params');
            var previousAdminPage = _deps.getPreviousAdminPage();
            if (previousAdminPage === 'admin-subscriptions') {
                _deps.showPage('admin-subscriptions', {
                    page: _deps.getCurrentAdminSubscriptionsPage(),
                    status: _deps.getCurrentAdminSubscriptionsStatus() || '',
                    owner: _deps.getCurrentAdminSubscriptionsOwnerQuery() || ''
                });
            } else if (previousAdminPage === 'admin-user-detail') {
                var currentAdminUserDetailUserId = _deps.getCurrentAdminUserDetailUserId();
                if (currentAdminUserDetailUserId) {
                    _deps.showAdminUserDetail(currentAdminUserDetailUserId);
                } else {
                    _deps.showPage('admin-users');
                }
            } else {
                _deps.showPage('admin-users');
            }
            _deps.setCurrentEditingSubscriptionId(null);
        }

        async function confirmDeleteSubscription() {
            var currentEditingSubscriptionId = _deps.getCurrentEditingSubscriptionId();
            if (!currentEditingSubscriptionId) {
                await _deps.appShowAlert('ID подписки не найден.', { title: 'Ошибка', variant: 'error' });
                return;
            }
            var subscriptionName = document.getElementById('sub-name').value || ('Подписка ' + currentEditingSubscriptionId);
            var msg = 'Вы уверены, что хотите удалить подписку «' + subscriptionName + '»?\n\nЭто действие необратимо. Подписка будет удалена из базы данных, а клиенты удалены со всех серверов.';
            var ok = await _deps.appShowConfirm(msg, { title: 'Удаление подписки', confirmText: 'Удалить' });
            if (ok) deleteSubscription();
        }

        async function deleteSubscription() {
            try {
                var currentEditingSubscriptionId = _deps.getCurrentEditingSubscriptionId();
                if (!currentEditingSubscriptionId) {
                    await _deps.appShowAlert('ID подписки не найден.', { title: 'Ошибка', variant: 'error' });
                    return;
                }
                var deleteBtn = document.getElementById('admin-subscription-delete-btn');
                if (deleteBtn) {
                    deleteBtn.disabled = true;
                    deleteBtn.textContent = 'Удаление...';
                }
                var response = await _deps.apiFetch('/api/admin/subscription/' + currentEditingSubscriptionId + '/delete', {
                    method: 'POST',
                    headers: { 'Content-Type': 'application/json' },
                    body: JSON.stringify({ confirm: true })
                });
                if (!response.ok) {
                    var error = await response.json();
                    throw new Error(error.error || 'Ошибка удаления');
                }
                await _deps.appShowAlert('Подписка успешно удалена.', { title: 'Готово', variant: 'success' });
                goBackFromSubscriptionEdit();
            } catch (error) {
                console.error('Ошибка удаления подписки:', error);
                await _deps.appShowAlert('Ошибка удаления: ' + error.message, { title: 'Ошибка', variant: 'error' });
                var deleteBtnErr = document.getElementById('admin-subscription-delete-btn');
                if (deleteBtnErr) {
                    deleteBtnErr.disabled = false;
                    deleteBtnErr.textContent = 'Удалить подписку';
                }
            }
        }

        return {
            showAdminSubscriptionEdit: showAdminSubscriptionEdit,
            saveSubscriptionChanges: saveSubscriptionChanges,
            closeSubscriptionConfirmModal: closeSubscriptionConfirmModal,
            confirmSaveSubscriptionChanges: confirmSaveSubscriptionChanges,
            syncSubscription: syncSubscription,
            switchSubscriptionTab: switchSubscriptionTab,
            loadSubscriptionKeys: loadSubscriptionKeys,
            loadTrafficBuckets: loadTrafficBuckets,
            createTrafficBucket: createTrafficBucket,
            saveTrafficBucketUpdate: saveTrafficBucketUpdate,
            saveAllTrafficAssignments: saveAllTrafficAssignments,
            adjustTrafficBucketUsage: adjustTrafficBucketUsage,
            copyToClipboard: copyToClipboard,
            goBackFromSubscriptionEdit: goBackFromSubscriptionEdit,
            confirmDeleteSubscription: confirmDeleteSubscription,
            deleteSubscription: deleteSubscription
        };
    }

    window.DarallaAdminSubscriptionEditFeature = window.DarallaAdminSubscriptionEditFeature || {};
    window.DarallaAdminSubscriptionEditFeature.create = createAdminSubscriptionEditFeature;
})();
