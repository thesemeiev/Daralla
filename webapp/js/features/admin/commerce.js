(function () {
    function createAdminCommerceFeature(deps) {
        var _deps = deps || {};

        async function loadAdminCommercePage() {
            var loadingEl = document.getElementById('admin-commerce-loading');
            var formEl = document.getElementById('admin-commerce-form');
            var errEl = document.getElementById('admin-commerce-error');
            var msgEl = document.getElementById('admin-commerce-form-message');
            if (msgEl) {
                msgEl.style.display = 'none';
                msgEl.textContent = '';
                msgEl.className = 'form-message';
            }
            if (errEl) {
                errEl.style.display = 'none';
                errEl.textContent = '';
            }
            if (loadingEl) loadingEl.style.display = 'block';
            if (formEl) formEl.style.display = 'none';
            try {
                var res = await _deps.apiFetch('/api/admin/commerce', { method: 'GET', headers: { 'Content-Type': 'application/json' } });
                var data = await res.json();
                if (!res.ok || !data.success) throw new Error(data.error || 'Не удалось загрузить настройки');
                var pm = document.getElementById('admin-commerce-price-month');
                var p3 = document.getElementById('admin-commerce-price-3month');
                var dl = document.getElementById('admin-commerce-device-limit');
                if (pm) pm.value = String(data.price_month != null ? data.price_month : 150);
                if (p3) p3.value = String(data.price_3month != null ? data.price_3month : 350);
                if (dl) dl.value = String(data.default_device_limit != null ? data.default_device_limit : 1);
            } catch (e) {
                console.error('loadAdminCommercePage', e);
                if (errEl) {
                    errEl.textContent = e.message || String(e);
                    errEl.style.display = 'block';
                }
            } finally {
                if (loadingEl) loadingEl.style.display = 'none';
                if (formEl) formEl.style.display = 'block';
            }
        }

        async function saveAdminCommerce(event) {
            event.preventDefault();
            var pm = parseInt(document.getElementById('admin-commerce-price-month').value, 10);
            var p3 = parseInt(document.getElementById('admin-commerce-price-3month').value, 10);
            var dl = parseInt(document.getElementById('admin-commerce-device-limit').value, 10);
            var msgEl = document.getElementById('admin-commerce-form-message');
            if (msgEl) {
                msgEl.style.display = 'none';
                msgEl.textContent = '';
            }
            if (isNaN(pm) || isNaN(p3) || isNaN(dl)) {
                if (msgEl) {
                    msgEl.className = 'form-message form-message--error';
                    msgEl.textContent = 'Введите целые числа';
                    msgEl.style.display = 'block';
                }
                return;
            }
            try {
                var res = await _deps.apiFetch('/api/admin/commerce', {
                    method: 'POST',
                    headers: { 'Content-Type': 'application/json' },
                    body: JSON.stringify({ price_month: pm, price_3month: p3, default_device_limit: dl })
                });
                var data = await res.json();
                if (!res.ok || !data.success) throw new Error(data.error || 'Ошибка сохранения');
                if (msgEl) {
                    msgEl.className = 'form-message form-message--success';
                    msgEl.textContent = 'Сохранено. Цены и лимит применяются для новых оплат и пробного периода.';
                    msgEl.style.display = 'block';
                }
                _deps.loadPrices();
            } catch (e) {
                console.error('saveAdminCommerce', e);
                if (msgEl) {
                    msgEl.className = 'form-message form-message--error';
                    msgEl.textContent = e.message || String(e);
                    msgEl.style.display = 'block';
                }
            }
        }

        return {
            loadAdminCommercePage: loadAdminCommercePage,
            saveAdminCommerce: saveAdminCommerce
        };
    }

    window.DarallaAdminCommerceFeature = window.DarallaAdminCommerceFeature || {};
    window.DarallaAdminCommerceFeature.create = createAdminCommerceFeature;
})();
