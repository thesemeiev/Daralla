(function () {
    function createAuthAccountFeature(deps) {
        var _deps = deps || {};

        function showWebAccessModal() {
            var usernameEl = document.getElementById('web-access-username');
            var pwEl = document.getElementById('web-access-password');
            var pw2El = document.getElementById('web-access-password-confirm');
            if (usernameEl) usernameEl.value = '';
            if (pwEl) pwEl.value = '';
            if (pw2El) pw2El.value = '';
            _deps.showModal('web-access-modal');
        }

        async function handleWebAccessSetup(event) {
            event.preventDefault();
            var username = (document.getElementById('web-access-username').value || '').trim().toLowerCase();
            var password = document.getElementById('web-access-password').value;
            var confirm = document.getElementById('web-access-password-confirm').value;
            if (username.length < 3) {
                await _deps.appShowAlert('Логин должен быть не менее 3 символов', { title: 'Ошибка', variant: 'error' });
                return;
            }
            if (password.length < 6) {
                await _deps.appShowAlert('Пароль: минимум 8 символов, нужны буква и цифра', { title: 'Ошибка', variant: 'error' });
                return;
            }
            if (password !== confirm) {
                await _deps.appShowAlert('Пароли не совпадают', { title: 'Ошибка', variant: 'error' });
                return;
            }

            var btn = event.target.querySelector('button[type="submit"]');
            var originalText = btn.textContent;
            btn.disabled = true;
            btn.textContent = 'Сохранение...';
            try {
                var response = await fetch('/api/user/web-access/setup', {
                    method: 'POST',
                    headers: { 'Content-Type': 'application/json' },
                    body: JSON.stringify({
                        initData: _deps.getTgInitData(),
                        username: username,
                        password: password
                    })
                });
                var result = await response.json();
                if (result.success) {
                    _deps.closeModal('web-access-modal');
                    await refreshAboutAccount();
                    _deps.platform.showAlert(result.message);
                } else {
                    _deps.platform.showAlert(result.error || 'Ошибка при настройке');
                }
            } catch (e) {
                _deps.platform.showAlert('Ошибка сети');
            } finally {
                btn.disabled = false;
                btn.textContent = originalText;
            }
        }

        async function refreshAboutAccount() {
            var userIdEl = document.getElementById('about-user-id');
            var loginEl = document.getElementById('about-login');
            var tgIdEl = document.getElementById('about-telegram-id');
            var unlinked = document.getElementById('link-telegram-unlinked');
            var linked = document.getElementById('link-telegram-linked');
            var tgSetup = document.getElementById('tg-web-access-setup');
            var tgManage = document.getElementById('tg-web-access-manage');
            var loginSection = document.getElementById('link-telegram-section');
            if (!userIdEl || !loginEl || !tgIdEl) return;

            if (!_deps.platform.isTelegram() && !_deps.getWebAuthToken()) {
                userIdEl.textContent = '—';
                loginEl.textContent = '—';
                tgIdEl.textContent = '—';
                if (loginSection) loginSection.style.display = 'none';
                if (unlinked && linked) {
                    unlinked.style.display = 'block';
                    linked.style.display = 'none';
                }
                _deps.updateProfileCard(null, null);
                return;
            }

            try {
                var r = await _deps.apiFetch('/api/user/link-status', { method: 'GET' });
                var data = await r.json();
                if (data.success) {
                    userIdEl.textContent = data.user_id || '—';
                    loginEl.textContent = data.username || '—';
                    tgIdEl.textContent = data.telegram_id || '—';
                    _deps.updateProfileCard(data.user_id, data.username);
                    if (data.telegram_linked) {
                        if (!_deps.setProfileAvatarFromInitData()) _deps.loadProfileAvatar();
                    }
                    if (tgSetup && tgManage) {
                        if (data.web_access_enabled) {
                            tgSetup.style.display = 'none';
                            tgManage.style.display = 'block';
                        } else {
                            tgSetup.style.display = 'block';
                            tgManage.style.display = 'none';
                        }
                    }
                    if (!_deps.platform.isTelegram() || _deps.getWebAuthToken()) {
                        if (loginSection) loginSection.style.display = 'block';
                        if (unlinked && linked) {
                            if (data.telegram_linked) {
                                unlinked.style.display = 'none';
                                linked.style.display = 'block';
                            } else {
                                unlinked.style.display = 'block';
                                linked.style.display = 'none';
                            }
                        }
                    } else if (loginSection) {
                        loginSection.style.display = 'none';
                    }
                } else {
                    if (_deps.platform.isTelegram()) {
                        var u = _deps.platform.getTgUser();
                        var tid = (u && u.id != null) ? String(u.id) : '—';
                        userIdEl.textContent = '—';
                        loginEl.textContent = tid;
                        tgIdEl.textContent = tid;
                        _deps.updateProfileCard(null, tid);
                    } else {
                        _deps.updateProfileCard(null, null);
                    }
                    if (loginSection) loginSection.style.display = 'none';
                }
            } catch (e) {
                console.error('refreshAboutAccount error:', e);
                if (_deps.platform.isTelegram()) {
                    var u2 = _deps.platform.getTgUser();
                    var tid2 = (u2 && u2.id != null) ? String(u2.id) : '—';
                    userIdEl.textContent = '—';
                    loginEl.textContent = tid2;
                    tgIdEl.textContent = tid2;
                    _deps.updateProfileCard(null, tid2);
                } else {
                    _deps.updateProfileCard(null, null);
                }
            }
        }

        async function handleLinkTelegram(event) {
            if (event) event.preventDefault();
            if (_deps.platform.isTelegram() || !_deps.getWebAuthToken()) return;
            var btn = document.getElementById('link-telegram-btn');
            var originalText = btn ? btn.textContent : '';
            if (btn) {
                btn.disabled = true;
                btn.textContent = 'Переход...';
            }
            try {
                var r = await _deps.apiFetch('/api/user/link-telegram/start', { method: 'POST' });
                var data = await r.json();
                if (data.success && data.link) {
                    window.location.href = data.link;
                    return;
                }
                _deps.showFormMessage('account-form-message', 'error', data.error || 'Ошибка привязки');
            } catch (e) {
                _deps.showFormMessage('account-form-message', 'error', 'Ошибка сети');
            } finally {
                if (btn) {
                    btn.disabled = false;
                    btn.textContent = originalText;
                }
            }
        }

        async function handleChangeLogin(event) {
            event.preventDefault();
            if (!_deps.platform.isTelegram() && !_deps.getWebAuthToken()) return;
            var form = document.getElementById('form-change-login');
            var btn = form && form.querySelector('button[type="submit"]');
            var current = document.getElementById('change-login-current');
            var newLogin = document.getElementById('change-login-new');
            if (!current || !newLogin) return;
            var cur = (current.value || '').trim();
            var neu = (newLogin.value || '').trim().toLowerCase();
            if (!cur) {
                _deps.showFormMessage('account-form-message', 'error', 'Введите текущий пароль');
                return;
            }
            if (neu.length < 3) {
                _deps.showFormMessage('account-form-message', 'error', 'Логин слишком короткий (минимум 3 символа)');
                return;
            }
            if (btn) {
                btn.disabled = true;
                btn.textContent = '…';
            }
            try {
                var r = await _deps.apiFetch('/api/user/change-login', {
                    method: 'POST',
                    headers: { 'Content-Type': 'application/json' },
                    body: JSON.stringify({ current_password: cur, new_login: neu })
                });
                var data = await r.json();
                if (data.success) {
                    current.value = '';
                    newLogin.value = '';
                    _deps.closeModal('change-login-modal');
                    await refreshAboutAccount();
                    _deps.showFormMessage('account-form-message', 'success', data.message || 'Логин изменён');
                } else {
                    _deps.showFormMessage('account-form-message', 'error', data.error || 'Ошибка смены логина');
                }
            } catch (e) {
                _deps.showFormMessage('account-form-message', 'error', 'Ошибка сети');
            } finally {
                if (btn) {
                    btn.disabled = false;
                    btn.textContent = 'Сменить логин';
                }
            }
        }

        async function handleChangePassword(event) {
            event.preventDefault();
            if (!_deps.platform.isTelegram() && !_deps.getWebAuthToken()) return;
            var form = document.getElementById('form-change-password');
            var btn = form && form.querySelector('button[type="submit"]');
            var current = document.getElementById('change-pw-current');
            var newPw = document.getElementById('change-pw-new');
            var confirm = document.getElementById('change-pw-confirm');
            if (!current || !newPw || !confirm) return;
            var cur = (current.value || '').trim();
            var neu = (newPw.value || '').trim();
            var conf = (confirm.value || '').trim();
            if (!cur) {
                _deps.showFormMessage('account-form-message', 'error', 'Введите текущий пароль');
                return;
            }
            if (neu.length < 8) {
                _deps.showFormMessage('account-form-message', 'error', 'Новый пароль: минимум 8 символов, нужны буква и цифра');
                return;
            }
            if (neu !== conf) {
                _deps.showFormMessage('account-form-message', 'error', 'Пароли не совпадают');
                return;
            }
            if (btn) {
                btn.disabled = true;
                btn.textContent = '…';
            }
            try {
                var r = await _deps.apiFetch('/api/user/change-password', {
                    method: 'POST',
                    headers: { 'Content-Type': 'application/json' },
                    body: JSON.stringify({ current_password: cur, new_password: neu })
                });
                var data = await r.json();
                if (data.success) {
                    current.value = '';
                    newPw.value = '';
                    confirm.value = '';
                    _deps.closeModal('change-password-modal');
                    _deps.showFormMessage('account-form-message', 'success', data.message || 'Пароль изменён');
                } else {
                    _deps.showFormMessage('account-form-message', 'error', data.error || 'Ошибка смены пароля');
                }
            } catch (e) {
                _deps.showFormMessage('account-form-message', 'error', 'Ошибка сети');
            } finally {
                if (btn) {
                    btn.disabled = false;
                    btn.textContent = 'Сменить пароль';
                }
            }
        }

        async function handleUnlinkTelegram(event) {
            event.preventDefault();
            if (!_deps.platform.isTelegram() && !_deps.getWebAuthToken()) return;
            var form = document.getElementById('form-unlink-telegram');
            var btn = form && form.querySelector('button[type="submit"]');
            var password = document.getElementById('unlink-telegram-password');
            if (!password) return;
            var pwd = (password.value || '').trim();
            if (!pwd) {
                _deps.showFormMessage('account-form-message', 'error', 'Введите текущий пароль');
                return;
            }
            if (btn) {
                btn.disabled = true;
                btn.textContent = '…';
            }
            try {
                var r = await _deps.apiFetch('/api/user/unlink-telegram', {
                    method: 'POST',
                    headers: { 'Content-Type': 'application/json' },
                    body: JSON.stringify({ current_password: pwd })
                });
                var data = await r.json();
                if (data.success) {
                    password.value = '';
                    _deps.closeModal('unlink-telegram-modal');
                    await refreshAboutAccount();
                    _deps.showFormMessage('account-form-message', 'success', data.message || 'Telegram успешно отвязан');
                } else {
                    _deps.showFormMessage('account-form-message', 'error', data.error || 'Ошибка отвязки Telegram');
                }
            } catch (e) {
                _deps.showFormMessage('account-form-message', 'error', 'Ошибка сети');
            } finally {
                if (btn) {
                    btn.disabled = false;
                    btn.textContent = 'Отвязать';
                }
            }
        }

        return {
            showWebAccessModal: showWebAccessModal,
            handleWebAccessSetup: handleWebAccessSetup,
            refreshAboutAccount: refreshAboutAccount,
            handleLinkTelegram: handleLinkTelegram,
            handleChangeLogin: handleChangeLogin,
            handleChangePassword: handleChangePassword,
            handleUnlinkTelegram: handleUnlinkTelegram
        };
    }

    window.DarallaAuthAccountFeature = window.DarallaAuthAccountFeature || {};
    window.DarallaAuthAccountFeature.create = createAuthAccountFeature;
})();
