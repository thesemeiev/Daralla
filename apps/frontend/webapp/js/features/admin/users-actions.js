(function () {
    function createAdminUsersActionsFeature(deps) {
        var _deps = deps || {};

        function goBackFromUserDetail() {
            _deps.showPage('admin-users');
        }

        function showDeleteUserConfirm(userId) {
            var modal = document.getElementById('delete-user-confirm-modal');
            if (!modal) {
                var modalHTML = '\n'
                    + '            <div id="delete-user-confirm-modal" class="modal admin-inline-hidden">\n'
                    + '                <div class="modal-content">\n'
                    + '                    <h2>⚠️ Удаление пользователя</h2>\n'
                    + '                    <p class="delete-modal-text">\n'
                    + '                        Вы уверены, что хотите удалить этого пользователя?<br><br>\n'
                    + '                        Это действие удалит:\n'
                    + '                        <ul class="delete-modal-list">\n'
                    + '                            <li>Все подписки пользователя</li>\n'
                    + '                            <li>Все клиенты на серверах</li>\n'
                    + '                            <li>Все платежи</li>\n'
                    + '                            <li>Все данные пользователя</li>\n'
                    + '                        </ul>\n'
                    + '                        <strong class="delete-modal-warning">Это действие нельзя отменить!</strong>\n'
                    + '                    </p>\n'
                    + '                    <div class="admin-inline-row admin-mt-lg admin-inline-row-stretch">\n'
                    + '                        <button class="btn-secondary admin-btn-modal-action" onclick="closeDeleteUserModal()">Отмена</button>\n'
                    + '                        <button class="btn-danger admin-btn-modal-action admin-btn-modal-danger" id="delete-user-confirm-btn">Удалить</button>\n'
                    + '                    </div>\n'
                    + '                </div>\n'
                    + '            </div>\n'
                    + '        ';
                document.body.insertAdjacentHTML('beforeend', modalHTML);
            }

            var confirmBtn = document.getElementById('delete-user-confirm-btn');
            if (confirmBtn) {
                confirmBtn.onclick = function () { return confirmDeleteUser(userId); };
            }

            document.getElementById('delete-user-confirm-modal').style.display = 'flex';
        }

        function closeDeleteUserModal() {
            var modal = document.getElementById('delete-user-confirm-modal');
            if (modal) modal.style.display = 'none';
            var confirmBtn = document.getElementById('delete-user-confirm-btn');
            if (confirmBtn) {
                confirmBtn.disabled = false;
                confirmBtn.textContent = 'Удалить';
            }
        }

        async function confirmDeleteUser(userId) {
            try {
                var confirmBtn = document.getElementById('delete-user-confirm-btn');
                if (confirmBtn) {
                    confirmBtn.disabled = true;
                    confirmBtn.textContent = 'Удаление...';
                }

                var response = await _deps.apiFetch('/api/admin/user/' + userId + '/delete', {
                    method: 'POST',
                    headers: { 'Content-Type': 'application/json' },
                    body: JSON.stringify({ confirm: true })
                });

                if (!response.ok) {
                    var errorData = await response.json();
                    throw new Error(errorData.error || 'Ошибка удаления пользователя');
                }

                var data = await response.json();
                closeDeleteUserModal();
                var successMsg = 'Пользователь удален:\n- Подписок: ' + data.stats.subscriptions_deleted
                    + '\n- Платежей: ' + data.stats.payments_deleted
                    + '\n- Серверов очищено: ' + data.deleted_servers.length;
                _deps.platform.showAlert(successMsg);

                setTimeout(function () {
                    _deps.showPage('admin-users');
                    _deps.loadAdminUsers(1, '');
                }, 500);

                var confirmBtnAfter = document.getElementById('delete-user-confirm-btn');
                if (confirmBtnAfter) {
                    confirmBtnAfter.disabled = false;
                    confirmBtnAfter.textContent = 'Удалить';
                }
            } catch (error) {
                console.error('Ошибка удаления пользователя:', error);
                _deps.platform.showAlert('Ошибка удаления пользователя: ' + (error && error.message));
                var confirmBtn = document.getElementById('delete-user-confirm-btn');
                if (confirmBtn) {
                    confirmBtn.disabled = false;
                    confirmBtn.textContent = 'Удалить';
                }
            }
        }

        return {
            goBackFromUserDetail: goBackFromUserDetail,
            showDeleteUserConfirm: showDeleteUserConfirm,
            closeDeleteUserModal: closeDeleteUserModal,
            confirmDeleteUser: confirmDeleteUser
        };
    }

    window.DarallaAdminUsersActionsFeature = window.DarallaAdminUsersActionsFeature || {};
    window.DarallaAdminUsersActionsFeature.create = createAdminUsersActionsFeature;
})();
