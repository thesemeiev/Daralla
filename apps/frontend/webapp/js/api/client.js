(function (window) {
    'use strict';

    async function apiFetch(url, options, deps) {
        options = options || {};
        deps = deps || {};
        var platform = deps.platform || window.platform;
        var logout = deps.logout || window.logout;
        if (!platform || typeof platform.getAuth !== 'function') {
            throw new Error('platform.getAuth is required');
        }

        if (!options.headers) options.headers = {};
        var auth = platform.getAuth();
        if (auth.type === 'tg' && auth.initData) {
            var separator = url.includes('?') ? '&' : '?';
            url = url + separator + 'initData=' + encodeURIComponent(auth.initData);
        } else if (auth.type === 'web' && auth.token) {
            options.headers['Authorization'] = 'Bearer ' + auth.token;
        }
        if ((options.method === 'POST' || options.method === 'PUT') && !options.body) {
            options.body = JSON.stringify({});
            if (!options.headers['Content-Type']) {
                options.headers['Content-Type'] = 'application/json';
            }
        }
        options.credentials = options.credentials || 'include';
        console.log('[API] Запрос: ' + (options.method || 'GET') + ' ' + url, {
            mode: platform.isTelegram && platform.isTelegram() ? 'Telegram' : 'Web',
            hasToken: !!(auth.token || auth.initData)
        });
        try {
            var response = await fetch(url, options);
            if (response.status === 401 && (!platform.isTelegram || !platform.isTelegram())) {
                console.warn('[API] Ошибка 401: Токен недействителен или истек');
                if (typeof logout === 'function') {
                    logout();
                }
            }
            return response;
        } catch (e) {
            console.error('[API] Ошибка сетевого запроса (' + url + '):', e);
            throw e;
        }
    }

    window.DarallaApiClient = {
        apiFetch: apiFetch
    };
})(window);
