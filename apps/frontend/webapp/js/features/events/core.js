(function () {
    function createEventsFeature(deps) {
        var _deps = deps || {};

        async function loadEvents() {
            var loadingEl = document.getElementById('events-loading');
            var emptyEl = document.getElementById('events-empty');
            var listWrap = document.getElementById('events-list-wrap');
            var listEl = document.getElementById('events-list');
            if (loadingEl) loadingEl.style.display = 'block';
            if (emptyEl) emptyEl.style.display = 'none';
            if (listWrap) listWrap.style.display = 'none';
            try {
                var response = await _deps.apiFetch('/api/events/');
                var data = { events: [], active: [], upcoming: [] };
                if (response.ok) {
                    try { data = await response.json(); } catch (e) {}
                }
                var active = data.active || [];
                var upcoming = data.upcoming || [];
                var ended = data.ended || [];
                var hasAny = active.length > 0 || upcoming.length > 0 || ended.length > 0;
                if (loadingEl) loadingEl.style.display = 'none';
                if (!hasAny) {
                    if (emptyEl) emptyEl.style.display = 'block';
                } else {
                    if (listWrap) listWrap.style.display = 'block';
                    if (listEl) {
                        var html = '';
                        if (active.length > 0) {
                            html += '<p class="event-section-title">Событие идёт</p>';
                            html += active.map(function (ev) { return _deps.renderEventCard(ev, true); }).join('');
                        }
                        if (upcoming.length > 0) {
                            html += '<p class="event-section-title">Скоро</p>';
                            html += upcoming.map(function (ev) { return _deps.renderEventCard(ev, false); }).join('');
                        }
                        if (ended.length > 0) {
                            html += '<p class="event-section-title">Завершённые</p>';
                            html += ended.map(function (ev) { return _deps.renderEventCard(ev, false, true); }).join('');
                        }
                        listEl.innerHTML = html;
                    }
                }
            } catch (e) {
                if (loadingEl) loadingEl.style.display = 'none';
                if (emptyEl) emptyEl.style.display = 'block';
            }
            if (typeof window.currentNavIndex !== 'undefined' && typeof _deps.moveNavIndicator === 'function') {
                requestAnimationFrame(function () {
                    requestAnimationFrame(function () { _deps.moveNavIndicator(window.currentNavIndex); });
                });
            }
        }

        function showEventDetail(eventId) {
            var timer = _deps.getEventDetailLeaderboardTimer();
            if (timer) {
                clearInterval(timer);
                _deps.setEventDetailLeaderboardTimer(null);
            }
            var contentEl = document.getElementById('event-detail-content');
            if (contentEl) contentEl.innerHTML = '<div class="loading"><p>Загрузка...</p></div>';
            _deps.showPage('event-detail', { id: eventId });
            loadEventDetail(eventId);
        }

        function loadEventDetail(eventId) {
            var contentEl = document.getElementById('event-detail-content');
            if (!contentEl) return;
            contentEl.innerHTML = '<div class="loading"><p>Загрузка...</p></div>';
            Promise.all([
                _deps.apiFetch('/api/events/' + eventId).then(function (r) { return r.ok ? r.json() : null; }),
                _deps.apiFetch('/api/events/' + eventId + '/leaderboard?limit=20').then(function (r) { return r.ok ? r.json() : { leaderboard: [] }; }).then(function (d) { return d.leaderboard || []; }),
                _deps.apiFetch('/api/events/' + eventId + '/my-place').then(function (r) { return r.ok ? r.json() : {}; }).then(function (d) { return d.place || null; }),
                _deps.apiFetch('/api/events/my-code').then(function (r) { return r.ok ? r.json() : {}; }).then(function (d) { return d.code || ''; })
            ]).then(function (results) {
                var ev = results[0];
                var leaderboard = results[1];
                var myPlace = results[2];
                var myCode = results[3];
                if (!contentEl) return;
                if (!ev) { contentEl.innerHTML = '<p class="hint">Событие не найдено</p>'; return; }
                var live = _deps.isEventLive(ev);
                var ended = (ev.computed_status === 'ended') || (ev.end_at && new Date(ev.end_at) < new Date());
                var icons = typeof _deps.getEventIcons === 'function'
                    ? _deps.getEventIcons()
                    : { live: '', clock: '' };
                var statusClass = live ? 'event-detail-status event-detail-status--live' : (ended ? 'event-detail-status event-detail-status--ended' : 'event-detail-status event-detail-status--upcoming');
                var statusIcon = live ? icons.live : (ended ? '🏁' : icons.clock);
                var statusText = live ? 'Идёт' : (ended ? 'Завершено' : 'Скоро');
                var daysText = _deps.getEventDaysText(ev, live, ended);
                var innerClass = live ? 'event-detail-inner event-detail-live' : 'event-detail-inner';
                var html = '<div class="' + innerClass + '" style="padding:16px;">' +
                    '<div class="' + statusClass + '">' + statusIcon + '<span>' + statusText + '</span></div>' +
                    '<h2 style="margin:0 0 12px 0;">' + (ev.name || 'Событие') + '</h2>' +
                    (ev.description ? '<p class="event-description" style="margin:0 0 12px 0;">' + ev.description + '</p>' : '') +
                    '<p class="event-dates" style="font-size:14px;">' + (ev.start_at || '').slice(0, 10) + ' — ' + (ev.end_at || '').slice(0, 10) + '</p>';
                if (daysText) html += '<p class="event-days">' + daysText + '</p>';
                var rewards = ev.rewards || [];
                var winningPlaces = rewards.map(function (r) { return r.place; });
                var isWinner = myPlace && winningPlaces.indexOf(myPlace.place) >= 0;
                if (ended) {
                    html += '<p class="event-thanks">Спасибо за участие!</p>';
                    if (isWinner && ev.support_url) {
                        html += '<div class="event-winner-block">';
                        html += '<p class="event-winner-text">Поздравляем! Вы в числе победителей.</p>';
                        html += '<p class="event-winner-hint">За вашей наградой обратитесь в службу поддержки.</p>';
                        html += '<a href="' + _deps.escapeHtml(ev.support_url) + '" target="_blank" rel="noopener" class="btn-primary" style="display:inline-block;padding:10px 20px;text-decoration:none;color:inherit;">Служба поддержки</a>';
                        html += '</div>';
                    }
                }
                if (rewards.length > 0) {
                    html += '<div class="event-rewards-block"><p class="event-rewards-title">Награды</p><ul class="event-rewards-list">';
                    rewards.forEach(function (r) {
                        var text = r.description || (r.days ? (r.days + ' дн.') : 'приз');
                        var placeClass = r.place === 1 ? 'event-reward-place--1' : r.place === 2 ? 'event-reward-place--2' : r.place === 3 ? 'event-reward-place--3' : '';
                        html += '<li class="event-reward-item"><span class="event-reward-place ' + placeClass + '">' + r.place + ' место</span> — ' + text + '</li>';
                    });
                    html += '</ul></div>';
                }
                if (live) {
                    html += '<p class="event-referral-hint">Приглашайте друзей — поднимайтесь в рейтинге.</p>';
                    html += '<p class="event-referral-code-hint">Дайте другу свой код. Когда он введёт его при покупке или продлении, ваш рейтинг вырастет.</p>';
                    if (myCode) {
                        html += '<div class="event-referral-code-block" style="margin-bottom:16px;padding:12px;display:flex;align-items:center;justify-content:space-between;gap:12px;">';
                        html += '<code class="event-referral-code">' + _deps.escapeHtml(myCode) + '</code>';
                        html += '<button type="button" class="btn-primary" style="padding:8px 16px;flex-shrink:0;" onclick="copyEventReferralCode(\'' + myCode.replace(/'/g, "\\'") + '\')">Копировать</button>';
                        html += '</div>';
                    }
                }
                html += _deps.buildLeaderboardHtml(leaderboard, myPlace);
                html += '</div>';
                contentEl.innerHTML = html;
                contentEl.setAttribute('data-event-detail-id', String(eventId));
                if (live) {
                    _deps.setEventDetailLeaderboardTimer(setInterval(function () {
                        var el = document.getElementById('event-detail-content');
                        if (!el || el.getAttribute('data-event-detail-id') !== String(eventId)) {
                            var t = _deps.getEventDetailLeaderboardTimer();
                            if (t) clearInterval(t);
                            _deps.setEventDetailLeaderboardTimer(null);
                            return;
                        }
                        Promise.all([
                            _deps.apiFetch('/api/events/' + eventId + '/leaderboard?limit=20').then(function (r) { return r.ok ? r.json() : { leaderboard: [] }; }).then(function (d) { return d.leaderboard || []; }),
                            _deps.apiFetch('/api/events/' + eventId + '/my-place').then(function (r) { return r.ok ? r.json() : {}; }).then(function (d) { return d.place || null; })
                        ]).then(function (res) {
                            var list = res[0];
                            var place = res[1];
                            var wrap = el && el.querySelector('.live-ranking');
                            if (wrap && wrap.parentNode) {
                                var temp = document.createElement('div');
                                temp.innerHTML = _deps.buildLeaderboardHtml(list, place);
                                var newWrap = temp.firstElementChild;
                                if (newWrap) wrap.parentNode.replaceChild(newWrap, wrap);
                            }
                        });
                    }, 30000));
                }
            }).catch(function () {
                if (contentEl) contentEl.innerHTML = '<p class="hint">Не удалось загрузить событие</p>';
            });
        }

        async function copyEventReferralCode(code) {
            var ok = await _deps.copyTextToClipboard(code);
            if (ok) {
                await _deps.appShowAlert('Код скопирован в буфер обмена.', { title: 'Готово', variant: 'success' });
            } else {
                var el = document.getElementById('generic-copy-manual-url');
                var h = document.getElementById('generic-copy-manual-heading');
                if (el) el.value = code;
                if (h) h.textContent = 'Скопируйте код вручную';
                _deps.showModal('generic-copy-manual-modal');
            }
        }

        return {
            loadEvents: loadEvents,
            showEventDetail: showEventDetail,
            loadEventDetail: loadEventDetail,
            copyEventReferralCode: copyEventReferralCode
        };
    }

    window.DarallaEventsFeature = window.DarallaEventsFeature || {};
    window.DarallaEventsFeature.create = createEventsFeature;
})();
