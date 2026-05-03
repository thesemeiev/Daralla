(function () {
    function createAdminUsersListFeature(deps) {
        var _deps = deps || {};
        var searchTimeout = null;

        async function loadAdminUsers(page, search) {
            page = page == null ? 1 : page;
            search = search == null ? '' : search;
            try {
                var response = await _deps.apiFetch('/api/admin/users', {
                    method: 'POST',
                    headers: { 'Content-Type': 'application/json' },
                    body: JSON.stringify({ page: page, limit: 20, search: search })
                });
                if (!response.ok) throw new Error('Ошибка загрузки пользователей');

                var data = await window.DarallaApiClient.responseJson(response);
                document.getElementById('admin-users-loading').style.display = 'none';
                document.getElementById('admin-users-content').style.display = 'block';
                document.getElementById('admin-total-users').textContent = data.total || 0;

                var listEl = document.getElementById('admin-users-list');
                listEl.innerHTML = '';
                if (data.users && data.users.length > 0) {
                    data.users.forEach(function (user) {
                        var card = document.createElement('div');
                        card.className = 'admin-user-card';
                        card.onclick = function () { return showAdminUserDetail(user.user_id); };
                        var firstSeen = new Date(user.first_seen * 1000).toLocaleDateString('ru-RU');
                        var lastSeen = new Date(user.last_seen * 1000).toLocaleDateString('ru-RU');
                        var extra = [
                            user.telegram_id && ('TG: ' + _deps.escapeHtml(user.telegram_id)),
                            user.username && ('Логин: ' + _deps.escapeHtml(user.username))
                        ].filter(Boolean).join(' · ');
                        card.innerHTML = '\n'
                            + '                    <div class="admin-user-id">ID: ' + _deps.escapeHtml(user.user_id) + '</div>\n'
                            + (extra ? ('<div class="admin-user-extra">' + extra + '</div>') : '')
                            + '\n                    <div class="admin-user-meta">\n'
                            + '                        <span>Создан: ' + firstSeen + '</span>\n'
                            + '                        <span>Активен: ' + lastSeen + '</span>\n'
                            + '                    </div>\n'
                            + '                    <div class="admin-user-subscriptions">Подписок: ' + (user.subscriptions_count || 0) + '</div>\n'
                            + '                ';
                        listEl.appendChild(card);
                    });
                    if (data.pages > 1) {
                        showAdminPagination(data.page, data.pages);
                    } else {
                        document.getElementById('admin-users-pagination').style.display = 'none';
                    }
                } else {
                    listEl.innerHTML = '<div class="empty"><p>Пользователи не найдены</p></div>';
                    document.getElementById('admin-users-pagination').style.display = 'none';
                }

                _deps.setCurrentAdminUserPage(page);
                _deps.setCurrentAdminUserSearch(search);
                var searchInput = document.getElementById('admin-user-search');
                if (searchInput) searchInput.value = search;
                try { location.hash = _deps.buildHash('admin-users', { page: String(page), search: search }); } catch (e) {}
            } catch (error) {
                console.error('Ошибка загрузки пользователей:', error);
                document.getElementById('admin-users-loading').style.display = 'none';
                _deps.showError('admin-users-error', 'Ошибка загрузки пользователей');
            }
        }

        function handleAdminUserSearch() {
            clearTimeout(searchTimeout);
            var searchInput = document.getElementById('admin-user-search');
            var search = searchInput ? searchInput.value.trim() : '';
            searchTimeout = setTimeout(function () {
                loadAdminUsers(1, search);
            }, 500);
        }

        function showAdminPagination(currentPage, totalPages) {
            var paginationEl = document.getElementById('admin-users-pagination');
            if (!paginationEl) return;
            paginationEl.style.display = 'flex';
            paginationEl.innerHTML = '';

            var prevBtn = document.createElement('button');
            prevBtn.textContent = '←';
            prevBtn.disabled = currentPage === 1;
            prevBtn.onclick = function () { return loadAdminUsers(currentPage - 1, _deps.getCurrentAdminUserSearch()); };
            paginationEl.appendChild(prevBtn);

            var startPage = Math.max(1, currentPage - 2);
            var endPage = Math.min(totalPages, currentPage + 2);
            for (var i = startPage; i <= endPage; i++) {
                (function (p) {
                    var pageBtn = document.createElement('button');
                    pageBtn.textContent = p;
                    pageBtn.className = p === currentPage ? 'active' : '';
                    pageBtn.onclick = function () { return loadAdminUsers(p, _deps.getCurrentAdminUserSearch()); };
                    paginationEl.appendChild(pageBtn);
                })(i);
            }

            var nextBtn = document.createElement('button');
            nextBtn.textContent = '→';
            nextBtn.disabled = currentPage === totalPages;
            nextBtn.onclick = function () { return loadAdminUsers(currentPage + 1, _deps.getCurrentAdminUserSearch()); };
            paginationEl.appendChild(nextBtn);
        }

        async function showAdminUserDetail(userId) {
            try {
                _deps.setPreviousAdminPage('admin-users');
                _deps.showPage('admin-user-detail', { id: userId });
                document.getElementById('admin-user-detail-loading').style.display = 'block';
                document.getElementById('admin-user-detail-content').innerHTML = '';

                var response = await _deps.apiFetch('/api/admin/user/' + userId, {
                    method: 'POST',
                    headers: { 'Content-Type': 'application/json' }
                });
                if (!response.ok) throw new Error('Ошибка загрузки информации о пользователе');
                var data = await window.DarallaApiClient.responseJson(response);
                document.getElementById('admin-user-detail-loading').style.display = 'none';
                _deps.setCurrentAdminUserDetailUserId(userId);

                var contentEl = document.getElementById('admin-user-detail-content');
                var user = data.user;
                var infoRows = [
                    { label: 'ID аккаунта', value: user.user_id },
                    user.telegram_id ? { label: 'Telegram ID', value: user.telegram_id } : null,
                    user.username ? { label: 'Логин', value: user.username } : null,
                    { label: 'Первый запуск', value: user.first_seen_formatted },
                    { label: 'Последняя активность', value: user.last_seen_formatted }
                ].filter(Boolean);
                contentEl.innerHTML = '\n'
                    + '            <div class="admin-user-detail-section">\n'
                    + '                <h3>Информация</h3>\n'
                    + infoRows.map(function (r) {
                        return '\n'
                            + '                    <div class="admin-detail-item">\n'
                            + '                        <span class="admin-detail-label">' + _deps.escapeHtml(r.label) + '</span>\n'
                            + '                        <span class="admin-detail-value">' + _deps.escapeHtml(r.value) + '</span>\n'
                            + '                    </div>\n'
                            + '                ';
                    }).join('')
                    + '\n            </div>\n'
                    + '\n            <div class="admin-user-detail-section">\n'
                    + '                <h3>Подписки (' + data.subscriptions.length + ')</h3>\n'
                    + (data.subscriptions.length > 0
                        ? data.subscriptions.map(function (sub) {
                            var isSubActive = sub.status === 'active' || (sub.status === 'trial' && sub.expires_at && new Date(sub.expires_at * 1000) > new Date());
                            var statusClass = sub.status === 'deleted' ? 'deleted' : sub.status === 'canceled' ? 'canceled' : (isSubActive ? 'active' : 'expired');
                            var statusLabel = sub.status === 'active' ? 'Активна' : sub.status === 'expired' ? 'Истекла' : sub.status === 'trial' ? 'Пробная' : sub.status === 'deleted' ? 'Удалена' : 'Отменена';
                            return '\n'
                                + '                        <div class="admin-subscription-card" onclick="showAdminSubscriptionEdit(' + sub.id + ')">\n'
                                + '                            <div class="admin-subscription-head">\n'
                                + '                                <div class="admin-subscription-name">' + _deps.escapeHtml(sub.name) + '</div>\n'
                                + '                                <div class="admin-subscription-status ' + statusClass + '">' + statusLabel + '</div>\n'
                                + '                            </div>\n'
                                + '                            <div class="admin-subscription-info">\n'
                                + '                                <div>Создана: ' + _deps.escapeHtml(sub.created_at_formatted) + '</div>\n'
                                + '                                <div>Истекает: ' + _deps.escapeHtml(sub.expires_at_formatted) + '</div>\n'
                                + '                                <div>Устройств: ' + sub.device_limit + '</div>\n'
                                + '                            </div>\n'
                                + '                        </div>\n'
                                + '                    ';
                        }).join('')
                        : '<p class="admin-detail-empty hint">Нет подписок</p>')
                    + '\n            </div>\n'
                    + '\n            ' + (data.payments && data.payments.length > 0
                        ? ('\n                <div class="admin-user-detail-section">\n'
                            + '                    <h3>Платежи (' + data.payments.length + ')</h3>\n'
                            + data.payments.map(function (payment) {
                                return '\n'
                                    + '                        <div class="admin-detail-item">\n'
                                    + '                            <span class="admin-detail-label">' + _deps.escapeHtml(payment.created_at_formatted) + '</span>\n'
                                    + '                            <span class="admin-detail-value">' + (payment.amount || 0).toLocaleString('ru-RU') + ' ₽ (' + _deps.escapeHtml(payment.status) + ')</span>\n'
                                    + '                        </div>\n'
                                    + '                    ';
                            }).join('')
                            + '\n                </div>\n')
                        : '')
                    + '\n            <div class="admin-user-detail-actions">\n'
                    + '                <button type="button" class="btn-primary" onclick="showCreateSubscriptionForm(\'' + _deps.escapeHtml(data.user.user_id) + '\')">Создать подписку</button>\n'
                    + '                <button type="button" class="btn-danger" onclick="showDeleteUserConfirm(\'' + _deps.escapeHtml(data.user.user_id) + '\')">Удалить пользователя</button>\n'
                    + '            </div>\n'
                    + '        ';
            } catch (error) {
                console.error('Ошибка загрузки информации о пользователе:', error);
                document.getElementById('admin-user-detail-loading').style.display = 'none';
                document.getElementById('admin-user-detail-content').innerHTML = '<div class="error"><p>Ошибка загрузки информации</p></div>';
            }
        }

        return {
            loadAdminUsers: loadAdminUsers,
            handleAdminUserSearch: handleAdminUserSearch,
            showAdminPagination: showAdminPagination,
            showAdminUserDetail: showAdminUserDetail
        };
    }

    window.DarallaAdminUsersListFeature = window.DarallaAdminUsersListFeature || {};
    window.DarallaAdminUsersListFeature.create = createAdminUsersListFeature;
})();
