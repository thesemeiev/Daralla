(function () {
    function bindSubmit(formId, handler) {
        var form = document.getElementById(formId);
        if (!form || typeof handler !== 'function') return;
        form.addEventListener('submit', function (event) {
            handler(event);
        });
    }

    function bindClickById(elementId, handler) {
        var el = document.getElementById(elementId);
        if (!el || typeof handler !== 'function') return;
        el.addEventListener('click', function (event) {
            handler(event);
        });
    }

    function bindChangeById(elementId, handler) {
        var el = document.getElementById(elementId);
        if (!el || typeof handler !== 'function') return;
        el.addEventListener('change', function (event) {
            handler(event);
        });
    }

    function bindProxyCheckboxToggle(containerId, inputId) {
        var container = document.getElementById(containerId);
        var input = document.getElementById(inputId);
        if (!container || !input) return;
        container.addEventListener('click', function (event) {
            if (event.target === input) return;
            input.click();
        });
    }

    function bindSelectOnClickById(elementId) {
        var el = document.getElementById(elementId);
        if (!el) return;
        el.addEventListener('click', function () {
            if (typeof el.select === 'function') el.select();
        });
    }

    function bindActionButtons(api) {
        document.querySelectorAll('[data-action]').forEach(function (el) {
            var action = el.getAttribute('data-action');
            var handler = action && (api[action] || window[action]);
            if (typeof handler !== 'function') return;
            var arg = el.getAttribute('data-arg');
            el.addEventListener('click', function (event) {
                if (arg !== null) handler(arg);
                else handler(event);
            });
        });
    }

    function init(api) {
        api = api || {};
        bindSubmit('login-form', api.handleWebLogin);
        bindSubmit('register-form', api.handleWebRegister);
        bindSubmit('web-access-form', api.handleWebAccessSetup);
        bindSubmit('admin-notification-form', api.saveNotificationRule);
        bindSubmit('admin-event-form', api.submitAdminEventForm);
        bindSubmit('admin-create-subscription-form', api.createSubscription);
        bindSubmit('admin-subscription-edit-form', api.saveSubscriptionChanges);
        bindSubmit('admin-commerce-form', api.saveAdminCommerce);
        bindSubmit('server-group-form', api.saveServerGroup);
        bindSubmit('server-config-form', api.saveServerConfig);
        bindSubmit('form-change-login', api.handleChangeLogin);
        bindSubmit('form-change-password', api.handleChangePassword);
        bindSubmit('form-unlink-telegram', api.handleUnlinkTelegram);

        bindClickById('profile-card', function () { api.showPage('account'); });
        bindClickById('link-telegram-btn', api.handleLinkTelegram);
        bindClickById('logout-account-btn', api.logout);
        bindClickById('admin-server-group-edit-btn', function () {
            if (typeof api.getCurrentSelectedGroupId !== 'function') return;
            var groupId = api.getCurrentSelectedGroupId();
            if (!groupId) return;
            api.editServerGroup(groupId);
        });
        bindProxyCheckboxToggle('login-remember-wrap', 'login-remember');
        bindProxyCheckboxToggle('group-default-wrap', 'group-default-input');
        bindSelectOnClickById('subscription-copy-manual-url');
        bindSelectOnClickById('generic-copy-manual-url');
        bindActionButtons(api);
        bindChangeById('notif-rule-event-type', api.onNotifRuleEventTypeChange);
        bindChangeById('notif-rule-show-time', api.updateNotifPreview);
        bindChangeById('notif-rule-show-expiry', api.updateNotifPreview);
        bindChangeById('notif-rule-repeat', api.toggleRepeatFields);
        bindChangeById('admin-subscriptions-status', api.reloadAdminSubscriptionsWithFilters);

        document.querySelectorAll('.bottom-nav .nav-item[data-page]').forEach(function (item) {
            item.addEventListener('click', function () {
                var page = item.getAttribute('data-page');
                if (page && typeof api.showPage === 'function') api.showPage(page);
            });
        });
    }

    window.DarallaDomBindings = { init: init };
})();
