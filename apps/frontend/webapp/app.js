var TG_STUB = window.DarallaPlatform.TG_STUB;
var isMiniAppHost = window.DarallaPlatform.isMiniAppHost;
var ROUTE_PAGE_NAMES = window.DarallaRouting.ROUTE_PAGE_NAMES;
var getPageFromHash = window.DarallaRouting.getPageFromHash;
var parseHashRoute = window.DarallaRouting.parseHashRoute;
var buildHash = window.DarallaRouting.buildHash;
var isPageAllowedForUser = window.DarallaRouting.isPageAllowedForUser;

// Тема оформления: localStorage = light | dark | system; data-theme = разрешённая light | dark
var THEME_KEY = 'daralla-theme';
var _themeSchemeMq = null;
var _themeSchemeHandler = null;

function getThemePreference() {
    try {
        var stored = localStorage.getItem(THEME_KEY);
        if (stored === 'light' || stored === 'dark' || stored === 'system') return stored;
    } catch (e) {}
    return 'system';
}

function resolveSystemTheme() {
    if (typeof window === 'undefined' || !window.matchMedia) return 'dark';
    return window.matchMedia('(prefers-color-scheme: light)').matches ? 'light' : 'dark';
}

/** Разрешённая тема (для data-theme, графики, Telegram header) */
function getTheme() {
    var pref = getThemePreference();
    if (pref === 'light' || pref === 'dark') return pref;
    return resolveSystemTheme();
}

function syncThemeSchemeListener() {
    if (_themeSchemeMq && _themeSchemeHandler) {
        if (_themeSchemeMq.removeEventListener) {
            _themeSchemeMq.removeEventListener('change', _themeSchemeHandler);
        } else if (_themeSchemeMq.removeListener) {
            _themeSchemeMq.removeListener(_themeSchemeHandler);
        }
        _themeSchemeMq = null;
        _themeSchemeHandler = null;
    }
    if (getThemePreference() !== 'system' || typeof window === 'undefined' || !window.matchMedia) return;
    _themeSchemeMq = window.matchMedia('(prefers-color-scheme: dark)');
    _themeSchemeHandler = function () {
        applyTheme();
    };
    if (_themeSchemeMq.addEventListener) {
        _themeSchemeMq.addEventListener('change', _themeSchemeHandler);
    } else {
        _themeSchemeMq.addListener(_themeSchemeHandler);
    }
}

function setTheme(theme) {
    if (theme !== 'light' && theme !== 'dark' && theme !== 'system') return;
    try {
        localStorage.setItem(THEME_KEY, theme);
    } catch (e) {}
    applyTheme();
}

function applyTheme() {
    var theme = getTheme();
    var root = document.documentElement;
    if (root) root.setAttribute('data-theme', theme);
    var meta = document.querySelector('meta[name="theme-color"]');
    if (meta) meta.setAttribute('content', theme === 'light' ? '#f0f0f2' : '#131314');
    if (typeof platform !== 'undefined' && platform.reapplyTgUi) platform.reapplyTgUi();
    if (typeof serverGlobe !== 'undefined' && serverGlobe && typeof serverGlobe.draw === 'function') {
        try {
            serverGlobe.draw();
        } catch (e) {}
    }
    syncThemeSchemeListener();
}

function refreshThemeToggleUi() {
    var pref = getThemePreference();
    document.querySelectorAll('.theme-btn').forEach(function (b) {
        var t = b.getAttribute('data-theme');
        if (t) b.classList.toggle('active', t === pref);
    });
}

function initThemeToggle() {
    refreshThemeToggleUi();
    document.querySelectorAll('.theme-btn').forEach(function (btn) {
        var pref = btn.getAttribute('data-theme');
        if (!pref) return;
        btn.addEventListener('click', function () {
            setTheme(pref);
            refreshThemeToggleUi();
        });
    });
}

// Адаптер платформы: веб vs Telegram Mini App.
var platform = window.DarallaPlatform.createPlatform({
    getTheme: getTheme,
    parseHashRoute: parseHashRoute,
    routePageNames: ROUTE_PAGE_NAMES,
    loadTelegramScript: loadTelegramScript,
    appShowAlert: appShowAlert,
    appShowConfirm: appShowConfirm,
    getWebAuthToken: function () { return webAuthToken; }
});

// Обратная совместимость: глобальные tg и isWebMode выставляются в DOMContentLoaded после platform.init()
var tg = (window.Telegram && window.Telegram.WebApp) ? window.Telegram.WebApp : TG_STUB;
var uiGuardsFeature = window.DarallaUiGuards.create();
uiGuardsFeature.installFocusGuard();
var navIndicatorFeature = window.DarallaNavigationIndicatorFeature.create({
    showPage: function (pageName) { return showPage(pageName); }
});
var aboutSceneFeature = window.DarallaAboutSceneFeature.create({
    getCurrentPage: function () { return currentPage; },
    getTheme: function () { return getTheme(); }
});

// Централизованный runtime state (источник значений по умолчанию для app.js)
var appState = window.DarallaAppState.create({
    webAuthToken: window.DarallaAuthSession.getInitialToken(),
    isWebMode: !tg.initData
});

// Глобальные переменные состояния (собраны в одном месте)
let webAuthToken = appState.webAuthToken;
let currentUserId = appState.currentUserId;
let isWebMode = appState.isWebMode;
let currentSubscriptionDetail = appState.currentSubscriptionDetail;
let currentPage = appState.currentPage;
let serverLoadChartInterval = appState.serverLoadChartInterval;
let notifRuleEditingId = appState.notifRuleEditingId;
let notifSelectedTriggerHours = appState.notifSelectedTriggerHours;
let currentExtendSubscriptionId = appState.currentExtendSubscriptionId;
let currentPaymentData = appState.currentPaymentData;
let currentPaymentPeriod = appState.currentPaymentPeriod;
let currentPaymentGateway = appState.currentPaymentGateway || 'yookassa';
let currentPlategaPaymentMethod = appState.currentPlategaPaymentMethod || 'sbp';
let isAdmin = appState.isAdmin;
let currentAdminUserPage = appState.currentAdminUserPage;
let currentAdminUserSearch = appState.currentAdminUserSearch;
let currentAdminUserDetailUserId = appState.currentAdminUserDetailUserId;
let currentEditingSubscriptionId = appState.currentEditingSubscriptionId;
let previousAdminPage = appState.previousAdminPage;
let currentCreatingSubscriptionUserId = appState.currentCreatingSubscriptionUserId;
let currentAdminSubscriptionsPage = appState.currentAdminSubscriptionsPage;
let currentAdminSubscriptionsStatus = appState.currentAdminSubscriptionsStatus;
let currentAdminSubscriptionsOwnerQuery = appState.currentAdminSubscriptionsOwnerQuery;
let adminSubscriptionsSearchTimeout = appState.adminSubscriptionsSearchTimeout;
let originalSubscriptionData = appState.originalSubscriptionData;
let currentSubscriptionServers = appState.currentSubscriptionServers;
let dashRevenueChart = appState.dashRevenueChart;
let currentAdminGroups = appState.currentAdminGroups;
let currentAdminServers = appState.currentAdminServers;
let currentSelectedGroupId = appState.currentSelectedGroupId;
let adminServerReorderMode = appState.adminServerReorderMode;

var appFeatures = window.DarallaAppComposition.create({
    onRemoveAuthToken: function (token) { webAuthToken = token; },
    setCurrentUserId: function (value) { currentUserId = value; },
    showPage: function (pageName, params) { return showPage(pageName, params); },
    getPlatform: function () { return platform; },
    apiFetch: function (url, options) { return apiFetch(url, options); },
    setAuthToken: function (token) { return setAuthToken(token); },
    setWebAuthToken: function (token) { webAuthToken = token; },
    checkAdminAccess: function () { return checkAdminAccess(); },
    showFormMessage: function (container, type, text) { return showFormMessage(container, type, text); },
    appShowAlert: function (message, options) { return appShowAlert(message, options); },
    appShowConfirm: function (message, options) { return appShowConfirm(message, options); },
    showModal: function (modalId) { return showModal(modalId); },
    closeModal: function (modalId) { return closeModal(modalId); },
    platform: platform,
    getTgInitData: function () { return tg && tg.initData; },
    getWebAuthToken: function () { return webAuthToken; },
    updateProfileCard: function (userId, username) { return updateProfileCard(userId, username); },
    setProfileAvatarFromInitData: function () { return setProfileAvatarFromInitData(); },
    loadProfileAvatar: function () { return loadProfileAvatar(); },
    escapeHtml: escapeHtml,
    formatTimeRemaining: formatTimeRemaining,
    initTelegramFlow: function () { return initTelegramFlow(); },
    setCurrentSubscriptionDetail: function (value) { currentSubscriptionDetail = value; },
    onBuySubscription: function () {
        currentPaymentPeriod = 'month';
        currentPaymentGateway = 'yookassa';
        currentPlategaPaymentMethod = 'sbp';
        currentExtendSubscriptionId = null;
        resetCheckoutPaymentState();
        showPage('choose-payment-method');
    },
    setCurrentCreatingSubscriptionUserId: function (value) { currentCreatingSubscriptionUserId = value; },
    getCurrentCreatingSubscriptionUserId: function () { return currentCreatingSubscriptionUserId; },
    setPreviousAdminPage: function (value) { previousAdminPage = value; },
    getPreviousAdminPage: function () { return previousAdminPage; },
    showAdminUserDetail: function (userId) { return showAdminUserDetail(userId); },
    buildHash: buildHash,
    showError: function (elementId, message) { return showError(elementId, message); },
    setCurrentAdminUserDetailUserId: function (value) { currentAdminUserDetailUserId = value; },
    getCurrentAdminUserSearch: function () { return currentAdminUserSearch; },
    setCurrentAdminUserPage: function (value) { currentAdminUserPage = value; },
    setCurrentAdminUserSearch: function (value) { currentAdminUserSearch = value; },
    loadAdminUsers: function (page, search) { return loadAdminUsers(page, search); },
    copyTextToClipboard: function (text) { return copyTextToClipboard(text); },
    getCurrentPage: function () { return currentPage; },
    getCurrentEditingSubscriptionId: function () { return currentEditingSubscriptionId; },
    setCurrentEditingSubscriptionId: function (value) { currentEditingSubscriptionId = value; },
    getOriginalSubscriptionData: function () { return originalSubscriptionData; },
    setOriginalSubscriptionData: function (value) { originalSubscriptionData = value; },
    getCurrentSubscriptionServers: function () { return currentSubscriptionServers; },
    setCurrentSubscriptionServers: function (value) { currentSubscriptionServers = value; },
    getCurrentAdminSubscriptionsPage: function () { return currentAdminSubscriptionsPage; },
    getCurrentAdminSubscriptionsStatus: function () { return currentAdminSubscriptionsStatus; },
    getCurrentAdminSubscriptionsOwnerQuery: function () { return currentAdminSubscriptionsOwnerQuery; },
    getCurrentAdminUserDetailUserId: function () { return currentAdminUserDetailUserId; },
    goBackFromCreateSubscription: function () { return goBackFromCreateSubscription(); },
    getServerLoadChartInterval: function () { return serverLoadChartInterval; },
    setServerLoadChartInterval: function (value) { serverLoadChartInterval = value; },
    getDashRevenueChart: function () { return dashRevenueChart; },
    setDashRevenueChart: function (value) { dashRevenueChart = value; },
    loadServerMap: function () { return loadServerMap(); },
    renderEventCard: function (ev, isLive, isEnded) { return renderEventCard(ev, isLive, isEnded); },
    moveNavIndicator: function (index) { return moveNavIndicator(index); },
    getEventDetailLeaderboardTimer: function () { return eventDetailLeaderboardTimer; },
    setEventDetailLeaderboardTimer: function (value) { eventDetailLeaderboardTimer = value; },
    isEventLive: function (ev) { return isEventLive(ev); },
    getEventDaysText: function (ev, isLive, isEnded) { return getEventDaysText(ev, isLive, isEnded); },
    getEventIcons: function () { return { live: EVENT_ICON_LIVE, clock: EVENT_ICON_CLOCK }; },
    buildLeaderboardHtml: function (leaderboard, myPlace) { return buildLeaderboardHtml(leaderboard, myPlace); },
    notifCardPreviewText: function (rule) { return notifCardPreviewText(rule); },
    notifTriggerLabel: function (rule) { return notifTriggerLabel(rule); },
    notifFormatHours: function (hours) { return notifFormatHours(hours); },
    getNotifEventLabels: function () { return NOTIF_EVENT_LABELS; },
    notifParseTemplate: function (raw) { return notifParseTemplate(raw); },
    setRepeatData: function (repeatHours, maxRepeats) { return setRepeatData(repeatHours, maxRepeats); },
    setNotifTriggerFromHours: function (hours, eventType) { return setNotifTriggerFromHours(hours, eventType); },
    onNotifRuleEventTypeChange: function () { return onNotifRuleEventTypeChange(); },
    updateNotifPreview: function () { return updateNotifPreview(); },
    setNotifRuleEditingId: function (value) { notifRuleEditingId = value; },
    getNotifRuleEditingId: function () { return notifRuleEditingId; },
    setNotifSelectedTriggerHours: function (value) { notifSelectedTriggerHours = value; },
    getNotifTriggerHours: function () { return getNotifTriggerHours(); },
    getRepeatData: function () { return getRepeatData(); },
    buildNotifTemplate: function () { return buildNotifTemplate(); },
    closeNotificationRuleForm: function () { return closeNotificationRuleForm(); },
    setCurrentPaymentData: function (value) { currentPaymentData = value; },
    getCurrentPaymentData: function () { return currentPaymentData; },
    setCurrentExtendSubscriptionId: function (value) { currentExtendSubscriptionId = value; },
    getCurrentExtendSubscriptionId: function () { return currentExtendSubscriptionId; },
    setCurrentPaymentPeriod: function (value) { currentPaymentPeriod = value; },
    getCurrentPaymentPeriod: function () { return currentPaymentPeriod; },
    setCurrentPaymentGateway: function (value) { currentPaymentGateway = value; },
    getCurrentPaymentGateway: function () { return currentPaymentGateway; },
    setCurrentPlategaPaymentMethod: function (value) { currentPlategaPaymentMethod = value; },
    getCurrentPlategaPaymentMethod: function () { return currentPlategaPaymentMethod; },
    isHttpUrl: function (value) { return isHttpUrl(value); },
    getReferralCodeFromCurrentPage: function () { return getReferralCodeFromCurrentPage(); },
    hideFormMessage: function (container) { return hideFormMessage(container); },
    removePaymentResultSubline: function () { return removePaymentResultSubline(); },
    ensurePaymentResultSubline: function (page) { return ensurePaymentResultSubline(page); },
    showAppToast: function (message, duration, variant) { return showAppToast(message, duration, variant); },
    loadSubscriptions: function () { return loadSubscriptions(); },
    openPaymentUrl: function () { return openPaymentUrl(); },
    loadPrices: function () { return loadPrices(); },
    getCurrentAdminGroups: function () { return currentAdminGroups; },
    setCurrentAdminGroups: function (value) { currentAdminGroups = value; },
    getCurrentAdminServers: function () { return currentAdminServers; },
    setCurrentAdminServers: function (value) { currentAdminServers = value; },
    getCurrentSelectedGroupId: function () { return currentSelectedGroupId; },
    setCurrentSelectedGroupId: function (value) { currentSelectedGroupId = value; },
    getAdminServerReorderMode: function () { return adminServerReorderMode; },
    setAdminServerReorderMode: function (value) { adminServerReorderMode = value; }
});

var authFeature = appFeatures.authFeature;
var authFormsFeature = appFeatures.authFormsFeature;
var authAccountFeature = appFeatures.authAccountFeature;
var subscriptionsFeature = appFeatures.subscriptionsFeature;
var adminUsersFeature = appFeatures.adminUsersFeature;
var adminUsersListFeature = appFeatures.adminUsersListFeature;
var adminUsersActionsFeature = appFeatures.adminUsersActionsFeature;
var adminSubscriptionEditFeature = appFeatures.adminSubscriptionEditFeature;
var adminSubscriptionCreateFeature = appFeatures.adminSubscriptionCreateFeature;
var adminStatsDashboardFeature = appFeatures.adminStatsDashboardFeature;
var adminBroadcastFeature = appFeatures.adminBroadcastFeature;
var serversFeature = appFeatures.serversFeature;
var eventsFeature = appFeatures.eventsFeature;
var notificationsFeature = appFeatures.notificationsFeature;
var paymentsFeature = appFeatures.paymentsFeature;
var adminCommerceFeature = appFeatures.adminCommerceFeature;
var adminServersFeature = appFeatures.adminServersFeature;
var appActions = window.DarallaAppActions.create();

function setAuthToken(token) {
    webAuthToken = authFeature.setAuthToken(token);
}

function removeAuthToken() {
    webAuthToken = authFeature.removeAuthToken();
}

// Функция для выполнения защищенных запросов к API
async function apiFetch(url, options = {}) {
    return window.DarallaApiClient.apiFetch(url, options, { platform: platform, logout: logout });
}

var logout = authFeature.logout.bind(authFeature);

/** Таймаут автоскрытия сообщения формы (мс). 0 = не скрывать автоматически. */
var FORM_MESSAGE_AUTO_HIDE_MS = 6000;

/**
 * Показывает сообщение об ошибке или успехе в блоке формы (вместо alert).
 * Через FORM_MESSAGE_AUTO_HIDE_MS секунд сообщение автоматически скрывается.
 * @param {string|HTMLElement} containerOrId - ID элемента или сам контейнер с блоком .form-message
 * @param {string} type - 'error' | 'success'
 * @param {string} text - текст сообщения
 */
function showFormMessage(containerOrId, type, text) {
    return window.DarallaUiMessages.showFormMessage(containerOrId, type, text, FORM_MESSAGE_AUTO_HIDE_MS);
}

/**
 * Скрывает сообщение формы (при открытии страницы логина/регистрации и т.д.)
 */
function hideFormMessage(containerOrId) {
    return window.DarallaUiMessages.hideFormMessage(containerOrId);
}

/** Короткое уведомление внизу экрана (оплата, общий UX) */
function showAppToast(message, duration, variant) {
    return window.DarallaUiMessages.showToast(message, duration, variant);
}

function removePaymentResultSubline() {
    var sub = document.getElementById('payment-result-subline');
    if (sub) sub.remove();
}

function ensurePaymentResultSubline(page) {
    var sub = document.getElementById('payment-result-subline');
    if (!sub) {
        sub = document.createElement('p');
        sub.id = 'payment-result-subline';
        sub.className = 'payment-result-subline';
        var header = page.querySelector('.detail-header');
        if (header && header.parentNode) {
            header.parentNode.insertBefore(sub, header.nextSibling);
        } else {
            return null;
        }
    }
    return sub;
}

// Инициализация tg.ready/expand/цветов выполняется в DOMContentLoaded после waitForTelegram

// Текущая страница хранится в централизованном state-блоке выше.

function applyRoute(route, isAuthenticated, isAdmin) {
    if (!route) return false;
    var pageName = route.pageName;
    if (!platform.canShowPage(pageName)) pageName = 'subscriptions';
    if (!isPageAllowedForUser(pageName, isAuthenticated, isAdmin)) return false;
    var p = route.params;
    if (route.pageName === 'admin-user-detail' && p.id) {
        showAdminUserDetail(p.id);
        return true;
    }
    if (route.pageName === 'subscription-detail' && p.id) {
        loadSubscriptions().then(function () {
            var subs = window.allSubscriptions || [];
            var sub = subs.find(function (s) { return String(s.id) === String(p.id); });
            if (sub) showSubscriptionDetail(sub);
            else showPage('subscriptions');
        });
        return true;
    }
    if (route.pageName === 'event-detail' && p.id) {
        showEventDetail(Number(p.id));
        return true;
    }
    if (route.pageName === 'admin-subscription-edit' && p.id) {
        showAdminSubscriptionEdit(Number(p.id));
        return true;
    }
    if (route.pageName === 'admin-server-group' && p.groupId) {
        showPage('admin-server-group', { groupId: String(p.groupId) });
        return true;
    }
    if (route.pageName === 'buy-subscription') {
        currentPaymentPeriod = 'month';
        currentPaymentGateway = 'yookassa';
        currentPlategaPaymentMethod = 'sbp';
        currentExtendSubscriptionId = null;
        resetCheckoutPaymentState();
        showPage('choose-payment-method');
        return true;
    }
    if (route.pageName === 'extend-subscription') {
        if (p.id) {
            showExtendSubscriptionModal(Number(p.id));
        } else {
            showPage('subscriptions');
        }
        return true;
    }
    if (route.pageName === 'admin-create-subscription' && p.userId) {
        showCreateSubscriptionForm(p.userId);
        return true;
    }
    if (pageName === 'admin-users') {
        showPage('admin-users', { page: p.page, search: p.search });
        var searchEl = document.getElementById('admin-user-search');
        if (searchEl) searchEl.value = p.search || '';
        return true;
    }
    if (pageName === 'admin-subscriptions') {
        showPage('admin-subscriptions', {
            page: p.page,
            status: p.status,
            owner: p.owner,
            long: p.long
        });
        return true;
    }
    showPage(pageName);
    return true;
}

// Интервалы для автоматического обновления хранятся в централизованном state-блоке выше.

// Функция переключения страниц (params — необязательный объект для hash)
function showPage(pageName, params) {
    if (pageName === 'landing' && !platform.canShowPage('landing')) {
        showPage('subscriptions', params);
        return;
    }
    if (pageName === 'landing' && currentUserId) {
        showPage('subscriptions', params);
        return;
    }
    if (currentPage === 'admin-stats' && pageName !== 'admin-stats' && serverLoadChartInterval) {
        clearInterval(serverLoadChartInterval);
        serverLoadChartInterval = null;
    }
    if (currentPage === 'event-detail' && pageName !== 'event-detail' && typeof eventDetailLeaderboardTimer !== 'undefined' && eventDetailLeaderboardTimer) {
        clearInterval(eventDetailLeaderboardTimer);
        eventDetailLeaderboardTimer = null;
    }
    if (currentPage === 'about' && pageName !== 'about' && typeof aboutPageDispose === 'function') {
        aboutPageDispose();
    }
    if (pageName !== 'admin-server-group') {
        adminServerReorderMode = false;
        var reorderBtn = document.getElementById('admin-server-reorder-toggle-btn');
        if (reorderBtn) {
            reorderBtn.textContent = 'Порядок';
            reorderBtn.classList.remove('is-active');
        }
        var groupRoot = document.getElementById('admin-server-group-page-root');
        if (groupRoot) groupRoot.classList.remove('admin-server-group-page--reorder');
    }

    // Сбрасываем скролл наверх при переключении страниц
    window.scrollTo(0, 0);
    document.documentElement.scrollTop = 0;
    document.body.scrollTop = 0;
    var landingScroll = document.getElementById('landing-scroll');
    if (landingScroll) landingScroll.scrollTop = 0;
    
    // Показываем нижний навбар только на главных пользовательских разделах (не для админки)
    const bottomNav = document.querySelector('.bottom-nav');
    const isMainSectionPage = (
        pageName === 'subscriptions' ||
        pageName === 'servers' ||
        pageName === 'events' ||
        pageName === 'instructions' ||
        pageName === 'about'
    );
    if (bottomNav) {
        bottomNav.style.display = isMainSectionPage ? 'flex' : 'none';
    }

    platform.mainButton.hide();

    // Скрываем все страницы
    document.querySelectorAll('.page').forEach(page => {
        page.style.display = 'none';
    });
    
    // Показываем нужную страницу
    const pageEl = document.getElementById(`page-${pageName}`);
    if (pageEl) {
        pageEl.style.display = 'block';
        pageEl.classList.add('active');
    }
    
    // Обновляем навигацию
    document.querySelectorAll('.nav-item').forEach(item => {
        item.classList.remove('active');
    });
    
    // Активируем нужный пункт навигации (только для главных разделов)
    if (isMainSectionPage) {
        const navItems = document.querySelectorAll('.nav-item');
        let activeIndex = -1;
        
        if (pageName === 'subscriptions') {
            navItems[0]?.classList.add('active');
            activeIndex = 0;
        } else if (pageName === 'servers') {
            navItems[1]?.classList.add('active');
            activeIndex = 1;
        } else if (pageName === 'events') {
            navItems[2]?.classList.add('active');
            activeIndex = 2;
        } else if (pageName === 'instructions') {
            navItems[3]?.classList.add('active');
            activeIndex = 3;
        } else if (pageName === 'about') {
            navItems[4]?.classList.add('active');
            activeIndex = 4;
        } else if ((pageName === 'admin-stats' || pageName.startsWith('admin-')) && document.getElementById('admin-nav-button')) {
            const adminButton = document.getElementById('admin-nav-button');
            adminButton.classList.add('active');
            const allNavItems = Array.from(document.querySelectorAll('.nav-item'));
            activeIndex = allNavItems.indexOf(adminButton);
        }
        
        // Перемещаем индикатор к активной кнопке после того, как layout навбара и страницы устоится
        // (иначе при переходе на «События» и др. rects читаются до reflow — выделение съезжает)
        if (activeIndex >= 0) {
            requestAnimationFrame(function () {
                requestAnimationFrame(function () {
                    moveNavIndicator(activeIndex);
                });
            });
            // Повторный пересчёт после загрузки контента (напр. список событий), чтобы не съезжало
            setTimeout(function () {
                if (typeof window.currentNavIndex !== 'undefined') moveNavIndicator(window.currentNavIndex);
            }, 220);
        }
    }
    
    currentPage = pageName;
    
    // Анимация появления формы при открытии входа/регистрации
    if (pageName === 'login' || pageName === 'register') {
        if (pageName === 'login') hideFormMessage('login-form-message');
        if (pageName === 'register') hideFormMessage('register-form-message');
        const formId = pageName === 'login' ? 'login-form' : 'register-form';
        const successId = pageName === 'login' ? 'login-success-msg' : 'register-success-msg';
        const form = document.getElementById(formId);
        const successMsg = document.getElementById(successId);
        if (successMsg) {
            successMsg.style.display = 'none';
            successMsg.classList.remove('auth-success-visible');
        }
        if (form) {
            form.style.display = '';
            form.classList.remove('auth-form-enter', 'form-shake');
            void form.offsetHeight;
            form.classList.add('auth-form-enter');
            setTimeout(function () { form.classList.remove('auth-form-enter'); }, 500);
        }
    }
    
    // Загружаем данные для страницы
    if (pageName === 'subscriptions') {
        loadSubscriptions();
        refreshAboutAccount();
    } else if (pageName === 'account') {
        hideFormMessage('account-form-message');
        refreshAboutAccount();
    } else if (pageName === 'subscription-detail') {
        hideFormMessage('subscription-detail-message');
    } else if (pageName === 'payment') {
        hideFormMessage('payment-form-message');
    } else if (pageName === 'servers') {
        loadServers();
    } else if (pageName === 'events') {
        loadEvents();
    } else if (pageName === 'admin-users') {
        var page = (params && (params.page != null || params.search !== undefined))
            ? (Number(params.page) || 1)
            : currentAdminUserPage;
        var search = (params && params.search !== undefined)
            ? String(params.search)
            : currentAdminUserSearch;
        loadAdminUsers(page, search);
    } else if (pageName === 'admin-subscriptions') {
        var subPage = (params && params.page != null)
            ? (Number(params.page) || 1)
            : currentAdminSubscriptionsPage;
        if (params) {
            if (params.status !== undefined) {
                currentAdminSubscriptionsStatus = String(params.status || '');
            }
            if (params.owner !== undefined) {
                currentAdminSubscriptionsOwnerQuery = String(params.owner || '');
            }
            if (params.long !== undefined) {
                // Legacy parameter ignored
            }
        }
        loadAdminSubscriptions(subPage);
    } else if (pageName === 'admin-stats') {
        loadAdminStats();
    } else if (pageName === 'admin-broadcast') {
        loadBroadcastPage();
    } else if (pageName === 'admin-server-management') {
        loadServerManagement();
    } else if (pageName === 'admin-server-group') {
        var agId = params && params.groupId != null ? Number(params.groupId) : NaN;
        if (!agId || isNaN(agId)) {
            showPage('admin-server-management');
        } else {
            loadAdminServerGroupPage(agId);
        }
    } else if (pageName === 'admin-commerce') {
        loadAdminCommercePage();
    } else if (pageName === 'admin-events') {
        loadAdminEventsPage();
    } else if (pageName === 'admin-notifications') {
        loadNotificationRules();
    } else if (pageName === 'choose-payment-method') {
        currentPaymentPeriod = currentPaymentPeriod || 'month';
        updateReferralCodeBlockVisibility();
        syncChooseOptionCards();
        bindChoosePaymentSubmit();
        loadPrices();
    } else if (pageName === 'landing') {
        var landingScroll = document.getElementById('landing-scroll');
        if (landingScroll) landingScroll.scrollTop = 0;
        initLandingObserver();
        initLandingWheelAndHint();
    } else if (pageName === 'about') {
        initAboutPage();
    }

    if (ROUTE_PAGE_NAMES.has(pageName)) {
        try { location.hash = buildHash(pageName, params || {}); } catch (e) {}
    }
}
var updateProfileCard = authFeature.updateProfileCard.bind(authFeature);var setProfileAvatarFromInitData = authFeature.setProfileAvatarFromInitData.bind(authFeature);var loadProfileAvatar = authFeature.loadProfileAvatar.bind(authFeature);
function initLandingObserver() {
    var scrollEl = document.getElementById('landing-scroll');
    var sections = document.querySelectorAll('#page-landing .landing-section');
    if (!scrollEl || !sections.length) return;
    sections.forEach(function (s) { s.classList.remove('in-view'); });
    var observer = new IntersectionObserver(
        function (entries) {
            entries.forEach(function (entry) {
                if (entry.isIntersecting) {
                    entry.target.classList.add('in-view');
                }
            });
        },
        { root: scrollEl, threshold: 0.35, rootMargin: '0px' }
    );
    sections.forEach(function (s) { observer.observe(s); });
}

var landingWheelAndHintInited = false;

function initLandingWheelAndHint() {
    var scrollEl = document.getElementById('landing-scroll');
    var hintEl = document.getElementById('landing-scroll-hint');
    var pageLanding = document.getElementById('page-landing');
    if (!scrollEl || !hintEl || !pageLanding) return;

    function updateHintVisibility() {
        if (currentPage !== 'landing') return;
        var threshold = 80;
        if (scrollEl.scrollTop < threshold) {
            hintEl.classList.add('visible');
        } else {
            hintEl.classList.remove('visible');
        }
    }

    if (!landingWheelAndHintInited) {
        landingWheelAndHintInited = true;
        // Только управление подсказкой: сам скролл обрабатывает браузер
        scrollEl.addEventListener('scroll', updateHintVisibility);
    }

    updateHintVisibility();
}

// --- Страница «О нас»: 3D-сеть узлов + рёбра, фон тёмный → белый при скролле ---
var initAboutPage = aboutSceneFeature.initAboutPage.bind(aboutSceneFeature);
var aboutPageDispose = aboutSceneFeature.aboutPageDispose.bind(aboutSceneFeature);
// Функция показа модального окна
function showModal(modalId) {
    const modal = document.getElementById(modalId);
    if (modal) {
        modal.style.display = 'flex';
        // Блокируем скролл основной страницы
        document.body.style.overflow = 'hidden';
    }
}

// Функция закрытия модального окна
function closeModal(modalId) {
    const modal = document.getElementById(modalId);
    if (modal) {
        modal.style.display = 'none';
        // Возвращаем скролл основной страницы
        document.body.style.overflow = '';
    }
}

/**
 * Копирование в буфер: сначала Clipboard API, затем execCommand (Opera и др.).
 * @param {string} text
 * @returns {Promise<boolean>}
 */
function copyTextToClipboard(text) {
    return window.DarallaClipboard.copyTextToClipboard(text);
}

function copyTextToClipboardExec(s) {
    return window.DarallaClipboard.copyTextToClipboardExec(s);
}

function _appDialogOnEscape(e) {
    if (e.key !== 'Escape') return;
    var modal = document.getElementById('app-dialog');
    if (!modal || modal.style.display !== 'flex') return;
    var cancelBtn = document.getElementById('app-dialog-btn-cancel');
    if (cancelBtn && cancelBtn.style.display !== 'none') {
        cancelBtn.click();
    } else {
        var p = document.getElementById('app-dialog-btn-primary');
        if (p) p.click();
    }
}

function appShowAlert(message, opts) {
    opts = opts || {};
    return new Promise(function (resolve) {
        var modal = document.getElementById('app-dialog');
        if (!modal) {
            resolve();
            return;
        }
        var titleEl = document.getElementById('app-dialog-title');
        var bodyEl = document.getElementById('app-dialog-body');
        var promptWrap = document.getElementById('app-dialog-prompt-wrap');
        var cancelBtn = document.getElementById('app-dialog-btn-cancel');
        var primaryBtn = document.getElementById('app-dialog-btn-primary');
        var input = document.getElementById('app-dialog-prompt-input');
        titleEl.textContent = opts.title || 'Сообщение';
        bodyEl.textContent = message || '';
        bodyEl.style.whiteSpace = 'pre-wrap';
        bodyEl.style.display = '';
        promptWrap.style.display = 'none';
        cancelBtn.style.display = 'none';
        primaryBtn.textContent = opts.okText || 'OK';
        modal.classList.remove('app-dialog--error', 'app-dialog--success', 'app-dialog--info');
        if (opts.variant === 'error') modal.classList.add('app-dialog--error');
        else if (opts.variant === 'success') modal.classList.add('app-dialog--success');
        else if (opts.variant === 'info') modal.classList.add('app-dialog--info');
        function finish() {
            primaryBtn.onclick = null;
            document.removeEventListener('keydown', _appDialogOnEscape);
            closeModal('app-dialog');
            resolve();
        }
        primaryBtn.onclick = finish;
        document.addEventListener('keydown', _appDialogOnEscape);
        showModal('app-dialog');
        try { input.blur(); } catch (err) {}
    });
}

function appShowConfirm(message, opts) {
    opts = opts || {};
    return new Promise(function (resolve) {
        var modal = document.getElementById('app-dialog');
        if (!modal) {
            resolve(false);
            return;
        }
        var titleEl = document.getElementById('app-dialog-title');
        var bodyEl = document.getElementById('app-dialog-body');
        var promptWrap = document.getElementById('app-dialog-prompt-wrap');
        var cancelBtn = document.getElementById('app-dialog-btn-cancel');
        var primaryBtn = document.getElementById('app-dialog-btn-primary');
        titleEl.textContent = opts.title || 'Подтверждение';
        bodyEl.textContent = message || '';
        bodyEl.style.whiteSpace = 'pre-wrap';
        bodyEl.style.display = '';
        promptWrap.style.display = 'none';
        cancelBtn.style.display = '';
        cancelBtn.textContent = opts.cancelText || 'Отмена';
        primaryBtn.textContent = opts.confirmText || 'Подтвердить';
        modal.classList.remove('app-dialog--error', 'app-dialog--success', 'app-dialog--info');
        function cleanup() {
            primaryBtn.onclick = null;
            cancelBtn.onclick = null;
            document.removeEventListener('keydown', _appDialogOnEscape);
            closeModal('app-dialog');
        }
        cancelBtn.onclick = function () { cleanup(); resolve(false); };
        primaryBtn.onclick = function () { cleanup(); resolve(true); };
        document.addEventListener('keydown', _appDialogOnEscape);
        showModal('app-dialog');
    });
}

/**
 * @param {string} labelText — подпись к полю ввода
 * @param {string} defaultValue
 * @param {{ title?: string, hint?: string }} opts
 * @returns {Promise<string|null>} null если отмена
 */
function appShowPrompt(labelText, defaultValue, opts) {
    opts = opts || {};
    return new Promise(function (resolve) {
        var modal = document.getElementById('app-dialog');
        if (!modal) {
            resolve(null);
            return;
        }
        var titleEl = document.getElementById('app-dialog-title');
        var bodyEl = document.getElementById('app-dialog-body');
        var promptWrap = document.getElementById('app-dialog-prompt-wrap');
        var cancelBtn = document.getElementById('app-dialog-btn-cancel');
        var primaryBtn = document.getElementById('app-dialog-btn-primary');
        var labelEl = document.getElementById('app-dialog-prompt-label');
        var input = document.getElementById('app-dialog-prompt-input');
        titleEl.textContent = opts.title || 'Ввод';
        if (opts.hint) {
            bodyEl.textContent = opts.hint;
            bodyEl.style.display = '';
        } else {
            bodyEl.textContent = '';
            bodyEl.style.display = 'none';
        }
        bodyEl.style.whiteSpace = 'pre-wrap';
        promptWrap.style.display = '';
        labelEl.textContent = labelText || '';
        input.value = defaultValue != null ? String(defaultValue) : '';
        cancelBtn.style.display = '';
        cancelBtn.textContent = opts.cancelText || 'Отмена';
        primaryBtn.textContent = opts.okText || 'Сохранить';
        modal.classList.remove('app-dialog--error', 'app-dialog--success', 'app-dialog--info');
        function cleanup() {
            primaryBtn.onclick = null;
            cancelBtn.onclick = null;
            input.onkeydown = null;
            document.removeEventListener('keydown', _appDialogOnEscape);
            closeModal('app-dialog');
        }
        cancelBtn.onclick = function () { cleanup(); resolve(null); };
        primaryBtn.onclick = function () {
            var v = (input.value || '').trim();
            cleanup();
            resolve(v);
        };
        input.onkeydown = function (ev) {
            if (ev.key === 'Enter') {
                ev.preventDefault();
                primaryBtn.click();
            }
        };
        document.addEventListener('keydown', _appDialogOnEscape);
        showModal('app-dialog');
        setTimeout(function () {
            try {
                input.focus();
                input.select();
            } catch (e) {}
        }, 50);
    });
}

// Функция показа детальной информации о подписке
var showSubscriptionDetail = subscriptionsFeature.showSubscriptionDetail.bind(subscriptionsFeature);
// Функция загрузки подписок
var loadSubscriptions = subscriptionsFeature.loadSubscriptions.bind(subscriptionsFeature);

// Функция отображения подписок
var renderSubscriptions = subscriptionsFeature.renderSubscriptions.bind(subscriptionsFeature);
// Функция создания карточки подписки
var createSubscriptionCard = subscriptionsFeature.createSubscriptionCard.bind(subscriptionsFeature);
// Функция загрузки серверов
var loadServers = serversFeature.loadServers.bind(serversFeature);

// Иконки для событий (inline SVG, без смайликов)
var EVENT_ICON_LIVE = '<svg class="event-icon-svg" width="14" height="14" viewBox="0 0 24 24" fill="none" xmlns="http://www.w3.org/2000/svg"><circle cx="12" cy="12" r="4" fill="currentColor"/></svg>';
var EVENT_ICON_CLOCK = '<svg class="event-icon-svg" width="14" height="14" viewBox="0 0 24 24" fill="none" xmlns="http://www.w3.org/2000/svg"><circle cx="12" cy="12" r="9" stroke="currentColor" stroke-width="2" fill="none"/><path d="M12 6v6l4 2" stroke="currentColor" stroke-width="2" stroke-linecap="round"/></svg>';
var EVENT_ICON_TROPHY = '<svg class="event-icon-svg" width="18" height="18" viewBox="0 0 24 24" fill="none" xmlns="http://www.w3.org/2000/svg"><path d="M8 4h8v4c0 4.4-1.8 8-4 8s-4-3.6-4-8V4z" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"/><path d="M6 8h2c0 3.3 1.3 6 3 6s3-2.7 3-6h2" stroke="currentColor" stroke-width="2" stroke-linecap="round"/><path d="M12 14v4M9 18h6" stroke="currentColor" stroke-width="2" stroke-linecap="round"/><path d="M10 18v2h4v-2" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"/><rect x="8" y="20" width="8" height="2" rx="0.5" stroke="currentColor" stroke-width="2" fill="none"/></svg>';

function renderEventCard(ev, isLive, isEnded) {
    isEnded = !!isEnded;
    var start = (ev.start_at || '').slice(0, 10);
    var end = (ev.end_at || '').slice(0, 10);
    var cardClass = 'event-card' + (isLive ? ' event-card--live' : '');
    var badgeClass = isLive ? 'event-badge event-badge--live event-badge--blink' : (isEnded ? 'event-badge event-badge--ended' : 'event-badge event-badge--upcoming');
    var badgeIcon = isLive ? EVENT_ICON_LIVE : (isEnded ? '🏁' : EVENT_ICON_CLOCK);
    var badgeText = isLive ? 'Идёт' : (isEnded ? 'Завершено' : 'Скоро');
    var daysText = getEventDaysText(ev, isLive, isEnded);
    var html = '<div class="' + cardClass + '">' +
        '<div class="' + badgeClass + '" style="margin-bottom:10px;">' + badgeIcon + '<span>' + badgeText + '</span></div>' +
        '<h3 style="margin:0 0 8px 0;font-size:1.1em;">' + (ev.name || 'Событие') + '</h3>' +
        (ev.description ? '<p class="event-description">' + ev.description + '</p>' : '') +
        '<p class="event-dates">' + start + ' — ' + end + '</p>';
    if (daysText) html += '<p class="event-days">' + daysText + '</p>';
    var rewards = ev.rewards || [];
    if (rewards.length > 0) {
        var places = rewards.map(function (r) { return r.place + ' место'; }).join(', ');
        html += '<p class="event-card-rewards">Награды: ' + places + '</p>';
    }
    html += '<button type="button" class="btn-primary" style="margin-top:12px;width:100%;" onclick="showEventDetail(' + ev.id + ')">Подробнее</button>' +
        '</div>';
    return html;
}

// Загрузка списка событий (модуль событий)
var loadEvents = eventsFeature.loadEvents.bind(eventsFeature);
var eventDetailLeaderboardTimer = null;
var showEventDetail = eventsFeature.showEventDetail.bind(eventsFeature);
function isEventLive(ev) {
    if (!ev || !ev.start_at || !ev.end_at) return false;
    var now = new Date().toISOString();
    return ev.start_at <= now && ev.end_at >= now;
}

function daysWord(n) {
    n = Math.abs(n);
    var mod10 = n % 10;
    var mod100 = n % 100;
    if (mod100 >= 11 && mod100 <= 14) return 'дней';
    if (mod10 === 1) return 'день';
    if (mod10 >= 2 && mod10 <= 4) return 'дня';
    return 'дней';
}

function getEventDaysText(ev, isLive, isEnded) {
    if (!ev || !ev.start_at || !ev.end_at) return '';
    var now = Date.now();
    var start = new Date(ev.start_at).getTime();
    var end = new Date(ev.end_at).getTime();
    if (isLive) {
        var daysLeft = Math.ceil((end - now) / 86400000);
        if (daysLeft <= 0) return 'Заканчивается сегодня';
        return 'До конца: ' + daysLeft + ' ' + daysWord(daysLeft);
    }
    if (isEnded || end < now) {
        var daysAgo = Math.ceil((now - end) / 86400000);
        if (daysAgo <= 0) return 'Закончилось сегодня';
        return 'Закончилось ' + daysAgo + ' ' + daysWord(daysAgo) + ' назад';
    }
    var daysUntil = Math.ceil((start - now) / 86400000);
    if (daysUntil <= 0) return 'Начинается сегодня';
    return 'До начала: ' + daysUntil + ' ' + daysWord(daysUntil);
}

function buildLeaderboardHtml(leaderboard, myPlace) {
    var list = leaderboard || [];
    var empty = list.length === 0;
    var html = '<div class="live-ranking">';
    if (myPlace) {
        html += '<p style="margin:0 0 12px 0;font-weight:600;">Ваша позиция: ' + myPlace.place + ' (засчитано оплат: ' + myPlace.count + ')</p>';
    }
    html += '<div class="live-ranking-title">' + EVENT_ICON_TROPHY + '<span>Рейтинг</span></div>';
    if (empty) {
        html += '<p class="leaderboard-empty-hint event-description" style="margin:12px 0 0 0;">Пока никого в рейтинге.</p>';
    } else {
        html += '<ul class="leaderboard-list">';
        list.forEach(function (row) {
            var topClass = row.place === 1 ? 'leaderboard-row--top1' : row.place === 2 ? 'leaderboard-row--top2' : row.place === 3 ? 'leaderboard-row--top3' : '';
            var accountId = row.account_id || row.referrer_user_id || '';
            html += '<li class="leaderboard-row ' + topClass + '">' + row.place + '. ' + escapeHtml(accountId) + ' — ' + row.count + '</li>';
        });
        html += '</ul>';
    }
    html += '</div>';
    return html;
}
var loadEventDetail = eventsFeature.loadEventDetail.bind(eventsFeature);
var copyEventReferralCode = eventsFeature.copyEventReferralCode.bind(eventsFeature);
var adminEventEditingId = null;
async function loadAdminEventsPage() {
    var loadingEl = document.getElementById('admin-events-loading');
    var listWrap = document.getElementById('admin-events-list-wrap');
    var listEl = document.getElementById('admin-events-list');
    if (loadingEl) loadingEl.style.display = 'block';
    if (listWrap) listWrap.style.display = 'none';
    try {
        var r = await apiFetch('/api/events/admin/list');
        var data = r.ok ? await r.json() : { events: [] };
        var events = data.events || [];
        if (loadingEl) loadingEl.style.display = 'none';
        if (listWrap) listWrap.style.display = 'block';
        if (listEl) {
            if (events.length === 0) {
                listEl.innerHTML = '<p class="hint">Нет событий. Нажмите «Создать».</p>';
            } else {
                listEl.innerHTML = events.map(function (ev) {
                    var start = (ev.start_at || '').slice(0, 16);
                    var end = (ev.end_at || '').slice(0, 16);
                    return '<div class="event-card" style="border-radius:8px;padding:16px;margin-bottom:12px;">' +
                        '<h3 style="margin:0 0 8px 0;font-size:1.1em;">' + (ev.name || 'Событие') + '</h3>' +
                        '<p class="event-dates">' + start + ' — ' + end + '</p>' +
                        '<div style="display:flex;gap:8px;margin-top:12px;flex-wrap:wrap;">' +
                        '<button type="button" class="btn-secondary" onclick="editAdminEvent(' + ev.id + ')">Редактировать</button>' +
                        '<button type="button" class="btn-secondary admin-event-delete" onclick="deleteAdminEvent(' + ev.id + ')">Удалить</button>' +
                        '</div></div>';
                }).join('');
            }
        }
    } catch (e) {
        if (loadingEl) loadingEl.style.display = 'none';
        if (listEl) listEl.innerHTML = '<p class="hint">Ошибка загрузки</p>';
    }
}
function showAdminEventForm(editId) {
    adminEventEditingId = editId || null;
    document.getElementById('admin-event-form-title').textContent = editId ? 'Редактировать событие' : 'Создать событие';
    document.getElementById('admin-event-name').value = '';
    document.getElementById('admin-event-description').value = '';
    document.getElementById('admin-event-start').value = '';
    document.getElementById('admin-event-end').value = '';
    document.getElementById('admin-event-reward1').value = '';
    document.getElementById('admin-event-reward2').value = '';
    document.getElementById('admin-event-reward3').value = '';
    if (editId) {
        apiFetch('/api/events/' + editId).then(function (r) { return r.ok ? r.json() : null; }).then(function (ev) {
            if (!ev) return;
            document.getElementById('admin-event-name').value = ev.name || '';
            document.getElementById('admin-event-description').value = ev.description || '';
            document.getElementById('admin-event-start').value = (ev.start_at || '').slice(0, 16);
            document.getElementById('admin-event-end').value = (ev.end_at || '').slice(0, 16);
            var rewards = ev.rewards || [];
            if (rewards[0]) document.getElementById('admin-event-reward1').value = rewards[0].description || (rewards[0].days ? (rewards[0].days + ' дн.') : '');
            if (rewards[1]) document.getElementById('admin-event-reward2').value = rewards[1].description || (rewards[1].days ? (rewards[1].days + ' дн.') : '');
            if (rewards[2]) document.getElementById('admin-event-reward3').value = rewards[2].description || (rewards[2].days ? (rewards[2].days + ' дн.') : '');
        });
    }
    document.getElementById('admin-event-form-modal').style.display = 'flex';
}
function editAdminEvent(id) {
    showAdminEventForm(id);
}
function closeAdminEventForm() {
    document.getElementById('admin-event-form-modal').style.display = 'none';
    adminEventEditingId = null;
}
async function submitAdminEventForm(event) {
    event.preventDefault();
    var name = document.getElementById('admin-event-name').value.trim();
    var description = document.getElementById('admin-event-description').value.trim();
    var startAt = (document.getElementById('admin-event-start').value || '').trim();
    var endAt = (document.getElementById('admin-event-end').value || '').trim();
    if (!startAt || !endAt) { await appShowAlert('Укажите начало и окончание', { title: 'Ошибка', variant: 'error' }); return; }
    if (startAt.length === 16) startAt += ':00';
    if (endAt.length === 16) endAt += ':00';
    var forParse = function (v) {
        if (v.indexOf('T') < 0 && v.indexOf(' ') > 0) return v.replace(' ', 'T');
        return v;
    };
    var tsStart = Date.parse(forParse(startAt));
    var tsEnd = Date.parse(forParse(endAt));
    if (isNaN(tsStart) || isNaN(tsEnd)) {
        await appShowAlert('Не удалось разобрать дату или время. Проверьте поля «Начало» и «Окончание».', { title: 'Ошибка', variant: 'error' });
        return;
    }
    if (tsStart >= tsEnd) {
        await appShowAlert('Дата начала должна быть раньше даты окончания.', { title: 'Ошибка', variant: 'error' });
        return;
    }
    var r1 = (document.getElementById('admin-event-reward1').value || '').trim();
    var r2 = (document.getElementById('admin-event-reward2').value || '').trim();
    var r3 = (document.getElementById('admin-event-reward3').value || '').trim();
    var rewards = [];
    if (r1) rewards.push({ place: 1, description: r1 });
    if (r2) rewards.push({ place: 2, description: r2 });
    if (r3) rewards.push({ place: 3, description: r3 });
    var payload = { name: name, description: description, start_at: startAt, end_at: endAt, rewards: rewards };
    var url = adminEventEditingId ? '/api/events/admin/' + adminEventEditingId : '/api/events/admin/create';
    var method = adminEventEditingId ? 'PUT' : 'POST';
    try {
        var r = await apiFetch(url, {
            method: method,
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify(payload)
        });
        if (r.ok) { closeAdminEventForm(); loadAdminEventsPage(); } else {
            var d = await r.json().catch(function () { return {}; });
            await appShowAlert(d.error || 'Ошибка', { title: 'Ошибка', variant: 'error' });
        }
    } catch (e) {
        await appShowAlert('Ошибка сети', { title: 'Ошибка', variant: 'error' });
    }
}
async function deleteAdminEvent(eventId) {
    var ok = await appShowConfirm('Удалить событие?', { title: 'Подтверждение' });
    if (!ok) return;
    try {
        var r = await apiFetch('/api/events/admin/' + eventId, { method: 'DELETE' });
        if (r.ok) loadAdminEventsPage(); else await appShowAlert('Ошибка удаления', { variant: 'error' });
    } catch (e) {
        await appShowAlert('Ошибка сети', { variant: 'error' });
    }
}

// ── Notification Rules ──

var NOTIF_EVENT_LABELS = {
    'expiry_warning': 'Истекает подписка',
    'no_subscription': 'Нет подписки'
};

var NOTIF_TRIGGER_PRESETS = {
    'expiry_warning': [
        { label: '3 дня', hours: 72 },
        { label: '1 день', hours: 24 },
        { label: '6 часов', hours: 6 },
        { label: '1 час', hours: 1 },
    ],
    'no_subscription': [
        { label: '1 день', hours: 24 },
        { label: '3 дня', hours: 72 },
        { label: '7 дней', hours: 168 },
        { label: '14 дней', hours: 336 },
    ]
};

function pluralDays(n) {
    if (n % 10 === 1 && n % 100 !== 11) return 'день';
    if (n % 10 >= 2 && n % 10 <= 4 && (n % 100 < 10 || n % 100 >= 20)) return 'дня';
    return 'дней';
}

function notifTriggerLabel(rule) {
    var h = Math.abs(rule.trigger_hours);
    return notifFormatHours(h);
}

function notifFormatHours(h) {
    if (h % 24 === 0 && h >= 24) {
        var d = h / 24;
        return d + ' ' + pluralDays(d);
    }
    return h + ' ч.';
}

function notifParseTemplate(raw) {
    try {
        var obj = JSON.parse(raw);
        if (obj && typeof obj.title === 'string') return obj;
    } catch (e) { /* legacy */ }
    return { title: '', body: raw, show_time_remaining: false, show_expiry_date: false };
}

function notifCardPreviewText(rule) {
    var t = notifParseTemplate(rule.message_template);
    return t.title || t.body || '—';
}

function renderNotifTriggerChips(eventType) {
    var container = document.getElementById('notif-trigger-chips');
    var presets = NOTIF_TRIGGER_PRESETS[eventType] || [];
    container.innerHTML = presets.map(function (p) {
        return '<button type="button" class="notif-chip" data-hours="' + p.hours + '" onclick="selectNotifTriggerChip(this,' + p.hours + ')">' + p.label + '</button>';
    }).join('') + '<button type="button" class="notif-chip" data-hours="custom" onclick="selectNotifTriggerCustom(this)">Другое</button>';
}

function selectNotifTriggerChip(btn, hours) {
    notifSelectedTriggerHours = hours;
    document.querySelectorAll('#notif-trigger-chips .notif-chip').forEach(function (c) { c.classList.remove('selected'); });
    btn.classList.add('selected');
    document.getElementById('notif-trigger-custom-wrap').style.display = 'none';
    document.getElementById('notif-rule-trigger-value').removeAttribute('required');
}

function selectNotifTriggerCustom(btn) {
    notifSelectedTriggerHours = null;
    document.querySelectorAll('#notif-trigger-chips .notif-chip').forEach(function (c) { c.classList.remove('selected'); });
    btn.classList.add('selected');
    document.getElementById('notif-trigger-custom-wrap').style.display = 'block';
    var inp = document.getElementById('notif-rule-trigger-value');
    inp.setAttribute('required', '');
    inp.focus();
}

function getNotifTriggerHours() {
    if (notifSelectedTriggerHours) return notifSelectedTriggerHours;
    var val = parseInt(document.getElementById('notif-rule-trigger-value').value, 10);
    var unit = document.getElementById('notif-rule-trigger-unit').value;
    if (!val || val < 1) return 0;
    return unit === 'days' ? val * 24 : val;
}

function setNotifTriggerFromHours(absHours, eventType) {
    renderNotifTriggerChips(eventType);
    var presets = NOTIF_TRIGGER_PRESETS[eventType] || [];
    var matched = presets.find(function (p) { return p.hours === absHours; });
    if (matched) {
        notifSelectedTriggerHours = matched.hours;
        var chips = document.querySelectorAll('#notif-trigger-chips .notif-chip');
        chips.forEach(function (c) {
            if (parseInt(c.getAttribute('data-hours'), 10) === matched.hours) c.classList.add('selected');
        });
        document.getElementById('notif-trigger-custom-wrap').style.display = 'none';
    } else {
        notifSelectedTriggerHours = null;
        var customBtn = document.querySelector('#notif-trigger-chips .notif-chip[data-hours="custom"]');
        if (customBtn) customBtn.classList.add('selected');
        document.getElementById('notif-trigger-custom-wrap').style.display = 'block';
        if (absHours % 24 === 0 && absHours >= 24) {
            document.getElementById('notif-rule-trigger-value').value = absHours / 24;
            document.getElementById('notif-rule-trigger-unit').value = 'days';
        } else {
            document.getElementById('notif-rule-trigger-value').value = absHours;
            document.getElementById('notif-rule-trigger-unit').value = 'hours';
        }
    }
}

function onNotifRuleEventTypeChange() {
    var et = document.getElementById('notif-rule-event-type').value;
    renderNotifTriggerChips(et);
    notifSelectedTriggerHours = null;
    document.getElementById('notif-trigger-custom-wrap').style.display = 'none';
    var hint = document.getElementById('notif-rule-trigger-hint');
    hint.textContent = et === 'expiry_warning'
        ? 'За сколько ДО истечения подписки отправить уведомление'
        : 'Через сколько ПОСЛЕ потери подписки отправить уведомление';
    updateNotifPreview();
}

function updateNotifPreview() {
    var title = (document.getElementById('notif-rule-title').value || '').trim();
    var body = (document.getElementById('notif-rule-body').value || '').trim();
    var showTime = document.getElementById('notif-rule-show-time').checked;
    var showExpiry = document.getElementById('notif-rule-show-expiry').checked;

    var html = '';
    if (title) html += '<b>' + escapeHtml(title) + '</b>\n\n';
    if (showTime) html += 'Осталось: <b>2 дня 14 часов</b>\n';
    if (showExpiry) html += 'Истекает: <b>25.02.2026 18:00</b>\n';
    if ((showTime || showExpiry) && body) html += '\n';
    if (body) html += escapeHtml(body);

    var bubble = document.getElementById('notif-preview-bubble');
    bubble.innerHTML = html || '<span style="opacity:0.4">Начните вводить текст…</span>';
}
var loadNotificationRules = notificationsFeature.loadNotificationRules.bind(notificationsFeature);
var showNotificationRuleForm = notificationsFeature.showNotificationRuleForm.bind(notificationsFeature);

function closeNotificationRuleForm() {
    closeModal('admin-notification-form-modal');
    notifRuleEditingId = null;
}

function toggleRepeatFields() {
    var show = document.getElementById('notif-rule-repeat').checked;
    document.getElementById('notif-repeat-fields').style.display = show ? 'block' : 'none';
}

function getRepeatData() {
    if (!document.getElementById('notif-rule-repeat').checked) {
        return { repeat_every_hours: 0, max_repeats: 1 };
    }
    var val = parseInt(document.getElementById('notif-rule-repeat-value').value) || 1;
    var unit = document.getElementById('notif-rule-repeat-unit').value;
    var hours = unit === 'days' ? val * 24 : val;
    var maxR = parseInt(document.getElementById('notif-rule-max-repeats').value) || 1;
    return { repeat_every_hours: hours, max_repeats: Math.max(1, maxR) };
}

function setRepeatData(repeatEveryHours, maxRepeats) {
    var repeatEl = document.getElementById('notif-rule-repeat');
    if (repeatEveryHours > 0 && maxRepeats > 1) {
        repeatEl.checked = true;
        toggleRepeatFields();
        if (repeatEveryHours % 24 === 0 && repeatEveryHours >= 24) {
            document.getElementById('notif-rule-repeat-value').value = repeatEveryHours / 24;
            document.getElementById('notif-rule-repeat-unit').value = 'days';
        } else {
            document.getElementById('notif-rule-repeat-value').value = repeatEveryHours;
            document.getElementById('notif-rule-repeat-unit').value = 'hours';
        }
        document.getElementById('notif-rule-max-repeats').value = maxRepeats;
    } else {
        repeatEl.checked = false;
        toggleRepeatFields();
        document.getElementById('notif-rule-repeat-value').value = 3;
        document.getElementById('notif-rule-repeat-unit').value = 'days';
        document.getElementById('notif-rule-max-repeats').value = 5;
    }
}

function buildNotifTemplate() {
    return JSON.stringify({
        title: (document.getElementById('notif-rule-title').value || '').trim(),
        body: (document.getElementById('notif-rule-body').value || '').trim(),
        show_time_remaining: document.getElementById('notif-rule-show-time').checked,
        show_expiry_date: document.getElementById('notif-rule-show-expiry').checked
    });
}

var saveNotificationRule = notificationsFeature.saveNotificationRule.bind(notificationsFeature);
var deleteNotificationRule = notificationsFeature.deleteNotificationRule.bind(notificationsFeature);var toggleNotificationRule = notificationsFeature.toggleNotificationRule.bind(notificationsFeature);
var testSendNotificationRule = notificationsFeature.testSendNotificationRule.bind(notificationsFeature);

// Функция отображения серверов
// Переменная для хранения экземпляра глобуса
let serverGlobe = null;
let globeAnimationId = null;

/** Координаты для отрисовки на глобусе; null если нет или невалидны (широта/долгота 0 считаются валидными). */
function serverMapCoords(server) {
    if (!server) return null;
    var lat = Number(server.lat);
    var lng = Number(server.lng);
    if (!Number.isFinite(lat) || !Number.isFinite(lng)) return null;
    if (lat < -90 || lat > 90 || lng < -180 || lng > 180) return null;
    return { lat: lat, lng: lng };
}

/** Держим угол в (-π, π], чтобы cos/sin не теряли точность при долгом вращении. */
function _wrapAngleRad(a) {
    var twoPi = Math.PI * 2;
    return ((a + Math.PI) % twoPi + twoPi) % twoPi - Math.PI;
}

// Кастомный 2D глобус на Canvas
class CustomGlobe {
    constructor(canvas, servers) {
        this.canvas = canvas;
        this.ctx = canvas.getContext('2d', { alpha: true });
        this.servers = servers;
        this.rotation = 0; // Горизонтальное вращение (yaw)
        this.pitch = 0; // Вертикальное вращение (pitch) - наклон вверх/вниз
        this.isDragging = false;
        this.lastX = 0;
        this.lastY = 0;
        this.zoom = 1;
        /** После отпускания мыши/пальца автоповорот возобновляется не сразу, а через паузу (мс). */
        this.autoRotatePausedUntil = 0;
        this.mapContainer = canvas.parentElement; // Сохраняем ссылку на контейнер
        
        // Получаем реальные размеры с учетом devicePixelRatio
        const dpr = window.devicePixelRatio || 1;
        const displayWidth = canvas.width / dpr;
        const displayHeight = canvas.height / dpr;
        
        this.baseWidth = displayWidth;
        this.baseHeight = displayHeight;
        this.centerX = displayWidth / 2;
        this.centerY = displayHeight / 2;
        // Увеличиваем радиус для более реалистичного отображения расстояний между точками
        this.radius = Math.min(displayWidth, displayHeight) * 0.5;
        
        // Для pinch-to-zoom
        this.touches = [];
        this.lastDistance = 0;
        this.isPinching = false;
        
        this.setupEventListeners();
        this.animate();
    }
    
    setupEventListeners() {
        // Перетаскивание
        this.canvas.addEventListener('mousedown', (e) => this.onMouseDown(e));
        this.canvas.addEventListener('mousemove', (e) => this.onMouseMove(e));
        this.canvas.addEventListener('mouseup', () => this.onMouseUp());
        this.canvas.addEventListener('mouseleave', () => this.onMouseUp());
        
        // Touch события для мобильных
        this.canvas.addEventListener('touchstart', (e) => {
            e.preventDefault();
            this.touches = Array.from(e.touches);
            
            if (this.touches.length === 1) {
                // Одно касание - перетаскивание
                const touch = this.touches[0];
                this.onMouseDown({ clientX: touch.clientX, clientY: touch.clientY });
                this.isPinching = false;
            } else if (this.touches.length === 2) {
                // Два касания - pinch-to-zoom
                this.isPinching = true;
                this.isDragging = false;
                this.lastDistance = this.getTouchDistance(this.touches[0], this.touches[1]);
            }
        });
        
        this.canvas.addEventListener('touchmove', (e) => {
            e.preventDefault();
            this.touches = Array.from(e.touches);
            
            if (this.touches.length === 1 && !this.isPinching) {
                // Одно касание - перетаскивание
                const touch = this.touches[0];
                this.onMouseMove({ clientX: touch.clientX, clientY: touch.clientY });
            } else if (this.touches.length === 2) {
                // Два касания - pinch-to-zoom
                this.isPinching = true;
                this.isDragging = false;
                const currentDistance = this.getTouchDistance(this.touches[0], this.touches[1]);
                const scale = currentDistance / this.lastDistance;
                this.zoom *= scale;
                this.zoom = Math.max(0.5, Math.min(6, this.zoom)); // Увеличиваем максимум до 6x
                this.lastDistance = currentDistance;
                this.draw();
            }
        });
        
        this.canvas.addEventListener('touchend', (e) => {
            e.preventDefault();
            this.touches = Array.from(e.touches);
            
            if (this.touches.length === 0) {
                this.onMouseUp();
                this.isPinching = false;
            } else if (this.touches.length === 1) {
                // Переключаемся обратно на перетаскивание
                this.isPinching = false;
                const touch = this.touches[0];
                this.onMouseDown({ clientX: touch.clientX, clientY: touch.clientY });
            }
        });
        
        // Масштабирование колесиком
        this.canvas.addEventListener('wheel', (e) => {
            e.preventDefault();
            this.zoom += e.deltaY * -0.001;
            this.zoom = Math.max(0.5, Math.min(6, this.zoom)); // Увеличиваем максимум до 6x
            this.autoRotatePausedUntil = Date.now() + CustomGlobe.AUTO_ROTATE_PAUSE_MS;
            this.draw();
        });
    }
    
    onMouseDown(e) {
        const rect = this.canvas.getBoundingClientRect();
        this.lastX = e.clientX - rect.left;
        this.lastY = e.clientY - rect.top;
        this.isDragging = true;
    }
    
    onMouseMove(e) {
        if (!this.isDragging) return;
        
        const rect = this.canvas.getBoundingClientRect();
        const currentX = e.clientX - rect.left;
        const currentY = e.clientY - rect.top;
        
        const deltaX = currentX - this.lastX;
        const deltaY = currentY - this.lastY;
        
        // Горизонтальное вращение (влево-вправо)
        // Скорость вращения обратно пропорциональна зуму (при большом зуме - медленнее)
        const rotationSpeed = 0.01 / this.zoom;
        this.rotation = _wrapAngleRad(this.rotation + deltaX * rotationSpeed);
        
        // Вертикальное вращение (вверх-вниз) - ограничиваем угол наклона
        const pitchSpeed = 0.01 / this.zoom;
        this.pitch += deltaY * pitchSpeed;
        this.pitch = Math.max(-Math.PI / 2, Math.min(Math.PI / 2, this.pitch)); // Ограничиваем от -90 до 90 градусов
        
        this.lastX = currentX;
        this.lastY = currentY;
        this.draw();
    }
    
    onMouseUp() {
        this.isDragging = false;
        this.autoRotatePausedUntil = Date.now() + CustomGlobe.AUTO_ROTATE_PAUSE_MS;
    }
    
    // Вычисление расстояния между двумя точками касания
    getTouchDistance(touch1, touch2) {
        const dx = touch2.clientX - touch1.clientX;
        const dy = touch2.clientY - touch1.clientY;
        return Math.sqrt(dx * dx + dy * dy);
    }
    
    // Преобразование координат в проекцию глобуса с учетом наклона
    latLngToXY(lat, lng) {
        // Преобразуем широту и долготу в радианы
        const latRad = lat * Math.PI / 180;
        const lngRad = lng * Math.PI / 180;
        
        // Применяем горизонтальное вращение
        const rotatedLng = lngRad + this.rotation;
        
        // Вычисляем 3D координаты на сфере (стандартная сферическая система координат)
        // Инвертируем долготу для правильной ориентации (восток справа, запад слева)
        const x3d = Math.cos(latRad) * Math.cos(-rotatedLng);
        const y3d = Math.sin(latRad);
        const z3d = Math.cos(latRad) * Math.sin(-rotatedLng);
        
        // Применяем вертикальное вращение (pitch) - поворот вокруг оси X
        const cosPitch = Math.cos(this.pitch);
        const sinPitch = Math.sin(this.pitch);
        const yRotated = y3d * cosPitch - z3d * sinPitch;
        const zRotated = y3d * sinPitch + z3d * cosPitch;
        
        // Ортографическая проекция (параллельная проекция)
        // Применяем zoom к радиусу, чтобы точки расходились при увеличении
        const scaledRadius = this.radius * this.zoom;
        // Используем базовый центр для вычислений координат
        const baseCenterX = this.baseWidth / 2;
        const baseCenterY = this.baseHeight / 2;
        const x = baseCenterX + scaledRadius * x3d;
        const y = baseCenterY - scaledRadius * yRotated; // Инвертируем Y для правильной ориентации

        // Видимость: ортографическая проекция вдоль +Z — видна передняя полусфера (z >= 0 после поворота).
        // Проекция лежит внутри круга радиуса scaledRadius; без «квадрата» maxDistance (он давал ложные отсечения).
        const limbEps = 1e-4;
        const dx = x - baseCenterX;
        const dy = y - baseCenterY;
        const r2 = dx * dx + dy * dy;
        const rMax2 = scaledRadius * scaledRadius + limbEps;
        const visible = zRotated >= -limbEps && r2 <= rMax2;

        return { x, y, visible };
    }
    
    // Получить название города по данным сервера
    getCityName(server) {
        // Маппинг стран/локаций на города (на английском)
        const cityMap = {
            'Poland': 'Warsaw',
            'Netherlands': 'Dronten',
            'Russia': 'Moscow',
            'Latvia': 'Riga',
            'Germany': 'Frankfurt'
        };
        
        // Сначала пробуем по location
        if (server.location && cityMap[server.location]) {
            return cityMap[server.location];
        }
        
        // Если location не подходит, пробуем определить по координатам
        var c = serverMapCoords(server);
        if (c) {
            // Warsaw: 52.2297, 21.0122
            if (Math.abs(c.lat - 52.2297) < 0.5 && Math.abs(c.lng - 21.0122) < 0.5) {
                return 'Warsaw';
            }
            // Dronten: 52.5167, 5.7167
            if (Math.abs(c.lat - 52.5167) < 0.5 && Math.abs(c.lng - 5.7167) < 0.5) {
                return 'Dronten';
            }
            // Moscow: 55.7558, 37.6173
            if (Math.abs(c.lat - 55.7558) < 0.5 && Math.abs(c.lng - 37.6173) < 0.5) {
                return 'Moscow';
            }
            // Riga: 56.9496, 24.1052
            if (Math.abs(c.lat - 56.9496) < 0.5 && Math.abs(c.lng - 24.1052) < 0.5) {
                return 'Riga';
            }
            // Frankfurt am Main: 50.1109, 8.6821
            if (Math.abs(c.lat - 50.1109) < 0.5 && Math.abs(c.lng - 8.6821) < 0.5) {
                return 'Frankfurt';
            }
        }
        
        // Fallback на display_name или server_name
        return server.display_name || server.server_name || server.location || '';
    }

    /**
     * Подпись к точке сервера на глобусе (раньше метод не был объявлен — draw() падал после первой точки).
     * Приоритет: название на карте из админки → отображаемое имя → внутреннее имя ноды → локация.
     */
    getGlobeServerLabel(server) {
        if (!server) return '';
        var ml = server.map_label;
        if (ml != null && String(ml).trim() !== '') return String(ml).trim();
        var dn = server.display_name;
        if (dn != null && String(dn).trim() !== '') return String(dn).trim();
        var nm = server.name;
        if (nm != null && String(nm).trim() !== '') return String(nm).trim();
        var loc = server.location;
        if (loc != null && String(loc).trim() !== '' && String(loc).trim() !== 'Other') {
            return String(loc).trim();
        }
        return '';
    }
    
    // Рисует точки крупных городов (серые)
    drawMajorCities(ctx) {
        const cities = this.getMajorCities();
        var themeLight = typeof getTheme === 'function' && getTheme() === 'light';
        const grayColor = themeLight ? '#9a9aa2' : '#7a7a82';
        const cityStroke = themeLight ? '#c8c8d0' : '#4a4a52';
        const cityLabelFill = themeLight ? '#1a1a1e' : '#ececed';
        const cityLabelStroke = themeLight ? 'rgba(255, 255, 255, 0.92)' : 'rgba(0, 0, 0, 0.55)';
        const size = 4;

        cities.forEach(city => {
            const pos = this.latLngToXY(city.lat, city.lng);
            if (!pos.visible) return;

            ctx.fillStyle = grayColor;
            ctx.fillRect(Math.floor(pos.x - size/2), Math.floor(pos.y - size/2), size, size);
            ctx.strokeStyle = cityStroke;
            ctx.lineWidth = 1;
            ctx.strokeRect(Math.floor(pos.x - size/2), Math.floor(pos.y - size/2), size, size);

            const label = city.name;
            const fontSize = 10;
            ctx.font = `${fontSize}px Arial, sans-serif`;
            ctx.textAlign = 'left';
            ctx.textBaseline = 'middle';

            const padding = 6;
            const labelX = Math.round(pos.x + size + padding);
            const labelY = Math.round(pos.y);

            ctx.imageSmoothingEnabled = false;

            ctx.fillStyle = cityLabelFill;
            ctx.strokeStyle = cityLabelStroke;
            ctx.lineWidth = 2;
            ctx.lineJoin = 'round';
            ctx.strokeText(label, labelX, labelY);
            ctx.fillText(label, labelX, labelY);
        });
    }
    
    // Список крупных городов для отображения на глобусе
    getMajorCities() {
        return [
            // Европа
            { name: 'London', lat: 51.5074, lng: -0.1278 },
            { name: 'Paris', lat: 48.8566, lng: 2.3522 },
            { name: 'Berlin', lat: 52.5200, lng: 13.4050 },
            { name: 'Rome', lat: 41.9028, lng: 12.4964 },
            { name: 'Madrid', lat: 40.4168, lng: -3.7038 },
            { name: 'Prague', lat: 50.0755, lng: 14.4378 },
            { name: 'Vienna', lat: 48.2082, lng: 16.3738 },
            { name: 'Stockholm', lat: 59.3293, lng: 18.0686 },
            { name: 'Copenhagen', lat: 55.6761, lng: 12.5683 },
            { name: 'Oslo', lat: 59.9139, lng: 10.7522 },
            { name: 'Dublin', lat: 53.3498, lng: -6.2603 },
            { name: 'Lisbon', lat: 38.7223, lng: -9.1393 },
            { name: 'Athens', lat: 37.9838, lng: 23.7275 },
            { name: 'Istanbul', lat: 41.0082, lng: 28.9784 },
            { name: 'Kyiv', lat: 50.4501, lng: 30.5234 },
            { name: 'Minsk', lat: 53.9045, lng: 27.5615 },
            { name: 'Grozny', lat: 43.3183, lng: 45.6981 },
            { name: 'Brussels', lat: 50.8503, lng: 4.3517 },
            { name: 'Budapest', lat: 47.4979, lng: 19.0402 },
            { name: 'Bucharest', lat: 44.4268, lng: 26.1025 },
            { name: 'Belgrade', lat: 44.7866, lng: 20.4489 },
            { name: 'Zagreb', lat: 45.8150, lng: 15.9819 },
            { name: 'Sofia', lat: 42.6977, lng: 23.3219 },
            { name: 'Tirana', lat: 41.3275, lng: 19.8187 },
            { name: 'Skopje', lat: 41.9981, lng: 21.4254 },
            { name: 'Sarajevo', lat: 43.8563, lng: 18.4131 },
            { name: 'Podgorica', lat: 42.4304, lng: 19.2594 },
            { name: 'Chisinau', lat: 47.0104, lng: 28.8638 },
            { name: 'Vilnius', lat: 54.6872, lng: 25.2797 },
            { name: 'Barcelona', lat: 41.3851, lng: 2.1734 },
            { name: 'Milan', lat: 45.4642, lng: 9.1900 },
            { name: 'Munich', lat: 48.1351, lng: 11.5820 },
            { name: 'Zurich', lat: 47.3769, lng: 8.5417 },
            // Северная Америка
            { name: 'New York', lat: 40.7128, lng: -74.0060 },
            { name: 'Los Angeles', lat: 34.0522, lng: -118.2437 },
            { name: 'Chicago', lat: 41.8781, lng: -87.6298 },
            { name: 'Toronto', lat: 43.6532, lng: -79.3832 },
            { name: 'Miami', lat: 25.7617, lng: -80.1918 },
            { name: 'San Francisco', lat: 37.7749, lng: -122.4194 },
            { name: 'Seattle', lat: 47.6062, lng: -122.3321 },
            { name: 'Vancouver', lat: 49.2827, lng: -123.1207 },
            { name: 'Montreal', lat: 45.5017, lng: -73.5673 },
            { name: 'Boston', lat: 42.3601, lng: -71.0589 },
            { name: 'Washington', lat: 38.9072, lng: -77.0369 },
            { name: 'Atlanta', lat: 33.7490, lng: -84.3880 },
            { name: 'Dallas', lat: 32.7767, lng: -96.7970 },
            { name: 'Houston', lat: 29.7604, lng: -95.3698 },
            { name: 'Mexico City', lat: 19.4326, lng: -99.1332 },
            // Южная Америка
            { name: 'Sao Paulo', lat: -23.5505, lng: -46.6333 },
            { name: 'Buenos Aires', lat: -34.6037, lng: -58.3816 },
            { name: 'Rio de Janeiro', lat: -22.9068, lng: -43.1729 },
            { name: 'Lima', lat: -12.0464, lng: -77.0428 },
            { name: 'Bogota', lat: 4.7110, lng: -74.0721 },
            { name: 'Santiago', lat: -33.4489, lng: -70.6693 },
            { name: 'Caracas', lat: 10.4806, lng: -66.9036 },
            { name: 'Quito', lat: -0.1807, lng: -78.4678 },
            { name: 'Montevideo', lat: -34.9011, lng: -56.1645 },
            { name: 'Asuncion', lat: -25.2637, lng: -57.5759 },
            { name: 'La Paz', lat: -16.2902, lng: -68.1341 },
            { name: 'Brasilia', lat: -15.7942, lng: -47.8822 },
            { name: 'Recife', lat: -8.0476, lng: -34.8770 },
            { name: 'Salvador', lat: -12.9714, lng: -38.5014 },
            { name: 'Medellin', lat: 6.2476, lng: -75.5658 },
            { name: 'Guayaquil', lat: -2.1709, lng: -79.9224 },
            // Азия
            { name: 'Tokyo', lat: 35.6762, lng: 139.6503 },
            { name: 'Beijing', lat: 39.9042, lng: 116.4074 },
            { name: 'Shanghai', lat: 31.2304, lng: 121.4737 },
            { name: 'Hong Kong', lat: 22.3193, lng: 114.1694 },
            { name: 'Singapore', lat: 1.3521, lng: 103.8198 },
            { name: 'Bangkok', lat: 13.7563, lng: 100.5018 },
            { name: 'Delhi', lat: 28.6139, lng: 77.2090 },
            { name: 'Mumbai', lat: 19.0760, lng: 72.8777 },
            { name: 'Dubai', lat: 25.2048, lng: 55.2708 },
            { name: 'Seoul', lat: 37.5665, lng: 126.9780 },
            { name: 'Jakarta', lat: -6.2088, lng: 106.8456 },
            { name: 'Manila', lat: 14.5995, lng: 120.9842 },
            { name: 'Kuala Lumpur', lat: 3.1390, lng: 101.6869 },
            { name: 'Ho Chi Minh City', lat: 10.8231, lng: 106.6297 },
            { name: 'Bangalore', lat: 12.9716, lng: 77.5946 },
            { name: 'Chennai', lat: 13.0827, lng: 80.2707 },
            { name: 'Kolkata', lat: 22.5726, lng: 88.3639 },
            { name: 'Karachi', lat: 24.8607, lng: 67.0011 },
            { name: 'Lahore', lat: 31.5204, lng: 74.3587 },
            { name: 'Tehran', lat: 35.6892, lng: 51.3890 },
            { name: 'Riyadh', lat: 24.7136, lng: 46.6753 },
            { name: 'Mecca', lat: 21.3891, lng: 39.8579 },
            { name: 'Medina', lat: 24.5247, lng: 39.5692 },
            { name: 'Tel Aviv', lat: 32.0853, lng: 34.7818 },
            { name: 'Jerusalem', lat: 31.7683, lng: 35.2137 },
            { name: 'Amman', lat: 31.9539, lng: 35.9106 },
            { name: 'Beirut', lat: 33.8938, lng: 35.5018 },
            { name: 'Baghdad', lat: 33.3152, lng: 44.3661 },
            { name: 'Damascus', lat: 33.5138, lng: 36.2765 },
            { name: 'Almaty', lat: 43.2220, lng: 76.8512 },
            { name: 'Tashkent', lat: 41.2995, lng: 69.2401 },
            { name: 'Bishkek', lat: 42.8746, lng: 74.5698 },
            { name: 'Dushanbe', lat: 38.5598, lng: 68.7870 },
            { name: 'Ashgabat', lat: 37.9601, lng: 58.3261 },
            { name: 'Kabul', lat: 34.5553, lng: 69.2075 },
            { name: 'Islamabad', lat: 33.6844, lng: 73.0479 },
            { name: 'Dhaka', lat: 23.8103, lng: 90.4125 },
            { name: 'Yangon', lat: 16.8661, lng: 96.1951 },
            { name: 'Phnom Penh', lat: 11.5564, lng: 104.9282 },
            // Россия
            { name: 'Novosibirsk', lat: 55.0084, lng: 82.9357 },
            { name: 'Yekaterinburg', lat: 56.8431, lng: 60.6454 },
            { name: 'Kazan', lat: 55.8304, lng: 49.0661 },
            { name: 'Nizhny Novgorod', lat: 56.2965, lng: 43.9361 },
            { name: 'Chelyabinsk', lat: 55.1644, lng: 61.4368 },
            { name: 'Samara', lat: 53.2001, lng: 50.15 },
            { name: 'Omsk', lat: 54.9885, lng: 73.3242 },
            { name: 'Rostov-on-Don', lat: 47.2357, lng: 39.7015 },
            { name: 'Ufa', lat: 54.7348, lng: 55.9578 },
            { name: 'Krasnoyarsk', lat: 56.0184, lng: 92.8672 },
            { name: 'Voronezh', lat: 51.6720, lng: 39.1843 },
            { name: 'Perm', lat: 58.0105, lng: 56.2502 },
            { name: 'Volgograd', lat: 48.7194, lng: 44.5018 },
            { name: 'Krasnodar', lat: 45.0355, lng: 38.9753 },
            { name: 'Saratov', lat: 51.5336, lng: 46.0342 },
            { name: 'Tyumen', lat: 57.1522, lng: 65.5272 },
            { name: 'Tolyatti', lat: 53.5303, lng: 49.3461 },
            { name: 'Izhevsk', lat: 56.8528, lng: 53.2115 },
            { name: 'Barnaul', lat: 53.3606, lng: 83.7636 },
            { name: 'Ulyanovsk', lat: 54.3142, lng: 48.4031 },
            { name: 'Irkutsk', lat: 52.2864, lng: 104.2807 },
            { name: 'Khabarovsk', lat: 48.4802, lng: 135.0719 },
            { name: 'Yaroslavl', lat: 57.6266, lng: 39.8938 },
            { name: 'Vladivostok', lat: 43.1155, lng: 131.8825 },
            { name: 'Tomsk', lat: 56.4977, lng: 84.9744 },
            { name: 'Orenburg', lat: 51.7682, lng: 55.0970 },
            { name: 'Kemerovo', lat: 55.3543, lng: 86.0883 },
            // Африка
            { name: 'Cairo', lat: 30.0444, lng: 31.2357 },
            { name: 'Johannesburg', lat: -26.2041, lng: 28.0473 },
            { name: 'Lagos', lat: 6.5244, lng: 3.3792 },
            { name: 'Nairobi', lat: -1.2921, lng: 36.8219 },
            { name: 'Casablanca', lat: 33.5731, lng: -7.5898 },
            { name: 'Cape Town', lat: -33.9249, lng: 18.4241 },
            { name: 'Addis Ababa', lat: 9.1450, lng: 38.7667 },
            { name: 'Tunis', lat: 36.8065, lng: 10.1815 },
            { name: 'Algiers', lat: 36.7538, lng: 3.0588 },
            { name: 'Rabat', lat: 34.0209, lng: -6.8416 },
            { name: 'Khartoum', lat: 15.5007, lng: 32.5599 },
            { name: 'Dar es Salaam', lat: -6.7924, lng: 39.2083 },
            { name: 'Kampala', lat: 0.3476, lng: 32.5825 },
            { name: 'Accra', lat: 5.6037, lng: -0.1870 },
            { name: 'Abidjan', lat: 5.3600, lng: -4.0083 },
            { name: 'Dakar', lat: 14.7167, lng: -17.4677 },
            { name: 'Luanda', lat: -8.8383, lng: 13.2344 },
            { name: 'Kinshasa', lat: -4.4419, lng: 15.2663 },
            { name: 'Durban', lat: -29.8587, lng: 31.0218 },
            { name: 'Alexandria', lat: 31.2001, lng: 29.9187 },
            { name: 'Tripoli', lat: 32.8872, lng: 13.1913 },
            // Австралия и Океания
            { name: 'Sydney', lat: -33.8688, lng: 151.2093 },
            { name: 'Melbourne', lat: -37.8136, lng: 144.9631 },
            { name: 'Auckland', lat: -36.8485, lng: 174.7633 },
            { name: 'Brisbane', lat: -27.4698, lng: 153.0251 },
            { name: 'Perth', lat: -31.9505, lng: 115.8605 },
            { name: 'Adelaide', lat: -34.9285, lng: 138.6007 },
            { name: 'Darwin', lat: -12.4634, lng: 130.8456 },
            { name: 'Honolulu', lat: 21.3099, lng: -157.8581 },
            { name: 'Wellington', lat: -41.2865, lng: 174.7762 }
        ];
    }
    
    draw() {
        const ctx = this.ctx;
        var themeLight = typeof getTheme === 'function' && getTheme() === 'light';
        /* Светлая тема: тот же градиент, что в тёмной, но на шаг светлее по каждому стопу */
        var globeGradient = themeLight
            ? ['#3f3f47', '#2d2d34', '#1e1e24']
            : ['#34343a', '#222226', '#131314'];
        var globeGridStroke = 'rgba(255, 255, 255, 0.14)';
        var labelColor = themeLight ? '#1a1a1e' : '#ececed';
        var labelStroke = themeLight ? 'rgba(255, 255, 255, 0.85)' : 'rgba(0, 0, 0, 0.55)';
        // Получаем реальные размеры с учетом devicePixelRatio
        const dpr = window.devicePixelRatio || 1;
        const width = this.canvas.width / dpr;
        const height = this.canvas.height / dpr;
        
        /* Прозрачная очистка — фон как у body (mesh + базовый цвет), без «плашки» fillRect */
        ctx.clearRect(0, 0, width, height);
        
        // Рисуем круг глобуса (цвет карточек #1c1e22)
        ctx.save();
        ctx.translate(this.centerX, this.centerY);
        // Убираем ctx.scale - применяем zoom только в latLngToXY для единообразия
        
        // Внешний круг (граница) - применяем zoom к радиусу
        const scaledRadius = this.radius * this.zoom;
        const gradient = ctx.createRadialGradient(0, 0, 0, 0, 0, scaledRadius);
        gradient.addColorStop(0, globeGradient[0]);
        gradient.addColorStop(0.5, globeGradient[1]);
        gradient.addColorStop(1, globeGradient[2]);
        
        ctx.beginPath();
        ctx.arc(0, 0, scaledRadius, 0, Math.PI * 2);
        ctx.fillStyle = gradient;
        ctx.fill();

        // Рисуем сетку (меридианы и параллели) в пиксельном стиле с учетом наклона
        ctx.strokeStyle = globeGridStroke;
        ctx.lineWidth = 1 / this.zoom; // Компенсируем толщину линии при зуме
        
        // Меридианы (вертикальные линии)
        for (let i = 0; i < 12; i++) {
            const lng = (i * 30 - 180) * Math.PI / 180;
            ctx.beginPath();
            let firstPoint = true;
            for (let lat = -90; lat <= 90; lat += 5) {
                const pos = this.latLngToXY(lat, lng * 180 / Math.PI);
                if (pos.visible) {
                    if (firstPoint) {
                        ctx.moveTo(pos.x - this.centerX, pos.y - this.centerY);
                        firstPoint = false;
                    } else {
                        ctx.lineTo(pos.x - this.centerX, pos.y - this.centerY);
                    }
                } else {
                    firstPoint = true; // Начинаем новую линию, если точка невидима
                }
            }
            ctx.stroke();
        }
        
        // Параллели (горизонтальные линии)
        for (let lat = -60; lat <= 60; lat += 30) {
            ctx.beginPath();
            let firstPoint = true;
            for (let lng = -180; lng <= 180; lng += 10) {
                const pos = this.latLngToXY(lat, lng);
                if (pos.visible) {
                    if (firstPoint) {
                        ctx.moveTo(pos.x - this.centerX, pos.y - this.centerY);
                        firstPoint = false;
                    } else {
                        ctx.lineTo(pos.x - this.centerX, pos.y - this.centerY);
                    }
                } else {
                    firstPoint = true;
                }
            }
            ctx.stroke();
        }
        
        ctx.restore();
        
        // Рисуем точки крупных городов (серые)
        this.drawMajorCities(ctx);
        
        // Рисуем точки серверов
        this.servers.forEach(server => {
            var coords = serverMapCoords(server);
            if (!coords) return;

            const pos = this.latLngToXY(coords.lat, coords.lng);
            if (!pos.visible) return;
            
            // Определяем цвет и размер на основе здоровья сервера
            let color = '#4CAF50'; // Зеленый (Online)
            let size = 6;
            
            if (server.status === 'offline') {
                color = '#F44336'; // Красный (Offline)
                size = 8;
            } else if (server.status === 'unknown') {
                color = '#9E9E9E'; // Серый (Unknown)
                size = 6;
            } else if (server.usage_percentage > 80) {
                // Если сервер онлайн, но сильно загружен - оранжевый
                color = '#FF9800'; 
                size = 8;
            }
            
            // Размер точки фиксированный, не зависит от зума
            
            // Рисуем точку в пиксельном стиле
            ctx.fillStyle = color;
            ctx.fillRect(Math.floor(pos.x - size/2), Math.floor(pos.y - size/2), size, size);
            
            ctx.strokeStyle = '#fff';
            ctx.lineWidth = 1;
            ctx.strokeRect(Math.floor(pos.x - size/2), Math.floor(pos.y - size/2), size, size);
            
            // Свечение
            const glowSize = size * 2;
            const glow = ctx.createRadialGradient(pos.x, pos.y, 0, pos.x, pos.y, glowSize);
            glow.addColorStop(0, color + '80');
            glow.addColorStop(1, color + '00');
            ctx.fillStyle = glow;
            ctx.fillRect(Math.floor(pos.x - glowSize), Math.floor(pos.y - glowSize), glowSize * 2, glowSize * 2);
            
            const label = this.getGlobeServerLabel(server);
            if (label) {
                // Размер шрифта фиксированный, не масштабируется с зумом
                const fontSize = 10;
                ctx.font = `${fontSize}px Arial, sans-serif`;
                ctx.textAlign = 'left';
                ctx.textBaseline = 'middle';
                
                // Отключаем сглаживание для четкого текста
                ctx.imageSmoothingEnabled = false;
                
                // Измеряем размер текста
                const textMetrics = ctx.measureText(label);
                const textWidth = textMetrics.width;
                const textHeight = fontSize;
                // Padding фиксированный
                const padding = 4;
                
                // Позиция подписи (справа от точки)
                // Выравниваем по пикселям для четкости
                const labelX = Math.round(pos.x + size + padding);
                const labelY = Math.round(pos.y);
                
                // Рисуем текст без фона (или с очень прозрачным фоном для читаемости)
                ctx.fillStyle = labelColor;
                ctx.strokeStyle = labelStroke;
                ctx.lineWidth = 1.5;
                ctx.lineJoin = 'round';
                ctx.miterLimit = 2;
                // Обводка для читаемости
                ctx.strokeText(label, labelX, labelY);
                // Сам текст
                ctx.fillText(label, labelX, labelY);
            }
        });
    }
    
    animate() {
        try {
            var pauseUntil = this.autoRotatePausedUntil || 0;
            var allowAuto = !this.isDragging && Date.now() >= pauseUntil;
            if (allowAuto) {
                // Угол держим в узком диапазоне — иначе rotation раздувается, cos/sin теряют точность.
                this.rotation = _wrapAngleRad(this.rotation + 0.005);
            }
            this.draw();
        } catch (err) {
            console.error('Globe animate/draw:', err);
        }
        this.animationId = requestAnimationFrame(() => this.animate());
    }
    
    destroy() {
        if (this.animationId) {
            cancelAnimationFrame(this.animationId);
        }
    }
}

/** Пауза автоповорота после взаимодействия (мс), затем снова крутится сам. */
CustomGlobe.AUTO_ROTATE_PAUSE_MS = 3500;

// Загрузка кастомного глобуса серверов
async function loadServerMap() {
    try {
        const mapContainer = document.getElementById('server-map');
        const mapError = document.getElementById('server-map-error');
        
        if (!mapContainer) {
            return;
        }
        
        // Запрашиваем данные о серверах через защищенный API
        const response = await apiFetch(`/api/user/server-usage`);
        
        if (!response.ok) {
            throw new Error('Ошибка загрузки данных серверов');
        }
        
        const result = await response.json();
        if (!result.success || !result.servers || result.servers.length === 0) {
            if (mapError) {
                mapError.style.display = 'none';
            }
            if (serverGlobe) {
                serverGlobe.destroy();
                serverGlobe = null;
            }
            return;
        }
        
        // Скрываем ошибку
        if (mapError) {
            mapError.style.display = 'none';
        }
        
        // Уничтожаем предыдущий глобус
        if (serverGlobe) {
            serverGlobe.destroy();
            serverGlobe = null;
        }
        
        // Очищаем контейнер
        mapContainer.innerHTML = '';
        
        // Настраиваем контейнер для того, чтобы глобус уходил в фон
        mapContainer.style.overflow = 'visible';
        mapContainer.style.position = 'relative';
        mapContainer.style.zIndex = '0';
        
        // Создаем canvas с учетом devicePixelRatio для четкого рендеринга
        const dpr = window.devicePixelRatio || 1;
        const canvas = document.createElement('canvas');
        const displayWidth = mapContainer.clientWidth;
        const displayHeight = mapContainer.clientHeight || 300;
        
        // Устанавливаем реальный размер canvas (с учетом DPR)
        canvas.width = displayWidth * dpr;
        canvas.height = displayHeight * dpr;
        
        // Устанавливаем отображаемый размер и позиционирование
        canvas.style.width = displayWidth + 'px';
        canvas.style.height = displayHeight + 'px';
        canvas.style.position = 'absolute';
        canvas.style.top = '0';
        canvas.style.left = '0';
        canvas.style.cursor = 'grab';
        canvas.style.imageRendering = 'pixelated';
        canvas.style.pointerEvents = 'auto'; // Чтобы события работали
        canvas.style.background = 'transparent';
        
        // Масштабируем контекст для четкого рендеринга
        const ctx = canvas.getContext('2d', { alpha: true });
        ctx.scale(dpr, dpr);
        
        mapContainer.appendChild(canvas);
        
        // Обрабатываем изменение размера
        const resizeObserver = new ResizeObserver(() => {
            const dpr = window.devicePixelRatio || 1;
            const displayWidth = mapContainer.clientWidth;
            const displayHeight = mapContainer.clientHeight || 300;
            
            canvas.width = displayWidth * dpr;
            canvas.height = displayHeight * dpr;
            canvas.style.width = displayWidth + 'px';
            canvas.style.height = displayHeight + 'px';
            
            // Масштабируем контекст заново
            const ctx = canvas.getContext('2d', { alpha: true });
            ctx.scale(dpr, dpr);
            
            if (serverGlobe) {
                // Обновляем базовые размеры
                serverGlobe.baseWidth = displayWidth;
                serverGlobe.baseHeight = displayHeight;
                serverGlobe.centerX = displayWidth / 2;
                serverGlobe.centerY = displayHeight / 2;
                serverGlobe.radius = Math.min(displayWidth, displayHeight) * 0.5;
                // Обновляем размеры canvas в объекте
                serverGlobe.canvas = canvas;
                serverGlobe.ctx = ctx;
            }
        });
        resizeObserver.observe(mapContainer);
        
        // Создаем кастомный глобус
        serverGlobe = new CustomGlobe(canvas, result.servers);
        
    } catch (error) {
        console.error('Ошибка загрузки глобуса серверов:', error);
        const mapError = document.getElementById('server-map-error');
        if (mapError) {
            mapError.style.display = 'block';
        }
    }
}
var renderServers = serversFeature.renderServers.bind(serversFeature);
// Функция копирования ссылки подписки
// Функция показа модального окна переименования подписки
async function showRenameSubscriptionModal() {
    if (!currentSubscriptionDetail) {
        await appShowAlert('Информация о подписке не найдена.', { title: 'Ошибка', variant: 'error' });
        return;
    }
    const currentName = currentSubscriptionDetail.name;
    const newName = await appShowPrompt('Название подписки', currentName, {
        title: 'Переименование',
        hint: 'Введите новое название подписки.',
        okText: 'Сохранить'
    });
    if (newName === null) return;
    const trimmedName = newName.trim();
    if (!trimmedName) {
        await appShowAlert('Название не может быть пустым.', { title: 'Ошибка', variant: 'error' });
        return;
    }
    if (trimmedName === currentName) return;
    renameSubscription(currentSubscriptionDetail.id, trimmedName);
}

// Состояние оплаты хранится в централизованном state-блоке выше.

/** Ссылка на оплату (https/http), без учёта регистра схемы */
function isHttpUrl(s) {
    if (s == null) return false;
    var t = String(s).trim();
    if (!t) return false;
    var low = t.toLowerCase();
    return low.indexOf('http://') === 0 || low.indexOf('https://') === 0;
}
var extractPaymentUrlFromCreateResponse = paymentsFeature.extractPaymentUrlFromCreateResponse.bind(paymentsFeature);
/** Сброс состояния незавершённого платежа перед новым оформлением (не трогает sessionStorage продления). */
var resetCheckoutPaymentState = paymentsFeature.resetCheckoutPaymentState.bind(paymentsFeature);
// Функция показа страницы продления подписки (сразу на оформление с карточками)
var showExtendSubscriptionModal = paymentsFeature.showExtendSubscriptionModal.bind(paymentsFeature);
// Переход на страницу оформления (покупка — с подписок)
var goToChoosePaymentMethod = paymentsFeature.goToChoosePaymentMethod.bind(paymentsFeature);

// Функция возврата со страницы оформления
var goBackFromChoosePayment = paymentsFeature.goBackFromChoosePayment.bind(paymentsFeature);

// Функция возврата с страницы оплаты (на страницу оформления)
var goBackFromPayment = paymentsFeature.goBackFromPayment.bind(paymentsFeature);

/** После редиректа с сайта ЮKassa: payment_return=1; payment_id в query или в sessionStorage */
function handlePaymentReturnFromQuery() {
    var params = new URLSearchParams(window.location.search || '');
    if (params.get('payment_return') !== '1') return;
    var pid = params.get('payment_id');
    if (!pid) {
        try {
            pid = sessionStorage.getItem('payment_return_payment_id') || '';
        } catch (e) { pid = ''; }
    }
    if (!pid) return;
    if (!platform.isTelegram() && !currentUserId) return;
    var extRaw = sessionStorage.getItem('payment_extend_sub_id');
    var extId = extRaw ? parseInt(extRaw, 10) : null;
    if (!extRaw || isNaN(extId)) extId = null;
    try {
        window.history.replaceState(null, '', window.location.pathname + (window.location.hash || ''));
    } catch (e) { /* ignore */ }
    currentPaymentData = {
        payment_id: pid,
        gateway: 'yookassa',
        extend_subscription_id: extId
    };
    showPage('payment');
    showPaymentPage();
}

function openPaymentUrl() {
    var btn = document.getElementById('payment-link-button');
    var url = (currentPaymentData && currentPaymentData.payment_url)
        ? String(currentPaymentData.payment_url).trim()
        : '';
    var paymentId = currentPaymentData && currentPaymentData.payment_id;
    if (!url && btn && btn.dataset.paymentUrl) {
        url = String(btn.dataset.paymentUrl).trim();
        paymentId = btn.dataset.paymentId || paymentId;
    }
    if (!isHttpUrl(url)) {
        platform.showAlert('Ошибка: ссылка на оплату не найдена');
        return;
    }
    platform.openExternalUrl(url);
    if (paymentId) {
        var extPoll = (currentPaymentData && currentPaymentData.extend_subscription_id != null)
            ? currentPaymentData.extend_subscription_id
            : currentExtendSubscriptionId;
        checkPaymentStatus(paymentId, extPoll);
    }
}
if (typeof window !== 'undefined') window.openPaymentUrl = openPaymentUrl;

/** Обработчик клика по кнопке «Перейти к оплате» (кнопка, не ссылка — нет двойного перехода в вебе). */
function bindPaymentLinkButton() {
    if (document.body._paymentLinkDelegationBound) return;
    document.body._paymentLinkDelegationBound = true;
    function handlePaymentLinkClick(e) {
        var btn = document.getElementById('payment-link-button');
        if (!btn || (e.target !== btn && !btn.contains(e.target))) return;
        if (btn.onclick) return;
        e.preventDefault();
        e.stopPropagation();
        if (btn.classList.contains('payment-link-disabled') || btn.getAttribute('aria-disabled') === 'true') return;
        openPaymentUrl();
    }
    document.body.addEventListener('click', handlePaymentLinkClick, true);
    document.body.addEventListener('touchend', function (e) {
        var btn = document.getElementById('payment-link-button');
        if (!btn || (e.target !== btn && !btn.contains(e.target))) return;
        if (btn.onclick) return;
        if (btn.classList.contains('payment-link-disabled') || btn.getAttribute('aria-disabled') === 'true') return;
        e.preventDefault();
        openPaymentUrl();
    }, { passive: false, capture: true });
}
if (document.readyState === 'loading') document.addEventListener('DOMContentLoaded', bindPaymentLinkButton);
else bindPaymentLinkButton();

/** Делегирование кликов «Купить»/«Продлить» — если onclick не сработает (например десктопный TG), переход на выбор способа оплаты всё равно выполнится. */
function bindGoToChoosePaymentDelegation() {
    if (document.body._goToChooseDelegationBound) return;
    document.body._goToChooseDelegationBound = true;
    document.body.addEventListener('click', function (e) {
        var btn = e.target && e.target.closest && e.target.closest('[data-goto-choose][data-period]');
        if (!btn) return;
        var period = btn.getAttribute('data-period');
        if (!period || (period !== 'month' && period !== '3month')) return;
        e.preventDefault();
        e.stopPropagation();
        var subId = btn.getAttribute('data-extend') === '1' ? currentExtendSubscriptionId : null;
        goToChoosePaymentMethod(period, subId);
    }, true);
}
if (document.readyState === 'loading') document.addEventListener('DOMContentLoaded', bindGoToChoosePaymentDelegation);
else bindGoToChoosePaymentDelegation();

async function updateReferralCodeBlockVisibility() {
    var buyBlock = document.getElementById('buy-referral-code-block');
    var extendBlock = document.getElementById('extend-referral-code-block');
    var chooseBlock = document.getElementById('choose-referral-code-block');
    if (buyBlock) buyBlock.style.display = 'none';
    if (extendBlock) extendBlock.style.display = 'none';
    if (!chooseBlock) return;
    try {
        var r = await apiFetch('/api/events/');
        if (!r.ok) return;
        var data = await r.json();
        var hasActive = (data.active || []).length > 0;
        chooseBlock.style.display = hasActive ? 'block' : 'none';
    } catch (e) {
        chooseBlock.style.display = 'none';
    }
}

function getReferralCodeFromCurrentPage() {
    var chooseBlock = document.getElementById('choose-referral-code-block');
    if (!chooseBlock || chooseBlock.style.display === 'none') return '';
    var input = chooseBlock.querySelector('.referral-code-input');
    return input ? (input.value || '').trim() : '';
}

/** Карточки периода и способа оплаты на странице choose-payment-method. */
function syncChooseOptionCards() {
    var container = document.getElementById('page-choose-payment-method');
    if (!container) return;
    var periodRow = container.querySelector('.choose-options-row[aria-label="Период подписки"]');
    var paymentTypeRow = container.querySelector('.choose-options-row[aria-label="Тип оплаты"]');
    var paymentRow = container.querySelector('.choose-options-row[aria-label="Провайдер оплаты"]');
    var plategaMethodBlock = document.getElementById('choose-platega-method-block');
    var plategaMethodRow = plategaMethodBlock && plategaMethodBlock.querySelector('.choose-options-row[aria-label="Метод оплаты Platega"]');
    var plategaProviderSubEl = document.getElementById('choose-platega-provider-sub');
    var submitBtn = document.getElementById('choose-payment-submit');
    var summaryPeriodEl = document.getElementById('choose-summary-period');
    var summaryTypeEl = document.getElementById('choose-summary-type');
    var summaryProviderEl = document.getElementById('choose-summary-provider');
    var summaryPriceEl = document.getElementById('choose-summary-price');
    if (!periodRow || !paymentTypeRow || !paymentRow) return;

    function getCurrentPaymentType() {
        if (currentPaymentGateway === 'cryptocloud') return 'crypto';
        if (currentPaymentGateway === 'platega' && currentPlategaPaymentMethod === 'crypto') return 'crypto';
        return 'fiat';
    }

    function updatePayButtonText() {
        var period = currentPaymentPeriod === '3month' ? '3month' : 'month';
        var periodPriceEl = periodRow.querySelector('.choose-option-card[data-period="' + period + '"] .choose-option-price');
        var priceText = periodPriceEl ? String(periodPriceEl.textContent || '').trim() : '';
        if (!priceText) priceText = period === '3month' ? '350₽' : '150₽';
        if (submitBtn) submitBtn.textContent = 'Создать платёж ' + priceText;
        if (summaryPriceEl) summaryPriceEl.textContent = priceText;
    }

    function providerLabel(gateway) {
        if (gateway === 'cryptocloud') return 'CryptoCloud';
        if (gateway === 'platega') {
            return currentPlategaPaymentMethod === 'crypto' ? 'Platega (Крипта)' : 'Platega (СБП)';
        }
        return 'YooKassa';
    }

    function updateSummary() {
        var period = currentPaymentPeriod === '3month' ? '3month' : 'month';
        if (summaryPeriodEl) summaryPeriodEl.textContent = period === '3month' ? '3 месяца' : '1 месяц';
        if (summaryTypeEl) summaryTypeEl.textContent = getCurrentPaymentType() === 'crypto' ? 'Крипта' : 'Рубли';
        if (summaryProviderEl) summaryProviderEl.textContent = providerLabel(currentPaymentGateway || 'yookassa');
        if (plategaProviderSubEl) {
            plategaProviderSubEl.textContent = getCurrentPaymentType() === 'crypto' ? 'Крипта' : 'СБП';
        }
        updatePayButtonText();
    }

    function supportsPaymentType(card, paymentType) {
        var allowed = String(card.getAttribute('data-supported-types') || '').trim();
        if (!allowed) return true;
        return allowed.split(',').map(function (v) { return String(v || '').trim(); }).indexOf(paymentType) !== -1;
    }

    function setPeriod(period) {
        currentPaymentPeriod = period === '3month' ? '3month' : 'month';
        periodRow.querySelectorAll('.choose-option-card[data-period]').forEach(function (card) {
            var isSelected = card.getAttribute('data-period') === currentPaymentPeriod;
            card.classList.toggle('choose-option-card-selected', isSelected);
            card.setAttribute('aria-pressed', isSelected ? 'true' : 'false');
        });
        updateSummary();
    }

    function setPaymentType(paymentType) {
        var normalized = paymentType === 'crypto' ? 'crypto' : 'fiat';
        paymentTypeRow.querySelectorAll('.choose-option-card[data-payment-type]').forEach(function (card) {
            var isSelected = card.getAttribute('data-payment-type') === normalized;
            card.classList.toggle('choose-option-card-selected', isSelected);
            card.setAttribute('aria-pressed', isSelected ? 'true' : 'false');
        });

        var hasSelectedGateway = false;
        paymentRow.querySelectorAll('.choose-option-card[data-gateway]').forEach(function (card) {
            var allowed = supportsPaymentType(card, normalized);
            card.style.display = allowed ? '' : 'none';
            card.classList.toggle('choose-option-card-disabled', !allowed);
            if (!allowed && card.classList.contains('choose-option-card-selected')) {
                card.classList.remove('choose-option-card-selected');
                card.setAttribute('aria-pressed', 'false');
            }
            if (allowed && card.getAttribute('data-gateway') === currentPaymentGateway) {
                hasSelectedGateway = true;
            }
        });

        if (!hasSelectedGateway) {
            currentPaymentGateway = normalized === 'crypto' ? 'cryptocloud' : 'yookassa';
        }
        if (currentPaymentGateway === 'platega') {
            currentPlategaPaymentMethod = normalized === 'crypto' ? 'crypto' : 'sbp';
        }
        setGateway(currentPaymentGateway, normalized);
    }

    function setGateway(gateway, paymentTypeOverride) {
        var paymentType = paymentTypeOverride === 'crypto' ? 'crypto' : (paymentTypeOverride === 'fiat' ? 'fiat' : getCurrentPaymentType());
        var g = 'yookassa';
        if (gateway === 'cryptocloud') g = 'cryptocloud';
        if (gateway === 'platega') g = 'platega';
        var gatewayCard = paymentRow.querySelector('.choose-option-card[data-gateway="' + g + '"]');
        if (!gatewayCard || !supportsPaymentType(gatewayCard, paymentType)) {
            g = paymentType === 'crypto' ? 'cryptocloud' : 'yookassa';
        }
        currentPaymentGateway = g;
        paymentRow.querySelectorAll('.choose-option-card[data-gateway]').forEach(function (card) {
            var isSelected = card.style.display !== 'none' && card.getAttribute('data-gateway') === g;
            card.classList.toggle('choose-option-card-selected', isSelected);
            card.setAttribute('aria-pressed', isSelected ? 'true' : 'false');
        });
        if (plategaMethodBlock) plategaMethodBlock.style.display = g === 'platega' ? '' : 'none';
        if (g === 'platega') {
            currentPlategaPaymentMethod = paymentType === 'crypto' ? 'crypto' : 'sbp';
            setPlategaMethod(currentPlategaPaymentMethod, paymentType);
        }
        updateSummary();
    }

    function setPlategaMethod(method, paymentTypeOverride) {
        var paymentType = paymentTypeOverride === 'crypto' ? 'crypto' : (paymentTypeOverride === 'fiat' ? 'fiat' : getCurrentPaymentType());
        var resolved = method === 'crypto' ? 'crypto' : 'sbp';
        if (paymentType === 'crypto') resolved = 'crypto';
        if (paymentType === 'fiat') resolved = 'sbp';
        currentPlategaPaymentMethod = resolved;
        if (!plategaMethodRow) return;
        plategaMethodRow.querySelectorAll('.choose-option-card[data-platega-method]').forEach(function (card) {
            var allowed = supportsPaymentType(card, paymentType);
            card.style.display = allowed ? '' : 'none';
            card.classList.toggle('choose-option-card-disabled', !allowed);
            var isSelected = allowed && card.getAttribute('data-platega-method') === resolved;
            card.classList.toggle('choose-option-card-selected', isSelected);
            card.setAttribute('aria-pressed', isSelected ? 'true' : 'false');
        });
        updateSummary();
    }

    periodRow.querySelectorAll('.choose-option-card[data-period]').forEach(function (card) {
        card.removeEventListener('click', card._periodClick);
        card._periodClick = function () { setPeriod(card.getAttribute('data-period')); };
        card.addEventListener('click', card._periodClick);
    });
    paymentTypeRow.querySelectorAll('.choose-option-card[data-payment-type]').forEach(function (card) {
        card.removeEventListener('click', card._paymentTypeClick);
        card._paymentTypeClick = function () { setPaymentType(card.getAttribute('data-payment-type')); };
        card.addEventListener('click', card._paymentTypeClick);
    });
    paymentRow.querySelectorAll('.choose-option-card[data-gateway]').forEach(function (card) {
        card.removeEventListener('click', card._gatewayClick);
        card._gatewayClick = function () { setGateway(card.getAttribute('data-gateway')); };
        card.addEventListener('click', card._gatewayClick);
    });
    if (plategaMethodRow) {
        plategaMethodRow.querySelectorAll('.choose-option-card[data-platega-method]').forEach(function (card) {
            card.removeEventListener('click', card._plategaMethodClick);
            card._plategaMethodClick = function () { setPlategaMethod(card.getAttribute('data-platega-method')); };
            card.addEventListener('click', card._plategaMethodClick);
        });
    }

    setPeriod(currentPaymentPeriod || 'month');
    setPaymentType(getCurrentPaymentType());
    setGateway(currentPaymentGateway || 'yookassa');
    setPlategaMethod(currentPlategaPaymentMethod || 'sbp');
    updateSummary();
}

/** Кнопка «Оплатить» на странице оформления. */
function bindChoosePaymentSubmit() {
    var btn = document.getElementById('choose-payment-submit');
    if (!btn) return;
    if (btn._choosePaymentBound) return;
    btn._choosePaymentBound = true;
    btn.addEventListener('click', function () {
        var container = document.getElementById('page-choose-payment-method');
        var periodCard = container && container.querySelector('.choose-option-card[data-period].choose-option-card-selected');
        var gatewayCard = container && container.querySelector('.choose-option-card[data-gateway].choose-option-card-selected');
        var period = periodCard ? (periodCard.getAttribute('data-period') === '3month' ? '3month' : 'month') : (currentPaymentPeriod || 'month');
        var gateway = 'yookassa';
        if (gatewayCard) {
            var selectedGateway = gatewayCard.getAttribute('data-gateway');
            if (selectedGateway === 'cryptocloud') gateway = 'cryptocloud';
            if (selectedGateway === 'platega') gateway = 'platega';
        }
        var gatewayMethod = null;
        if (gateway === 'platega') {
            var methodCard = container && container.querySelector('.choose-option-card[data-platega-method].choose-option-card-selected');
            gatewayMethod = methodCard ? methodCard.getAttribute('data-platega-method') : (currentPlategaPaymentMethod || 'sbp');
            currentPlategaPaymentMethod = gatewayMethod === 'crypto' ? 'crypto' : 'sbp';
        }
        currentPaymentGateway = gateway;
        createPayment(period, currentExtendSubscriptionId, gateway, gatewayMethod);
    });
}

// Функция создания платежа (вызывается со страницы оформления)
var createPayment = paymentsFeature.createPayment.bind(paymentsFeature);
// Функция показа страницы оплаты
var showPaymentPage = paymentsFeature.showPaymentPage.bind(paymentsFeature);
// Показать на странице оплаты состояние «Оплата прошла» (обновить карточку, кнопка «К подпискам»)
var showPaymentSuccessState = paymentsFeature.showPaymentSuccessState.bind(paymentsFeature);
// Показать на странице оплаты состояние отмены/ошибки (красный статус, кнопка «Попробовать снова»)
var showPaymentErrorState = paymentsFeature.showPaymentErrorState.bind(paymentsFeature);
// Функция проверки статуса платежа
// Примечание: основная обработка платежа идет через вебхук от YooKassa (/webhook/yookassa)
// Polling здесь нужен только для UX - чтобы пользователь видел обновление в мини-приложении
// Вебхук обрабатывает платеж на сервере и обновляет БД, polling просто проверяет статус в БД
var clearPaymentStatusPolling = paymentsFeature.clearPaymentStatusPolling.bind(paymentsFeature);var checkPaymentStatus = paymentsFeature.checkPaymentStatus.bind(paymentsFeature);
// Функция переименования подписки
async function renameSubscription(subId, newName) {
    try {
        const response = await apiFetch(`/api/user/subscription/${subId}/rename`, {
            method: 'POST',
            headers: {
                'Content-Type': 'application/json'
            },
            body: JSON.stringify({
                name: newName
            })
        });
        
        if (!response.ok) {
            const error = await response.json();
            throw new Error(error.error || 'Ошибка переименования');
        }
        
        const data = await response.json();
        
        // Обновляем локальные данные
        currentSubscriptionDetail.name = newName;
        
        // Обновляем отображение
        const nameEl = document.getElementById('detail-subscription-name');
        if (nameEl) {
            nameEl.textContent = escapeHtml(newName);
        }
        document.getElementById('subscription-name-display').textContent = escapeHtml(newName);
        
        // Показываем уведомление об успехе
        showFormMessage('subscription-detail-message', 'success', 'Подписка успешно переименована');
        
        // Обновляем список подписок, если он открыт
        if (document.getElementById('page-subscriptions').classList.contains('active')) {
            loadSubscriptions();
        }
        
    } catch (error) {
        console.error('Ошибка переименования подписки:', error);
        showFormMessage('subscription-detail-message', 'error', 'Ошибка переименования: ' + error.message);
    }
}

async function copySubscriptionLink(token) {
    const webhookUrl = window.location.origin;
    const subscriptionUrl = `${webhookUrl}/sub/${token}`;
    const ok = await copyTextToClipboard(subscriptionUrl);
    if (ok) {
        showModal('subscription-copy-success-modal');
    } else {
        var manualEl = document.getElementById('subscription-copy-manual-url');
        if (manualEl) manualEl.value = subscriptionUrl;
        showModal('subscription-copy-manual-modal');
    }
}

// Функция экранирования HTML
function escapeHtml(text) {
    const div = document.createElement('div');
    div.textContent = text;
    return div.innerHTML;
}

// Функция форматирования оставшегося времени
function formatTimeRemaining(expiresAt) {
    const now = Math.floor(Date.now() / 1000);
    const remaining = expiresAt - now;
    
    if (remaining <= 0) {
        return 'Истекла';
    }
    
    const days = Math.floor(remaining / (24 * 60 * 60));
    const hours = Math.floor((remaining % (24 * 60 * 60)) / (60 * 60));
    
    if (days > 0) {
        return `${days} дн. ${hours} ч.`;
    } else {
        return `${hours} ч.`;
    }
}

// ==================== АДМИН-ПАНЕЛЬ ====================

// Состояние админ-панели хранится в централизованном state-блоке выше.

// Состояние страницы подписок в админке хранится в централизованном state-блоке выше.

// Проверка прав админа
// Функция проверки прав админа
async function checkAdminAccess() {
    try {
        const response = await apiFetch(`/api/admin/check`, {
            method: 'POST',
            headers: {
                'Content-Type': 'application/json'
            }
        });
        
        if (response.ok) {
            const data = await response.json();
            isAdmin = data.is_admin || false;
            
            console.log('Результат проверки прав админа:', isAdmin);
            // Обновляем UI, зависящий от прав админа (профиль и старая кнопка в навбаре)
            updateAdminUI();
            
            return isAdmin;
        } else {
            const errorText = await response.text();
            console.error('Ошибка ответа от сервера:', response.status, errorText);
        }
        return false;
    } catch (error) {
        console.error('Ошибка проверки прав админа:', error);
        return false;
    }
}

// Загрузка списка подписок
async function loadAdminSubscriptions(page = 1, options = {}) {
    try {
        const loadingEl = document.getElementById('admin-subscriptions-loading');
        const contentEl = document.getElementById('admin-subscriptions-content');
        const errorEl = document.getElementById('admin-subscriptions-error');
        if (loadingEl) loadingEl.style.display = 'block';
        if (contentEl) contentEl.style.display = 'none';
        if (errorEl) errorEl.style.display = 'none';

        // Обновляем состояние фильтров из options (если переданы)
        if (options.status !== undefined) {
            currentAdminSubscriptionsStatus = options.status;
        }
        if (options.ownerQuery !== undefined) {
            currentAdminSubscriptionsOwnerQuery = options.ownerQuery;
        }

        const response = await apiFetch('/api/admin/subscriptions', {
            method: 'POST',
            headers: {
                'Content-Type': 'application/json'
            },
            body: JSON.stringify({
                page,
                limit: 20,
                status: currentAdminSubscriptionsStatus || undefined,
                owner_query: currentAdminSubscriptionsOwnerQuery || undefined
            })
        });

        if (!response.ok) {
            throw new Error('Ошибка загрузки подписок');
        }

        const data = await response.json();

        if (loadingEl) loadingEl.style.display = 'none';
        if (contentEl) contentEl.style.display = 'block';

        // Обновляем статистику
        const totalEl = document.getElementById('admin-subscriptions-total');
        if (totalEl) totalEl.textContent = data.total || 0;

        // Отображаем список подписок
        const listEl = document.getElementById('admin-subscriptions-list');
        if (!listEl) return;
        listEl.innerHTML = '';

        if (data.subscriptions && data.subscriptions.length > 0) {
            const now = Math.floor(Date.now() / 1000);
            data.subscriptions.forEach(sub => {
                const card = document.createElement('div');
                card.className = 'admin-subscription-card';
                card.onclick = () => {
                    previousAdminPage = 'admin-subscriptions';
                    showAdminSubscriptionEdit(sub.id);
                };

                // Оставшееся время
                let timeLeftLabel = '';
                let timeLeftClass = 'time-left-ok';
                
                if (sub.status === 'deleted') {
                    timeLeftLabel = 'Удалена';
                    timeLeftClass = 'time-left-deleted';
                } else if (sub.expires_at) {
                    const remaining = sub.expires_at - now;
                    const days = Math.floor(remaining / (24 * 60 * 60));
                    timeLeftLabel = formatTimeRemaining(sub.expires_at);
                    
                    if (remaining <= 0 || days < 1) {
                        timeLeftClass = 'time-left-danger';
                    } else if (days < 7) {
                        timeLeftClass = 'time-left-danger';
                    } else if (days < 30) {
                        timeLeftClass = 'time-left-warning';
                    }
                }

                const ownerDisplay = sub.user_id ? `ID: ${sub.user_id}` : (sub.username || '');

                card.innerHTML = `
                    <div class="admin-subscription-row-main">
                        <div class="admin-subscription-row-left">
                            <div class="admin-subscription-name">${escapeHtml(sub.name || 'Без названия')}</div>
                            ${ownerDisplay ? `<div class="admin-subscription-owner-id">${escapeHtml(ownerDisplay)}</div>` : ''}
                        </div>
                        ${timeLeftLabel ? `<div class="admin-subscription-time-left ${timeLeftClass}">${escapeHtml(timeLeftLabel)}</div>` : ''}
                    </div>
                `;

                listEl.appendChild(card);
            });

            // Пагинация
            if (data.pages > 1) {
                showAdminSubscriptionsPagination(data.page, data.pages);
            } else {
                const pagEl = document.getElementById('admin-subscriptions-pagination');
                if (pagEl) pagEl.style.display = 'none';
            }
        } else {
            listEl.innerHTML = '<div class="empty"><p>Подписки не найдены</p></div>';
            const pagEl = document.getElementById('admin-subscriptions-pagination');
            if (pagEl) pagEl.style.display = 'none';
        }

        currentAdminSubscriptionsPage = page;

        // Синхронизируем фильтры в UI
        const statusSelect = document.getElementById('admin-subscriptions-status');
        if (statusSelect && statusSelect.value !== (currentAdminSubscriptionsStatus || '')) {
            statusSelect.value = currentAdminSubscriptionsStatus || '';
        }
        const ownerInput = document.getElementById('admin-subscriptions-owner-search');
        if (ownerInput && ownerInput.value !== (currentAdminSubscriptionsOwnerQuery || '')) {
            ownerInput.value = currentAdminSubscriptionsOwnerQuery || '';
        }

        // Обновляем hash для возможности возврата на ту же страницу
        try {
            location.hash = buildHash('admin-subscriptions', {
                page: String(page),
                status: currentAdminSubscriptionsStatus || '',
                owner: currentAdminSubscriptionsOwnerQuery || ''
            });
        } catch (e) {}
    } catch (error) {
        console.error('Ошибка загрузки подписок:', error);
        const loadingEl = document.getElementById('admin-subscriptions-loading');
        const errorEl = document.getElementById('admin-subscriptions-error');
        if (loadingEl) loadingEl.style.display = 'none';
        if (errorEl) errorEl.style.display = 'block';
    }
}

// Поиск по владельцу
function handleAdminSubscriptionsSearch() {
    clearTimeout(adminSubscriptionsSearchTimeout);
    const input = document.getElementById('admin-subscriptions-owner-search');
    const value = input ? input.value.trim() : '';
    adminSubscriptionsSearchTimeout = setTimeout(() => {
        currentAdminSubscriptionsOwnerQuery = value;
        loadAdminSubscriptions(1);
    }, 500);
}

// Применение фильтров (статус и т.п.)
function reloadAdminSubscriptionsWithFilters() {
    const statusSelect = document.getElementById('admin-subscriptions-status');
    if (statusSelect) {
        currentAdminSubscriptionsStatus = statusSelect.value || '';
    }
    loadAdminSubscriptions(1);
}

// Пагинация для подписок
function showAdminSubscriptionsPagination(currentPage, totalPages) {
    const paginationEl = document.getElementById('admin-subscriptions-pagination');
    if (!paginationEl) return;
    paginationEl.style.display = 'flex';
    paginationEl.innerHTML = '';

    const prevBtn = document.createElement('button');
    prevBtn.textContent = '←';
    prevBtn.disabled = currentPage === 1;
    prevBtn.onclick = () => loadAdminSubscriptions(currentPage - 1);
    paginationEl.appendChild(prevBtn);

    const startPage = Math.max(1, currentPage - 2);
    const endPage = Math.min(totalPages, currentPage + 2);

    for (let i = startPage; i <= endPage; i++) {
        const pageBtn = document.createElement('button');
        pageBtn.textContent = i;
        pageBtn.className = i === currentPage ? 'active' : '';
        pageBtn.onclick = () => loadAdminSubscriptions(i);
        paginationEl.appendChild(pageBtn);
    }

    const nextBtn = document.createElement('button');
    nextBtn.textContent = '→';
    nextBtn.disabled = currentPage === totalPages;
    nextBtn.onclick = () => loadAdminSubscriptions(currentPage + 1);
    paginationEl.appendChild(nextBtn);
}

// Обновление UI, зависящего от прав админа (профиль и старая кнопка в навбаре)
function updateAdminUI() {
    // Показываем/скрываем блок в профиле
    var adminSection = document.getElementById('admin-account-section');
    if (adminSection) {
        adminSection.style.display = isAdmin ? 'block' : 'none';
    }
    // На всякий случай удаляем старую кнопку админ-панели из нижней навигации, если она уже существует
    var legacyAdminButton = document.getElementById('admin-nav-button');
    if (legacyAdminButton && legacyAdminButton.parentNode) {
        legacyAdminButton.parentNode.removeChild(legacyAdminButton);
    }
}

// Загрузка списка пользователей
var loadAdminUsers = adminUsersListFeature.loadAdminUsers.bind(adminUsersListFeature);

// Поиск пользователей
var handleAdminUserSearch = adminUsersListFeature.handleAdminUserSearch.bind(adminUsersListFeature);
// Пагинация
var showAdminPagination = adminUsersListFeature.showAdminPagination.bind(adminUsersListFeature);
// Показать детальную информацию о пользователе
var showAdminUserDetail = adminUsersListFeature.showAdminUserDetail.bind(adminUsersListFeature);
// Показать форму редактирования подписки
var showAdminSubscriptionEdit = adminSubscriptionEditFeature.showAdminSubscriptionEdit.bind(adminSubscriptionEditFeature);
// Сохранение изменений подписки
var saveSubscriptionChanges = adminSubscriptionEditFeature.saveSubscriptionChanges.bind(adminSubscriptionEditFeature);

// Закрытие модального окна
var closeSubscriptionConfirmModal = adminSubscriptionEditFeature.closeSubscriptionConfirmModal.bind(adminSubscriptionEditFeature);

// Подтверждение и сохранение изменений
var confirmSaveSubscriptionChanges = adminSubscriptionEditFeature.confirmSaveSubscriptionChanges.bind(adminSubscriptionEditFeature);

// Синхронизация подписки
var syncSubscription = adminSubscriptionEditFeature.syncSubscription.bind(adminSubscriptionEditFeature);
// Переключение между вкладками редактирования подписки
var switchSubscriptionTab = adminSubscriptionEditFeature.switchSubscriptionTab.bind(adminSubscriptionEditFeature);

// Загрузка и отображение ключей подписки
var loadSubscriptionKeys = adminSubscriptionEditFeature.loadSubscriptionKeys.bind(adminSubscriptionEditFeature);
// Функция копирования в буфер обмена (админка)
var copyToClipboard = adminSubscriptionEditFeature.copyToClipboard.bind(adminSubscriptionEditFeature);
// Возврат назад из редактирования подписки
var goBackFromSubscriptionEdit = adminSubscriptionEditFeature.goBackFromSubscriptionEdit.bind(adminSubscriptionEditFeature);

// Показать форму создания подписки
var showCreateSubscriptionForm = adminUsersFeature.showCreateSubscriptionForm.bind(adminUsersFeature);
// Возврат назад из создания подписки
var goBackFromCreateSubscription = adminUsersFeature.goBackFromCreateSubscription.bind(adminUsersFeature);

// Возврат назад из детальной информации о пользователе
var goBackFromUserDetail = adminUsersActionsFeature.goBackFromUserDetail.bind(adminUsersActionsFeature);

// Показать модальное окно подтверждения удаления пользователя
var showDeleteUserConfirm = adminUsersActionsFeature.showDeleteUserConfirm.bind(adminUsersActionsFeature);
// Закрыть модальное окно удаления пользователя
var closeDeleteUserModal = adminUsersActionsFeature.closeDeleteUserModal.bind(adminUsersActionsFeature);
// Подтвердить удаление пользователя
var confirmDeleteUser = adminUsersActionsFeature.confirmDeleteUser.bind(adminUsersActionsFeature);
// Создание подписки
var createSubscription = adminSubscriptionCreateFeature.createSubscription.bind(adminSubscriptionCreateFeature);

// Подтверждение удаления подписки
var confirmDeleteSubscription = adminSubscriptionEditFeature.confirmDeleteSubscription.bind(adminSubscriptionEditFeature);

// Удаление подписки
var deleteSubscription = adminSubscriptionEditFeature.deleteSubscription.bind(adminSubscriptionEditFeature);
// Вспомогательная функция для отображения ошибок
function showError(elementId, message) {
    const errorEl = document.getElementById(elementId);
    if (errorEl) {
        errorEl.style.display = 'block';
        errorEl.innerHTML = `<p>${escapeHtml(message)}</p>`;
    }
}

// Главный экран админ-панели (две карточки «Аналитика» и «Управление») — данных не грузим
var loadAdminStats = adminStatsDashboardFeature.loadAdminStats.bind(adminStatsDashboardFeature);var formatRub = adminStatsDashboardFeature.formatRub.bind(adminStatsDashboardFeature);var renderRevenueChart = adminStatsDashboardFeature.renderRevenueChart.bind(adminStatsDashboardFeature);var renderGatewaySplit = adminStatsDashboardFeature.renderGatewaySplit.bind(adminStatsDashboardFeature);var loadDashboardServers = adminStatsDashboardFeature.loadDashboardServers.bind(adminStatsDashboardFeature);
// Предотвращаем закрытие приложения при скролле вверх
var preventCloseOnScroll = uiGuardsFeature.preventCloseOnScroll.bind(uiGuardsFeature);
// [Удалено: loadNotificationStats, loadNotificationDeliveryChart и др. графики уведомлений — оставлена только аналитика серверов]

// Убираем мигающую каретку при фокусе на нередактируемых элементах
// (listener инициализируется в platform/ui-guards.js).

// Загружаем цены с сервера и обновляем отображение (публичный API, без авторизации)
function applyLoadedPrices(prices) {
    var m = prices && prices.month != null ? prices.month : 150;
    var t = prices && prices['3month'] != null ? prices['3month'] : 350;
    document.querySelectorAll('.plan-price[data-period="month"]').forEach(function (el) { el.textContent = m + '₽'; });
    document.querySelectorAll('.plan-price[data-period="3month"]').forEach(function (el) { el.textContent = t + '₽'; });
    document.querySelectorAll('#page-choose-payment-method .choose-option-card[data-period="month"] .choose-option-price').forEach(function (el) { el.textContent = m + '₽'; });
    document.querySelectorAll('#page-choose-payment-method .choose-option-card[data-period="3month"] .choose-option-price').forEach(function (el) { el.textContent = t + '₽'; });
}

async function loadPrices() {
    document.querySelectorAll('.plan-price').forEach(function (el) { el.textContent = '— ₽'; });
    var fallback = { month: 150, '3month': 350 };
    try {
        var res = await fetch('/api/prices');
        if (res.ok) {
            var data = await res.json();
            applyLoadedPrices(data.prices || fallback);
            return;
        }
    } catch (e) {
        console.warn('Не удалось загрузить цены, используются значения по умолчанию', e);
    }
    applyLoadedPrices(fallback);
}

// Подгружаем скрипт Telegram с таймаутом. Вызывается только с хоста Mini App (app.daralla.ru).
function loadTelegramScript(timeoutMs) {
    return new Promise(function (resolve) {
        if (window.Telegram && window.Telegram.WebApp) {
            resolve();
            return;
        }
        var resolved = false;
        function done() {
            if (resolved) return;
            resolved = true;
            resolve();
        }
        var script = document.createElement('script');
        script.src = 'https://telegram.org/js/telegram-web-app.js';
        script.async = true;
        script.onload = done;
        script.onerror = done;
        document.head.appendChild(script);
        setTimeout(done, timeoutMs);
    });
}

// Ждём появления Telegram Web App API (после loadTelegramScript) или таймаут
function waitForTelegram(maxMs) {
    return loadTelegramScript(maxMs);
}

// Загружаем подписки при загрузке страницы
document.addEventListener('DOMContentLoaded', async () => {
    applyTheme();
    var landingEl = document.getElementById('page-landing');
    if (landingEl) landingEl.style.display = '';
    await platform.init();
    tg = platform.getTgRef();
    isWebMode = !platform.isTelegram();

    // app.daralla.ru только для Mini App (Telegram). В браузере без Telegram — редирект на daralla.ru.
    if (isMiniAppHost() && !platform.isTelegram()) {
        var mainHost = location.hostname.replace(/^app\./, '');
        if (mainHost !== location.hostname) {
            var target = location.protocol + '//' + mainHost + (location.pathname || '') + (location.search || '') + (location.hash || '');
            location.replace(target);
            return;
        }
    }

    if (!platform.isTelegram()) {
        webAuthToken = await window.DarallaAuthSession.hydrateTokenFromIndexedDb(webAuthToken);
    }

    loadPrices();
    preventCloseOnScroll();
    if ('serviceWorker' in navigator) {
        navigator.serviceWorker.register('/sw.js', { scope: '/' }).then(function () {}, function (err) { console.warn('SW register failed', err); });
    }
    if (!platform.isTelegram()) {
        document.body.classList.add('web-mode');
        try {
            var response = await fetch('/api/auth/verify', {
                method: 'POST',
                credentials: 'include',
                headers: { 'Content-Type': 'application/json' },
                body: webAuthToken ? JSON.stringify({ token: webAuthToken }) : '{}'
            });
            var result = await response.json();
            if (result.success) {
                currentUserId = result.user_id;
                await checkAdminAccess();
                var route = parseHashRoute();
                if (route && isPageAllowedForUser(route.pageName, true, isAdmin)) {
                    applyRoute(route, true, isAdmin);
                } else {
                    showPage(platform.getDefaultPage(true));
                }
            } else {
                var routeGuest = parseHashRoute();
                if (routeGuest && isPageAllowedForUser(routeGuest.pageName, false, false)) {
                    applyRoute(routeGuest, false, false);
                } else {
                    showPage(platform.getDefaultPage(false));
                }
            }
        } catch (e) {
            var routeGuest2 = parseHashRoute();
            if (routeGuest2 && isPageAllowedForUser(routeGuest2.pageName, false, false)) {
                applyRoute(routeGuest2, false, false);
            } else {
                showPage(platform.getDefaultPage(false));
            }
        }
    } else {
        await initTelegramFlow();
    }

    handlePaymentReturnFromQuery();

    initNavIndicator();
    initThemeToggle();
    if (window.DarallaDomBindings && typeof window.DarallaDomBindings.init === 'function') {
        window.DarallaDomBindings.init({
            showPage: showPage,
            logout: logout,
            handleWebLogin: handleWebLogin,
            handleWebRegister: handleWebRegister,
            handleWebAccessSetup: handleWebAccessSetup,
            handleLinkTelegram: handleLinkTelegram,
            handleChangeLogin: handleChangeLogin,
            handleChangePassword: handleChangePassword,
            handleUnlinkTelegram: handleUnlinkTelegram,
            saveNotificationRule: saveNotificationRule,
            onNotifRuleEventTypeChange: onNotifRuleEventTypeChange,
            updateNotifPreview: updateNotifPreview,
            toggleRepeatFields: toggleRepeatFields,
            reloadAdminSubscriptionsWithFilters: reloadAdminSubscriptionsWithFilters,
            getCurrentSelectedGroupId: function () { return currentSelectedGroupId; },
            editServerGroup: editServerGroup,
            submitAdminEventForm: submitAdminEventForm,
            createSubscription: createSubscription,
            saveSubscriptionChanges: saveSubscriptionChanges,
            saveAdminCommerce: saveAdminCommerce,
            saveServerGroup: saveServerGroup,
            saveServerConfig: saveServerConfig
        });
    }
    window.addEventListener('hashchange', function () {
        var route = parseHashRoute();
        if (!route || route.pageName === currentPage) return;
        if (!applyRoute(route, !!currentUserId, isAdmin)) {
            showPage(platform.getDefaultPage(!!currentUserId));
        }
    });
});

async function initTelegramFlow() {
    var auth = platform.getAuth();
    try {
        if (auth.type === 'tg' && auth.initData) {
            var response = await fetch('/api/user/register', {
                method: 'POST',
                headers: {
                    'Content-Type': 'application/json'
                },
                body: JSON.stringify({
                    initData: auth.initData
                })
            });
            
            if (response.ok) {
                const data = await response.json();
                if (data.trial_created) {
                    console.log('Пробная подписка создана для нового пользователя');
                }
            } else if (response.status === 401) {
                console.warn('Unauthorized in initTelegramFlow');
            }
        }
    } catch (error) {
        console.error('Ошибка регистрации пользователя:', error);
    }
    
    // Проверяем deep link параметры
    const urlParams = new URLSearchParams(window.location.search);
    const startapp = urlParams.get('startapp');
    
    if (startapp) {
        if (startapp.startsWith('extend_subscription_')) {
            const subscriptionId = parseInt(startapp.replace('extend_subscription_', ''));
            if (subscriptionId && !isNaN(subscriptionId)) {
                await loadSubscriptions();
                setTimeout(() => {
                    showExtendSubscriptionModal(subscriptionId);
                }, 300);
                await checkAdminAccess();
                return;
            }
        } else if (startapp.startsWith('subscription_')) {
            const subscriptionId = parseInt(startapp.replace('subscription_', ''));
            if (subscriptionId && !isNaN(subscriptionId)) {
                await loadSubscriptions();
                setTimeout(() => {
                    const subscriptions = window.allSubscriptions || [];
                    const sub = subscriptions.find(s => s.id === subscriptionId);
                    if (sub) {
                        showSubscriptionDetail(sub);
                    } else {
                        showPage('subscriptions');
                    }
                }, 300);
                await checkAdminAccess();
                return;
            }
        } else if (startapp === 'subscriptions') {
            showPage('subscriptions');
            await loadSubscriptions();
            await checkAdminAccess();
            return;
        }
    }

    await loadSubscriptions();
    await checkAdminAccess();
    var route = parseHashRoute();
    if (route && isPageAllowedForUser(route.pageName, true, isAdmin)) {
        applyRoute(route, true, isAdmin);
    } else {
        showPage('subscriptions');
    }
}

// Обработчики веб-авторизации
var handleWebLogin = authFormsFeature.handleWebLogin.bind(authFormsFeature);

var handleWebRegister = authFormsFeature.handleWebRegister.bind(authFormsFeature);

// === НАСТРОЙКА ВЕБ-ДОСТУПА (ИЗ ТГ) ===

var showWebAccessModal = authAccountFeature.showWebAccessModal.bind(authAccountFeature);

var handleWebAccessSetup = authAccountFeature.handleWebAccessSetup.bind(authAccountFeature);
var refreshAboutAccount = authAccountFeature.refreshAboutAccount.bind(authAccountFeature);
var handleLinkTelegram = authAccountFeature.handleLinkTelegram.bind(authAccountFeature);

var handleChangeLogin = authAccountFeature.handleChangeLogin.bind(authAccountFeature);

var handleChangePassword = authAccountFeature.handleChangePassword.bind(authAccountFeature);

var handleUnlinkTelegram = authAccountFeature.handleUnlinkTelegram.bind(authAccountFeature);

// Загрузка статистики подписок

// Страница рассылки (админ)
var broadcastActions = appActions.bindFeature(adminBroadcastFeature, [
    'loadBroadcastPage',
    'setBroadcastMode',
    'renderBroadcastUserResults',
    'searchUsersForBroadcast',
    'toggleUserForBroadcast',
    'clearUserSelection',
    'updateSelectedCount',
    'updateBroadcastRecipientsCount',
    'updateSendButtonState',
    'updateSelectedChips',
    'removeUserFromSelection',
    'selectAllBroadcastResults',
    'highlightMatchRaw',
    'sendBroadcast'
]);
var loadBroadcastPage = broadcastActions.loadBroadcastPage;
var setBroadcastMode = broadcastActions.setBroadcastMode;
var renderBroadcastUserResults = broadcastActions.renderBroadcastUserResults;
var searchUsersForBroadcast = broadcastActions.searchUsersForBroadcast;
var toggleUserForBroadcast = broadcastActions.toggleUserForBroadcast;
var clearUserSelection = broadcastActions.clearUserSelection;
var updateSelectedCount = broadcastActions.updateSelectedCount;
var updateBroadcastRecipientsCount = broadcastActions.updateBroadcastRecipientsCount;
var updateSendButtonState = broadcastActions.updateSendButtonState;
var updateSelectedChips = broadcastActions.updateSelectedChips;
var removeUserFromSelection = broadcastActions.removeUserFromSelection;
var selectAllBroadcastResults = broadcastActions.selectAllBroadcastResults;
var highlightMatchRaw = broadcastActions.highlightMatchRaw;
var sendBroadcast = broadcastActions.sendBroadcast;

// Блок инструкций вынесен в features/instructions/setup.js

// --- Нижняя навигация: индикатор с CSS-переходами и перетаскиванием (одинаково на всех ширинах) ---
var moveNavIndicator = navIndicatorFeature.moveNavIndicator.bind(navIndicatorFeature);
var initNavIndicator = navIndicatorFeature.initNavIndicator.bind(navIndicatorFeature);
// === ЦЕНЫ И ЛИМИТ УСТРОЙСТВ (АДМИН) ===

var adminCommerceActions = appActions.bindFeature(adminCommerceFeature, [
    'loadAdminCommercePage',
    'saveAdminCommerce'
]);
var loadAdminCommercePage = adminCommerceActions.loadAdminCommercePage;
var saveAdminCommerce = adminCommerceActions.saveAdminCommerce;

// === УПРАВЛЕНИЕ СЕРВЕРАМИ И ГРУППАМИ (АДМИН) ===

var adminServerActions = appActions.bindFeature(adminServersFeature, [
    'loadServerManagement',
    'loadServerGroups',
    'renderServerGroups',
    'showAddServerGroupModal',
    'editServerGroup',
    'saveServerGroup',
    'loadAdminServerGroupPage',
    'toggleAdminServerReorderMode',
    'toggleServerActive',
    'sortAdminServersByClientOrder',
    'refreshAdminServersInGroup',
    'nudgeServerOrder',
    'renderServersInGroup',
    'setServerClientFlowFormState',
    'getServerClientFlowPayload',
    'showAddServerConfigModal',
    'editServerConfig',
    'saveServerConfig',
    'deleteServerConfig',
    'syncAllServers',
    'runSyncAllServers'
]);
var loadServerManagement = adminServerActions.loadServerManagement;
var loadServerGroups = adminServerActions.loadServerGroups;
var renderServerGroups = adminServerActions.renderServerGroups;
var showAddServerGroupModal = adminServerActions.showAddServerGroupModal;
var editServerGroup = adminServerActions.editServerGroup;
var saveServerGroup = adminServerActions.saveServerGroup;
var loadAdminServerGroupPage = adminServerActions.loadAdminServerGroupPage;
var toggleAdminServerReorderMode = adminServerActions.toggleAdminServerReorderMode;
var toggleServerActive = adminServerActions.toggleServerActive;
var sortAdminServersByClientOrder = adminServerActions.sortAdminServersByClientOrder;
var refreshAdminServersInGroup = adminServerActions.refreshAdminServersInGroup;
var nudgeServerOrder = adminServerActions.nudgeServerOrder;
var renderServersInGroup = adminServerActions.renderServersInGroup;
var setServerClientFlowFormState = adminServerActions.setServerClientFlowFormState;
var getServerClientFlowPayload = adminServerActions.getServerClientFlowPayload;
var showAddServerConfigModal = adminServerActions.showAddServerConfigModal;
var editServerConfig = adminServerActions.editServerConfig;
var saveServerConfig = adminServerActions.saveServerConfig;
var deleteServerConfig = adminServerActions.deleteServerConfig;
var syncAllServers = adminServerActions.syncAllServers;
var runSyncAllServers = adminServerActions.runSyncAllServers;

// Public UI API: whitelisted globals used by inline handlers in index.html
var PUBLIC_UI_API_NAMES = [
    'clearUserSelection',
    'closeAdminEventForm',
    'closeInstructionModal',
    'closeModal',
    'closeNotificationRuleForm',
    'closeSubscriptionConfirmModal',
    'confirmDeleteSubscription',
    'confirmSaveSubscriptionChanges',
    'createSubscription',
    'editServerGroup',
    'goBackFromChoosePayment',
    'goBackFromCreateSubscription',
    'goBackFromPayment',
    'goBackFromSubscriptionEdit',
    'goBackFromUserDetail',
    'goToChoosePaymentMethod',
    'handleChangeLogin',
    'handleChangePassword',
    'handleLinkTelegram',
    'handleUnlinkTelegram',
    'handleWebAccessSetup',
    'handleWebLogin',
    'handleWebRegister',
    'loadAdminSubscriptions',
    'loadAdminUsers',
    'loadBroadcastPage',
    'loadServers',
    'loadSubscriptions',
    'logout',
    'nextInstructionStep',
    'onNotifRuleEventTypeChange',
    'prevInstructionStep',
    'reloadAdminSubscriptionsWithFilters',
    'saveAdminCommerce',
    'saveNotificationRule',
    'saveServerConfig',
    'saveServerGroup',
    'saveSubscriptionChanges',
    'selectAllBroadcastResults',
    'sendBroadcast',
    'showAddServerConfigModal',
    'showAddServerGroupModal',
    'showAdminEventForm',
    'showInstructionModal',
    'showModal',
    'showNotificationRuleForm',
    'showPage',
    'showWebAccessModal',
    'submitAdminEventForm',
    'switchSubscriptionTab',
    'syncAllServers',
    'testSendNotificationRule',
    'toggleAdminServerReorderMode',
    'toggleRepeatFields',
    'updateNotifPreview'
];

PUBLIC_UI_API_NAMES.forEach(function (name) {
    if (typeof globalThis[name] === 'function') {
        window[name] = globalThis[name];
    }
});
