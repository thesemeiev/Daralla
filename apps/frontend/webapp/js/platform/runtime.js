(function () {
    // Парсим initData из URL hash (Telegram передаёт tgWebAppData в hash при открытии Mini App).
    function parseInitDataFromHash() {
        var hash = (window.location.hash || '').replace(/^#/, '');
        if (!hash || hash.indexOf('tgWebAppData') === -1) return null;
        var queryPart = hash;
        var qIdx = hash.indexOf('?');
        if (qIdx >= 0) queryPart = hash.substr(qIdx + 1);
        var params = {};
        queryPart.split('&').forEach(function (p) {
            var eq = p.indexOf('=');
            if (eq >= 0) {
                params[decodeURIComponent(p.substr(0, eq))] = decodeURIComponent(p.substr(eq + 1));
            }
        });
        var raw = params.tgWebAppData;
        if (!raw) return null;
        var unsafe = { user: {} };
        raw.split('&').forEach(function (p) {
            var eq = p.indexOf('=');
            if (eq >= 0) {
                var k = decodeURIComponent(p.substr(0, eq));
                var v = decodeURIComponent(p.substr(eq + 1));
                try {
                    if ((v.charAt(0) === '{' && v.slice(-1) === '}') || (v.charAt(0) === '[' && v.slice(-1) === ']')) {
                        v = JSON.parse(v);
                    }
                } catch (e) {}
                unsafe[k] = v;
            }
        });
        if (unsafe.user && typeof unsafe.user === 'object') {
            unsafe.user = unsafe.user;
        }
        return { initData: raw, initDataUnsafe: unsafe };
    }

    // Telegram Web App API — заглушка, если скрипт не загрузился.
    var TG_STUB = {
        initData: '',
        initDataUnsafe: { user: {} },
        ready: function () {},
        expand: function () {},
        setHeaderColor: function () {},
        setBackgroundColor: function () {},
        disableVerticalSwipes: false,
        openLink: function () {},
        showAlert: function () {},
        showConfirm: function (msg, cb) { if (typeof cb === 'function') cb(false); },
        MainButton: {
            setText: function () {},
            show: function () {},
            hide: function () {},
            disable: function () {},
            enable: function () {}
        }
    };

    var MINI_APP_HOST = 'app.daralla.ru';

    function isMiniAppHost() {
        return typeof window !== 'undefined' && window.location && (window.location.hostname || '').toLowerCase() === MINI_APP_HOST;
    }

    function createPlatform(deps) {
        var _deps = deps || {};
        var _tg = (typeof window !== 'undefined' && window.Telegram && window.Telegram.WebApp) ? window.Telegram.WebApp : TG_STUB;
        var _isTelegram = !!(_tg && _tg.initData);

        function getTheme() {
            return typeof _deps.getTheme === 'function' ? _deps.getTheme() : 'dark';
        }

        function getRoute() {
            if (typeof _deps.parseHashRoute === 'function') return _deps.parseHashRoute();
            return null;
        }

        function getRoutePageNames() {
            return _deps.routePageNames instanceof Set ? _deps.routePageNames : new Set();
        }

        function getWebToken() {
            return typeof _deps.getWebAuthToken === 'function' ? _deps.getWebAuthToken() : null;
        }

        function applyTgUi() {
            if (!_isTelegram || !_tg) return;
            try {
                _tg.ready();
                _tg.expand();
                if (_tg.disableVerticalSwipes) _tg.disableVerticalSwipes();
                var color = getTheme() === 'light' ? '#f0f0f2' : '#131314';
                _tg.setHeaderColor(color);
                _tg.setBackgroundColor(color);
            } catch (e) {}
        }

        var api = {
            init: function () {
                if (!isMiniAppHost()) {
                    _isTelegram = false;
                    _tg = TG_STUB;
                    return Promise.resolve();
                }
                var hashInit = parseInitDataFromHash();
                if (hashInit && hashInit.initData) {
                    _tg = Object.assign({}, TG_STUB, { initData: hashInit.initData, initDataUnsafe: hashInit.initDataUnsafe || { user: {} } });
                    _isTelegram = true;
                    try { sessionStorage.setItem('tg_init_data', _tg.initData); } catch (e) {}
                    return _deps.loadTelegramScript(400).then(function () {
                        if (window.Telegram && window.Telegram.WebApp) {
                            _tg = window.Telegram.WebApp;
                            try { sessionStorage.setItem('tg_init_data', _tg.initData); } catch (e) {}
                        }
                        applyTgUi();
                    });
                }
                var stored = '';
                try { stored = sessionStorage.getItem('tg_init_data') || ''; } catch (e) {}
                if (stored) {
                    _tg = Object.assign({}, TG_STUB, { initData: stored, initDataUnsafe: { user: {} } });
                    _isTelegram = true;
                    return _deps.loadTelegramScript(400).then(function () {
                        if (window.Telegram && window.Telegram.WebApp) {
                            _tg = window.Telegram.WebApp;
                            try { sessionStorage.setItem('tg_init_data', _tg.initData); } catch (e) {}
                        }
                        applyTgUi();
                    });
                }
                return _deps.loadTelegramScript(400).then(function () {
                    _tg = (window.Telegram && window.Telegram.WebApp) ? window.Telegram.WebApp : TG_STUB;
                    _isTelegram = !!(_tg && _tg.initData);
                    if (_tg.initData) try { sessionStorage.setItem('tg_init_data', _tg.initData); } catch (e) {}
                    applyTgUi();
                });
            },
            isTelegram: function () { return _isTelegram; },
            getAuth: function () {
                if (_isTelegram && _tg && _tg.initData) return { type: 'tg', initData: _tg.initData };
                return { type: 'web', token: getWebToken() || null };
            },
            reapplyTgUi: applyTgUi,
            getTgRef: function () { return _tg; },
            getTgUser: function () { return _tg && _tg.initDataUnsafe && _tg.initDataUnsafe.user ? _tg.initDataUnsafe.user : null; },
            openExternalUrl: function (url) {
                if (!url || String(url).indexOf('http') !== 0) return;
                if (_isTelegram) {
                    var webApp = (typeof window !== 'undefined' && window.Telegram && window.Telegram.WebApp) ? window.Telegram.WebApp : _tg;
                    var hasOpenLink = webApp && typeof webApp.openLink === 'function' && webApp.openLink !== TG_STUB.openLink;
                    if (hasOpenLink) {
                        try {
                            webApp.openLink(url);
                        } catch (err) {
                            window.location.href = url;
                        }
                    } else {
                        window.location.href = url;
                    }
                } else {
                    var a = document.createElement('a');
                    a.href = url;
                    a.target = '_blank';
                    a.rel = 'noopener noreferrer';
                    a.style.display = 'none';
                    document.body.appendChild(a);
                    a.click();
                    document.body.removeChild(a);
                }
            },
            getDefaultPage: function (isAuthenticated) {
                if (_isTelegram) return 'subscriptions';
                var route = getRoute();
                if (route && getRoutePageNames().has(route.pageName)) return route.pageName;
                return isAuthenticated ? 'subscriptions' : 'landing';
            },
            canShowPage: function (pageName) {
                if (_isTelegram && pageName === 'landing') return false;
                return true;
            },
            mainButton: {
                _onClick: null,
                show: function (text, onClick) {
                    if (!_isTelegram || !_tg || !_tg.MainButton) return;
                    try {
                        this._onClick = onClick;
                        _tg.MainButton.setText(text || '');
                        _tg.MainButton.onClick(function () {
                            if (typeof api.mainButton._onClick === 'function') api.mainButton._onClick();
                        });
                        _tg.MainButton.show();
                    } catch (e) { console.warn('MainButton.show error', e); }
                },
                hide: function () {
                    if (!_isTelegram || !_tg || !_tg.MainButton) return;
                    try { _tg.MainButton.hide(); } catch (e) {}
                    this._onClick = null;
                },
                disable: function () {
                    if (_isTelegram && _tg && _tg.MainButton && typeof _tg.MainButton.disable === 'function') _tg.MainButton.disable();
                },
                enable: function () {
                    if (_isTelegram && _tg && _tg.MainButton && typeof _tg.MainButton.enable === 'function') _tg.MainButton.enable();
                }
            },
            showAlert: function (msg) {
                _deps.appShowAlert(String(msg || ''), { title: 'Сообщение' });
            },
            showConfirm: function (msg, callback) {
                _deps.appShowConfirm(String(msg || ''), { title: 'Подтверждение' }).then(function (ok) {
                    if (typeof callback === 'function') callback(ok);
                });
            }
        };

        return api;
    }

    window.DarallaPlatform = window.DarallaPlatform || {};
    window.DarallaPlatform.parseInitDataFromHash = parseInitDataFromHash;
    window.DarallaPlatform.TG_STUB = TG_STUB;
    window.DarallaPlatform.MINI_APP_HOST = MINI_APP_HOST;
    window.DarallaPlatform.isMiniAppHost = isMiniAppHost;
    window.DarallaPlatform.createPlatform = createPlatform;
})();
