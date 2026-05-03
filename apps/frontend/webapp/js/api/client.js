(function (window) {
    'use strict';

    function _sleep(ms) {
        return new Promise(function (resolve) {
            setTimeout(resolve, ms);
        });
    }

    /** nginx из setup_nginx_after_ssl.sh отдаёт 503 текстом «Bot is starting» пока upstream не поднялся */
    var TRANSIENT_HTTP = [502, 503];
    var TRANSIENT_MAX_ATTEMPTS = 15;

    /**
     * Читает тело ответа и парсит JSON. Если пришла HTML/текст ошибки прокси («Service…»),
     * даёт понятную ошибку вместо SyntaxError от JSON.parse.
     */
    async function responseJson(response) {
        var text = await response.text();
        var trimmed = (text || '').trim();
        if (!trimmed) {
            return {};
        }
        try {
            return JSON.parse(trimmed);
        } catch (parseErr) {
            var preview = trimmed.length > 200 ? trimmed.slice(0, 200) + '…' : trimmed;
            var hint = '';
            var low = trimmed.slice(0, 80).toLowerCase();
            var booting = /bot is starting|starting\.{3}|temporarily unavailable/.test(low);
            if (booting) {
                hint = 'Сервер ещё запускается или nginx не достучался до приложения. Подождите минуту и обновите страницу. ';
            } else if (response.status >= 502 || low.indexOf('<!doctype') >= 0 || low.indexOf('<html') >= 0) {
                hint = 'Сервис временно недоступен или вернул страницу ошибки вместо JSON. ';
            } else if (/^service\s/i.test(trimmed)) {
                hint = 'Прокси или бэкенд вернули текст ошибки вместо JSON. ';
            }
            throw new Error(hint + 'HTTP ' + response.status + ': ' + preview);
        }
    }

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
            var response;
            var transientAttempts = 0;
            while (true) {
                response = await fetch(url, options);
                var st = response.status;
                var transient = TRANSIENT_HTTP.indexOf(st) >= 0;
                if (!transient || transientAttempts >= TRANSIENT_MAX_ATTEMPTS - 1) {
                    break;
                }
                transientAttempts++;
                var waitMs = Math.min(2800, 380 + transientAttempts * 320);
                console.warn('[API] HTTP ' + st + ', повтор через ' + waitMs + ' мс (' + transientAttempts + '/' + TRANSIENT_MAX_ATTEMPTS + ') ' + url);
                await _sleep(waitMs);
            }
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
        apiFetch: apiFetch,
        responseJson: responseJson
    };
})(window);
