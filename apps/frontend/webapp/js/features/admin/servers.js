(function () {
    function createAdminServersFeature(deps) {
        var _deps = deps || {};
        var SERVER_CLIENT_FLOW_VALUE = 'xtls-rprx-vision';
        var _GIB = Math.pow(1024, 3);

        function getGroups() { return _deps.getCurrentAdminGroups(); }
        function setGroups(v) { _deps.setCurrentAdminGroups(v); }
        function getServers() { return _deps.getCurrentAdminServers(); }
        function setServers(v) { _deps.setCurrentAdminServers(v); }
        function getGroupId() { return _deps.getCurrentSelectedGroupId(); }
        function setGroupId(v) { _deps.setCurrentSelectedGroupId(v); }
        function getReorder() { return !!_deps.getAdminServerReorderMode(); }
        function setReorder(v) { _deps.setAdminServerReorderMode(!!v); }

        function showAdminToast(message, duration) {
            duration = duration || 4500;
            var el = document.getElementById('admin-toast');
            if (!el) {
                el = document.createElement('div');
                el.id = 'admin-toast';
                el.className = 'admin-toast';
                el.setAttribute('role', 'status');
                document.body.appendChild(el);
            }
            el.textContent = message;
            el.classList.add('admin-toast--visible');
            clearTimeout(showAdminToast._timer);
            showAdminToast._timer = setTimeout(function () {
                el.classList.remove('admin-toast--visible');
            }, duration);
        }

        function adminSyncSubscriptionsAlertMessage(result) {
            var parts = [];
            if (result.sync_stats) {
                var s = result.sync_stats;
                if (s.clients_created != null) parts.push('клиентов создано: ' + s.clients_created);
                if (s.servers_added != null) parts.push('серверов добавлено: ' + s.servers_added);
                if (s.servers_removed != null) parts.push('серверов снято: ' + s.servers_removed);
                if (s.errors && s.errors.length) parts.push('ошибки: ' + s.errors.slice(0, 5).join('; '));
            }
            var msg = 'Синхронизация подписок с серверами: ' + (parts.length ? parts.join(', ') : 'OK');
            if (result.sync_error) msg += '\nПредупреждение: ' + result.sync_error;
            return msg;
        }

        async function loadServerManagement() {
            var loadingEl = document.getElementById('admin-server-management-loading');
            var contentEl = document.getElementById('admin-server-management-content');
            if (loadingEl) loadingEl.style.display = 'block';
            if (contentEl) contentEl.style.display = 'none';
            try {
                await loadServerGroups();
                if (loadingEl) loadingEl.style.display = 'none';
                if (contentEl) contentEl.style.display = 'block';
            } catch (err) {
                console.error('Ошибка загрузки управления серверами:', err);
                if (loadingEl) loadingEl.style.display = 'none';
                await _deps.appShowAlert('Ошибка при загрузке данных: ' + err.message, { title: 'Ошибка', variant: 'error' });
            }
        }

        async function loadServerGroups() {
            var listEl = document.getElementById('admin-server-groups-list');
            try {
                var response = await _deps.apiFetch('/api/admin/server-groups', {
                    method: 'POST',
                    headers: { 'Content-Type': 'application/json' },
                    body: JSON.stringify({ action: 'list' })
                });
                if (!response.ok) throw new Error('Ошибка сети при получении групп');
                var result = await response.json();
                if (result.success) {
                    setGroups(result.groups || []);
                    renderServerGroups(getGroups(), result.stats || []);
                } else {
                    throw new Error(result.error || 'Ошибка API');
                }
            } catch (err) {
                console.error('Ошибка в loadServerGroups:', err);
                if (listEl) listEl.innerHTML = '<p class="error-text">Ошибка: ' + err.message + '</p>';
                throw err;
            }
        }

        function renderServerGroups(groups, stats) {
            var listEl = document.getElementById('admin-server-groups-list');
            if (!listEl) return;
            if (!groups || groups.length === 0) {
                listEl.innerHTML = '<div class="admin-sm-empty"><p class="admin-sm-empty-title">Групп пока нет</p><p class="admin-sm-empty-hint">Создайте первую группу — в неё добавятся серверы для подписок.</p></div>';
                return;
            }
            var cards = groups.map(function (group) {
                var groupStats = (stats || []).find(function (s) { return s.id === group.id; }) || {};
                var safeName = _deps.escapeHtml(group.name);
                var subs = groupStats.active_subscriptions || 0;
                var srv = groupStats.active_servers || 0;
                return '\n'
                    + '            <div id="group-card-' + group.id + '" class="admin-user-card group-card" role="button" tabindex="0" data-group-id="' + group.id + '"\n'
                    + '                onclick="showPage(\'admin-server-group\', { groupId: \'' + group.id + '\' })"\n'
                    + '                onkeydown="if(event.key===\'Enter\'||event.key===\' \'){event.preventDefault();showPage(\'admin-server-group\', { groupId: \'' + group.id + '\' });}">\n'
                    + '                <div class="card-content-wrapper">\n'
                    + '                    <div class="card-main-info">\n'
                    + '                        <div class="card-title-row">\n'
                    + '                            <span class="card-title">' + safeName + '</span>\n'
                    + '                            <div class="card-badges">\n'
                    + (group.is_default ? '<span class="badge-default">По умолчанию</span>' : '')
                    + (!group.is_active ? '<span class="badge-inactive">Неактивна</span>' : '')
                    + '                            </div>\n'
                    + '                        </div>\n'
                    + '                        <div class="card-description">' + _deps.escapeHtml(group.description || 'Без описания') + '</div>\n'
                    + '                        <div class="card-stats-row">\n'
                    + '                            <span class="admin-stat-pill" title="Активные подписки"><span class="admin-stat-pill__value">' + subs + '</span> подписок</span>\n'
                    + '                            <span class="admin-stat-pill" title="Активные серверы в группе"><span class="admin-stat-pill__value">' + srv + '</span> серверов</span>\n'
                    + '                        </div>\n'
                    + '                    </div>\n'
                    + '                    <div class="group-card-side">\n'
                    + '                        <button type="button" class="btn-secondary card-action-btn" onclick="event.stopPropagation(); editServerGroup(' + group.id + ')">Изменить</button>\n'
                    + '                        <span class="group-card-chevron" aria-hidden="true"></span>\n'
                    + '                    </div>\n'
                    + '                </div>\n'
                    + '            </div>\n';
            }).join('');
            listEl.innerHTML = '<div class="admin-server-groups-grid">' + cards + '</div>';
        }

        function showAddServerGroupModal() {
            var titleEl = document.getElementById('server-group-modal-title');
            var idEl = document.getElementById('group-id-input');
            var nameEl = document.getElementById('group-name-input');
            var descEl = document.getElementById('group-desc-input');
            var defaultEl = document.getElementById('group-default-input');
            if (titleEl) titleEl.innerText = 'Добавить группу';
            if (idEl) idEl.value = '';
            if (nameEl) nameEl.value = '';
            if (descEl) descEl.value = '';
            if (defaultEl) defaultEl.checked = false;
            _deps.showModal('server-group-modal');
        }

        function editServerGroup(groupId) {
            if (groupId == null || groupId === '') return;
            var group = getGroups().find(function (g) { return g.id === groupId; });
            if (!group) return;
            document.getElementById('server-group-modal-title').innerText = 'Редактировать группу';
            document.getElementById('group-id-input').value = group.id;
            document.getElementById('group-name-input').value = group.name;
            document.getElementById('group-desc-input').value = group.description || '';
            document.getElementById('group-default-input').checked = !!group.is_default;
            _deps.showModal('server-group-modal');
        }

        async function saveServerGroup(event) {
            event.preventDefault();
            var id = document.getElementById('group-id-input').value;
            var name = document.getElementById('group-name-input').value;
            var description = document.getElementById('group-desc-input').value;
            var is_default = document.getElementById('group-default-input').checked ? 1 : 0;
            try {
                var url = id ? '/api/admin/server-group/update' : '/api/admin/server-groups';
                var body = { name: name, description: description, is_default: is_default, action: id ? undefined : 'add', id: id || undefined };
                var response = await _deps.apiFetch(url, {
                    method: 'POST',
                    headers: { 'Content-Type': 'application/json' },
                    body: JSON.stringify(body)
                });
                var result = await response.json();
                if (result.success) {
                    _deps.closeModal('server-group-modal');
                    loadServerGroups();
                } else {
                    await _deps.appShowAlert('Ошибка: ' + result.error, { title: 'Ошибка', variant: 'error' });
                }
            } catch (err) {
                console.error('Ошибка сохранения группы:', err);
                await _deps.appShowAlert('Ошибка при сохранении', { title: 'Ошибка', variant: 'error' });
            }
        }

        async function loadAdminServerGroupPage(groupId) {
            var gid = Number(groupId);
            if (!gid || isNaN(gid)) {
                setGroupId(null);
                _deps.showPage('admin-server-management');
                return;
            }
            setGroupId(gid);
            if (!getGroups() || !getGroups().length) {
                try {
                    await loadServerGroups();
                } catch (e) {
                    setGroupId(null);
                    _deps.showPage('admin-server-management');
                    return;
                }
            }
            var g = getGroups().find(function (x) { return x.id === gid; });
            if (!g) {
                setGroupId(null);
                _deps.showPage('admin-server-management');
                return;
            }
            setReorder(false);
            var reorderBtn = document.getElementById('admin-server-reorder-toggle-btn');
            if (reorderBtn) {
                reorderBtn.textContent = 'Порядок';
                reorderBtn.classList.remove('is-active');
            }
            var groupRoot = document.getElementById('admin-server-group-page-root');
            if (groupRoot) groupRoot.classList.remove('admin-server-group-page--reorder');
            var titleEl = document.getElementById('admin-server-group-page-title');
            if (titleEl) titleEl.textContent = g.name ? ('Серверы — ' + g.name) : 'Серверы';
            var listEl = document.getElementById('admin-servers-in-group-list');
            if (!listEl) return;
            listEl.innerHTML = '<div class="spinner"></div>';
            try {
                var response = await _deps.apiFetch('/api/admin/servers-config', {
                    method: 'POST',
                    headers: { 'Content-Type': 'application/json' },
                    body: JSON.stringify({ action: 'list', group_id: gid })
                });
                var result = await response.json();
                if (result.success) {
                    setServers(result.servers);
                    renderServersInGroup(result.servers);
                    await loadGroupTrafficTemplateForm();
                } else {
                    listEl.innerHTML = '<p class="error-text">Ошибка загрузки</p>';
                }
            } catch (err) {
                console.error('Ошибка загрузки серверов:', err);
                listEl.innerHTML = '<p class="error-text">Ошибка загрузки</p>';
            }
        }

        function _bytesFromGib(gib) {
            var g = parseFloat(gib);
            if (isNaN(g) || g < 0) return 0;
            return Math.round(g * _GIB);
        }

        function _gibFromBytes(bytes) {
            var b = Number(bytes) || 0;
            if (b <= 0) return '';
            return (Math.round((b / _GIB) * 1000) / 1000).toString();
        }

        function renderTrafficLimitedServerChecks(servers, selectedSet) {
            var wrap = document.getElementById('sg-traffic-limited-servers');
            if (!wrap) return;
            var sel = selectedSet || {};
            if (!servers || !servers.length) {
                wrap.innerHTML = '<p class="hint">В группе пока нет серверов.</p>';
                return;
            }
            var sorted = sortAdminServersByClientOrder(servers.slice());
            wrap.innerHTML = sorted.map(function (s) {
                var name = s.name || '';
                var checked = sel[name] ? 'checked' : '';
                return ''
                    + '<label class="traffic-template-server-pill">'
                    + '<input type="checkbox" class="sg-traffic-lim-cb" value="' + _deps.escapeHtml(name) + '" ' + checked + '>'
                    + '<span>' + _deps.escapeHtml(name) + '</span>'
                    + '</label>';
            }).join('');
        }

        async function loadGroupTrafficTemplateForm() {
            var gid = getGroupId();
            var wrap = document.getElementById('sg-traffic-limited-servers');
            if (!gid || !wrap) return;
            try {
                var response = await _deps.apiFetch('/api/admin/server-group/traffic-template', {
                    method: 'POST',
                    headers: { 'Content-Type': 'application/json' },
                    body: JSON.stringify({ action: 'get', group_id: gid })
                });
                var result = await response.json();
                if (!result.success) throw new Error(result.error || 'Ошибка');
                var tpl = result.template;
                var limited = result.limited_server_names || [];
                var sel = {};
                limited.forEach(function (n) { sel[n] = true; });
                document.getElementById('sg-traffic-enabled').checked = !!(tpl && tpl.enabled);
                document.getElementById('sg-traffic-bucket-name').value = (tpl && tpl.limited_bucket_name) ? tpl.limited_bucket_name : 'Лимитированные ноды';
                document.getElementById('sg-traffic-limit-gib').value = tpl ? _gibFromBytes(tpl.limit_bytes) : '';
                document.getElementById('sg-traffic-unlimited').checked = !!(tpl && tpl.is_unlimited);
                renderTrafficLimitedServerChecks(getServers() || [], sel);
            } catch (e) {
                console.error('loadGroupTrafficTemplateForm', e);
                wrap.innerHTML = '<p class="error-text">Не удалось загрузить шаблон трафика.</p>';
            }
        }

        function _collectGroupTrafficTemplatePayload() {
            var gid = getGroupId();
            var lim = [];
            document.querySelectorAll('.sg-traffic-lim-cb:checked').forEach(function (cb) {
                if (cb.value) lim.push(cb.value);
            });
            return {
                action: 'save',
                group_id: gid,
                enabled: !!document.getElementById('sg-traffic-enabled').checked,
                limited_bucket_name: (document.getElementById('sg-traffic-bucket-name').value || '').trim() || 'Лимитированные ноды',
                limit_bytes: _bytesFromGib(document.getElementById('sg-traffic-limit-gib').value || '0'),
                is_unlimited: !!document.getElementById('sg-traffic-unlimited').checked,
                limited_server_names: lim
            };
        }

        async function saveGroupTrafficTemplate() {
            try {
                var body = _collectGroupTrafficTemplatePayload();
                var response = await _deps.apiFetch('/api/admin/server-group/traffic-template', {
                    method: 'POST',
                    headers: { 'Content-Type': 'application/json' },
                    body: JSON.stringify(body)
                });
                var result = await response.json();
                if (!result.success) throw new Error(result.error || 'Ошибка');
                showAdminToast('Шаблон трафика сохранён');
                await loadGroupTrafficTemplateForm();
            } catch (e) {
                await _deps.appShowAlert(e.message || String(e), { title: 'Ошибка', variant: 'error' });
            }
        }

        async function previewGroupTrafficTemplate() {
            try {
                var gid = getGroupId();
                if (!gid) return;
                var response = await _deps.apiFetch('/api/admin/server-group/traffic-template', {
                    method: 'POST',
                    headers: { 'Content-Type': 'application/json' },
                    body: JSON.stringify({ action: 'apply', group_id: gid, dry_run: true, force: false })
                });
                var result = await response.json();
                if (result.ok === false) throw new Error(result.error || 'Ошибка');
                var t = result.total != null ? result.total : 0;
                var a = result.applied != null ? result.applied : 0;
                var s = result.skipped != null ? result.skipped : 0;
                var e = (result.errors && result.errors.length) ? (' Ошибок: ' + result.errors.length + '.') : '';
                await _deps.appShowAlert(
                    'Dry-run: подписок ' + t + ', будет применено ' + a + ', пропущено ' + s + '.' + e,
                    { title: 'Проверка', variant: 'success' }
                );
            } catch (e) {
                await _deps.appShowAlert(e.message || String(e), { title: 'Ошибка', variant: 'error' });
            }
        }

        async function applyGroupTrafficTemplate() {
            var ok = await _deps.appShowConfirm(
                'Применить шаблон ко всем подпискам этой группы? Подписки с ручной настройкой трафика будут пропущены.',
                { title: 'Применить шаблон', confirmText: 'Применить' }
            );
            if (!ok) return;
            try {
                var gid = getGroupId();
                var response = await _deps.apiFetch('/api/admin/server-group/traffic-template', {
                    method: 'POST',
                    headers: { 'Content-Type': 'application/json' },
                    body: JSON.stringify({ action: 'apply', group_id: gid, dry_run: false, force: false })
                });
                var result = await response.json();
                if (result.ok === false) throw new Error(result.error || 'Ошибка');
                showAdminToast('Готово: применено ' + (result.applied || 0) + ', пропущено ' + (result.skipped || 0));
            } catch (e) {
                await _deps.appShowAlert(e.message || String(e), { title: 'Ошибка', variant: 'error' });
            }
        }

        async function applyGroupTrafficTemplateForce() {
            var ok = await _deps.appShowConfirm(
                'Перезаписать настройки трафика по шаблону для всех подписок группы, включая те, где уже есть кастомные пакеты? Это опасная операция.',
                { title: 'Force', confirmText: 'Перезаписать' }
            );
            if (!ok) return;
            try {
                var gid = getGroupId();
                var response = await _deps.apiFetch('/api/admin/server-group/traffic-template', {
                    method: 'POST',
                    headers: { 'Content-Type': 'application/json' },
                    body: JSON.stringify({ action: 'apply', group_id: gid, dry_run: false, force: true })
                });
                var result = await response.json();
                if (result.ok === false) throw new Error(result.error || 'Ошибка');
                showAdminToast('Force: применено ' + (result.applied || 0) + ', пропущено ' + (result.skipped || 0));
            } catch (e) {
                await _deps.appShowAlert(e.message || String(e), { title: 'Ошибка', variant: 'error' });
            }
        }

        function toggleAdminServerReorderMode() {
            setReorder(!getReorder());
            var reorderBtn = document.getElementById('admin-server-reorder-toggle-btn');
            if (reorderBtn) {
                reorderBtn.textContent = getReorder() ? 'Готово' : 'Порядок';
                reorderBtn.classList.toggle('is-active', getReorder());
            }
            var groupRoot = document.getElementById('admin-server-group-page-root');
            if (groupRoot) groupRoot.classList.toggle('admin-server-group-page--reorder', getReorder());
            renderServersInGroup(getServers() || []);
        }

        async function toggleServerActive(serverId, makeActive) {
            var input = document.querySelector('input[data-server-toggle="' + serverId + '"]');
            if (!input || input.dataset.busy === '1') return;
            input.dataset.busy = '1';
            input.disabled = true;
            var revertTo = !makeActive;
            try {
                var response = await _deps.apiFetch('/api/admin/server-config/update', {
                    method: 'POST',
                    headers: { 'Content-Type': 'application/json' },
                    body: JSON.stringify({ id: serverId, is_active: makeActive ? 1 : 0 })
                });
                var result = await response.json();
                if (!result.success) throw new Error(result.error || 'Ошибка');
                var srv = getServers().find(function (s) { return s.id === serverId; });
                if (srv) srv.is_active = makeActive ? 1 : 0;
                var row = input.closest('.server-power-cell');
                var label = row && row.querySelector('.server-power-label');
                if (label) {
                    label.textContent = makeActive ? 'В сети' : 'Отключён';
                    label.classList.toggle('is-off', !makeActive);
                }
                var hint = row && row.querySelector('.server-power-hint');
                if (hint) hint.textContent = makeActive ? 'В подписках' : 'Не в ключах';
                var card = input.closest('.admin-server-row') || input.closest('.server-card');
                if (card) card.classList.toggle('server-card-muted', !makeActive);
                var parts = [];
                parts.push(makeActive ? 'Сервер включён' : 'Сервер выключен');
                if (result.sync_stats) {
                    var s = result.sync_stats;
                    if (s.clients_created != null) parts.push('клиентов: +' + s.clients_created);
                    if (s.servers_added != null) parts.push('привязок: +' + s.servers_added);
                    if (s.servers_removed != null) parts.push('снято: ' + s.servers_removed);
                }
                if (result.sync_error) parts.push('Предупреждение: ' + result.sync_error);
                showAdminToast(parts.join(' · '));
            } catch (e) {
                input.checked = revertTo;
                await _deps.appShowAlert('Не удалось изменить: ' + (e.message || e), { title: 'Ошибка', variant: 'error' });
            } finally {
                input.disabled = false;
                delete input.dataset.busy;
            }
        }

        function sortAdminServersByClientOrder(servers) {
            return servers.slice().sort(function (a, b) {
                var ao = a.client_sort_order != null ? Number(a.client_sort_order) : a.id;
                var bo = b.client_sort_order != null ? Number(b.client_sort_order) : b.id;
                if (ao !== bo) return ao - bo;
                return a.id - b.id;
            });
        }

        async function refreshAdminServersInGroup() {
            if (getGroupId() == null) return;
            try {
                var response = await _deps.apiFetch('/api/admin/servers-config', {
                    method: 'POST',
                    headers: { 'Content-Type': 'application/json' },
                    body: JSON.stringify({ action: 'list', group_id: getGroupId() })
                });
                var result = await response.json();
                if (result.success) {
                    setServers(result.servers);
                    renderServersInGroup(result.servers);
                    await loadGroupTrafficTemplateForm();
                }
            } catch (err) {
                console.error('refreshAdminServersInGroup:', err);
            }
        }

        async function nudgeServerOrder(serverId, delta) {
            if (!getGroupId()) return;
            var sorted = sortAdminServersByClientOrder(getServers().slice());
            var idx = sorted.findIndex(function (s) { return s.id === serverId; });
            if (idx < 0) return;
            var j = idx + delta;
            if (j < 0 || j >= sorted.length) return;
            var tmp = sorted[idx];
            sorted[idx] = sorted[j];
            sorted[j] = tmp;
            var ids = sorted.map(function (s) { return s.id; });
            try {
                var response = await _deps.apiFetch('/api/admin/servers-config', {
                    method: 'POST',
                    headers: { 'Content-Type': 'application/json' },
                    body: JSON.stringify({ action: 'reorder', group_id: getGroupId(), server_ids: ids })
                });
                var result = await response.json();
                if (!result.success) throw new Error(result.error || 'Ошибка');
                setServers(sorted);
                sorted.forEach(function (s, i) { s.client_sort_order = i; });
                renderServersInGroup(sorted);
                showAdminToast('Порядок сохранён');
            } catch (e) {
                await _deps.appShowAlert(e.message || String(e), { title: 'Ошибка', variant: 'error' });
                await refreshAdminServersInGroup();
            }
        }

        function renderServersInGroup(servers) {
            var listEl = document.getElementById('admin-servers-in-group-list');
            if (!listEl) return;
            if (!servers || servers.length === 0) {
                listEl.innerHTML = '<div class="admin-sm-empty admin-sm-empty--compact"><p class="admin-sm-empty-title">В группе нет серверов</p><p class="admin-sm-empty-hint">Добавьте ноду кнопкой «+ Сервер».</p></div>';
                return;
            }
            var sorted = sortAdminServersByClientOrder(servers);
            var n = sorted.length;
            var reorder = getReorder();
            var cards = sorted.map(function (server, i) {
                var on = server.is_active === 1 || server.is_active === true;
                var safeTitle = _deps.escapeHtml(server.display_name || server.name);
                var safeHost = _deps.escapeHtml(server.host || '');
                var safeName = _deps.escapeHtml(server.name || '');
                var upDisabled = i === 0 ? ' disabled' : '';
                var downDisabled = i === n - 1 ? ' disabled' : '';
                var orderCol = reorder ? ('<div class="admin-server-order-col"><span class="server-order-badge" aria-hidden="true">' + (i + 1) + '</span><div class="server-reorder-nudge server-reorder-nudge--large" role="group" aria-label="Сдвиг в списке"><button type="button" class="server-reorder-nudge-btn server-reorder-nudge-btn--large"' + upDisabled + ' onclick="event.stopPropagation(); nudgeServerOrder(' + server.id + ', -1)" aria-label="Выше">↑</button><button type="button" class="server-reorder-nudge-btn server-reorder-nudge-btn--large"' + downDisabled + ' onclick="event.stopPropagation(); nudgeServerOrder(' + server.id + ', 1)" aria-label="Ниже">↓</button></div></div>') : '';
                var menuCol = !reorder ? ('<details class="admin-server-row-menu" onclick="event.stopPropagation()"><summary class="admin-server-row-menu-summary" aria-label="Действия">⋯</summary><div class="admin-server-row-menu-panel"><button type="button" class="admin-server-row-menu-item" onclick="event.stopPropagation(); this.closest(\'details\').removeAttribute(\'open\'); editServerConfig(' + server.id + ')">Изменить</button><button type="button" class="admin-server-row-menu-item admin-server-row-menu-item--danger" onclick="event.stopPropagation(); this.closest(\'details\').removeAttribute(\'open\'); deleteServerConfig(' + server.id + ')">Удалить</button></div></details>') : '';
                return '\n        <div class="admin-server-row admin-user-card server-card-reorderable' + (on ? '' : ' server-card-muted') + '" data-server-id="' + server.id + '">' + orderCol + '<div class="admin-server-row__main"><div class="admin-server-row__text"><div class="admin-server-row__title">' + safeTitle + '</div><div class="admin-server-row__meta">' + safeHost + ' · ' + safeName + '</div></div><div class="admin-server-row__power server-power-cell" onclick="event.stopPropagation()"><div class="admin-server-power-toggle"><span class="server-power-label' + (on ? '' : ' is-off') + '">' + (on ? 'В сети' : 'Отключён') + '</span><label class="ui-switch ui-switch--compact" title="' + (on ? 'Выключить ноду' : 'Включить ноду') + '"><input type="checkbox" data-server-toggle="' + server.id + '" ' + (on ? 'checked' : '') + ' onchange="toggleServerActive(' + server.id + ', this.checked)" aria-label="Сервер в работе"><span class="ui-switch-slider" aria-hidden="true"></span></label></div><span class="server-power-hint">' + (on ? 'В подписках' : 'Не в ключах') + '</span></div>' + menuCol + '</div></div>';
            }).join('');
            listEl.innerHTML = '<div class="server-reorder-stack admin-server-rows">' + cards + '</div>';
        }

        function setServerClientFlowFormState(serverFlowRaw) {
            var enable = document.getElementById('server-client-flow-enable');
            var legacyWarn = document.getElementById('server-flow-legacy-warning');
            if (!enable) return;
            if (legacyWarn) legacyWarn.style.display = 'none';
            var v = (serverFlowRaw || '').trim();
            if (!v) { enable.checked = false; return; }
            enable.checked = true;
            if (v !== SERVER_CLIENT_FLOW_VALUE && legacyWarn) legacyWarn.style.display = 'block';
        }

        function getServerClientFlowPayload() {
            var enable = document.getElementById('server-client-flow-enable');
            if (!enable) return null;
            return enable.checked ? SERVER_CLIENT_FLOW_VALUE : null;
        }

        function showAddServerConfigModal() {
            if (getGroupId() == null) {
                void _deps.appShowAlert('Сначала откройте группу серверов.', { title: 'Группа не выбрана', variant: 'error' });
                return;
            }
            document.getElementById('server-config-modal-title').innerText = 'Добавить сервер';
            document.getElementById('server-id-input').value = '';
            document.getElementById('server-name-input').value = '';
            document.getElementById('server-display-input').value = '';
            document.getElementById('server-host-input').value = '';
            document.getElementById('server-login-input').value = '';
            document.getElementById('server-pass-input').value = '';
            document.getElementById('server-vpnhost-input').value = '';
            var subPortEl = document.getElementById('server-subscription-port-input');
            if (subPortEl) subPortEl.value = '2096';
            document.getElementById('server-subscription-url-input').value = '';
            setServerClientFlowFormState('');
            document.getElementById('server-map-label-input').value = '';
            document.getElementById('server-lat-input').value = '';
            document.getElementById('server-lng-input').value = '';
            document.getElementById('server-location-input').value = '';
            document.getElementById('server-max-concurrent-input').value = '50';
            var activeEl = document.getElementById('server-is-active-input');
            if (activeEl) activeEl.checked = true;
            _deps.showModal('server-config-modal');
        }

        function editServerConfig(serverId) {
            var server = getServers().find(function (s) { return s.id === serverId; });
            if (!server) return;
            document.getElementById('server-config-modal-title').innerText = 'Редактировать сервер';
            document.getElementById('server-id-input').value = server.id;
            document.getElementById('server-name-input').value = server.name;
            document.getElementById('server-display-input').value = server.display_name || '';
            document.getElementById('server-host-input').value = server.host;
            document.getElementById('server-login-input').value = server.login;
            document.getElementById('server-pass-input').value = server.password;
            document.getElementById('server-vpnhost-input').value = server.vpn_host || '';
            document.getElementById('server-subscription-url-input').value = server.subscription_url || '';
            setServerClientFlowFormState(server.client_flow || '');
            document.getElementById('server-map-label-input').value = server.map_label || '';
            document.getElementById('server-lat-input').value = server.lat || '';
            document.getElementById('server-lng-input').value = server.lng || '';
            document.getElementById('server-location-input').value = server.location || '';
            document.getElementById('server-max-concurrent-input').value = server.max_concurrent_clients != null ? String(server.max_concurrent_clients) : '50';
            var activeEl = document.getElementById('server-is-active-input');
            if (activeEl) activeEl.checked = (server.is_active === 1 || server.is_active === true);
            _deps.showModal('server-config-modal');
        }

        async function saveServerConfig(event) {
            event.preventDefault();
            var id = document.getElementById('server-id-input').value;
            var body = {
                group_id: getGroupId(),
                name: document.getElementById('server-name-input').value,
                display_name: document.getElementById('server-display-input').value,
                host: document.getElementById('server-host-input').value,
                login: document.getElementById('server-login-input').value,
                password: document.getElementById('server-pass-input').value,
                vpn_host: document.getElementById('server-vpnhost-input').value || null,
                subscription_url: document.getElementById('server-subscription-url-input').value || null,
                client_flow: getServerClientFlowPayload(),
                map_label: document.getElementById('server-map-label-input').value ? document.getElementById('server-map-label-input').value.trim() : null,
                lat: document.getElementById('server-lat-input').value ? parseFloat(document.getElementById('server-lat-input').value) : null,
                lng: document.getElementById('server-lng-input').value ? parseFloat(document.getElementById('server-lng-input').value) : null,
                location: document.getElementById('server-location-input').value ? document.getElementById('server-location-input').value.trim() : null,
                max_concurrent_clients: (function () { var v = document.getElementById('server-max-concurrent-input').value; var n = parseInt(v, 10); return (v !== '' && !isNaN(n) && n >= 1) ? n : null; })(),
                is_active: document.getElementById('server-is-active-input') ? document.getElementById('server-is-active-input').checked : true,
                id: id || undefined,
                action: id ? undefined : 'add'
            };
            try {
                var url = id ? '/api/admin/server-config/update' : '/api/admin/servers-config';
                var response = await _deps.apiFetch(url, {
                    method: 'POST',
                    headers: { 'Content-Type': 'application/json' },
                    body: JSON.stringify(body)
                });
                var result = await response.json();
                if (result.success) {
                    _deps.closeModal('server-config-modal');
                    await refreshAdminServersInGroup();
                    if (result.flow_sync_started && result.server_id) {
                        await _deps.appShowAlert(
                            'Синхронизация flow для всех клиентов на этой ноде запущена в фоне. При необходимости повторите вручную через API или дождитесь завершения (см. логи бота).',
                            { title: 'Flow', variant: 'success' }
                        );
                    }
                    if (result.sync_stats || result.sync_error) {
                        await _deps.appShowAlert(adminSyncSubscriptionsAlertMessage(result), { title: 'Синхронизация' });
                    }
                } else {
                    await _deps.appShowAlert('Ошибка: ' + result.error, { variant: 'error' });
                }
            } catch (err) {
                console.error('Ошибка сохранения сервера:', err);
                await _deps.appShowAlert('Ошибка при сохранении', { variant: 'error' });
            }
        }

        async function deleteServerConfig(serverId) {
            var okDel = await _deps.appShowConfirm(
                'Удалить конфигурацию сервера? На панели этой ноды клиенты не удаляются. Бот перестанет использовать сервер и обновит привязки подписок в базе (снятие связей без очистки панели удалённой ноды).',
                { title: 'Удаление сервера', confirmText: 'Удалить' }
            );
            if (!okDel) return;
            try {
                var response = await _deps.apiFetch('/api/admin/server-config/delete', {
                    method: 'POST',
                    headers: { 'Content-Type': 'application/json' },
                    body: JSON.stringify({ id: serverId })
                });
                var result = await response.json();
                if (result.success) {
                    await refreshAdminServersInGroup();
                    if (result.sync_stats || result.sync_error) {
                        await _deps.appShowAlert(adminSyncSubscriptionsAlertMessage(result), { title: 'Синхронизация' });
                    }
                } else {
                    await _deps.appShowAlert('Ошибка: ' + result.error, { variant: 'error' });
                }
            } catch (err) {
                console.error('Ошибка удаления сервера:', err);
                await _deps.appShowAlert('Ошибка при удалении', { variant: 'error' });
            }
        }

        async function syncAllServers() {
            var ok = await _deps.appShowConfirm('Выполнить полную синхронизацию всех подписок с серверами? Это может занять некоторое время.', { title: 'Синхронизация' });
            if (!ok) return;
            runSyncAllServers();
        }

        async function showSyncOutboxStatus() {
            try {
                var resp = await _deps.apiFetch('/api/admin/sync-outbox', {
                    method: 'POST',
                    headers: { 'Content-Type': 'application/json' },
                    body: JSON.stringify({ action: 'stats', limit: 30 })
                });
                var data = await resp.json();
                if (!data || !data.success) throw new Error((data && data.error) || 'Ошибка outbox');
                var s = data.stats || {};
                var lines = [
                    'Pending: ' + (s.pending || 0),
                    'Retry: ' + (s.retry || 0),
                    'Processing: ' + (s.processing || 0),
                    'Dead: ' + (s.dead || 0),
                    'Due now: ' + (s.due_now || 0)
                ];
                if (s.dead > 0) {
                    var retry = await _deps.appShowConfirm(
                        'Найдено dead-задач: ' + s.dead + '. Перезапустить их?',
                        { title: 'Outbox синка', confirmText: 'Retry dead' }
                    );
                    if (retry) {
                        var rr = await _deps.apiFetch('/api/admin/sync-outbox', {
                            method: 'POST',
                            headers: { 'Content-Type': 'application/json' },
                            body: JSON.stringify({ action: 'retry_dead', limit: 200 })
                        });
                        var rd = await rr.json();
                        if (rd && rd.success) lines.push('Перезапущено: ' + (rd.retried || 0));
                    }
                }
                await _deps.appShowAlert(lines.join('\n'), { title: 'Outbox синка' });
            } catch (e) {
                await _deps.appShowAlert('Не удалось получить статус outbox: ' + (e.message || e), { title: 'Ошибка', variant: 'error' });
            }
        }

        async function runSyncAllServers() {
            var btns = [document.getElementById('admin-sync-all-panels-btn'), document.getElementById('admin-sync-all-panels-group-btn')].filter(Boolean);
            btns.forEach(function (b) { b.disabled = true; });
            _deps.platform.mainButton.show('СИНХРОНИЗАЦИЯ...', function () {});
            _deps.platform.mainButton.disable();
            try {
                var response = await _deps.apiFetch('/api/admin/sync-all', { method: 'POST', headers: { 'Content-Type': 'application/json' } });
                var result = await response.json();
                if (result.success) {
                    var st = result.stats || {};
                    var parts = [
                        'Подписок проверено: ' + (st.subscriptions_checked != null ? st.subscriptions_checked : '—'),
                        'Узлов (ensure): ' + (st.total_servers_synced != null ? st.total_servers_synced : '—'),
                        'Клиентов создано: ' + (st.total_clients_created != null ? st.total_clients_created : '—'),
                        'Сирот удалено: ' + (st.orphaned_clients_deleted != null ? st.orphaned_clients_deleted : 0)
                    ];
                    var errN = st.total_errors;
                    if (errN == null && st.errors && st.errors.length) errN = st.errors.length;
                    if (errN) parts.push('Замечаний в логе sync: ' + errN);
                    try {
                        var outboxResp = await _deps.apiFetch('/api/admin/sync-outbox', {
                            method: 'POST',
                            headers: { 'Content-Type': 'application/json' },
                            body: JSON.stringify({ action: 'stats', limit: 30 })
                        });
                        var outboxData = await outboxResp.json();
                        if (outboxData && outboxData.success && outboxData.stats) {
                            var stOut = outboxData.stats;
                            parts.push('Outbox: pending=' + (stOut.pending || 0) + ', retry=' + (stOut.retry || 0) + ', dead=' + (stOut.dead || 0));
                            if (stOut.dead > 0) {
                                var retryDead = await _deps.appShowConfirm(
                                    'Есть зависшие outbox-задачи синка: ' + stOut.dead + '. Перезапустить их сейчас?',
                                    { title: 'Outbox синка', confirmText: 'Перезапустить' }
                                );
                                if (retryDead) {
                                    var retryResp = await _deps.apiFetch('/api/admin/sync-outbox', {
                                        method: 'POST',
                                        headers: { 'Content-Type': 'application/json' },
                                        body: JSON.stringify({ action: 'retry_dead', limit: 200 })
                                    });
                                    var retryData = await retryResp.json();
                                    if (retryData && retryData.success) {
                                        parts.push('Outbox перезапущено: ' + (retryData.retried || 0));
                                    }
                                }
                            }
                        }
                    } catch (outboxErr) {
                        console.warn('outbox stats error:', outboxErr);
                    }
                    _deps.platform.showAlert('Синхронизация завершена.\n\n' + parts.join('\n'));
                    loadServerGroups();
                } else {
                    _deps.platform.showAlert('Ошибка: ' + (result.error || 'Неизвестно'));
                }
            } catch (err) {
                console.error('Ошибка синхронизации:', err);
                _deps.platform.showAlert('Ошибка при выполнении синхронизации: ' + (err.message || String(err)));
            } finally {
                _deps.platform.mainButton.hide();
                btns.forEach(function (b) { b.disabled = false; });
            }
        }

        return {
            loadServerManagement: loadServerManagement,
            loadServerGroups: loadServerGroups,
            renderServerGroups: renderServerGroups,
            showAddServerGroupModal: showAddServerGroupModal,
            editServerGroup: editServerGroup,
            saveServerGroup: saveServerGroup,
            loadAdminServerGroupPage: loadAdminServerGroupPage,
            toggleAdminServerReorderMode: toggleAdminServerReorderMode,
            toggleServerActive: toggleServerActive,
            sortAdminServersByClientOrder: sortAdminServersByClientOrder,
            refreshAdminServersInGroup: refreshAdminServersInGroup,
            nudgeServerOrder: nudgeServerOrder,
            renderServersInGroup: renderServersInGroup,
            setServerClientFlowFormState: setServerClientFlowFormState,
            getServerClientFlowPayload: getServerClientFlowPayload,
            showAddServerConfigModal: showAddServerConfigModal,
            editServerConfig: editServerConfig,
            saveServerConfig: saveServerConfig,
            deleteServerConfig: deleteServerConfig,
            syncAllServers: syncAllServers,
            showSyncOutboxStatus: showSyncOutboxStatus,
            runSyncAllServers: runSyncAllServers,
            saveGroupTrafficTemplate: saveGroupTrafficTemplate,
            previewGroupTrafficTemplate: previewGroupTrafficTemplate,
            applyGroupTrafficTemplate: applyGroupTrafficTemplate,
            applyGroupTrafficTemplateForce: applyGroupTrafficTemplateForce
        };
    }

    window.DarallaAdminServersFeature = window.DarallaAdminServersFeature || {};
    window.DarallaAdminServersFeature.create = createAdminServersFeature;
})();
