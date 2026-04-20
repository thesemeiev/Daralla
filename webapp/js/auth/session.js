(function () {
    function createAuthStorage() {
        var config = {
            DB_NAME: 'daralla_auth',
            DB_VERSION: 1,
            STORE: 'keyval',
            KEY: 'web_token'
        };

        function openDb() {
            return new Promise(function (resolve, reject) {
                try {
                    if (!window.indexedDB) {
                        resolve(null);
                        return;
                    }
                    var req = indexedDB.open(config.DB_NAME, config.DB_VERSION);
                    req.onupgradeneeded = function (e) {
                        if (!e.target.result.objectStoreNames.contains(config.STORE)) {
                            e.target.result.createObjectStore(config.STORE);
                        }
                    };
                    req.onsuccess = function (e) { resolve(e.target.result); };
                    req.onerror = function () { reject(req.error || new Error('indexeddb open failed')); };
                } catch (err) {
                    reject(err);
                }
            });
        }

        return {
            get: function () {
                return new Promise(function (resolve) {
                    openDb().then(function (db) {
                        if (!db) {
                            resolve(null);
                            return;
                        }
                        var tx = db.transaction(config.STORE, 'readonly');
                        var store = tx.objectStore(config.STORE);
                        var getReq = store.get(config.KEY);
                        getReq.onsuccess = function () { resolve(getReq.result || null); };
                        getReq.onerror = function () { resolve(null); };
                        tx.onerror = function () { resolve(null); };
                    }).catch(function () {
                        resolve(null);
                    });
                });
            },
            set: function (value) {
                return new Promise(function (resolve) {
                    openDb().then(function (db) {
                        if (!db) {
                            resolve();
                            return;
                        }
                        var tx = db.transaction(config.STORE, 'readwrite');
                        var store = tx.objectStore(config.STORE);
                        store.put(value, config.KEY);
                        tx.oncomplete = function () { resolve(); };
                        tx.onerror = function () { resolve(); };
                    }).catch(function () {
                        resolve();
                    });
                });
            },
            remove: function () {
                return new Promise(function (resolve) {
                    openDb().then(function (db) {
                        if (!db) {
                            resolve();
                            return;
                        }
                        var tx = db.transaction(config.STORE, 'readwrite');
                        var store = tx.objectStore(config.STORE);
                        store.delete(config.KEY);
                        tx.oncomplete = function () { resolve(); };
                        tx.onerror = function () { resolve(); };
                    }).catch(function () {
                        resolve();
                    });
                });
            }
        };
    }

    var authStorage = createAuthStorage();

    function getInitialToken() {
        try {
            return localStorage.getItem('web_token');
        } catch (e) {
            return null;
        }
    }

    function setAuthToken(token) {
        try {
            localStorage.setItem('web_token', token);
        } catch (e) {}
        authStorage.set(token);
        return token;
    }

    function removeAuthToken() {
        try {
            localStorage.removeItem('web_token');
        } catch (e) {}
        authStorage.remove();
        return null;
    }

    async function hydrateTokenFromIndexedDb(currentToken) {
        var idbToken = await authStorage.get();
        if (idbToken && !currentToken) {
            try {
                localStorage.setItem('web_token', idbToken);
            } catch (e) {}
            return idbToken;
        }
        return currentToken;
    }

    window.DarallaAuthSession = {
        authStorage: authStorage,
        getInitialToken: getInitialToken,
        setAuthToken: setAuthToken,
        removeAuthToken: removeAuthToken,
        hydrateTokenFromIndexedDb: hydrateTokenFromIndexedDb
    };
})();
