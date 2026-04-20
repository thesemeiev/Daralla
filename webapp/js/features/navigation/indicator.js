(function () {
    function create(deps) {
        deps = deps || {};
        var showPage = typeof deps.showPage === 'function'
            ? deps.showPage
            : function (page) {
                if (typeof window.showPage === 'function') window.showPage(page);
            };

        var navIndicatorState = {
            currentX: 0,
            currentWidth: 56,
            currentScale: 1,
            targetX: 0,
            targetWidth: 56,
            targetScale: 1,
            isDragging: false
        };
        var DRAG_SCALE = 1.28;
        var DRAG_PILL_WIDTH = 80;
        var DRAG_PILL_HEIGHT = 56;

        function getNavIconCenterX(item, navRect) {
            var icon = item && item.querySelector('svg');
            var rect = icon ? icon.getBoundingClientRect() : item.getBoundingClientRect();
            return (rect.left + rect.right) / 2 - navRect.left;
        }

        function applyNavIndicatorPosition() {
            var indicator = document.querySelector('.nav-glass-indicator');
            if (!indicator) return;
            var s = navIndicatorState;
            indicator.style.width = s.currentWidth + 'px';
            if (s.isDragging) {
                indicator.style.height = DRAG_PILL_HEIGHT + 'px';
            } else {
                indicator.style.height = '';
            }
            indicator.style.transform =
                'translateX(' + (s.currentX | 0) + 'px) translateY(-50%) scale(' + s.currentScale.toFixed(3) + ')';
            updateNavIndicatorOverItem();
            var nav = document.querySelector('.bottom-nav');
            if (!nav) return;
            if (!s.isDragging && s.currentScale < 1.08) {
                nav.classList.add('nav-indicator-has-color');
            } else {
                nav.classList.remove('nav-indicator-has-color');
            }
        }

        function setNavIndicatorTargetFromIndex(index) {
            var nav = document.querySelector('.bottom-nav');
            var items = document.querySelectorAll('.nav-item');
            var indicator = document.querySelector('.nav-glass-indicator');
            if (!nav || !items[index] || !indicator) return;
            var navRect = nav.getBoundingClientRect();
            var item = items[index];
            var itemRect = item.getBoundingClientRect();
            var icon = item.querySelector('svg');
            var iconRect = icon ? icon.getBoundingClientRect() : itemRect;
            var iconCenterX = (iconRect.left + iconRect.right) / 2 - navRect.left;
            var w = Math.max(56, itemRect.width * 0.8);
            navIndicatorState.targetWidth = w;
            var x = iconCenterX - w / 2;
            if (!navIndicatorState.isDragging) {
                x = Math.max(0, Math.min(navRect.width - w, x));
            }
            navIndicatorState.targetX = x;
            window.currentNavIndex = index;
            navIndicatorState.currentX = navIndicatorState.targetX;
            navIndicatorState.currentWidth = navIndicatorState.targetWidth;
            navIndicatorState.currentScale = navIndicatorState.targetScale;
            applyNavIndicatorPosition();
        }

        function updateNavIndicatorOverItem() {
            var nav = document.querySelector('.bottom-nav');
            var items = document.querySelectorAll('.nav-item');
            if (!nav || !items.length) return;
            var navRect = nav.getBoundingClientRect();
            var s = navIndicatorState;
            var indicatorCenterX = s.currentX + s.currentWidth / 2;
            var halfW = s.currentWidth / 2;
            var bestIdx = -1;
            var bestDist = 1e9;
            items.forEach(function (item, i) {
                var iconCenterX = getNavIconCenterX(item, navRect);
                var d = Math.abs(iconCenterX - indicatorCenterX);
                if (d < halfW + 20 && d < bestDist) {
                    bestDist = d;
                    bestIdx = i;
                }
            });
            items.forEach(function (item, i) {
                if (i === bestIdx) item.classList.add('indicator-over');
                else item.classList.remove('indicator-over');
            });
        }

        function moveNavIndicator(index) {
            setNavIndicatorTargetFromIndex(index);
        }

        function initNavIndicator() {
            var navItems = document.querySelectorAll('.nav-item');
            var indicator = document.querySelector('.nav-glass-indicator');
            var nav = document.querySelector('.bottom-nav');

            if (!indicator || !nav || !navItems.length) return;
            indicator.classList.add('nav-indicator-mobile');

            function setInitialPosition() {
                var activeItem = document.querySelector('.nav-item.active');
                var idx = activeItem ? Array.from(navItems).indexOf(activeItem) : 0;
                var i = idx >= 0 ? idx : 0;
                setNavIndicatorTargetFromIndex(i);
                navIndicatorState.currentX = navIndicatorState.targetX;
                navIndicatorState.currentWidth = navIndicatorState.targetWidth;
                navIndicatorState.currentScale = navIndicatorState.targetScale = 1;
                applyNavIndicatorPosition();
            }

            requestAnimationFrame(function () {
                requestAnimationFrame(setInitialPosition);
            });

            navItems.forEach(function (item, index) {
                item.addEventListener('click', function () {
                    moveNavIndicator(index);
                });
            });

            function triggerPressEffect() {
                indicator.classList.add('pressing');
                setTimeout(function () {
                    indicator.classList.remove('pressing');
                }, 180);
            }

            navItems.forEach(function (item) {
                item.addEventListener('mousedown', triggerPressEffect);
                item.addEventListener('touchstart', triggerPressEffect, { passive: true });
            });

            var dragStartX = 0;
            var dragStartCenterX = 0;

            function getPointerX(e) {
                return e.touches ? e.touches[0].clientX : e.clientX;
            }

            function onPointerDown(e) {
                if (e.button !== 0 && !e.touches) return;
                var navEl = document.querySelector('.bottom-nav');
                if (!navEl || navEl.style.display === 'none') return;
                navIndicatorState.isDragging = true;
                navIndicatorState.lastAction = 'drag';
                navEl.classList.add('bottom-nav--dragging');
                indicator.classList.add('dragging');
                dragStartX = getPointerX(e);
                dragStartCenterX = navIndicatorState.currentX + navIndicatorState.currentWidth / 2;
                navIndicatorState.targetScale = DRAG_SCALE;
                navIndicatorState.targetWidth = DRAG_PILL_WIDTH;
                navIndicatorState.targetX = dragStartCenterX - DRAG_PILL_WIDTH / 2;
                navIndicatorState.currentScale = DRAG_SCALE;
                navIndicatorState.currentWidth = DRAG_PILL_WIDTH;
                navIndicatorState.currentX = dragStartCenterX - DRAG_PILL_WIDTH / 2;
                applyNavIndicatorPosition();
                e.preventDefault();
            }

            function onPointerMove(e) {
                if (!navIndicatorState.isDragging) return;
                var px = getPointerX(e);
                var delta = px - dragStartX;
                var centerX = dragStartCenterX + delta;
                navIndicatorState.targetX = centerX - DRAG_PILL_WIDTH / 2;
                navIndicatorState.currentX = navIndicatorState.targetX;
                applyNavIndicatorPosition();
                e.preventDefault();
            }

            function onPointerUp() {
                if (!navIndicatorState.isDragging) return;
                navIndicatorState.isDragging = false;
                indicator.classList.remove('dragging');
                var navEl = document.querySelector('.bottom-nav');
                if (navEl) navEl.classList.remove('bottom-nav--dragging');
                var items = document.querySelectorAll('.nav-item');
                var navRect = navEl.getBoundingClientRect();
                var centerX = navIndicatorState.currentX + navIndicatorState.currentWidth / 2;
                var bestIdx = 0;
                var bestDist = 1e9;
                items.forEach(function (item, i) {
                    var iconCenter = getNavIconCenterX(item, navRect);
                    var d = Math.abs(centerX - iconCenter);
                    if (d < bestDist) {
                        bestDist = d;
                        bestIdx = i;
                    }
                });
                var page = items[bestIdx].getAttribute('data-page');
                if (page) showPage(page);
                setNavIndicatorTargetFromIndex(bestIdx);
                navIndicatorState.targetScale = 1;
                navIndicatorState.currentScale = 1;
                navIndicatorState.currentX = navIndicatorState.targetX;
                navIndicatorState.currentWidth = navIndicatorState.targetWidth;
                applyNavIndicatorPosition();
            }

            indicator.addEventListener('mousedown', onPointerDown);
            indicator.addEventListener('touchstart', onPointerDown, { passive: false });
            document.addEventListener('mousemove', onPointerMove);
            document.addEventListener('mouseup', onPointerUp);
            document.addEventListener('touchmove', onPointerMove, { passive: false });
            document.addEventListener('touchend', onPointerUp);
            document.addEventListener('touchcancel', onPointerUp);
        }

        window.addEventListener('resize', function () {
            if (typeof window.currentNavIndex !== 'undefined') {
                setNavIndicatorTargetFromIndex(window.currentNavIndex);
            }
        });

        return {
            moveNavIndicator: moveNavIndicator,
            initNavIndicator: initNavIndicator
        };
    }

    window.DarallaNavigationIndicatorFeature = { create: create };
})();
