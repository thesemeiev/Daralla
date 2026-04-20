(function (window) {
    'use strict';

    var toastTimer = null;

    function showFormMessage(containerOrId, type, text, autoHideMs) {
        var el = typeof containerOrId === 'string' ? document.getElementById(containerOrId) : containerOrId;
        if (!el) return;
        var box = el.classList && el.classList.contains('form-message') ? el : el.querySelector('.form-message');
        if (!box) {
            box = document.createElement('div');
            box.className = 'form-message';
            box.setAttribute('role', 'alert');
            box.setAttribute('aria-live', 'polite');
            el.appendChild(box);
        }
        if (box._formMessageHideTimer) {
            clearTimeout(box._formMessageHideTimer);
            box._formMessageHideTimer = null;
        }
        box.textContent = text || '';
        box.className = 'form-message form-message--' + (type === 'success' ? 'success' : 'error');
        box.style.display = text ? 'block' : 'none';
        if (text && autoHideMs > 0) {
            box._formMessageHideTimer = setTimeout(function () {
                box._formMessageHideTimer = null;
                box.textContent = '';
                box.style.display = 'none';
            }, autoHideMs);
        }
    }

    function hideFormMessage(containerOrId) {
        var el = typeof containerOrId === 'string' ? document.getElementById(containerOrId) : containerOrId;
        if (!el) return;
        var box = el.classList && el.classList.contains('form-message') ? el : el.querySelector('.form-message');
        if (box) {
            if (box._formMessageHideTimer) {
                clearTimeout(box._formMessageHideTimer);
                box._formMessageHideTimer = null;
            }
            box.textContent = '';
            box.style.display = 'none';
        }
    }

    function showToast(message, duration, variant) {
        duration = duration || 5000;
        variant = variant || '';
        var el = document.getElementById('app-toast');
        if (!el) {
            el = document.createElement('div');
            el.id = 'app-toast';
            el.className = 'app-toast';
            el.setAttribute('role', 'status');
            document.body.appendChild(el);
        }
        el.textContent = message || '';
        el.classList.remove('app-toast--success');
        if (variant === 'success') el.classList.add('app-toast--success');
        el.classList.add('app-toast--visible');
        clearTimeout(toastTimer);
        toastTimer = setTimeout(function () {
            el.classList.remove('app-toast--visible');
        }, duration);
    }

    window.DarallaUiMessages = {
        showFormMessage: showFormMessage,
        hideFormMessage: hideFormMessage,
        showToast: showToast
    };
})(window);
