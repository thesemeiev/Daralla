(function () {
    function createAdminSubscriptionCreateFeature(deps) {
        var _deps = deps || {};

        async function createSubscription(event) {
            event.preventDefault();
            try {
                var userId = _deps.getCurrentCreatingSubscriptionUserId();
                if (!userId) {
                    await _deps.appShowAlert('ID пользователя не найден.', { title: 'Ошибка', variant: 'error' });
                    return;
                }

                var form = event.target;
                var formData = {
                    period: form.period.value,
                    device_limit: parseInt(form.device_limit.value, 10),
                    name: form.name.value.trim() || null
                };
                if (form.expires_at.value) {
                    formData.expires_at = Math.floor(new Date(form.expires_at.value).getTime() / 1000);
                }

                var submitBtn = form.querySelector('button[type="submit"]');
                submitBtn.disabled = true;
                submitBtn.textContent = 'Создание...';

                var response = await _deps.apiFetch('/api/admin/user/' + userId + '/create-subscription', {
                    method: 'POST',
                    headers: { 'Content-Type': 'application/json' },
                    body: JSON.stringify(formData)
                });
                if (!response.ok) {
                    var error = await window.DarallaApiClient.responseJson(response);
                    throw new Error(error.error || 'Ошибка создания подписки');
                }

                var data = await window.DarallaApiClient.responseJson(response);
                var message = 'Подписка успешно создана!';
                if (data.failed_servers && data.failed_servers.length > 0) {
                    message += '\n\nПредупреждение: не удалось создать клиентов на серверах: '
                        + data.failed_servers.map(function (s) { return s.server; }).join(', ');
                }
                await _deps.appShowAlert(message, { title: 'Готово', variant: 'success' });

                var formEl = event.target;
                var btn = formEl && formEl.querySelector('button[type="submit"]');
                if (btn) {
                    btn.disabled = false;
                    btn.textContent = 'Создать';
                }
                _deps.goBackFromCreateSubscription();
            } catch (error) {
                console.error('Ошибка создания подписки:', error);
                await _deps.appShowAlert('Ошибка создания: ' + error.message, { title: 'Ошибка', variant: 'error' });
                var formEl2 = event.target;
                var submitBtn2 = formEl2 && formEl2.querySelector('button[type="submit"]');
                if (submitBtn2) {
                    submitBtn2.disabled = false;
                    submitBtn2.textContent = 'Создать';
                }
            }
        }

        return {
            createSubscription: createSubscription
        };
    }

    window.DarallaAdminSubscriptionCreateFeature = window.DarallaAdminSubscriptionCreateFeature || {};
    window.DarallaAdminSubscriptionCreateFeature.create = createAdminSubscriptionCreateFeature;
})();
