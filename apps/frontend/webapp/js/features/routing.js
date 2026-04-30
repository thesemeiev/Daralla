(function () {
    var ROUTE_PAGE_NAMES = new Set([
        'landing', 'login', 'register',
        'subscriptions', 'subscription-detail', 'buy-subscription', 'extend-subscription', 'choose-payment-method', 'payment',
        'servers', 'events', 'event-detail', 'instructions', 'about', 'account',
        'admin-stats', 'admin-users', 'admin-broadcast', 'admin-subscriptions', 'admin-notifications',
        'admin-user-detail', 'admin-create-subscription', 'admin-subscription-edit', 'admin-server-management', 'admin-server-group',
        'admin-commerce', 'admin-events'
    ]);

    var ROUTE_PAGES_GUEST = new Set(['landing', 'login', 'register']);

    function isPageAdminOnly(pageName) {
        return pageName && pageName.startsWith('admin-');
    }

    function parseHashRoute() {
        var raw = (location.hash || '').replace(/^#/, '').trim();
        var question = raw.indexOf('?');
        var pageName = question >= 0 ? raw.slice(0, question).trim() : raw;
        var query = question >= 0 ? raw.slice(question + 1) : '';
        if (!ROUTE_PAGE_NAMES.has(pageName)) return null;
        var params = {};
        if (query) {
            try {
                var sp = new URLSearchParams(query);
                sp.forEach(function (v, k) { params[k] = v; });
            } catch (e) {}
        }
        return { pageName: pageName, params: params };
    }

    function getPageFromHash() {
        var route = parseHashRoute();
        return route ? route.pageName : null;
    }

    function buildHash(pageName, params) {
        if (!params || Object.keys(params).length === 0) return '#' + pageName;
        var q = Object.keys(params)
            .filter(function (k) { return params[k] != null && params[k] !== ''; })
            .map(function (k) { return encodeURIComponent(k) + '=' + encodeURIComponent(String(params[k])); })
            .join('&');
        return q ? '#' + pageName + '?' + q : '#' + pageName;
    }

    function isPageAllowedForUser(pageName, isAuthenticated, isAdminUser) {
        if (!pageName) return false;
        if (pageName === 'landing' && isAuthenticated) return false;
        if (ROUTE_PAGES_GUEST.has(pageName)) return true;
        if (!isAuthenticated) return false;
        if (isPageAdminOnly(pageName)) return !!isAdminUser;
        return true;
    }

    window.DarallaRouting = window.DarallaRouting || {};
    window.DarallaRouting.ROUTE_PAGE_NAMES = ROUTE_PAGE_NAMES;
    window.DarallaRouting.ROUTE_PAGES_GUEST = ROUTE_PAGES_GUEST;
    window.DarallaRouting.isPageAdminOnly = isPageAdminOnly;
    window.DarallaRouting.parseHashRoute = parseHashRoute;
    window.DarallaRouting.getPageFromHash = getPageFromHash;
    window.DarallaRouting.buildHash = buildHash;
    window.DarallaRouting.isPageAllowedForUser = isPageAllowedForUser;
})();
