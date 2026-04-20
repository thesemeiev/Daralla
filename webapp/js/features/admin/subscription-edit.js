(function () {
    function createAdminSubscriptionEditFeature(deps) {
        var _deps = deps || {};

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
                loadSubscriptionKeys(servers);
            } catch (error) {
                console.error('Ошибка загрузки подписки:', error);
                document.getElementById('admin-subscription-edit-loading').style.display = 'none';
                await _deps.appShowAlert('Не удалось загрузить подписку.', { title: 'Ошибка', variant: 'error' });
            }
        }

        async function saveSubscriptionChanges(event) {
            event.preventDefault();
            var submitBtn = event.target.querySelector('button[type="submit"]');
            if (submitBtn) {
                submitBtn.disabled = false;
                submitBtn.textContent = 'Сохранить';
            }

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
                var paramsBtn = document.querySelector('#page-admin-subscription-edit .tab-button[onclick*="params"]');
                if (paramsBtn) paramsBtn.classList.add('active');
                var paramsContent = document.getElementById('subscription-tab-params');
                if (paramsContent) paramsContent.classList.add('active');
            } else if (tabName === 'keys') {
                var keysBtn = document.querySelector('#page-admin-subscription-edit .tab-button[onclick*="keys"]');
                if (keysBtn) keysBtn.classList.add('active');
                var keysContent = document.getElementById('subscription-tab-keys');
                if (keysContent) keysContent.classList.add('active');
                var currentSubscriptionServers = _deps.getCurrentSubscriptionServers();
                if (currentSubscriptionServers && currentSubscriptionServers.length >= 0) {
                    loadSubscriptionKeys(currentSubscriptionServers);
                }
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
                var deleteBtn = document.querySelector('.btn-danger');
                deleteBtn.disabled = true;
                deleteBtn.textContent = 'Удаление...';
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
                var deleteBtn = document.querySelector('.btn-danger');
                if (deleteBtn) {
                    deleteBtn.disabled = false;
                    deleteBtn.textContent = 'Удалить подписку';
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
            copyToClipboard: copyToClipboard,
            goBackFromSubscriptionEdit: goBackFromSubscriptionEdit,
            confirmDeleteSubscription: confirmDeleteSubscription,
            deleteSubscription: deleteSubscription
        };
    }

    window.DarallaAdminSubscriptionEditFeature = window.DarallaAdminSubscriptionEditFeature || {};
    window.DarallaAdminSubscriptionEditFeature.create = createAdminSubscriptionEditFeature;
})();
