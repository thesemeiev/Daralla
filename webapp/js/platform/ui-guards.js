(function () {
    function createUiGuards() {
        var closeGuardBound = false;
        var focusGuardBound = false;

        function preventCloseOnScroll() {
            if (closeGuardBound) return;
            closeGuardBound = true;

            var touchStartY = 0;
            var touchEndY = 0;
            var isScrolling = false;

            document.addEventListener('touchstart', function (e) {
                touchStartY = e.touches[0].clientY;
                isScrolling = false;
            }, { passive: true });

            document.addEventListener('touchmove', function (e) {
                if (!touchStartY) return;
                touchEndY = e.touches[0].clientY;
                var scrollTop = window.pageYOffset || document.documentElement.scrollTop;
                var isScrollingUp = touchEndY > touchStartY;
                if (isScrollingUp && scrollTop === 0) {
                    var overscroll = touchEndY - touchStartY;
                    if (overscroll > 50) e.preventDefault();
                }
                isScrolling = true;
            }, { passive: false });

            document.addEventListener('touchend', function () {
                touchStartY = 0;
                touchEndY = 0;
                isScrolling = false;
            }, { passive: true });
        }

        function installFocusGuard() {
            if (focusGuardBound) return;
            focusGuardBound = true;

            document.addEventListener('focusin', function (e) {
                var el = e.target;
                if (!el || el === document.body || el === document.documentElement) {
                    setTimeout(function () {
                        if (document.activeElement === document.body || document.activeElement === document.documentElement) {
                            document.body && document.body.blur && document.body.blur();
                        }
                    }, 0);
                    return;
                }
                var tag = (el.tagName || '').toUpperCase();
                var role = (el.getAttribute && el.getAttribute('role')) || '';
                var editable = el.isContentEditable;
                if (tag === 'INPUT' || tag === 'TEXTAREA' || tag === 'SELECT' || tag === 'BUTTON' || tag === 'A' || role === 'button' || editable) return;
                setTimeout(function () {
                    if (document.activeElement === el && (el.tagName || '').toUpperCase() !== 'INPUT' && (el.tagName || '').toUpperCase() !== 'TEXTAREA' && (el.tagName || '').toUpperCase() !== 'SELECT') {
                        el.blur && el.blur();
                    }
                }, 0);
            });
        }

        return {
            preventCloseOnScroll: preventCloseOnScroll,
            installFocusGuard: installFocusGuard
        };
    }

    window.DarallaUiGuards = window.DarallaUiGuards || {};
    window.DarallaUiGuards.create = createUiGuards;
})();
