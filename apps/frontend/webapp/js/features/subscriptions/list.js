(function () {
    function createSubscriptionsFeature(deps) {
        var _deps = deps || {};

        function formatBinaryBytes(num) {
            var n = Number(num || 0);
            if (!isFinite(n) || n <= 0) return '0 B';
            var units = ['B', 'KB', 'MB', 'GB', 'TB'];
            var i = 0;
            while (n >= 1024 && i < units.length - 1) {
                n /= 1024;
                i++;
            }
            return (i === 0 ? Math.round(n) : n.toFixed(2)) + ' ' + units[i];
        }

        function _attrEscape(s) {
            return String(s)
                .replace(/&/g, '&amp;')
                .replace(/"/g, '&quot;')
                .replace(/</g, '&lt;');
        }

        function _trafficTopupButtonsHtml(sub) {
            var pkgs = typeof window !== 'undefined' ? (window.userTrafficTopupPackages || []) : [];
            if (!pkgs.length) return '';
            var isPayable = sub.status === 'active' || sub.status === 'trial';
            if (!isPayable) return '';
            var rows = [];
            var added = 0;
            pkgs.forEach(function (p) {
                if (p && p.enabled === false) return;
                if (!added) {
                    rows.push('<div class="traffic-topup-actions">');
                    rows.push('<span class="traffic-topup-actions-label">Докупить трафик</span>');
                    rows.push('<div class="traffic-topup-pack-grid">');
                }
                added++;
                var title = _deps.escapeHtml(p.title || 'Пакет');
                var gib = Number(p.gib) || 0;
                var price = Number(p.price);
                var badge = (p.badge && String(p.badge).trim())
                    ? '<span class="traffic-topup-pack-badge">' + _deps.escapeHtml(String(p.badge).trim()) + '</span>'
                    : '';
                rows.push(
                    '<button type="button" class="traffic-topup-pack-btn" data-traffic-topup '
                    + 'data-sub-id="' + _attrEscape(sub.id) + '" data-pkg-id="' + _attrEscape(p.id) + '">'
                    + badge
                    + '<span class="traffic-topup-pack-title">' + title + '</span>'
                    + '<span class="traffic-topup-pack-meta">' + gib + ' ГиБ · ' + (isFinite(price) ? price : '—') + ' ₽</span>'
                    + '</button>'
                );
            });
            if (!added) return '';
            rows.push('</div></div>');
            return rows.join('');
        }

        function bindTrafficTopupButtons(containerEl) {
            if (!containerEl) return;
            var btns = containerEl.querySelectorAll('[data-traffic-topup]');
            btns.forEach(function (btn) {
                btn.onclick = function () {
                    var sid = btn.getAttribute('data-sub-id');
                    var pid = btn.getAttribute('data-pkg-id');
                    if (typeof window.beginTrafficTopupCheckout !== 'function') return;
                    window.beginTrafficTopupCheckout(Number(sid), pid);
                };
            });
        }

        function bindCopySubscriptionLinkButton(containerEl, token) {
            if (!containerEl || typeof window.copySubscriptionLink !== 'function') return;
            var btn = containerEl.querySelector('.subscription-detail-copy-btn');
            if (!btn) return;
            btn.onclick = function () {
                window.copySubscriptionLink(token);
            };
        }

        var TRAFFIC_LEAD_COPY = 'Этот объём общий для серверов с лимитом в подписке. Через остальные серверы этот пакет не расходуется.';

        function _trafficIncludedPercentUsed(quota) {
            var cap = Number(quota.included_allowance_bytes) || 0;
            var used = Number(quota.included_used_bytes) || 0;
            if (cap <= 0) return 0;
            return Math.min(100, Math.round((used / cap) * 100));
        }

        function showSubscriptionDetail(sub) {
            window.scrollTo(0, 0);
            document.documentElement.scrollTop = 0;
            document.body.scrollTop = 0;

            var pageEl = document.getElementById('page-subscription-detail');
            var contentEl = document.getElementById('subscription-detail-content');
            if (!pageEl || !contentEl) return;

            if (typeof _deps.setCurrentSubscriptionDetail === 'function') {
                _deps.setCurrentSubscriptionDetail(sub);
            }

            var isActive = sub.status === 'active' || (sub.status === 'trial' && sub.expires_at && new Date(sub.expires_at * 1000) > new Date());
            var statusClass = isActive ? 'active' : 'expired';
            var statusText = sub.status === 'active'
                ? 'Активна'
                : sub.status === 'expired'
                    ? 'Истекла'
                    : sub.status === 'trial'
                        ? 'Пробная'
                        : sub.status;

            var pctUsed = sub.traffic_quota ? _trafficIncludedPercentUsed(sub.traffic_quota) : 0;
            var availableNow = sub.traffic_quota
                ? Math.max(0, sub.traffic_quota.included_allowance_bytes - sub.traffic_quota.included_used_bytes) + sub.traffic_quota.purchased_remaining_bytes
                : 0;

            contentEl.innerHTML = '\n'
                + '        <div class="subscription-detail-stack">\n'
                + '        <div class="detail-card subscription-detail-hero">\n'
                + '            <div class="subscription-detail-hero-head">\n'
                + '                <h2 class="subscription-detail-title" id="subscription-name-display">' + _deps.escapeHtml(sub.name) + '</h2>\n'
                + '                <div class="detail-status ' + statusClass + '">' + statusText + '</div>\n'
                + '            </div>\n'
                + '            <div class="detail-info-grid subscription-detail-meta">\n'
                + '                <div class="detail-info-item"><div class="detail-info-label">Устройств</div><div class="detail-info-value">' + sub.device_limit + '</div></div>\n'
                + '                <div class="detail-info-item"><div class="detail-info-label">Создана</div><div class="detail-info-value">' + sub.created_at_formatted + '</div></div>\n'
                + '                <div class="detail-info-item full-width"><div class="detail-info-label">' + (isActive ? 'Истекает' : 'Истекла') + '</div><div class="detail-info-value">' + sub.expires_at_formatted + '</div></div>\n'
                + '            </div>\n'
                + (isActive && sub.expires_at
                    ? '            <div class="subscription-detail-countdown"><span class="subscription-detail-countdown-label">Осталось до конца периода</span><span class="subscription-detail-countdown-value">' + _deps.formatTimeRemaining(sub.expires_at) + '</span></div>\n'
                    : '')
                + (isActive
                    ? '            <div class="subscription-detail-primary-action"><button type="button" class="btn-primary subscription-detail-copy-btn">Копировать ссылку подписки</button></div>\n'
                    : '')
                + '        </div>\n'
                + (sub.traffic_quota
                    ? '        <div class="detail-card subscription-traffic-card">\n'
                    + '                <h4 class="subscription-traffic-heading">Трафик</h4>\n'
                    + '                <p class="subscription-traffic-lead">' + _deps.escapeHtml(TRAFFIC_LEAD_COPY) + '</p>\n'
                    + '                <div class="subscription-traffic-available">\n'
                    + '                    <span class="subscription-traffic-available-label">Доступно сейчас</span>\n'
                    + '                    <span class="subscription-traffic-available-value">' + formatBinaryBytes(availableNow) + '</span>\n'
                    + '                </div>\n'
                    + '                <div class="subscription-traffic-progress" role="progressbar" aria-valuemin="0" aria-valuemax="100" aria-valuenow="' + pctUsed + '" aria-label="Израсходовано включённого трафика за период">\n'
                    + '                    <div class="subscription-traffic-progress-fill" style="width: ' + pctUsed + '%"></div>\n'
                    + '                </div>\n'
                    + '                <p class="subscription-traffic-progress-caption">Использовано включённого: ' + pctUsed + '% периодного пакета</p>\n'
                    + '                <div class="subscription-traffic-breakdown">\n'
                    + '                    <div class="subscription-traffic-breakdown-row"><span>Включено на период</span><strong>' + formatBinaryBytes(sub.traffic_quota.included_allowance_bytes) + '</strong></div>\n'
                    + '                    <div class="subscription-traffic-breakdown-row"><span>Израсходовано из включённого</span><strong>' + formatBinaryBytes(sub.traffic_quota.included_used_bytes) + '</strong></div>\n'
                    + '                    <div class="subscription-traffic-breakdown-row"><span>Докуплено (остаток)</span><strong>' + formatBinaryBytes(sub.traffic_quota.purchased_remaining_bytes) + '</strong></div>\n'
                    + '                </div>\n'
                    + '                <p class="hint subscription-traffic-hint">Включённый объём обновляется при оплате продления. Докупка не сгорает при продлении.</p>\n'
                    + _trafficTopupButtonsHtml(sub)
                    + '            </div>\n'
                    : '')
                + '        <div class="detail-actions subscription-detail-secondary-actions">\n'
                + '                <button type="button" class="action-button action-button--quiet" onclick="showRenameSubscriptionModal()">Переименовать подписку</button>\n'
                + ((sub.status === 'active' || sub.status === 'expired' || sub.status === 'trial')
                    ? '                <button type="button" class="action-button action-button--accent" onclick="showExtendSubscriptionModal(' + sub.id + ')">Продлить подписку</button>\n'
                    : '')
                + '        </div>\n'
                + '        </div>\n';

            bindTrafficTopupButtons(contentEl);
            _deps.showPage('subscription-detail', { id: String(sub.id) });
        }

        function createSubscriptionCard(sub) {
            var card = document.createElement('div');
            card.className = 'subscription-card ' + sub.status;
            card.style.cursor = 'pointer';
            card.onclick = function () { showSubscriptionDetail(sub); };

            var isActive = sub.status === 'active' || (sub.status === 'trial' && sub.expires_at && new Date(sub.expires_at * 1000) > new Date());
            var statusClass = isActive ? 'active' : 'expired';
            var statusText = sub.status === 'active'
                ? 'Активна'
                : sub.status === 'expired'
                    ? 'Истекла'
                    : sub.status === 'trial'
                        ? 'Пробная'
                        : sub.status;

            card.innerHTML = '\n'
                + '        <div class="subscription-header">\n'
                + '            <div class="subscription-name">' + _deps.escapeHtml(sub.name) + '</div>\n'
                + '            <div class="subscription-status subscription-status-blink ' + statusClass + '">' + statusText + '</div>\n'
                + '        </div>\n'
                + (isActive && sub.expires_at
                    ? '        <div class="days-badge"><span class="info-label">Осталось</span><span class="days-remaining">' + _deps.formatTimeRemaining(sub.expires_at) + '</span></div>\n'
                    : '')
                + (sub.traffic_quota
                    ? '        <div class="subscription-traffic-teaser">'
                    + '<span class="subscription-traffic-teaser-label">Трафик</span>'
                    + '<span class="subscription-traffic-teaser-value">' + formatBinaryBytes(Math.max(0, sub.traffic_quota.included_allowance_bytes - sub.traffic_quota.included_used_bytes) + sub.traffic_quota.purchased_remaining_bytes) + '</span>'
                    + '<span class="subscription-traffic-teaser-note">доступно (лимитные серверы в подписке)</span></div>\n'
                    : '');
            return card;
        }

        function renderSubscriptions(subscriptions) {
            var listEl = document.getElementById('subscriptions-list');
            if (!listEl) return;
            listEl.innerHTML = '';
            subscriptions.forEach(function (sub) {
                var card = createSubscriptionCard(sub);
                listEl.appendChild(card);
            });
        }

        async function loadSubscriptions() {
            var loadingEl = document.getElementById('loading');
            var errorEl = document.getElementById('error');
            var emptyEl = document.getElementById('empty');
            var subscriptionsEl = document.getElementById('subscriptions');

            if (loadingEl) loadingEl.style.display = 'block';
            if (errorEl) errorEl.style.display = 'none';
            if (emptyEl) emptyEl.style.display = 'none';
            if (subscriptionsEl) subscriptionsEl.style.display = 'none';

            try {
                var response = await _deps.apiFetch('/api/subscriptions?_t=' + Date.now());

                if (response.status === 401 && _deps.platform.isTelegram()) {
                    console.log('Unauthorized in loadSubscriptions (TG mode), retrying registration...');
                    await _deps.initTelegramFlow();
                    return;
                }

                if (!response.ok) {
                    throw new Error('HTTP error! status: ' + response.status);
                }

                var data = await window.DarallaApiClient.responseJson(response);
                if (!data.success) {
                    throw new Error(data.error || 'Ошибка получения данных');
                }

                try {
                    window.userTrafficTopupPackages = Array.isArray(data.traffic_topup_packages)
                        ? data.traffic_topup_packages
                        : [];
                } catch (ePkg) {}

                if (loadingEl) loadingEl.style.display = 'none';

                var totalEl = document.getElementById('total-count');
                var activeEl = document.getElementById('active-count');
                if (totalEl) totalEl.textContent = data.total || 0;
                if (activeEl) activeEl.textContent = data.active || 0;

                if (!data.subscriptions || data.subscriptions.length === 0) {
                    if (emptyEl) emptyEl.style.display = 'block';
                } else {
                    if (subscriptionsEl) subscriptionsEl.style.display = 'block';
                    window.allSubscriptions = data.subscriptions;
                    renderSubscriptions(data.subscriptions);
                }

                var subscriptionsListEl = document.getElementById('subscriptions-list');
                if (subscriptionsListEl && !document.getElementById('buy-subscription-button')) {
                    var buyButton = document.createElement('button');
                    buyButton.id = 'buy-subscription-button';
                    buyButton.className = 'btn-primary';
                    buyButton.style.cssText = 'width: 100%; margin-top: 16px;';
                    buyButton.textContent = 'Купить подписку';
                    buyButton.onclick = function () {
                        if (typeof _deps.onBuySubscription === 'function') _deps.onBuySubscription();
                    };
                    subscriptionsListEl.appendChild(buyButton);
                }
            } catch (error) {
                console.error('Ошибка загрузки подписок:', error);
                if (loadingEl) loadingEl.style.display = 'none';
                if (errorEl) errorEl.style.display = 'block';
            }
        }

        return {
            showSubscriptionDetail: showSubscriptionDetail,
            loadSubscriptions: loadSubscriptions,
            renderSubscriptions: renderSubscriptions,
            createSubscriptionCard: createSubscriptionCard
        };
    }

    window.DarallaSubscriptionsFeature = window.DarallaSubscriptionsFeature || {};
    window.DarallaSubscriptionsFeature.create = createSubscriptionsFeature;
})();
