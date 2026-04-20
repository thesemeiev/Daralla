(function () {
    function createAuthFeature(deps) {
        var _deps = deps || {};
        var _profileCardAvatarObjectURL = null;

        function setAuthToken(token) {
            return window.DarallaAuthSession.setAuthToken(token);
        }

        function removeAuthToken() {
            return window.DarallaAuthSession.removeAuthToken();
        }

        async function logout() {
            try {
                await fetch('/api/auth/logout', {
                    method: 'POST',
                    credentials: 'include',
                    headers: { 'Content-Type': 'application/json' },
                    body: '{}'
                });
            } catch (e) {}
            if (typeof _deps.onRemoveAuthToken === 'function') {
                _deps.onRemoveAuthToken(removeAuthToken());
            } else {
                removeAuthToken();
            }
            if (typeof _deps.setCurrentUserId === 'function') {
                _deps.setCurrentUserId(null);
            }
            if (typeof _deps.showPage === 'function') {
                _deps.showPage('login');
            }
        }

        function updateProfileCard(userId, username) {
            var titleEl = document.getElementById('profile-card-title');
            var subtitleEl = document.getElementById('profile-card-subtitle');
            if (!titleEl || !subtitleEl) return;
            titleEl.textContent = (username && username !== '-') ? username : 'Мой аккаунт';
            subtitleEl.textContent = (userId && userId !== '-') ? userId : 'Нажмите, чтобы открыть';
        }

        function setProfileAvatarFromInitData() {
            var platform = typeof _deps.getPlatform === 'function' ? _deps.getPlatform() : null;
            var user = platform && platform.getTgUser ? platform.getTgUser() : null;
            var photoUrl = user && user.photo_url;
            if (!photoUrl || typeof photoUrl !== 'string') return false;
            var iconEl = document.querySelector('.profile-card-icon');
            var imgEl = document.getElementById('profile-card-avatar');
            if (!iconEl || !imgEl) return false;
            if (_profileCardAvatarObjectURL) {
                URL.revokeObjectURL(_profileCardAvatarObjectURL);
                _profileCardAvatarObjectURL = null;
            }
            imgEl.src = photoUrl;
            iconEl.classList.add('has-avatar');
            return true;
        }

        async function loadProfileAvatar() {
            var iconEl = document.querySelector('.profile-card-icon');
            var imgEl = document.getElementById('profile-card-avatar');
            if (!iconEl || !imgEl) return;
            if (_profileCardAvatarObjectURL) {
                URL.revokeObjectURL(_profileCardAvatarObjectURL);
                _profileCardAvatarObjectURL = null;
            }
            iconEl.classList.remove('has-avatar');
            try {
                var apiFetch = typeof _deps.apiFetch === 'function' ? _deps.apiFetch : null;
                if (!apiFetch) return;
                var response = await apiFetch('/api/user/avatar', { method: 'GET' });
                if (!response.ok) return;
                var blob = await response.blob();
                _profileCardAvatarObjectURL = URL.createObjectURL(blob);
                imgEl.src = _profileCardAvatarObjectURL;
                iconEl.classList.add('has-avatar');
            } catch (e) {
                console.warn('loadProfileAvatar:', e);
            }
        }

        return {
            setAuthToken: setAuthToken,
            removeAuthToken: removeAuthToken,
            logout: logout,
            updateProfileCard: updateProfileCard,
            setProfileAvatarFromInitData: setProfileAvatarFromInitData,
            loadProfileAvatar: loadProfileAvatar
        };
    }

    window.DarallaAuthFeature = window.DarallaAuthFeature || {};
    window.DarallaAuthFeature.create = createAuthFeature;
})();
