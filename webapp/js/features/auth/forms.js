(function () {
    function createAuthFormsFeature(deps) {
        var _deps = deps || {};

        function shakeForm(formId) {
            var form = document.getElementById(formId);
            if (!form) return;
            form.classList.remove('form-shake');
            void form.offsetHeight;
            form.classList.add('form-shake');
            setTimeout(function () { form.classList.remove('form-shake'); }, 400);
        }

        async function handleWebLogin(event) {
            event.preventDefault();
            var username = document.getElementById('login-username').value;
            var password = document.getElementById('login-password').value;
            var remember = document.getElementById('login-remember').checked;
            var btn = event.target.querySelector('button[type="submit"]');
            var originalText = btn.textContent;
            btn.disabled = true;
            btn.textContent = 'Вход...';
            try {
                var response = await fetch('/api/auth/login', {
                    method: 'POST',
                    credentials: 'include',
                    headers: { 'Content-Type': 'application/json' },
                    body: JSON.stringify({ username: username, password: password, remember: remember })
                });
                var result = await response.json();
                if (result.success) {
                    if (remember) {
                        _deps.setAuthToken(result.token);
                    } else {
                        _deps.setWebAuthToken(result.token);
                    }
                    _deps.setCurrentUserId(result.user_id);
                    var formEl = event.target;
                    var successMsg = document.getElementById('login-success-msg');
                    if (formEl && successMsg) {
                        formEl.style.display = 'none';
                        successMsg.style.display = 'block';
                        successMsg.classList.add('auth-success-visible');
                        setTimeout(function () {
                            _deps.showPage('subscriptions');
                            _deps.checkAdminAccess();
                        }, 1500);
                    } else {
                        _deps.showPage('subscriptions');
                        _deps.checkAdminAccess();
                    }
                } else {
                    shakeForm('login-form');
                    _deps.showFormMessage('login-form-message', 'error', result.error || 'Ошибка входа');
                }
            } catch (e) {
                shakeForm('login-form');
                _deps.showFormMessage('login-form-message', 'error', 'Ошибка сети');
            } finally {
                btn.disabled = false;
                btn.textContent = originalText;
            }
        }

        async function handleWebRegister(event) {
            event.preventDefault();
            var username = document.getElementById('register-username').value;
            var password = document.getElementById('register-password').value;
            var confirm = document.getElementById('register-confirm').value;
            if (password !== confirm) {
                shakeForm('register-form');
                _deps.showFormMessage('register-form-message', 'error', 'Пароли не совпадают');
                return;
            }

            var btn = event.target.querySelector('button[type="submit"]');
            var originalText = btn.textContent;
            btn.disabled = true;
            btn.textContent = 'Регистрация...';
            try {
                var response = await fetch('/api/auth/register', {
                    method: 'POST',
                    credentials: 'include',
                    headers: { 'Content-Type': 'application/json' },
                    body: JSON.stringify({ username: username, password: password })
                });
                var result = await response.json();
                if (result.success) {
                    _deps.setAuthToken(result.token);
                    _deps.setCurrentUserId(result.user_id);
                    var formEl = event.target;
                    var successMsg = document.getElementById('register-success-msg');
                    if (formEl && successMsg) {
                        formEl.style.display = 'none';
                        successMsg.style.display = 'block';
                        successMsg.classList.add('auth-success-visible');
                        setTimeout(function () {
                            _deps.showPage('subscriptions');
                            _deps.checkAdminAccess();
                        }, 1500);
                    } else {
                        _deps.showPage('subscriptions');
                        _deps.checkAdminAccess();
                    }
                } else {
                    shakeForm('register-form');
                    _deps.showFormMessage('register-form-message', 'error', result.error || 'Ошибка регистрации');
                }
            } catch (e) {
                shakeForm('register-form');
                _deps.showFormMessage('register-form-message', 'error', 'Ошибка сети');
            } finally {
                btn.disabled = false;
                btn.textContent = originalText;
            }
        }

        return {
            handleWebLogin: handleWebLogin,
            handleWebRegister: handleWebRegister
        };
    }

    window.DarallaAuthFormsFeature = window.DarallaAuthFormsFeature || {};
    window.DarallaAuthFormsFeature.create = createAuthFormsFeature;
})();
