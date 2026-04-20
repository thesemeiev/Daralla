(function () {
    function createPaymentsFeature(deps) {
        var _deps = deps || {};
        var paymentCheckInterval = null;

        function extractPaymentUrlFromCreateResponse(data) {
            if (!data || typeof data !== 'object') return '';
            var url = data.payment_url || data.paymentUrl || data.confirmation_url || data.confirmationUrl;
            if (url != null && typeof url === 'object' && url.url) url = url.url;
            return url != null ? String(url).trim() : '';
        }

        function clearPaymentStatusPolling() {
            if (paymentCheckInterval) {
                clearInterval(paymentCheckInterval);
                paymentCheckInterval = null;
            }
        }

        function resetCheckoutPaymentState() {
            clearPaymentStatusPolling();
            _deps.setCurrentPaymentData(null);
        }

        async function showExtendSubscriptionModal(subscriptionId) {
            if (!subscriptionId) {
                await _deps.appShowAlert('ID подписки не найден.', { title: 'Ошибка', variant: 'error' });
                return;
            }
            _deps.setCurrentExtendSubscriptionId(subscriptionId);
            _deps.setCurrentPaymentPeriod('month');
            resetCheckoutPaymentState();
            _deps.showPage('choose-payment-method');
        }

        function goToChoosePaymentMethod(period, subscriptionId) {
            _deps.setCurrentPaymentPeriod(period === '3month' ? '3month' : 'month');
            if (subscriptionId != null) _deps.setCurrentExtendSubscriptionId(subscriptionId);
            else _deps.setCurrentExtendSubscriptionId(null);
            resetCheckoutPaymentState();
            _deps.showPage('choose-payment-method');
        }

        function goBackFromChoosePayment() {
            if (_deps.getCurrentExtendSubscriptionId()) _deps.showPage('subscription-detail');
            else _deps.showPage('subscriptions');
        }

        function goBackFromPayment() {
            clearPaymentStatusPolling();
            try { sessionStorage.removeItem('payment_return_payment_id'); } catch (e) {}
            _deps.setCurrentPaymentData(null);
            _deps.showPage('choose-payment-method');
        }

        async function createPayment(period, subscriptionId, gateway) {
            if (subscriptionId === undefined) subscriptionId = null;
            if (!gateway || (gateway !== 'yookassa' && gateway !== 'cryptocloud')) gateway = 'yookassa';
            try {
                var referrerCode = _deps.getReferralCodeFromCurrentPage();
                var body = { period: period, subscription_id: subscriptionId, gateway: gateway };
                if (referrerCode) body.referrer_code = referrerCode;

                _deps.setCurrentPaymentData(null);
                showPaymentPage();

                var response = await _deps.apiFetch('/api/user/payment/create', {
                    method: 'POST',
                    headers: { 'Content-Type': 'application/json' },
                    body: JSON.stringify(body)
                });

                if (!response.ok) {
                    var error = await response.json();
                    throw new Error(error.error || 'Ошибка создания платежа');
                }
                var data = await response.json();
                if (!data.success || !data.payment_id) throw new Error('Не удалось создать платёж');

                if (gateway === 'yookassa') {
                    var ykUrl = extractPaymentUrlFromCreateResponse(data);
                    if (!_deps.isHttpUrl(ykUrl)) throw new Error('Не удалось получить ссылку на оплату');
                    if (subscriptionId) sessionStorage.setItem('payment_extend_sub_id', String(subscriptionId));
                    else {
                        try { sessionStorage.removeItem('payment_extend_sub_id'); } catch (e) {}
                    }
                    try { sessionStorage.setItem('payment_return_payment_id', String(data.payment_id)); } catch (e) {}
                    _deps.setCurrentPaymentData({
                        payment_id: data.payment_id,
                        payment_url: String(ykUrl).trim(),
                        amount: data.amount,
                        period: data.period,
                        gateway: 'yookassa',
                        extend_subscription_id: subscriptionId || null
                    });
                    showPaymentPage();
                    return;
                }

                var payUrl = extractPaymentUrlFromCreateResponse(data);
                if (!_deps.isHttpUrl(payUrl)) throw new Error('Не удалось получить ссылку на оплату');
                if (subscriptionId) {
                    try { sessionStorage.setItem('payment_extend_sub_id', String(subscriptionId)); } catch (e) {}
                } else {
                    try { sessionStorage.removeItem('payment_extend_sub_id'); } catch (e) {}
                }
                _deps.setCurrentPaymentData({
                    payment_id: data.payment_id,
                    payment_url: String(payUrl).trim(),
                    amount: data.amount,
                    period: data.period,
                    gateway: gateway,
                    extend_subscription_id: subscriptionId || null
                });
                showPaymentPage();
            } catch (error) {
                console.error('Ошибка создания платежа:', error);
                var btn = document.getElementById('payment-link-button');
                if (btn) {
                    btn.textContent = 'Перейти к оплате';
                    btn.classList.remove('payment-link-disabled');
                    btn.setAttribute('aria-disabled', 'false');
                }
                _deps.showFormMessage('payment-form-message', 'error', 'Ошибка создания платежа: ' + error.message);
                goBackFromPayment();
            }
        }

        function showPaymentPage() {
            _deps.hideFormMessage('payment-form-message');
            clearPaymentStatusPolling();
            _deps.showPage('payment');
            var page = document.getElementById('page-payment');
            var hintEl = document.getElementById('payment-widget-hint');
            if (page) {
                _deps.removePaymentResultSubline();
                var statusEl = page.querySelector('.detail-status');
                if (statusEl) {
                    statusEl.textContent = 'Ожидает оплаты';
                    statusEl.className = 'detail-status active';
                }
                var toSubs = document.getElementById('payment-to-subscriptions-button');
                if (toSubs) toSubs.style.display = 'none';
                var retryBtn = document.getElementById('payment-retry-button');
                if (retryBtn) retryBtn.style.display = 'none';
                if (hintEl) hintEl.style.display = '';
            }

            var btn = document.getElementById('payment-link-button');
            if (btn) btn.style.display = '';
            var currentPaymentData = _deps.getCurrentPaymentData();
            if (!currentPaymentData) {
                document.getElementById('payment-period').textContent = 'Загрузка...';
                document.getElementById('payment-amount').textContent = 'Загрузка...';
                if (hintEl) hintEl.textContent = 'Ссылка действительна 15 минут';
                if (btn) {
                    btn.textContent = 'Создание платежа...';
                    btn.classList.add('payment-link-disabled');
                    btn.setAttribute('aria-disabled', 'true');
                    delete btn.dataset.paymentUrl;
                    delete btn.dataset.paymentId;
                    btn.onclick = null;
                    btn.style.display = '';
                }
                return;
            }

            var gw = currentPaymentData.gateway || 'yookassa';
            var periodText = currentPaymentData.period === 'month' ? '1 месяц' : (currentPaymentData.period === '3month' ? '3 месяца' : '—');
            document.getElementById('payment-period').textContent = periodText;
            document.getElementById('payment-amount').textContent = currentPaymentData.amount != null ? String(currentPaymentData.amount) + '₽' : '—';

            if (currentPaymentData.payment_id && !_deps.isHttpUrl(currentPaymentData.payment_url)) {
                if (hintEl) hintEl.textContent = 'Проверяем статус платежа…';
                if (btn) btn.style.display = 'none';
                var extWait = currentPaymentData.extend_subscription_id;
                if (extWait == null) {
                    try {
                        var raw = sessionStorage.getItem('payment_extend_sub_id');
                        var parsed = raw ? parseInt(raw, 10) : NaN;
                        if (raw && !isNaN(parsed)) extWait = parsed;
                    } catch (_e) {}
                }
                checkPaymentStatus(currentPaymentData.payment_id, extWait != null ? extWait : null);
                return;
            }

            if (hintEl) {
                if (gw === 'yookassa') hintEl.textContent = 'Оплата откроется на сайте ЮKassa в браузере. После оплаты вы вернётесь в приложение — статус проверится автоматически.';
                else if (gw === 'cryptocloud') hintEl.textContent = 'Оплата на странице CryptoCloud в браузере. Счёт действителен 15 минут; статус обновится после зачисления.';
                else hintEl.textContent = 'Ссылка действительна 15 минут';
            }

            if (btn) {
                btn.textContent = 'Перейти к оплате';
                btn.classList.remove('payment-link-disabled');
                btn.setAttribute('aria-disabled', 'false');
                btn.dataset.paymentUrl = currentPaymentData.payment_url || '';
                btn.dataset.paymentId = currentPaymentData.payment_id;
                btn.onclick = function (e) {
                    e.preventDefault();
                    e.stopPropagation();
                    e.stopImmediatePropagation();
                    if (btn.classList.contains('payment-link-disabled') || btn.getAttribute('aria-disabled') === 'true') return;
                    _deps.openPaymentUrl();
                    return false;
                };
                btn.style.display = '';
            }
            checkPaymentStatus(currentPaymentData.payment_id, currentPaymentData.extend_subscription_id || null);
        }

        function showPaymentSuccessState() {
            try { sessionStorage.removeItem('payment_return_payment_id'); } catch (e) {}
            var page = document.getElementById('page-payment');
            if (!page) return;
            var statusEl = page.querySelector('.detail-status');
            if (statusEl) {
                statusEl.textContent = '\u2713 Оплата прошла';
                statusEl.className = 'detail-status success';
            }
            var sub = _deps.ensurePaymentResultSubline(page);
            if (sub) sub.textContent = 'Подписка уже активна. Ссылку на ключи и продление смотрите в разделе «Подписки».';
            var btn = document.getElementById('payment-link-button');
            if (btn) btn.style.display = 'none';
            var hint = document.getElementById('payment-widget-hint');
            if (hint) hint.style.display = 'none';
            var actions = page.querySelector('.detail-actions');
            if (!actions) return;
            var toSubs = document.getElementById('payment-to-subscriptions-button');
            if (!toSubs) {
                toSubs = document.createElement('button');
                toSubs.id = 'payment-to-subscriptions-button';
                toSubs.type = 'button';
                toSubs.className = 'action-button action-button--accent payment-link-button';
                toSubs.textContent = 'К подпискам';
                toSubs.onclick = function () {
                    _deps.showPage('subscriptions');
                    _deps.loadSubscriptions();
                };
                actions.appendChild(toSubs);
            } else {
                toSubs.className = 'action-button action-button--accent payment-link-button';
            }
            toSubs.style.display = '';
        }

        function showPaymentErrorState(message) {
            var page = document.getElementById('page-payment');
            if (!page) return;
            var statusEl = page.querySelector('.detail-status');
            if (statusEl) {
                statusEl.textContent = 'Ошибка оплаты';
                statusEl.className = 'detail-status expired';
            }
            var sub = _deps.ensurePaymentResultSubline(page);
            if (sub) sub.textContent = message || '';
            var btn = document.getElementById('payment-link-button');
            if (btn) btn.style.display = 'none';
            var hint = document.getElementById('payment-widget-hint');
            if (hint) hint.style.display = 'none';
            var actions = page.querySelector('.detail-actions');
            if (!actions) return;
            var toSubs = document.getElementById('payment-to-subscriptions-button');
            if (toSubs) toSubs.style.display = 'none';
            var retryBtn = document.getElementById('payment-retry-button');
            if (!retryBtn) {
                retryBtn = document.createElement('button');
                retryBtn.id = 'payment-retry-button';
                retryBtn.type = 'button';
                retryBtn.className = 'action-button action-button--accent payment-link-button';
                retryBtn.textContent = 'Попробовать снова';
                retryBtn.onclick = function () { goBackFromPayment(); };
                actions.appendChild(retryBtn);
            } else {
                retryBtn.className = 'action-button action-button--accent payment-link-button';
            }
            retryBtn.style.display = '';
        }

        async function checkPaymentStatus(paymentId, subscriptionId) {
            if (subscriptionId === undefined) subscriptionId = null;
            if (paymentCheckInterval) clearInterval(paymentCheckInterval);
            var checkCount = 0;
            var maxChecks = 180;

            paymentCheckInterval = setInterval(async function () {
                try {
                    checkCount++;
                    if (checkCount > maxChecks) {
                        clearInterval(paymentCheckInterval);
                        paymentCheckInterval = null;
                        var finalResponse = await _deps.apiFetch('/api/user/payment/status/' + paymentId);
                        if (finalResponse.ok) {
                            var finalData = await finalResponse.json();
                            if (finalData.success && finalData.status === 'pending') {
                                var currentPage = document.querySelector('.page.active');
                                var isOnPaymentPage = currentPage && currentPage.id === 'page-payment';
                                if (isOnPaymentPage) {
                                    showPaymentErrorState('Время на оплату вышло. Создайте новый платёж в разделе «Подписки».');
                                } else {
                                    _deps.showFormMessage('payment-form-message', 'error', 'Платёж не был завершён: время ссылки истекло. Создайте новый платёж в «Подписках».');
                                    goBackFromPayment();
                                }
                            }
                        }
                        return;
                    }

                    var response = await _deps.apiFetch('/api/user/payment/status/' + paymentId);
                    if (!response.ok) return;
                    var data = await response.json();
                    if (data.success && data.status === 'succeeded' && data.activated) {
                        clearInterval(paymentCheckInterval);
                        paymentCheckInterval = null;
                        var page = document.querySelector('.page.active');
                        var isOnPaymentPage2 = page && page.id === 'page-payment';
                        if (isOnPaymentPage2) {
                            showPaymentSuccessState();
                            setTimeout(function () {
                                _deps.showPage('subscriptions');
                                _deps.loadSubscriptions();
                            }, 2500);
                        } else {
                            _deps.showAppToast('Оплата прошла, подписка активна. Откройте «Подписки», чтобы скопировать ключ.', 5500, 'success');
                            _deps.showPage('subscriptions');
                            setTimeout(_deps.loadSubscriptions, 1000);
                        }
                    } else if (data.success && (data.status === 'canceled' || data.status === 'refunded' || data.status === 'failed')) {
                        clearInterval(paymentCheckInterval);
                        paymentCheckInterval = null;
                        var page2 = document.querySelector('.page.active');
                        var onPayment = page2 && page2.id === 'page-payment';
                        var statusMessage = data.status === 'canceled'
                            ? 'Платёж отменён — средства не списывались. Попробуйте оплатить снова.'
                            : data.status === 'refunded'
                                ? 'Средства возвращены на карту или счёт. При необходимости создайте новый платёж.'
                                : 'Банк или платёжная система отклонили операцию. Попробуйте другой способ или позже.';
                        if (onPayment) {
                            showPaymentErrorState(statusMessage);
                        } else {
                            _deps.showFormMessage('payment-form-message', 'error', 'Ошибка оплаты: ' + statusMessage + ' Раздел «Подписки» или выбор способа оплаты.');
                            goBackFromPayment();
                        }
                    }
                } catch (error) {
                    console.error('Ошибка проверки статуса платежа:', error);
                }
            }, 5000);
        }

        return {
            extractPaymentUrlFromCreateResponse: extractPaymentUrlFromCreateResponse,
            clearPaymentStatusPolling: clearPaymentStatusPolling,
            resetCheckoutPaymentState: resetCheckoutPaymentState,
            showExtendSubscriptionModal: showExtendSubscriptionModal,
            goToChoosePaymentMethod: goToChoosePaymentMethod,
            goBackFromChoosePayment: goBackFromChoosePayment,
            goBackFromPayment: goBackFromPayment,
            createPayment: createPayment,
            showPaymentPage: showPaymentPage,
            showPaymentSuccessState: showPaymentSuccessState,
            showPaymentErrorState: showPaymentErrorState,
            checkPaymentStatus: checkPaymentStatus
        };
    }

    window.DarallaPaymentsFeature = window.DarallaPaymentsFeature || {};
    window.DarallaPaymentsFeature.create = createPaymentsFeature;
})();
