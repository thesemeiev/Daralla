(function () {
    function createNotificationsFeature(deps) {
        var _deps = deps || {};

        async function loadNotificationRules() {
            var loadingEl = document.getElementById('admin-notifications-loading');
            var listEl = document.getElementById('admin-notifications-list');
            var errorEl = document.getElementById('admin-notifications-error');
            loadingEl.style.display = 'block';
            listEl.style.display = 'none';
            errorEl.style.display = 'none';

            try {
                var response = await _deps.apiFetch('/api/admin/notification-rules', { method: 'GET' });
                if (!response.ok) throw new Error('Ошибка загрузки');
                var data = await response.json();
                loadingEl.style.display = 'none';
                listEl.style.display = 'block';

                if (!data.rules || data.rules.length === 0) {
                    listEl.innerHTML = '<p style="text-align:center;opacity:0.5;">Нет правил</p>';
                    return;
                }

                listEl.innerHTML = data.rules.map(function (rule) {
                    var badge = rule.event_type === 'expiry_warning' ? 'badge-warning' : 'badge-info';
                    var direction = rule.event_type === 'expiry_warning' ? 'до истечения' : 'после потери подписки';
                    var activeClass = rule.is_active ? 'active' : 'inactive';
                    var preview = _deps.escapeHtml(_deps.notifCardPreviewText(rule));
                    var labels = typeof _deps.getNotifEventLabels === 'function' ? _deps.getNotifEventLabels() : {};
                    return '<div class="admin-notification-card ' + activeClass + '" data-id="' + rule.id + '">' +
                        '<div class="notif-rule-header">' +
                        '<span class="notif-rule-badge ' + badge + '">' + _deps.escapeHtml(labels[rule.event_type] || rule.event_type) + '</span>' +
                        '<label class="toggle-switch toggle-sm" onclick="event.stopPropagation()">' +
                        '<input type="checkbox" ' + (rule.is_active ? 'checked' : '') +
                        ' onchange="toggleNotificationRule(' + rule.id + ', this.checked)">' +
                        '<span class="toggle-slider"></span>' +
                        '</label>' +
                        '</div>' +
                        '<div class="notif-rule-trigger">' + _deps.notifTriggerLabel(rule) + ' ' + direction + '</div>' +
                        (rule.repeat_every_hours > 0 && rule.max_repeats > 1
                            ? '<div class="notif-rule-repeat-info">Повтор: каждые ' + _deps.notifFormatHours(rule.repeat_every_hours) + ', макс. ' + rule.max_repeats + ' раз</div>'
                            : '') +
                        '<div class="notif-rule-template">' + preview + '</div>' +
                        '<div class="notif-rule-actions">' +
                        '<button class="btn-secondary btn-sm" onclick="showNotificationRuleForm(' + rule.id + ')">Изменить</button>' +
                        '<button class="btn-danger btn-sm" onclick="deleteNotificationRule(' + rule.id + ')">Удалить</button>' +
                        '</div>' +
                        '</div>';
                }).join('');
            } catch (e) {
                loadingEl.style.display = 'none';
                errorEl.textContent = 'Ошибка загрузки правил';
                errorEl.style.display = 'block';
            }
        }

        async function showNotificationRuleForm(ruleId) {
            _deps.setNotifRuleEditingId(ruleId || null);
            _deps.setNotifSelectedTriggerHours(null);

            var formTitle = document.getElementById('admin-notification-form-title');
            var eventTypeEl = document.getElementById('notif-rule-event-type');
            var titleEl = document.getElementById('notif-rule-title');
            var bodyEl = document.getElementById('notif-rule-body');
            var showTimeEl = document.getElementById('notif-rule-show-time');
            var showExpiryEl = document.getElementById('notif-rule-show-expiry');
            var activeEl = document.getElementById('notif-rule-active');

            formTitle.textContent = ruleId ? 'Изменить правило' : 'Создать правило';

            if (ruleId) {
                try {
                    var resp = await _deps.apiFetch('/api/admin/notification-rules', { method: 'GET' });
                    var data = await resp.json();
                    var rule = (data.rules || []).find(function (r) { return r.id === ruleId; });
                    if (rule) {
                        eventTypeEl.value = rule.event_type;
                        var t = _deps.notifParseTemplate(rule.message_template);
                        titleEl.value = t.title || '';
                        bodyEl.value = t.body || '';
                        showTimeEl.checked = !!t.show_time_remaining;
                        showExpiryEl.checked = !!t.show_expiry_date;
                        activeEl.checked = !!rule.is_active;
                        _deps.setRepeatData(rule.repeat_every_hours || 0, rule.max_repeats || 1);

                        var hint = document.getElementById('notif-rule-trigger-hint');
                        hint.textContent = rule.event_type === 'expiry_warning'
                            ? 'За сколько ДО истечения подписки отправить уведомление'
                            : 'Через сколько ПОСЛЕ потери подписки отправить уведомление';
                        _deps.setNotifTriggerFromHours(Math.abs(rule.trigger_hours), rule.event_type);
                    }
                } catch (e) {}
            } else {
                eventTypeEl.value = 'expiry_warning';
                titleEl.value = '';
                bodyEl.value = '';
                showTimeEl.checked = true;
                showExpiryEl.checked = true;
                activeEl.checked = true;
                _deps.setRepeatData(0, 1);
                _deps.onNotifRuleEventTypeChange();
            }

            _deps.updateNotifPreview();
            _deps.showModal('admin-notification-form-modal');
        }

        async function saveNotificationRule(event) {
            event.preventDefault();
            var eventType = document.getElementById('notif-rule-event-type').value;
            var hours = _deps.getNotifTriggerHours();
            var titleVal = (document.getElementById('notif-rule-title').value || '').trim();
            var bodyVal = (document.getElementById('notif-rule-body').value || '').trim();
            var isActive = document.getElementById('notif-rule-active').checked;

            if (!hours) { await _deps.appShowAlert('Укажите время срабатывания', { title: 'Ошибка', variant: 'error' }); return; }
            if (!titleVal && !bodyVal) { await _deps.appShowAlert('Заполните заголовок или текст сообщения', { title: 'Ошибка', variant: 'error' }); return; }

            var triggerHours = eventType === 'expiry_warning' ? -hours : hours;
            var repeat = _deps.getRepeatData();
            var payload = {
                event_type: eventType,
                trigger_hours: triggerHours,
                message_template: _deps.buildNotifTemplate(),
                is_active: isActive,
                repeat_every_hours: repeat.repeat_every_hours,
                max_repeats: repeat.max_repeats
            };

            try {
                var url = '/api/admin/notification-rules';
                var method = 'POST';
                if (_deps.getNotifRuleEditingId()) {
                    url += '/' + _deps.getNotifRuleEditingId();
                    method = 'PUT';
                }
                var resp = await _deps.apiFetch(url, {
                    method: method,
                    headers: { 'Content-Type': 'application/json' },
                    body: JSON.stringify(payload)
                });
                if (resp.ok) {
                    _deps.closeNotificationRuleForm();
                    loadNotificationRules();
                } else {
                    var d = await resp.json().catch(function () { return {}; });
                    await _deps.appShowAlert(d.error || 'Ошибка сохранения', { title: 'Ошибка', variant: 'error' });
                }
            } catch (err) { await _deps.appShowAlert('Ошибка сети', { variant: 'error' }); }
        }

        async function deleteNotificationRule(ruleId) {
            var ok = await _deps.appShowConfirm('Удалить правило уведомления?', { title: 'Подтверждение' });
            if (!ok) return;
            try {
                var r = await _deps.apiFetch('/api/admin/notification-rules/' + ruleId, { method: 'DELETE' });
                if (r.ok) loadNotificationRules(); else await _deps.appShowAlert('Ошибка удаления', { variant: 'error' });
            } catch (e) {
                await _deps.appShowAlert('Ошибка сети', { variant: 'error' });
            }
        }

        async function toggleNotificationRule(ruleId, isActive) {
            try {
                var r = await _deps.apiFetch('/api/admin/notification-rules/' + ruleId, {
                    method: 'PUT',
                    headers: { 'Content-Type': 'application/json' },
                    body: JSON.stringify({ is_active: isActive })
                });
                if (!r.ok) { await _deps.appShowAlert('Ошибка', { variant: 'error' }); loadNotificationRules(); }
            } catch (e) {
                await _deps.appShowAlert('Ошибка сети', { variant: 'error' });
                loadNotificationRules();
            }
        }

        async function testSendNotificationRule() {
            var template = _deps.buildNotifTemplate();
            var btn = document.querySelector('.btn-outline[onclick*="testSend"]');
            if (btn) { btn.disabled = true; btn.textContent = 'Отправка…'; }
            try {
                var resp = await _deps.apiFetch('/api/admin/notification-rules-test', {
                    method: 'POST',
                    headers: { 'Content-Type': 'application/json' },
                    body: JSON.stringify({ message_template: template })
                });
                var d = await resp.json().catch(function () { return {}; });
                if (resp.ok) {
                    if (btn) {
                        btn.textContent = 'Отправлено ✓';
                        setTimeout(function () { btn.textContent = 'Отправить тест мне'; btn.disabled = false; }, 2000);
                    }
                } else {
                    await _deps.appShowAlert(d.error || 'Ошибка отправки', { variant: 'error' });
                    if (btn) { btn.textContent = 'Отправить тест мне'; btn.disabled = false; }
                }
            } catch (err) {
                await _deps.appShowAlert('Ошибка сети', { variant: 'error' });
                if (btn) { btn.textContent = 'Отправить тест мне'; btn.disabled = false; }
            }
        }

        return {
            loadNotificationRules: loadNotificationRules,
            showNotificationRuleForm: showNotificationRuleForm,
            saveNotificationRule: saveNotificationRule,
            deleteNotificationRule: deleteNotificationRule,
            toggleNotificationRule: toggleNotificationRule,
            testSendNotificationRule: testSendNotificationRule
        };
    }

    window.DarallaNotificationsFeature = window.DarallaNotificationsFeature || {};
    window.DarallaNotificationsFeature.create = createNotificationsFeature;
})();
