(function () {
    function createServerListFeature(deps) {
        var _deps = deps || {};

        async function loadServers() {
            var loadingEl = document.getElementById('servers-loading');
            var errorEl = document.getElementById('servers-error');
            var contentEl = document.getElementById('servers-content');
            var listEl = document.getElementById('servers-list');

            if (loadingEl) loadingEl.style.display = 'block';
            if (errorEl) errorEl.style.display = 'none';
            if (contentEl) contentEl.style.display = 'none';

            try {
                _deps.loadServerMap();
                var response = await _deps.apiFetch('/api/servers');
                if (!response.ok) {
                    throw new Error('HTTP error! status: ' + response.status);
                }
                var data = await response.json();
                if (!data.success) {
                    throw new Error(data.error || 'Ошибка получения данных');
                }

                if (loadingEl) loadingEl.style.display = 'none';
                if (contentEl) contentEl.style.display = 'block';

                if (!data.servers || data.servers.length === 0) {
                    if (listEl) listEl.innerHTML = '<div class="empty"><p>Серверы не найдены</p></div>';
                } else {
                    renderServers(data.servers);
                }
            } catch (error) {
                console.error('Ошибка загрузки серверов:', error);
                if (loadingEl) loadingEl.style.display = 'none';
                if (errorEl) errorEl.style.display = 'block';
            }
        }

        function renderServers(servers) {
            var listEl = document.getElementById('servers-list');
            if (!listEl) return;
            listEl.innerHTML = '';
            servers.forEach(function (server) {
                var card = document.createElement('div');
                card.className = 'server-card ' + (server.status === 'online' ? 'online' : 'offline');
                var statusText = server.status === 'online' ? 'Онлайн' : 'Офлайн';
                card.innerHTML = '\n'
                    + '            <div class="server-header">\n'
                    + '                <div class="server-name">' + _deps.escapeHtml(server.name) + '</div>\n'
                    + '                <div class="server-status server-status-badge server-status-blink ' + server.status + '">' + statusText + '</div>\n'
                    + '            </div>\n';
                listEl.appendChild(card);
            });
        }

        return {
            loadServers: loadServers,
            renderServers: renderServers
        };
    }

    window.DarallaServersFeature = window.DarallaServersFeature || {};
    window.DarallaServersFeature.createList = createServerListFeature;
})();
