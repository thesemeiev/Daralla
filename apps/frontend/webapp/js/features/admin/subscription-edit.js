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

        function _buildServerChecksHtml(bucketId) {
            var servers = _deps.getCurrentSubscriptionServers() || [];
            var mapping = (_currentBucketSnapshot && _currentBucketSnapshot.server_bucket_map) || {};
            if (!servers.length) {
                return '<div class="hint">Нет привязанных серверов для этой подписки.</div>';
            }
            return servers.map(function (s) {
                var name = s.server_name || '';
                var checked = String(mapping[name]) === String(bucketId) ? 'checked' : '';
                return ''
                    + '<label class="traffic-bucket-server-item">'
                    + '<input type="checkbox" data-role="bucket-server" value="' + _deps.escapeHtml(name) + '" ' + checked + '>'
                    + '<span>' + _deps.escapeHtml(name) + '</span>'
                    + '</label>';
            }).join('');
        }

        function _bindTrafficBucketActions() {
            document.querySelectorAll('[data-action="saveTrafficBucketUpdate"]').forEach(function (btn) {
                btn.addEventListener('click', function () {
                    var bucketId = btn.getAttribute('data-bucket-id');
                    saveTrafficBucketUpdate(bucketId);
                });
            });
            document.querySelectorAll('[data-action="saveBucketServerAssignments"]').forEach(function (btn) {
                btn.addEventListener('click', function () {
                    var bucketId = btn.getAttribute('data-bucket-id');
                    saveBucketServerAssignments(bucketId);
                });
            });
            document.querySelectorAll('[data-action="adjustTrafficBucketUsage"]').forEach(function (btn) {
                btn.addEventListener('click', function () {
                    var bucketId = btn.getAttribute('data-bucket-id');
                    adjustTrafficBucketUsage(bucketId);
                });
            });
            document.querySelectorAll('[data-action="clearTrafficBucketServers"]').forEach(function (btn) {
                btn.addEventListener('click', function () {
                    var bucketId = btn.getAttribute('data-bucket-id');
                    clearTrafficBucketServers(bucketId);
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
                return ''
                    + '<div class="traffic-bucket-card">'
                    + '  <div class="traffic-bucket-head">'
                    + '    <div class="traffic-bucket-title">' + _deps.escapeHtml(b.name || ('Пакет #' + id)) + '</div>'
                    + '    <div class="traffic-bucket-status ' + statusClass + '">' + statusText + '</div>'
                    + '  </div>'
                    + '  <div class="traffic-bucket-meta">'
                    + '    <span>Окно учёта: ' + winDays + ' дн.</span>'
                    + '    <span>Слотов кредита: ' + creditTotal + '</span>'
                    + '    <span>Тип: ' + typeRu + '</span>'
                    + '    <span>Лимит пакета: ' + limitRu + '</span>'
                    + '    <span>Использовано за окно: ' + _formatBytes(used) + '</span>'
                    + '    <span>Остаток: ' + remainRu + '</span>'
                    + '  </div>'
                    + '  <div class="traffic-bucket-inline-form">'
                    + '    <label>Название <input type="text" id="bucket-name-' + id + '" value="' + _deps.escapeHtml(b.name || '') + '"></label>'
                    + '    <label>Лимит, ГиБ <input type="number" class="bucket-limit-gib-input" id="bucket-limit-gib-' + id + '" min="0" step="0.001" value="' + _deps.escapeHtml(gibVal) + '"' + (isUnlimited ? ' disabled' : '') + '></label>'
                    + '    <label>Окно, дн. <input type="number" id="bucket-window-' + id + '" min="1" value="' + winDays + '"></label>'
                    + '    <label>Слотов кредита <input type="number" id="bucket-credit-' + id + '" min="1" value="' + creditTotal + '"></label>'
                    + '    <label class="inline-check"><input type="checkbox" class="traffic-bucket-unlimited-cb" data-bucket-id="' + id + '" id="bucket-unlimited-' + id + '" ' + (isUnlimited ? 'checked' : '') + '> Без лимита трафика</label>'
                    + '    <label class="inline-check"><input type="checkbox" id="bucket-enabled-' + id + '" ' + (b.is_enabled ? 'checked' : '') + '> Учёт включён</label>'
                    + '    <button type="button" class="btn-secondary" data-action="saveTrafficBucketUpdate" data-bucket-id="' + id + '">Сохранить параметры</button>'
                    + '  </div>'
                    + '  <div class="traffic-bucket-assignments">'
                    + '    <div class="traffic-bucket-subtitle">Ноды в этом пакете</div>'
                    + '    <div class="traffic-bucket-servers">' + _buildServerChecksHtml(id) + '</div>'
                    + '    <div class="traffic-bucket-actions">'
                    + '      <button type="button" class="btn-secondary" data-action="saveBucketServerAssignments" data-bucket-id="' + id + '">Сохранить ноды</button>'
                    + '      <button type="button" class="btn-secondary" data-action="clearTrafficBucketServers" data-bucket-id="' + id + '">Снять все ноды с пакета</button>'
                    + '    </div>'
                    + '  </div>'
                    + '  <div class="traffic-bucket-adjust">'
                    + '    <label>Корректировка, ГиБ (+ или −) <input type="number" step="0.001" id="bucket-adjust-gib-' + id + '" value="0"></label>'
                    + '    <label>Комментарий <input type="text" id="bucket-adjust-reason-' + id + '" placeholder="например: компенсация"></label>'
                    + '    <button type="button" class="btn-secondary" data-action="adjustTrafficBucketUsage" data-bucket-id="' + id + '">Применить корректировку учёта</button>'
                    + '  </div>'
                    + '</div>';
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
                var isUnl = !!(unlimitedEl && unlimitedEl.checked);
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
                var data = await _trafficBucketApi('update', { bucket_id: Number(id), ...payload });
                renderTrafficBuckets(data);
                await _deps.appShowAlert('Параметры пакета сохранены.', { title: 'Готово', variant: 'success' });
            } catch (error) {
                await _deps.appShowAlert('Ошибка сохранения: ' + error.message, { title: 'Ошибка', variant: 'error' });
            }
        }

        async function saveBucketServerAssignments(bucketId) {
            try {
                var id = String(bucketId);
                var checked = Array.from(document.querySelectorAll('.traffic-bucket-card input[data-role="bucket-server"]:checked'))
                    .filter(function (el) {
                        var card = el.closest('.traffic-bucket-card');
                        if (!card) return false;
                        var btn = card.querySelector('[data-action="saveBucketServerAssignments"]');
                        return btn && String(btn.getAttribute('data-bucket-id')) === id;
                    })
                    .map(function (el) { return el.value; });
                var data = await _trafficBucketApi('assign_servers', {
                    bucket_id: Number(id),
                    server_names: checked
                });
                renderTrafficBuckets(data);
                await _deps.appShowAlert('Ноды назначены.', { title: 'Готово', variant: 'success' });
            } catch (error) {
                await _deps.appShowAlert('Ошибка назначения нод: ' + error.message, { title: 'Ошибка', variant: 'error' });
            }
        }

        async function clearTrafficBucketServers(bucketId) {
            try {
                var id = String(bucketId);
                var data = await _trafficBucketApi('clear_servers', { bucket_id: Number(id) });
                renderTrafficBuckets(data);
                await _deps.appShowAlert('Назначения нод очищены.', { title: 'Готово', variant: 'success' });
            } catch (error) {
                await _deps.appShowAlert('Ошибка очистки назначений: ' + error.message, { title: 'Ошибка', variant: 'error' });
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
            saveBucketServerAssignments: saveBucketServerAssignments,
            clearTrafficBucketServers: clearTrafficBucketServers,
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
