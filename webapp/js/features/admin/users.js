(function () {
    function createAdminUsersFeature(deps) {
        var _deps = deps || {};

        function showCreateSubscriptionForm(userId) {
            if (typeof _deps.setCurrentCreatingSubscriptionUserId === 'function') {
                _deps.setCurrentCreatingSubscriptionUserId(userId);
            }
            if (typeof _deps.setPreviousAdminPage === 'function') {
                _deps.setPreviousAdminPage('admin-user-detail');
            }
            _deps.showPage('admin-create-subscription', userId ? { userId: userId } : {});

            var nameEl = document.getElementById('create-sub-name');
            var expiresEl = document.getElementById('create-sub-expires-at');
            var limitEl = document.getElementById('create-sub-device-limit');
            var periodEl = document.getElementById('create-sub-period');
            if (nameEl) nameEl.value = '';
            if (expiresEl) expiresEl.value = '';
            if (limitEl) limitEl.value = '1';
            if (periodEl) periodEl.value = 'month';

            var form = document.getElementById('admin-create-subscription-form');
            if (form) {
                var submitBtn = form.querySelector('button[type="submit"]');
                if (submitBtn) {
                    submitBtn.disabled = false;
                    submitBtn.textContent = 'Создать';
                }
            }
        }

        function goBackFromCreateSubscription() {
            var previousAdminPage = typeof _deps.getPreviousAdminPage === 'function'
                ? _deps.getPreviousAdminPage()
                : null;
            var currentCreatingSubscriptionUserId = typeof _deps.getCurrentCreatingSubscriptionUserId === 'function'
                ? _deps.getCurrentCreatingSubscriptionUserId()
                : null;
            if (previousAdminPage === 'admin-user-detail' && currentCreatingSubscriptionUserId) {
                _deps.showAdminUserDetail(currentCreatingSubscriptionUserId);
            } else {
                _deps.showPage('admin-users');
            }
            if (typeof _deps.setCurrentCreatingSubscriptionUserId === 'function') {
                _deps.setCurrentCreatingSubscriptionUserId(null);
            }
        }

        return {
            showCreateSubscriptionForm: showCreateSubscriptionForm,
            goBackFromCreateSubscription: goBackFromCreateSubscription
        };
    }

    window.DarallaAdminUsersFeature = window.DarallaAdminUsersFeature || {};
    window.DarallaAdminUsersFeature.create = createAdminUsersFeature;
})();
