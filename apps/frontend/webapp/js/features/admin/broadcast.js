(function () {
    function createAdminBroadcastFeature(deps) {
        var _deps = deps || {};
        var state = {
            selectedUsers: [],
            userSearchTimeout: null,
            sendMode: 'all',
            currentQuery: '',
            currentResults: [],
            totalUsers: 0
        };

        async function loadBroadcastPage() {
            var loadingEl = document.getElementById('admin-broadcast-loading');
            var errorEl = document.getElementById('admin-broadcast-error');
            var contentEl = document.getElementById('admin-broadcast-content');
            var recipientsCountEl = document.getElementById('broadcast-recipients-count');
            var resultEl = document.getElementById('broadcast-result');

            if (errorEl) errorEl.style.display = 'none';
            if (resultEl) resultEl.style.display = 'none';
            if (loadingEl) loadingEl.style.display = 'flex';
            var loadingTextEl = document.getElementById('broadcast-loading-text');
            if (loadingTextEl) loadingTextEl.textContent = 'Загрузка данных...';
            if (contentEl) contentEl.style.display = 'none';

            try {
                var statsResponse = await _deps.apiFetch('/api/admin/stats', {
                    method: 'POST',
                    headers: { 'Content-Type': 'application/json' }
                });
                if (!statsResponse.ok) throw new Error('Ошибка загрузки данных');
                var statsData = await statsResponse.json();
                state.totalUsers = (statsData.stats && statsData.stats.users && statsData.stats.users.total) || 0;

                state.selectedUsers = [];
                state.currentQuery = '';
                state.currentResults = [];

                var modeAll = document.getElementById('broadcast-mode-all');
                var modeSelected = document.getElementById('broadcast-mode-selected');
                if (modeAll && modeSelected) {
                    modeAll.onchange = function () { return setBroadcastMode('all'); };
                    modeSelected.onchange = function () { return setBroadcastMode('selected'); };
                    modeAll.checked = true;
                    modeSelected.checked = false;
                }
                setBroadcastMode('all');

                if (recipientsCountEl) recipientsCountEl.textContent = state.totalUsers;
                if (loadingEl) loadingEl.style.display = 'none';
                if (contentEl) contentEl.style.display = 'block';
            } catch (error) {
                console.error('Ошибка загрузки страницы рассылки:', error);
                if (loadingEl) loadingEl.style.display = 'none';
                if (errorEl) errorEl.style.display = 'block';
                var errText = document.getElementById('broadcast-error-text');
                if (errText) errText.textContent = error.message || 'Ошибка загрузки данных';
            }
        }

        function setBroadcastMode(mode) {
            state.sendMode = mode;
            var selectionDiv = document.getElementById('broadcast-user-selection');
            var hintEl = document.getElementById('broadcast-mode-hint');
            var searchInput = document.getElementById('broadcast-user-search');

            if (mode === 'selected') {
                if (selectionDiv) selectionDiv.style.display = 'block';
                if (hintEl) hintEl.textContent = 'Отправка только выбранным пользователям';
                state.currentQuery = ((searchInput && searchInput.value) || '').trim();
                renderBroadcastUserResults();
            } else {
                if (selectionDiv) selectionDiv.style.display = 'none';
                state.selectedUsers = [];
                state.currentQuery = '';
                state.currentResults = [];
                if (searchInput) searchInput.value = '';
                if (hintEl) hintEl.textContent = 'Отправка всем пользователям';
            }
            updateSelectedCount();
            updateBroadcastRecipientsCount();
            updateSendButtonState();
        }

        function renderBroadcastUserResults() {
            var listEl = document.getElementById('broadcast-users-list');
            if (!listEl) return;
            var query = (state.currentQuery || '').trim();
            if (!query) {
                listEl.innerHTML = '<div class="broadcast-empty-state hint broadcast-empty-state-box">Введите ID для поиска</div>';
                return;
            }

            var usersToShow = (state.currentResults || []).filter(function (u) { return !state.selectedUsers.includes(u.user_id); });
            if (usersToShow.length === 0) {
                listEl.innerHTML = '<div class="broadcast-empty-state hint broadcast-empty-state-box">Нет результатов</div>';
                return;
            }

            listEl.innerHTML = '';
            var qLower = query.toLowerCase();
            usersToShow.forEach(function (user) {
                var userCard = document.createElement('div');
                userCard.className = 'broadcast-user-card';
                userCard.onclick = function () { return toggleUserForBroadcast(user.user_id); };

                var checkbox = document.createElement('input');
                checkbox.type = 'checkbox';
                checkbox.checked = false;
                checkbox.className = 'broadcast-user-checkbox';
                checkbox.onclick = function (e) {
                    e.stopPropagation();
                    toggleUserForBroadcast(user.user_id);
                };

                var userInfo = document.createElement('div');
                userInfo.className = 'broadcast-user-info';
                var idLine = highlightMatchRaw('ID: ' + String(user.user_id), qLower);
                var subsText = 'Подписок: ' + (user.subscriptions_count || 0);
                userInfo.innerHTML = '<div class="broadcast-user-id">' + idLine + '</div><div class="broadcast-user-subs">' + _deps.escapeHtml(subsText) + '</div>';

                userCard.appendChild(checkbox);
                userCard.appendChild(userInfo);
                listEl.appendChild(userCard);
            });
        }

        async function searchUsersForBroadcast() {
            clearTimeout(state.userSearchTimeout);
            var searchInput = document.getElementById('broadcast-user-search');
            var search = ((searchInput && searchInput.value) || '').trim();
            var listEl = document.getElementById('broadcast-users-list');
            state.currentQuery = search;

            if (!search) {
                state.currentResults = [];
                renderBroadcastUserResults();
                return;
            }

            state.userSearchTimeout = setTimeout(async function () {
                try {
                    listEl.innerHTML = '<div class="broadcast-empty-state hint broadcast-empty-state-box">Поиск...</div>';
                    var response = await _deps.apiFetch('/api/admin/users', {
                        method: 'POST',
                        headers: { 'Content-Type': 'application/json' },
                        body: JSON.stringify({ page: 1, limit: 50, search: search })
                    });
                    if (!response.ok) throw new Error('Ошибка поиска пользователей');
                    var data = await response.json();
                    if (!data.users || data.users.length === 0) {
                        listEl.innerHTML = '<div class="broadcast-empty-state hint broadcast-empty-state-box">Пользователи не найдены</div>';
                        return;
                    }
                    state.currentResults = data.users;
                    renderBroadcastUserResults();
                } catch (error) {
                    console.error('Ошибка поиска пользователей:', error);
                    listEl.innerHTML = '<div class="error-text error-text-box">Ошибка загрузки пользователей</div>';
                }
            }, 500);
        }

        function toggleUserForBroadcast(userId) {
            var index = state.selectedUsers.indexOf(userId);
            if (index === -1) state.selectedUsers.push(userId);
            else state.selectedUsers.splice(index, 1);
            updateSelectedCount();
            updateBroadcastRecipientsCount();
            updateSendButtonState();
            renderBroadcastUserResults();
        }

        function clearUserSelection() {
            state.selectedUsers = [];
            updateSelectedCount();
            updateBroadcastRecipientsCount();
            updateSendButtonState();
            renderBroadcastUserResults();
        }

        function updateSelectedCount() {
            var countEl = document.getElementById('broadcast-selected-count');
            if (countEl) countEl.textContent = state.selectedUsers.length;
            updateSelectedChips();
        }

        function updateBroadcastRecipientsCount() {
            var recipientsCountEl = document.getElementById('broadcast-recipients-count');
            if (!recipientsCountEl) return;
            recipientsCountEl.textContent = state.sendMode === 'selected' ? state.selectedUsers.length : (state.totalUsers || '-');
        }

        function updateSendButtonState() {
            var sendBtn = document.getElementById('broadcast-send-btn');
            if (!sendBtn) return;
            if (state.sendMode === 'selected' && state.selectedUsers.length === 0) {
                sendBtn.disabled = true;
                sendBtn.textContent = 'Отправить рассылку';
            } else {
                sendBtn.disabled = false;
                sendBtn.textContent = 'Отправить рассылку';
            }
        }

        function updateSelectedChips() {
            var chipsEl = document.getElementById('broadcast-selected-chips');
            if (!chipsEl) return;
            chipsEl.innerHTML = '';
            if (state.selectedUsers.length === 0) {
                chipsEl.style.display = 'none';
                return;
            }
            chipsEl.style.display = 'flex';
            state.selectedUsers.forEach(function (userId) {
                var chip = document.createElement('div');
                chip.className = 'chip';
                chip.innerHTML = '<span>' + _deps.escapeHtml(userId) + '</span><button aria-label="Удалить" onclick="removeUserFromSelection(\'' + userId + '\')">×</button>';
                chipsEl.appendChild(chip);
            });
        }

        function removeUserFromSelection(userId) {
            var idx = state.selectedUsers.indexOf(userId);
            if (idx > -1) {
                state.selectedUsers.splice(idx, 1);
                updateSelectedCount();
                updateBroadcastRecipientsCount();
                updateSendButtonState();
                renderBroadcastUserResults();
            }
        }

        function selectAllBroadcastResults() {
            var usersToShow = (state.currentResults || []).filter(function (u) { return !state.selectedUsers.includes(u.user_id); });
            if (!usersToShow.length) return;
            usersToShow.forEach(function (u) { state.selectedUsers.push(u.user_id); });
            updateSelectedCount();
            updateBroadcastRecipientsCount();
            updateSendButtonState();
            renderBroadcastUserResults();
        }

        function highlightMatchRaw(text, queryLower) {
            if (!queryLower) return _deps.escapeHtml(text);
            var lower = text.toLowerCase();
            var idx = lower.indexOf(queryLower);
            if (idx === -1) return _deps.escapeHtml(text);
            var before = text.slice(0, idx);
            var match = text.slice(idx, idx + queryLower.length);
            var after = text.slice(idx + queryLower.length);
            return _deps.escapeHtml(before) + '<span class="highlight-match">' + _deps.escapeHtml(match) + '</span>' + _deps.escapeHtml(after);
        }

        async function sendBroadcast() {
            var messageEl = document.getElementById('broadcast-message');
            var sendBtn = document.getElementById('broadcast-send-btn');
            var loadingEl = document.getElementById('admin-broadcast-loading');
            var errorEl = document.getElementById('admin-broadcast-error');
            var resultEl = document.getElementById('broadcast-result');
            var contentEl = document.getElementById('admin-broadcast-content');
            var message = messageEl.value.trim();

            if (!message) {
                _deps.platform.showAlert('Пожалуйста, введите текст сообщения');
                return;
            }
            var isSelectMode = state.sendMode === 'selected';
            if (isSelectMode && state.selectedUsers.length === 0) {
                _deps.platform.showAlert('Пожалуйста, выберите хотя бы одного пользователя');
                return;
            }

            var confirmText = isSelectMode
                ? ('Вы уверены, что хотите отправить рассылку ' + state.selectedUsers.length + ' выбранным пользователям?')
                : 'Вы уверены, что хотите отправить рассылку всем пользователям?';
            var confirmed = await _deps.appShowConfirm(confirmText, { title: 'Рассылка' });
            if (!confirmed) return;

            sendBtn.disabled = true;
            sendBtn.textContent = 'Отправка...';
            loadingEl.style.display = 'flex';
            document.getElementById('broadcast-loading-text').textContent = 'Отправка рассылки...';
            errorEl.style.display = 'none';
            resultEl.style.display = 'none';
            contentEl.style.display = 'none';

            try {
                var requestBody = { message: message };
                if (isSelectMode && state.selectedUsers.length > 0) requestBody.user_ids = state.selectedUsers;
                var response = await _deps.apiFetch('/api/admin/broadcast', {
                    method: 'POST',
                    headers: { 'Content-Type': 'application/json' },
                    body: JSON.stringify(requestBody)
                });
                if (!response.ok) {
                    var errorData = await response.json();
                    throw new Error(errorData.error || 'Ошибка отправки рассылки');
                }
                var data = await response.json();
                document.getElementById('broadcast-sent-count').textContent = data.sent || 0;
                document.getElementById('broadcast-failed-count').textContent = data.failed || 0;
                document.getElementById('broadcast-total-count').textContent = data.total || 0;
                resultEl.style.display = 'block';
                loadingEl.style.display = 'none';
                contentEl.style.display = 'block';
                messageEl.value = '';
                var resultMsg = 'Рассылка завершена!\n\nОтправлено: ' + data.sent + '\nОшибок: ' + data.failed + '\nВсего: ' + data.total;
                _deps.platform.showAlert(resultMsg);
            } catch (error) {
                console.error('Ошибка отправки рассылки:', error);
                loadingEl.style.display = 'none';
                errorEl.style.display = 'block';
                document.getElementById('broadcast-error-text').textContent = (error && error.message) || 'Ошибка отправки рассылки';
                contentEl.style.display = 'block';
            } finally {
                sendBtn.disabled = false;
                sendBtn.textContent = 'Отправить рассылку';
            }
        }

        return {
            loadBroadcastPage: loadBroadcastPage,
            setBroadcastMode: setBroadcastMode,
            renderBroadcastUserResults: renderBroadcastUserResults,
            searchUsersForBroadcast: searchUsersForBroadcast,
            toggleUserForBroadcast: toggleUserForBroadcast,
            clearUserSelection: clearUserSelection,
            updateSelectedCount: updateSelectedCount,
            updateBroadcastRecipientsCount: updateBroadcastRecipientsCount,
            updateSendButtonState: updateSendButtonState,
            updateSelectedChips: updateSelectedChips,
            removeUserFromSelection: removeUserFromSelection,
            selectAllBroadcastResults: selectAllBroadcastResults,
            highlightMatchRaw: highlightMatchRaw,
            sendBroadcast: sendBroadcast
        };
    }

    window.DarallaAdminBroadcastFeature = window.DarallaAdminBroadcastFeature || {};
    window.DarallaAdminBroadcastFeature.create = createAdminBroadcastFeature;
})();
