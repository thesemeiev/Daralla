// Telegram Web App API
const tg = window.Telegram.WebApp;

// Глобальные переменные для веб-авторизации
let webAuthToken = null;
try {
    webAuthToken = localStorage.getItem('web_token');
} catch (e) {
    console.warn('LocalStorage access blocked by browser');
}
let currentUserId = null;
let isWebMode = !tg.initData;

// Функция для выполнения защищенных запросов к API
async function apiFetch(url, options = {}) {
    if (!options.headers) options.headers = {};
    
    // Добавляем авторизацию
    if (tg.initData) {
        // Режим Telegram
        const separator = url.includes('?') ? '&' : '?';
        url = `${url}${separator}initData=${encodeURIComponent(tg.initData)}`;
    } else if (webAuthToken) {
        // Режим Веб
        options.headers['Authorization'] = `Bearer ${webAuthToken}`;
    }
    
    // Если это POST/PUT запрос и нет тела, добавляем пустой объект
    // Это предотвращает ошибки 400 на сервере при ожидании JSON
    if ((options.method === 'POST' || options.method === 'PUT') && !options.body) {
        options.body = JSON.stringify({});
        if (!options.headers['Content-Type']) {
            options.headers['Content-Type'] = 'application/json';
        }
    }
    
    console.log(`[API] Запрос: ${options.method || 'GET'} ${url}`, { mode: isWebMode ? 'Web' : 'Telegram', hasToken: !!webAuthToken });
    
    try {
        const response = await fetch(url, options);
        if (response.status === 401 && isWebMode) {
            console.warn('[API] Ошибка 401: Токен недействителен или истек');
            logout();
        }
        return response;
    } catch (e) {
        console.error(`[API] Ошибка сетевого запроса (${url}):`, e);
        throw e;
    }
}

function logout() {
    try {
        localStorage.removeItem('web_token');
    } catch (e) {}
    webAuthToken = null;
    currentUserId = null;
    showPage('login');
}

// Инициализация Telegram Web App
if (tg.initData) {
    tg.ready();
    tg.expand();
}

// Отключаем вертикальные свайпы для закрытия приложения (предотвращает закрытие при скролле вверх)
if (tg.disableVerticalSwipes) {
    tg.disableVerticalSwipes();
}

// Устанавливаем цветовую схему
tg.setHeaderColor('#1a1a1a');
tg.setBackgroundColor('#1a1a1a');

// Текущая страница
let currentPage = 'subscriptions';

// Интервалы для автоматического обновления
let serverLoadChartInterval = null;

// Функция переключения страниц
function showPage(pageName) {
    // Очищаем интервалы при уходе со страницы серверов
    if (currentPage === 'servers' && pageName !== 'servers' && serverLoadChartInterval) {
        clearInterval(serverLoadChartInterval);
        serverLoadChartInterval = null;
    }

    // Сбрасываем скролл наверх при переключении страниц
    window.scrollTo(0, 0);
    document.documentElement.scrollTop = 0;
    document.body.scrollTop = 0;
    var landingScroll = document.getElementById('landing-scroll');
    if (landingScroll) landingScroll.scrollTop = 0;
    
    // Показываем нижний навбар только на главных разделах
    const bottomNav = document.querySelector('.bottom-nav');
    const isMainSectionPage = (
        pageName === 'subscriptions' ||
        pageName === 'instructions' ||
        pageName === 'about' ||
        pageName === 'servers' ||
        pageName === 'admin-stats'
    );
    if (bottomNav) {
        bottomNav.style.display = isMainSectionPage ? 'flex' : 'none';
    }

    // Скрываем все страницы
    document.querySelectorAll('.page').forEach(page => {
        page.style.display = 'none';
    });

    /* Блокируем скролл окна на лендинге, чтобы колесо мыши скроллило только #landing-scroll */
    if (currentPage === 'landing' && pageName !== 'landing') {
        document.documentElement.style.overflow = '';
        document.body.style.overflow = '';
    }
    if (pageName === 'landing') {
        document.documentElement.style.overflow = 'hidden';
        document.body.style.overflow = 'hidden';
    }
    
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
        // Убеждаемся, что кнопка админа видна, если есть права
        if (isAdmin && !document.getElementById('admin-nav-button')) {
            addAdminNavButton();
        }
        
        const navItems = document.querySelectorAll('.nav-item');
        let activeIndex = -1;
        
        if (pageName === 'subscriptions') {
            navItems[0]?.classList.add('active');
            activeIndex = 0;
        } else if (pageName === 'servers') {
            navItems[1]?.classList.add('active');
            activeIndex = 1;
        } else if (pageName === 'instructions') {
            navItems[2]?.classList.add('active');
            activeIndex = 2;
        } else if (pageName === 'about') {
            navItems[3]?.classList.add('active');
            activeIndex = 3;
        } else if ((pageName === 'admin-stats' || pageName.startsWith('admin-')) && document.getElementById('admin-nav-button')) {
            const adminButton = document.getElementById('admin-nav-button');
            adminButton.classList.add('active');
            const allNavItems = Array.from(document.querySelectorAll('.nav-item'));
            activeIndex = allNavItems.indexOf(adminButton);
        }
        
        // Перемещаем индикатор к активной кнопке
        if (activeIndex >= 0) {
            moveNavIndicator(activeIndex);
        }
    }
    
    currentPage = pageName;
    
    // Анимация появления формы при открытии входа/регистрации
    if (pageName === 'login' || pageName === 'register') {
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
    } else if (pageName === 'servers') {
        loadServers();
    } else if (pageName === 'admin-users') {
        loadAdminUsers(1, currentAdminUserSearch);
    } else if (pageName === 'admin-stats') {
        loadAdminStats();
    } else if (pageName === 'admin-users-analytics') {
        loadUsersAnalyticsPage();
    } else if (pageName === 'admin-servers-analytics') {
        loadServersAnalyticsPage();
    } else if (pageName === 'admin-finance') {
        loadFinancePage();
    } else if (pageName === 'admin-notifications') {
        loadNotificationStats();
    } else if (pageName === 'admin-subscriptions') {
        loadSubscriptionStats();
    } else if (pageName === 'admin-broadcast') {
        loadBroadcastPage();
    } else if (pageName === 'admin-server-management') {
        loadServerManagement();
    } else if (pageName === 'landing') {
        var landingScroll = document.getElementById('landing-scroll');
        if (landingScroll) landingScroll.scrollTop = 0;
        initLandingObserver();
        initLandingWheelAndHint();
    } else if (pageName === 'about') {
        refreshAboutAccount();
    }
}

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
        /* Колесо мыши на ПК: document capture, иначе браузер скроллит окно и события не доходят до div */
        document.addEventListener('wheel', function (e) {
            if (currentPage !== 'landing') return;
            var pel = document.getElementById('page-landing');
            if (!pel || pel.style.display === 'none') return;
            var el = document.getElementById('landing-scroll');
            if (!el) return;
            e.preventDefault();
            e.stopPropagation();
            var dy = e.deltaY;
            if (e.deltaMode === 1) dy *= 40;
            else if (e.deltaMode === 2) dy *= 800;
            el.scrollTop += dy;
        }, { passive: false, capture: true });

        scrollEl.addEventListener('scroll', updateHintVisibility);
    }

    updateHintVisibility();
    if (currentPage === 'landing') scrollEl.focus({ preventScroll: true });
}

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

// Глобальная переменная для хранения текущей подписки
let currentSubscriptionDetail = null;

// Функция показа детальной информации о подписке
function showSubscriptionDetail(sub) {
    // Сбрасываем скролл наверх перед открытием деталей
    window.scrollTo(0, 0);
    document.documentElement.scrollTop = 0;
    document.body.scrollTop = 0;
    
    const pageEl = document.getElementById('page-subscription-detail');
    const nameEl = document.getElementById('detail-subscription-name');
    const contentEl = document.getElementById('subscription-detail-content');
    
    // Сохраняем подписку для использования в функциях переименования
    currentSubscriptionDetail = sub;
    
    // Проверяем существование элемента перед использованием
    if (nameEl) {
        nameEl.textContent = escapeHtml(sub.name);
    }
    
    const statusClass = sub.status === 'active' ? 'active' : 'expired';
    const statusText = sub.status === 'active' ? 'Активна' : 
                      sub.status === 'expired' ? 'Истекла' : 
                      sub.status === 'trial' ? 'Пробная' : sub.status;
    
    contentEl.innerHTML = `
        <div class="detail-card">
            <div class="detail-header">
                <div class="detail-status ${statusClass}">${statusText}</div>
            </div>
            
            <div class="detail-info-grid">
                <div class="detail-info-item">
                    <div class="detail-info-label">Название</div>
                    <div class="detail-info-value" id="subscription-name-display">${escapeHtml(sub.name)}</div>
                </div>
                
                <div class="detail-info-item">
                    <div class="detail-info-label">Устройств</div>
                    <div class="detail-info-value">${sub.device_limit}</div>
                </div>
                
                <div class="detail-info-item">
                    <div class="detail-info-label">Создана</div>
                    <div class="detail-info-value">${sub.created_at_formatted}</div>
                </div>
                
                <div class="detail-info-item">
                    <div class="detail-info-label">${sub.status === 'active' ? 'Истекает' : 'Истекла'}</div>
                    <div class="detail-info-value">${sub.expires_at_formatted}</div>
                </div>
                
                ${sub.status === 'active' && sub.expires_at ? `
                    <div class="detail-info-item full-width">
                        <div class="detail-info-label">Осталось</div>
                        <div class="detail-info-value days-highlight">${formatTimeRemaining(sub.expires_at)}</div>
                    </div>
                ` : ''}
            </div>
            
            <div class="detail-actions">
                <button class="action-button" onclick="showRenameSubscriptionModal()" style="margin-bottom: 12px;">
                    Переименовать подписку
                </button>
                ${sub.status === 'active' ? `
                    <button class="action-button" onclick="copySubscriptionLink('${sub.token}')" style="margin-bottom: 12px;">
                        Копировать ссылку подписки
                    </button>
                ` : ''}
                ${sub.status === 'active' || sub.status === 'expired' ? `
                    <button class="action-button" onclick="showExtendSubscriptionModal(${sub.id})" style="background: #4a9eff;">
                        Продлить подписку
                    </button>
                ` : ''}
            </div>
        </div>
    `;
    
    showPage('subscription-detail');
}

// Функция загрузки подписок
async function loadSubscriptions() {
    const loadingEl = document.getElementById('loading');
    const errorEl = document.getElementById('error');
    const emptyEl = document.getElementById('empty');
    const subscriptionsEl = document.getElementById('subscriptions');
    
    // Показываем загрузку
    if (loadingEl) loadingEl.style.display = 'block';
    if (errorEl) errorEl.style.display = 'none';
    if (emptyEl) emptyEl.style.display = 'none';
    if (subscriptionsEl) subscriptionsEl.style.display = 'none';
    
    try {
        // Запрашиваем подписки через защищенный API
        const response = await apiFetch(`/api/subscriptions`);
        
        if (!response.ok) {
            throw new Error(`HTTP error! status: ${response.status}`);
        }
        
        const data = await response.json();
        
        if (!data.success) {
            throw new Error(data.error || 'Ошибка получения данных');
        }
        
        // Скрываем загрузку
        if (loadingEl) loadingEl.style.display = 'none';
        
        // Обновляем статистику
        const totalEl = document.getElementById('total-count');
        const activeEl = document.getElementById('active-count');
        if (totalEl) totalEl.textContent = data.total || 0;
        if (activeEl) activeEl.textContent = data.active || 0;
        
        if (!data.subscriptions || data.subscriptions.length === 0) {
            // Нет подписок
            if (emptyEl) emptyEl.style.display = 'block';
        } else {
            // Показываем подписки
            if (subscriptionsEl) subscriptionsEl.style.display = 'block';
            window.allSubscriptions = data.subscriptions;
            renderSubscriptions(data.subscriptions);
        }
        
        // Добавляем кнопку "Купить подписку" в список подписок
        const subscriptionsListEl = document.getElementById('subscriptions-list');
        if (subscriptionsListEl && !document.getElementById('buy-subscription-button')) {
            const buyButton = document.createElement('button');
            buyButton.id = 'buy-subscription-button';
            buyButton.className = 'btn-primary';
            buyButton.style.cssText = 'width: 100%; margin-top: 16px;';
            buyButton.textContent = 'Купить подписку';
            buyButton.onclick = () => showPage('buy-subscription');
            subscriptionsListEl.appendChild(buyButton);
        }
        
    } catch (error) {
        console.error('Ошибка загрузки подписок:', error);
        if (loadingEl) loadingEl.style.display = 'none';
        if (errorEl) errorEl.style.display = 'block';
    }
}

// Функция отображения подписок
function renderSubscriptions(subscriptions) {
    const listEl = document.getElementById('subscriptions-list');
    listEl.innerHTML = '';
    
    subscriptions.forEach(sub => {
        const card = createSubscriptionCard(sub);
        listEl.appendChild(card);
    });
}

// Функция создания карточки подписки
function createSubscriptionCard(sub) {
    const card = document.createElement('div');
    card.className = `subscription-card ${sub.status}`;
    card.style.cursor = 'pointer';
    card.onclick = () => showSubscriptionDetail(sub);
    
    const statusClass = sub.status === 'active' ? 'active' : 'expired';
    const statusText = sub.status === 'active' ? 'Активна' : 
                      sub.status === 'expired' ? 'Истекла' : 
                      sub.status === 'trial' ? 'Пробная' : sub.status;
    
    card.innerHTML = `
        <div class="subscription-header">
            <div class="subscription-name">${escapeHtml(sub.name)}</div>
            <div class="subscription-status ${statusClass}">${statusText}</div>
        </div>
        
        <div class="subscription-info">
            <div class="info-item">
                <div class="info-label">Создана</div>
                <div class="info-value">${sub.created_at_formatted}</div>
            </div>
            <div class="info-item">
                <div class="info-label">${sub.status === 'active' ? 'Истекает' : 'Истекла'}</div>
                <div class="info-value">${sub.expires_at_formatted}</div>
            </div>
        </div>
        
        ${sub.status === 'active' && sub.expires_at ? `
            <div class="days-badge">
                <span class="info-label">Осталось</span>
                <span class="days-remaining">${formatTimeRemaining(sub.expires_at)}</span>
            </div>
        ` : ''}
    `;
    
    return card;
}

// Функция загрузки серверов
async function loadServers() {
    const loadingEl = document.getElementById('servers-loading');
    const errorEl = document.getElementById('servers-error');
    const contentEl = document.getElementById('servers-content');
    const listEl = document.getElementById('servers-list');
    
    if (loadingEl) loadingEl.style.display = 'block';
    if (errorEl) errorEl.style.display = 'none';
    if (contentEl) contentEl.style.display = 'none';
    
    try {
        const response = await apiFetch(`/api/servers`);
        
        if (!response.ok) {
            throw new Error(`HTTP error! status: ${response.status}`);
        }
        
        const data = await response.json();
        
        if (!data.success) {
            throw new Error(data.error || 'Ошибка получения данных');
        }
        
        if (loadingEl) loadingEl.style.display = 'none';
        if (contentEl) contentEl.style.display = 'block';
        
        // Загружаем карту серверов
        loadServerMap();
        
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

// Функция отображения серверов
// Переменная для хранения экземпляра глобуса
let serverGlobe = null;
let globeAnimationId = null;

// Кастомный 2D глобус на Canvas
class CustomGlobe {
    constructor(canvas, servers) {
        this.canvas = canvas;
        this.ctx = canvas.getContext('2d');
        this.servers = servers;
        this.rotation = 0; // Горизонтальное вращение (yaw)
        this.pitch = 0; // Вертикальное вращение (pitch) - наклон вверх/вниз
        this.isDragging = false;
        this.lastX = 0;
        this.lastY = 0;
        this.zoom = 1;
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
        this.rotation += deltaX * rotationSpeed;
        
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
        
        // Проверяем видимость (точка видна, если она на передней стороне сферы)
        // Учитываем увеличенный радиус при зуме для проверки границ
        const maxDistance = Math.max(this.baseWidth, this.baseHeight) * 0.6 * this.zoom;
        const visible = zRotated >= 0 && 
                       Math.abs(x - baseCenterX) < maxDistance && 
                       Math.abs(y - baseCenterY) < maxDistance;
        
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
        if (server.lat && server.lng) {
            // Warsaw: 52.2297, 21.0122
            if (Math.abs(server.lat - 52.2297) < 0.5 && Math.abs(server.lng - 21.0122) < 0.5) {
                return 'Warsaw';
            }
            // Dronten: 52.5167, 5.7167
            if (Math.abs(server.lat - 52.5167) < 0.5 && Math.abs(server.lng - 5.7167) < 0.5) {
                return 'Dronten';
            }
            // Moscow: 55.7558, 37.6173
            if (Math.abs(server.lat - 55.7558) < 0.5 && Math.abs(server.lng - 37.6173) < 0.5) {
                return 'Moscow';
            }
            // Riga: 56.9496, 24.1052
            if (Math.abs(server.lat - 56.9496) < 0.5 && Math.abs(server.lng - 24.1052) < 0.5) {
                return 'Riga';
            }
            // Frankfurt: 51.5074, 6.7760
            if (Math.abs(server.lat - 51.5074) < 0.5 && Math.abs(server.lng - 6.7760) < 0.5) {
                return 'Frankfurt';
            }
        }
        
        // Fallback на display_name или server_name
        return server.display_name || server.server_name || server.location || '';
    }
    
    // Рисует точки крупных городов (серые)
    drawMajorCities(ctx) {
        const cities = this.getMajorCities();
        const grayColor = '#888'; // Серый цвет
        const size = 4; // Размер точки меньше, чем у серверов
        
        cities.forEach(city => {
            const pos = this.latLngToXY(city.lat, city.lng);
            if (!pos.visible) return;
            
            // Все города — одинаковый стиль (серые точки)
            ctx.fillStyle = grayColor;
            ctx.fillRect(Math.floor(pos.x - size/2), Math.floor(pos.y - size/2), size, size);
            ctx.strokeStyle = '#666';
            ctx.lineWidth = 1;
            ctx.strokeRect(Math.floor(pos.x - size/2), Math.floor(pos.y - size/2), size, size);
            
            // Подпись города
            const label = city.name;
            const fontSize = 10;
            ctx.font = `${fontSize}px Arial, sans-serif`;
            ctx.textAlign = 'left';
            ctx.textBaseline = 'middle';
            
            const padding = 6;
            const labelX = Math.round(pos.x + size + padding);
            const labelY = Math.round(pos.y);
            
            ctx.imageSmoothingEnabled = false;
            
            ctx.fillStyle = '#fff';
            ctx.strokeStyle = 'rgba(0, 0, 0, 0.8)';
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
            { name: 'Helsinki', lat: 60.1699, lng: 24.9384 },
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
            { name: 'Frankfurt', lat: 50.1109, lng: 8.6821 },
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
            { name: 'Saint Petersburg', lat: 59.9343, lng: 30.3351 },
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
        // Получаем реальные размеры с учетом devicePixelRatio
        const dpr = window.devicePixelRatio || 1;
        const width = this.canvas.width / dpr;
        const height = this.canvas.height / dpr;
        
        // Очищаем canvas
        ctx.fillStyle = '#1a1a1a';
        ctx.fillRect(0, 0, width, height);
        
        // Рисуем круг глобуса (темный стиль)
        ctx.save();
        ctx.translate(this.centerX, this.centerY);
        // Убираем ctx.scale - применяем zoom только в latLngToXY для единообразия
        
        // Внешний круг (граница) - применяем zoom к радиусу
        const scaledRadius = this.radius * this.zoom;
        const gradient = ctx.createRadialGradient(0, 0, 0, 0, 0, scaledRadius);
        gradient.addColorStop(0, '#2a2a2a');
        gradient.addColorStop(0.7, '#1a1a1a');
        gradient.addColorStop(1, '#0a0a0a');
        
        ctx.beginPath();
        ctx.arc(0, 0, scaledRadius, 0, Math.PI * 2);
        ctx.fillStyle = gradient;
        ctx.fill();
        ctx.strokeStyle = '#333';
        ctx.lineWidth = 2 / this.zoom; // Компенсируем толщину линии при зуме
        ctx.stroke();
        
        // Рисуем сетку (меридианы и параллели) в пиксельном стиле с учетом наклона
        ctx.strokeStyle = '#333';
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
            if (!server.lat || !server.lng) return;
            
            const pos = this.latLngToXY(server.lat, server.lng);
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
            
            // Обводка
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
            
            // Подпись сервера: приоритет — map_label из настроек, иначе display_name или location
            const label = (server.map_label || server.display_name || server.location || server.name || '').trim();
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
                ctx.fillStyle = '#fff';
                ctx.strokeStyle = 'rgba(0, 0, 0, 0.5)';
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
        if (!this.isDragging) {
            this.rotation += 0.005; // Медленное автоматическое вращение
        }
        this.draw();
        this.animationId = requestAnimationFrame(() => this.animate());
    }
    
    destroy() {
        if (this.animationId) {
            cancelAnimationFrame(this.animationId);
        }
    }
}

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
        
        // Масштабируем контекст для четкого рендеринга
        const ctx = canvas.getContext('2d');
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
            const ctx = canvas.getContext('2d');
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

function renderServers(servers) {
    const listEl = document.getElementById('servers-list');
    listEl.innerHTML = '';
    
    servers.forEach(server => {
        const card = document.createElement('div');
        card.className = `server-card ${server.status === 'online' ? 'online' : 'offline'}`;
        
        const statusText = server.status === 'online' ? 'Онлайн' : 'Офлайн';
        const statusIcon = server.status === 'online' ? '🟢' : '🔴';
        
        card.innerHTML = `
            <div class="server-header">
                <div class="server-name">${escapeHtml(server.name)}</div>
                <div class="server-status ${server.status}">
                    <span class="status-icon">${statusIcon}</span>
                    <span>${statusText}</span>
                </div>
            </div>
            ${server.last_check ? `
                <div class="server-info">
                    <div class="info-label">Последняя проверка</div>
                    <div class="info-value">${escapeHtml(server.last_check)}</div>
                </div>
            ` : ''}
        `;
        
        listEl.appendChild(card);
    });
}

// Функция копирования ссылки подписки
// Функция показа модального окна переименования подписки
function showRenameSubscriptionModal() {
    if (!currentSubscriptionDetail) {
        alert('Ошибка: информация о подписке не найдена');
        return;
    }
    
    const currentName = currentSubscriptionDetail.name;
    const newName = prompt('Введите новое название подписки:', currentName);
    
    if (newName === null) {
        // Пользователь отменил
        return;
    }
    
    const trimmedName = newName.trim();
    if (!trimmedName) {
        alert('Название не может быть пустым');
        return;
    }
    
    if (trimmedName === currentName) {
        // Имя не изменилось
        return;
    }
    
    // Вызываем функцию переименования
    renameSubscription(currentSubscriptionDetail.id, trimmedName);
}

// Глобальная переменная для хранения ID подписки при продлении
let currentExtendSubscriptionId = null;
let currentPaymentData = null;

// Функция показа страницы продления подписки
function showExtendSubscriptionModal(subscriptionId) {
    if (!subscriptionId) {
        alert('Ошибка: ID подписки не найден');
        return;
    }
    
    currentExtendSubscriptionId = subscriptionId;
    showPage('extend-subscription');
}

// Функция возврата с страницы продления
function goBackFromExtend() {
    currentExtendSubscriptionId = null;
    showPage('subscription-detail');
}

// Функция возврата с страницы оплаты
function goBackFromPayment() {
    currentPaymentData = null;
    if (currentExtendSubscriptionId) {
        showPage('extend-subscription');
    } else {
        showPage('buy-subscription');
    }
}

// Функция открытия ссылки на оплату
function openPaymentLink() {
    if (!currentPaymentData || !currentPaymentData.payment_url) {
        alert('Ошибка: ссылка на оплату не найдена');
        return;
    }
    
    // Открываем ссылку на оплату через Telegram Mini App API
    if (tg && tg.openLink) {
        tg.openLink(currentPaymentData.payment_url);
    } else {
        // Fallback для обычных браузеров
        window.open(currentPaymentData.payment_url, '_blank');
    }
    
    // Начинаем проверку статуса платежа
    checkPaymentStatus(currentPaymentData.payment_id, currentExtendSubscriptionId);
}

// Функция создания платежа
async function createPayment(period, subscriptionId = null) {
    try {
        // Показываем страницу оплаты с индикатором загрузки
        currentPaymentData = null; // Сбрасываем, чтобы показать загрузку
        showPaymentPage();
        
        const response = await apiFetch('/api/user/payment/create', {
            method: 'POST',
            headers: {
                'Content-Type': 'application/json'
            },
            body: JSON.stringify({
                period,
                subscription_id: subscriptionId
            })
        });
        
        if (!response.ok) {
            const error = await response.json();
            throw new Error(error.error || 'Ошибка создания платежа');
        }
        
        const data = await response.json();
        
        if (!data.success || !data.payment_url) {
            throw new Error('Не удалось получить ссылку на оплату');
        }
        
        // Сохраняем данные платежа
        currentPaymentData = {
            payment_id: data.payment_id,
            payment_url: data.payment_url,
            amount: data.amount,
            period: data.period
        };
        
        // Обновляем страницу оплаты с данными (кнопка восстановится автоматически)
        showPaymentPage();
        
    } catch (error) {
        console.error('Ошибка создания платежа:', error);
        
        // Восстанавливаем кнопку при ошибке
        const paymentButton = document.getElementById('payment-link-button');
        if (paymentButton) {
            paymentButton.disabled = false;
            paymentButton.textContent = 'Перейти к оплате';
        }
        
        alert('Ошибка создания платежа: ' + error.message);
        
        // Возвращаемся назад при ошибке
        goBackFromPayment();
    }
}

// Функция показа страницы оплаты
function showPaymentPage() {
    // Показываем страницу
    showPage('payment');
    
    if (!currentPaymentData) {
        // Если данных еще нет, показываем индикатор загрузки
        document.getElementById('payment-period').textContent = 'Загрузка...';
        document.getElementById('payment-amount').textContent = 'Загрузка...';
        const paymentButton = document.getElementById('payment-link-button');
        if (paymentButton) {
            paymentButton.disabled = true;
            paymentButton.textContent = 'Создание платежа...';
        }
        return;
    }
    
    // Обновляем информацию на странице оплаты
    const periodText = currentPaymentData.period === 'month' ? '1 месяц' : '3 месяца';
    document.getElementById('payment-period').textContent = periodText;
    document.getElementById('payment-amount').textContent = currentPaymentData.amount + '₽';
    
    // Восстанавливаем кнопку
    const paymentButton = document.getElementById('payment-link-button');
    if (paymentButton) {
        paymentButton.disabled = false;
        paymentButton.textContent = 'Перейти к оплате';
    }
}

// Функция проверки статуса платежа
// Примечание: основная обработка платежа идет через вебхук от YooKassa (/webhook/yookassa)
// Polling здесь нужен только для UX - чтобы пользователь видел обновление в мини-приложении
// Вебхук обрабатывает платеж на сервере и обновляет БД, polling просто проверяет статус в БД
let paymentCheckInterval = null;

async function checkPaymentStatus(paymentId, subscriptionId = null) {
    // Останавливаем предыдущую проверку, если она есть
    if (paymentCheckInterval) {
        clearInterval(paymentCheckInterval);
    }
    
    let checkCount = 0;
    const maxChecks = 180; // Проверяем в течение 15 минут (каждые 5 секунд) - столько же, сколько YooKassa хранит pending платеж
    
    paymentCheckInterval = setInterval(async () => {
        try {
            checkCount++;
            
            if (checkCount > maxChecks) {
                clearInterval(paymentCheckInterval);
                paymentCheckInterval = null;
                
            // Конечная проверка статуса
            const finalResponse = await apiFetch(`/api/user/payment/status/${paymentId}`);
            if (finalResponse.ok) {
                const finalData = await finalResponse.json();
                if (finalData.success && finalData.status === 'pending') {
                    // Платеж все еще pending - возможно, пользователь не оплатил
                    if (tg && tg.showAlert) {
                        tg.showAlert('Платеж не был оплачен. Ссылка истекла. Вы можете создать новый платеж.');
                    } else {
                        alert('Платеж не был оплачен. Ссылка истекла. Вы можете создать новый платеж.');
                    }
                    goBackFromPayment();
                }
            }
            return;
        }
        
        const response = await apiFetch(`/api/user/payment/status/${paymentId}`);
        
        if (!response.ok) {
            return; // Продолжаем проверку
        }
        
        const data = await response.json();

            // Проверяем, что платеж успешен И обработан вебхуком (activated = true)
            // Вебхук обрабатывает платеж и устанавливает activated = true
            if (data.success && data.status === 'succeeded' && data.activated) {
                // Платеж успешно обработан вебхуком
                clearInterval(paymentCheckInterval);
                paymentCheckInterval = null;
                
                // Показываем уведомление только если мы еще на странице оплаты
                // Это предотвращает дублирование уведомлений
                const currentPage = document.querySelector('.page.active');
                const isOnPaymentPage = currentPage && currentPage.id === 'page-payment';
                
                if (isOnPaymentPage) {
                    if (tg && tg.showAlert) {
                        tg.showAlert('Подписка успешно активирована!');
                    } else {
                        alert('Подписка успешно активирована!');
                    }
                }
                
                // Обновляем список подписок
                showPage('subscriptions');
                setTimeout(() => {
                    loadSubscriptions();
                }, 1000);
            } else if (data.success && (data.status === 'canceled' || data.status === 'refunded' || data.status === 'failed')) {
                // Платеж отменен, возвращен или не прошел
                clearInterval(paymentCheckInterval);
                paymentCheckInterval = null;
                
                // Показываем уведомление об отмене
                const statusText = data.status === 'canceled' ? 'отменен' : 
                                 data.status === 'refunded' ? 'возвращен' : 'не прошел';
                
                if (tg && tg.showAlert) {
                    tg.showAlert(`Платеж ${statusText}. Вы можете попробовать оплатить снова.`);
                } else {
                    alert(`Платеж ${statusText}. Вы можете попробовать оплатить снова.`);
                }
                
                // Возвращаемся на предыдущую страницу
                goBackFromPayment();
            }
            
        } catch (error) {
            console.error('Ошибка проверки статуса платежа:', error);
            // Продолжаем проверку
        }
    }, 5000); // Проверяем каждые 5 секунд (вебхук обычно приходит быстрее)
}

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
        if (tg && tg.showAlert) {
            tg.showAlert('Подписка успешно переименована');
        } else {
            alert('Подписка успешно переименована');
        }
        
        // Обновляем список подписок, если он открыт
        if (document.getElementById('page-subscriptions').classList.contains('active')) {
            loadSubscriptions();
        }
        
    } catch (error) {
        console.error('Ошибка переименования подписки:', error);
        alert('Ошибка переименования: ' + error.message);
    }
}

function copySubscriptionLink(token) {
    const webhookUrl = window.location.origin;
    const subscriptionUrl = `${webhookUrl}/sub/${token}`;
    
    // Копируем в буфер обмена
    if (navigator.clipboard && navigator.clipboard.writeText) {
        navigator.clipboard.writeText(subscriptionUrl).then(() => {
            tg.showAlert('Ссылка скопирована в буфер обмена!');
        }).catch(err => {
            console.error('Ошибка копирования:', err);
            tg.showAlert('Ошибка копирования ссылки');
        });
    } else {
        // Fallback для старых браузеров
        const textarea = document.createElement('textarea');
        textarea.value = subscriptionUrl;
        textarea.style.position = 'fixed';
        textarea.style.opacity = '0';
        document.body.appendChild(textarea);
        textarea.select();
        try {
            document.execCommand('copy');
            tg.showAlert('Ссылка скопирована в буфер обмена!');
        } catch (err) {
            tg.showAlert('Ошибка копирования ссылки');
        }
        document.body.removeChild(textarea);
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

let isAdmin = false;
let currentAdminUserPage = 1;
let currentAdminUserSearch = '';
let currentEditingSubscriptionId = null;
let previousAdminPage = 'admin-users';

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
            
            // Добавляем кнопку "Админ-панель" в навигацию, если админ
            if (isAdmin) {
                console.log('Добавляем кнопку админ-панели');
                addAdminNavButton();
            }
            
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

// Добавление кнопки "Админ-панель" в навигацию
function addAdminNavButton() {
    if (!isAdmin) return; // Не добавляем, если не админ
    
    const nav = document.querySelector('.bottom-nav');
    if (!nav) {
        console.warn('Навигация не найдена, пробуем позже...');
        // Пробуем еще раз через небольшую задержку
        setTimeout(() => {
            addAdminNavButton();
        }, 500);
        return;
    }
    
    // Проверяем, не добавлена ли уже кнопка
    if (document.getElementById('admin-nav-button')) {
        console.log('Кнопка админ-панели уже добавлена');
        return;
    }
    
    console.log('Добавляем кнопку админ-панели в навигацию');
    
    const adminButton = document.createElement('button');
    adminButton.id = 'admin-nav-button';
    adminButton.className = 'nav-item';
    adminButton.setAttribute('data-page', 'admin-stats');
    adminButton.onclick = () => {
        console.log('Переход в админ-панель');
        showPage('admin-stats');
    };
    adminButton.innerHTML = `
        <svg width="24" height="24" viewBox="0 0 24 24" fill="none" xmlns="http://www.w3.org/2000/svg">
            <path d="M12 2L4 5V11C4 16.55 7.16 21.74 12 23C16.84 21.74 20 16.55 20 11V5L12 2Z" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"/>
            <path d="M12 8V12M12 16H12.01" stroke="currentColor" stroke-width="2" stroke-linecap="round"/>
        </svg>
    `;
    
    nav.appendChild(adminButton);
    console.log('Кнопка админ-панели успешно добавлена');
    
    // Если мы уже на странице админа, нужно обновить индикатор
    if (currentPage === 'admin-stats') {
        const allNavItems = document.querySelectorAll('.nav-item');
        const index = Array.from(allNavItems).indexOf(adminButton);
        if (index >= 0) {
            moveNavIndicator(index);
        }
    }
}

// Загрузка списка пользователей
async function loadAdminUsers(page = 1, search = '') {
    try {
        const response = await apiFetch('/api/admin/users', {
            method: 'POST',
            headers: {
                'Content-Type': 'application/json'
            },
            body: JSON.stringify({
                page,
                limit: 20,
                search
            })
        });
        
        if (!response.ok) {
            throw new Error('Ошибка загрузки пользователей');
        }
        
        const data = await response.json();
        
        document.getElementById('admin-users-loading').style.display = 'none';
        document.getElementById('admin-users-content').style.display = 'block';
        
        // Обновляем статистику
        document.getElementById('admin-total-users').textContent = data.total || 0;
        
        // Отображаем список пользователей
        const listEl = document.getElementById('admin-users-list');
        listEl.innerHTML = '';
        
        if (data.users && data.users.length > 0) {
            data.users.forEach(user => {
                const card = document.createElement('div');
                card.className = 'admin-user-card';
                card.onclick = () => showAdminUserDetail(user.user_id);
                
                const firstSeen = new Date(user.first_seen * 1000).toLocaleDateString('ru-RU');
                const lastSeen = new Date(user.last_seen * 1000).toLocaleDateString('ru-RU');
                
                card.innerHTML = `
                    <div class="admin-user-id">ID: ${escapeHtml(user.user_id)}</div>
                    <div class="admin-user-meta">
                        <span>Создан: ${firstSeen}</span>
                        <span>Активен: ${lastSeen}</span>
                    </div>
                    <div class="admin-user-subscriptions">Подписок: ${user.subscriptions_count || 0}</div>
                `;
                
                listEl.appendChild(card);
            });
            
            // Отображаем пагинацию
            if (data.pages > 1) {
                showAdminPagination(data.page, data.pages);
            } else {
                document.getElementById('admin-users-pagination').style.display = 'none';
            }
        } else {
            listEl.innerHTML = '<div class="empty"><p>Пользователи не найдены</p></div>';
            document.getElementById('admin-users-pagination').style.display = 'none';
        }
        
        currentAdminUserPage = page;
        currentAdminUserSearch = search;
    } catch (error) {
        console.error('Ошибка загрузки пользователей:', error);
        document.getElementById('admin-users-loading').style.display = 'none';
        showError('admin-users-error', 'Ошибка загрузки пользователей');
    }
}

// Поиск пользователей
let searchTimeout;
function handleAdminUserSearch() {
    clearTimeout(searchTimeout);
    const searchInput = document.getElementById('admin-user-search');
    const search = searchInput.value.trim();
    
    searchTimeout = setTimeout(() => {
        loadAdminUsers(1, search);
    }, 500);
}

// Пагинация
function showAdminPagination(currentPage, totalPages) {
    const paginationEl = document.getElementById('admin-users-pagination');
    paginationEl.style.display = 'flex';
    paginationEl.innerHTML = '';
    
    // Кнопка "Назад"
    const prevBtn = document.createElement('button');
    prevBtn.textContent = '←';
    prevBtn.disabled = currentPage === 1;
    prevBtn.onclick = () => loadAdminUsers(currentPage - 1, currentAdminUserSearch);
    paginationEl.appendChild(prevBtn);
    
    // Номера страниц
    const startPage = Math.max(1, currentPage - 2);
    const endPage = Math.min(totalPages, currentPage + 2);
    
    for (let i = startPage; i <= endPage; i++) {
        const pageBtn = document.createElement('button');
        pageBtn.textContent = i;
        pageBtn.className = i === currentPage ? 'active' : '';
        pageBtn.onclick = () => loadAdminUsers(i, currentAdminUserSearch);
        paginationEl.appendChild(pageBtn);
    }
    
    // Кнопка "Вперед"
    const nextBtn = document.createElement('button');
    nextBtn.textContent = '→';
    nextBtn.disabled = currentPage === totalPages;
    nextBtn.onclick = () => loadAdminUsers(currentPage + 1, currentAdminUserSearch);
    paginationEl.appendChild(nextBtn);
}

// Показать детальную информацию о пользователе
async function showAdminUserDetail(userId) {
    try {
        previousAdminPage = 'admin-users';
        showPage('admin-user-detail');
        
        document.getElementById('admin-user-detail-loading').style.display = 'block';
        document.getElementById('admin-user-detail-content').innerHTML = '';
        
        const response = await apiFetch(`/api/admin/user/${userId}`, {
            method: 'POST',
            headers: {
                'Content-Type': 'application/json'
            }
        });
        
        if (!response.ok) {
            throw new Error('Ошибка загрузки информации о пользователе');
        }
        
        const data = await response.json();
        
        document.getElementById('admin-user-detail-loading').style.display = 'none';
        
        // Сохраняем userId для использования при возврате назад
        currentAdminUserDetailUserId = userId;
        
        const contentEl = document.getElementById('admin-user-detail-content');
        
        // Информация о пользователе
        contentEl.innerHTML = `
            <div class="admin-user-detail-section">
                <h3>Информация</h3>
                <div class="admin-detail-item">
                    <span class="admin-detail-label">Telegram ID</span>
                    <span class="admin-detail-value">${escapeHtml(data.user.user_id)}</span>
                </div>
                <div class="admin-detail-item">
                    <span class="admin-detail-label">Первый запуск</span>
                    <span class="admin-detail-value">${escapeHtml(data.user.first_seen_formatted)}</span>
                </div>
                <div class="admin-detail-item">
                    <span class="admin-detail-label">Последняя активность</span>
                    <span class="admin-detail-value">${escapeHtml(data.user.last_seen_formatted)}</span>
                </div>
            </div>
            
            <div class="admin-user-detail-section">
                <h3>Подписки (${data.subscriptions.length})</h3>
                ${data.subscriptions.length > 0 ? 
                    data.subscriptions.map(sub => `
                        <div class="admin-subscription-card" onclick="showAdminSubscriptionEdit(${sub.id})">
                            <div class="admin-subscription-name">${escapeHtml(sub.name)}</div>
                            <div class="admin-subscription-status ${sub.status}">${sub.status === 'active' ? 'Активна' : sub.status === 'expired' ? 'Истекла' : 'Отменена'}</div>
                            <div class="admin-subscription-info">
                                <div>Создана: ${escapeHtml(sub.created_at_formatted)}</div>
                                <div>Истекает: ${escapeHtml(sub.expires_at_formatted)}</div>
                                <div>Устройств: ${sub.device_limit}</div>
                            </div>
                        </div>
                    `).join('') :
                    '<p style="color: #a0a0a0; padding: 16px;">Нет подписок</p>'
                }
            </div>
            
            ${data.payments && data.payments.length > 0 ? `
                <div class="admin-user-detail-section">
                    <h3>Платежи (${data.payments.length})</h3>
                    ${data.payments.map(payment => `
                        <div class="admin-detail-item">
                            <span class="admin-detail-label">${escapeHtml(payment.created_at_formatted)}</span>
                            <span class="admin-detail-value">${(payment.amount || 0).toLocaleString('ru-RU')} ₽ (${escapeHtml(payment.status)})</span>
                        </div>
                    `).join('')}
                </div>
            ` : ''}
            
            <div class="create-subscription-section" style="margin-top: 24px;">
                <button class="btn-primary" onclick="showCreateSubscriptionForm('${escapeHtml(data.user.user_id)}')" style="width: 100%; margin-bottom: 12px;">Создать подписку</button>
                <button class="btn-danger" onclick="showDeleteUserConfirm('${escapeHtml(data.user.user_id)}')" style="width: 100%; background: #d32f2f; color: #fff; border: none; padding: 12px; border-radius: 8px; cursor: pointer; font-size: 14px; font-weight: 500;">Удалить пользователя</button>
            </div>
        `;
    } catch (error) {
        console.error('Ошибка загрузки информации о пользователе:', error);
        document.getElementById('admin-user-detail-loading').style.display = 'none';
        document.getElementById('admin-user-detail-content').innerHTML = 
            '<div class="error"><p>Ошибка загрузки информации</p></div>';
    }
}

// Показать форму редактирования подписки
// Глобальная переменная для хранения исходных значений подписки
let originalSubscriptionData = null;

async function showAdminSubscriptionEdit(subId) {
    try {
        previousAdminPage = 'admin-user-detail';
        currentEditingSubscriptionId = subId;
        showPage('admin-subscription-edit');
        
        document.getElementById('admin-subscription-edit-loading').style.display = 'block';
        document.getElementById('admin-subscription-edit-content').style.display = 'none';
        
        const response = await apiFetch(`/api/admin/subscription/${subId}`, {
            method: 'POST',
            headers: {
                'Content-Type': 'application/json'
            }
        });
        
        if (!response.ok) {
            throw new Error('Ошибка загрузки подписки');
        }
        
        const data = await response.json();
        const sub = data.subscription;
        const servers = data.servers || [];
        
        // Сохраняем исходные данные для сравнения
        originalSubscriptionData = {
            name: sub.name || '',
            device_limit: sub.device_limit || 1,
            status: sub.status || 'active',
            expires_at: sub.expires_at
        };
        
        // Сохраняем данные серверов для отображения во вкладке "Ключи"
        currentSubscriptionServers = servers;
        
        document.getElementById('admin-subscription-edit-loading').style.display = 'none';
        document.getElementById('admin-subscription-edit-content').style.display = 'block';
        
        // ВАЖНО: Восстанавливаем состояние кнопки submit при загрузке
        const form = document.getElementById('admin-subscription-edit-form');
        if (form) {
            const submitBtn = form.querySelector('button[type="submit"]');
            if (submitBtn) {
                submitBtn.disabled = false;
                submitBtn.textContent = 'Сохранить';
            }
        }
        
        // Заполняем форму
        document.getElementById('sub-name').value = sub.name || '';
        document.getElementById('sub-device-limit').value = sub.device_limit || 1;
        
        // Показываем текущий статус (только информационный блок)
        const statusDisplayGroup = document.getElementById('sub-status-display-group');
        const statusDisplay = document.getElementById('sub-status-display');
        const statusHint = document.getElementById('sub-status-hint');
        
        const statusNames = {
            'active': 'Активна',
            'expired': 'Истекла',
            'deleted': 'Удалена'
        };
        const currentStatusName = statusNames[sub.status] || sub.status;
        
        if (sub.status === 'deleted') {
            statusDisplay.textContent = `Текущий статус: ${currentStatusName}`;
            statusDisplay.style.color = '#ff6b6b';
            statusHint.textContent = 'Финальный статус, нельзя изменить';
            statusDisplayGroup.style.display = 'block';
        } else {
            // Для active/expired статус управляется автоматически
            statusDisplay.textContent = `Текущий статус: ${currentStatusName}`;
            statusDisplay.style.color = sub.status === 'active' ? '#4CAF50' : '#ffa726';
            statusHint.textContent = 'Управляется автоматически через дату истечения';
            statusDisplayGroup.style.display = 'block';
        }
        
        // Конвертируем timestamp в datetime-local формат
        const expiresDate = new Date(sub.expires_at * 1000);
        const year = expiresDate.getFullYear();
        const month = String(expiresDate.getMonth() + 1).padStart(2, '0');
        const day = String(expiresDate.getDate()).padStart(2, '0');
        const hours = String(expiresDate.getHours()).padStart(2, '0');
        const minutes = String(expiresDate.getMinutes()).padStart(2, '0');
        document.getElementById('sub-expires-at').value = `${year}-${month}-${day}T${hours}:${minutes}`;
        
        // Загружаем ключи для отображения
        loadSubscriptionKeys(servers);
        
        // Загружаем ключи для отображения
        loadSubscriptionKeys(servers);
    } catch (error) {
        console.error('Ошибка загрузки подписки:', error);
        document.getElementById('admin-subscription-edit-loading').style.display = 'none';
        alert('Ошибка загрузки подписки');
    }
}

// Сохранение изменений подписки
async function saveSubscriptionChanges(event) {
    event.preventDefault();
    
    // ВАЖНО: Восстанавливаем состояние кнопки submit сразу после preventDefault
    const submitBtn = event.target.querySelector('button[type="submit"]');
    if (submitBtn) {
        submitBtn.disabled = false;
        submitBtn.textContent = 'Сохранить';
    }
    
    if (!currentEditingSubscriptionId || !originalSubscriptionData) {
        alert('Ошибка: данные подписки не загружены');
        return;
    }
    
    const form = event.target;
    const newData = {
        name: form.name.value,
        device_limit: parseInt(form.device_limit.value),
        expires_at: Math.floor(new Date(form.expires_at.value).getTime() / 1000)
    };
    
    // Статус не отправляем - он управляется автоматически через expires_at
    // Исключение: deleted статус можно установить только через кнопку удаления
    
    // Определяем, что изменилось
    const changes = [];
    if (newData.name !== originalSubscriptionData.name) {
        changes.push({
            field: 'Название',
            old: originalSubscriptionData.name || '(не указано)',
            new: newData.name || '(не указано)'
        });
    }
    if (newData.device_limit !== originalSubscriptionData.device_limit) {
        changes.push({
            field: 'Лимит устройств',
            old: originalSubscriptionData.device_limit,
            new: newData.device_limit
        });
    }
    // Статус не включаем в изменения - он управляется автоматически
    if (newData.expires_at !== originalSubscriptionData.expires_at) {
        const oldDate = new Date(originalSubscriptionData.expires_at * 1000).toLocaleString('ru-RU');
        const newDate = new Date(newData.expires_at * 1000).toLocaleString('ru-RU');
        changes.push({
            field: 'Дата истечения',
            old: oldDate,
            new: newDate
        });
    }
    
    // Если есть изменения, показываем модальное окно
    if (changes.length > 0) {
        // Сохраняем данные формы для использования после подтверждения
        window.pendingSubscriptionUpdate = newData;
        
        // Показываем список изменений
        const changesList = document.getElementById('subscription-changes-list');
        changesList.innerHTML = changes.map(change => `
            <div style="margin-bottom: 12px; padding-bottom: 12px; border-bottom: 1px solid #333;">
                <div style="font-weight: bold; color: #4CAF50; margin-bottom: 4px;">${escapeHtml(change.field)}</div>
                <div style="color: #999; font-size: 12px;">Было: ${escapeHtml(String(change.old))}</div>
                <div style="color: #fff; font-size: 12px;">Станет: ${escapeHtml(String(change.new))}</div>
            </div>
        `).join('');
        
        // Показываем модальное окно
        document.getElementById('subscription-confirm-modal').style.display = 'flex';
    } else {
        // Нет изменений - просто возвращаемся
        alert('Нет изменений для сохранения');
    }
}

// Закрытие модального окна
function closeSubscriptionConfirmModal() {
    // Восстанавливаем кнопку перед закрытием
    const confirmBtn = document.querySelector('#subscription-confirm-modal .btn-primary');
    if (confirmBtn) {
        confirmBtn.textContent = 'Подтвердить и сохранить';
        confirmBtn.disabled = false;
    }
    
    document.getElementById('subscription-confirm-modal').style.display = 'none';
    window.pendingSubscriptionUpdate = null;
}

// Подтверждение и сохранение изменений
async function confirmSaveSubscriptionChanges() {
    if (!window.pendingSubscriptionUpdate) {
        closeSubscriptionConfirmModal();
        return;
    }
    
    // Получаем кнопку и сохраняем оригинальный текст
    const confirmBtn = document.querySelector('#subscription-confirm-modal .btn-primary');
    const originalText = confirmBtn ? confirmBtn.textContent : 'Подтвердить и сохранить';
    
    try {
        // Показываем индикатор загрузки
        if (confirmBtn) {
            confirmBtn.textContent = 'Сохранение...';
            confirmBtn.disabled = true;
        }
        
        const response = await apiFetch(`/api/admin/subscription/${currentEditingSubscriptionId}/update`, {
            method: 'POST',
            headers: {
                'Content-Type': 'application/json'
            },
            body: JSON.stringify({
                ...window.pendingSubscriptionUpdate
            })
        });
        
        if (!response.ok) {
            const error = await response.json();
            throw new Error(error.error || 'Ошибка сохранения');
        }
        
        const data = await response.json();
        
        // ВАЖНО: Восстанавливаем кнопку ПЕРЕД закрытием модального окна
        if (confirmBtn) {
            confirmBtn.textContent = originalText;
            confirmBtn.disabled = false;
        }
        
        // Закрываем модальное окно
        closeSubscriptionConfirmModal();
        
        // Показываем успешное сообщение
        alert('Изменения сохранены и синхронизированы с серверами!');
        
        // Возвращаемся назад
        goBackFromSubscriptionEdit();
    } catch (error) {
        console.error('Ошибка сохранения подписки:', error);
        alert('Ошибка сохранения: ' + error.message);
        
        // Восстанавливаем кнопку при ошибке
        if (confirmBtn) {
            confirmBtn.textContent = originalText;
            confirmBtn.disabled = false;
        }
    }
}

// Синхронизация подписки
async function syncSubscription() {
    try {
        if (!currentEditingSubscriptionId) {
            alert('Ошибка: ID подписки не найден');
            return;
        }
        
        const syncBtn = document.querySelector('.btn-sync');
        syncBtn.disabled = true;
        syncBtn.textContent = 'Синхронизация...';
        
        const response = await apiFetch(`/api/admin/subscription/${currentEditingSubscriptionId}/sync`, {
            method: 'POST',
            headers: {
                'Content-Type': 'application/json'
            }
        });
        
        if (!response.ok) {
            throw new Error('Ошибка синхронизации');
        }
        
        const data = await response.json();
        
        // Отображаем результаты
        const resultsEl = document.getElementById('sync-results');
        resultsEl.style.display = 'block';
        resultsEl.innerHTML = '<h4>Результаты синхронизации:</h4>' +
            data.sync_results.map(result => `
                <div class="sync-result-item">
                    <span>${escapeHtml(result.server)}: </span>
                    <span class="${result.status === 'success' ? 'sync-result-success' : 'sync-result-error'}">
                        ${result.status === 'success' ? '✓ Успешно' : '✗ Ошибка: ' + escapeHtml(result.error || 'Неизвестная ошибка')}
                    </span>
                </div>
            `).join('');
        
        syncBtn.disabled = false;
        syncBtn.textContent = 'Синхронизировать';
    } catch (error) {
        console.error('Ошибка синхронизации:', error);
        alert('Ошибка синхронизации: ' + error.message);
        const syncBtn = document.querySelector('.btn-sync');
        syncBtn.disabled = false;
        syncBtn.textContent = 'Синхронизировать';
    }
}

// Переключение между вкладками редактирования подписки
function switchSubscriptionTab(tabName) {
    // Убираем активный класс со всех вкладок
    const tabButtons = document.querySelectorAll('#page-admin-subscription-edit .tab-button');
    tabButtons.forEach(btn => btn.classList.remove('active'));
    
    // Скрываем все содержимое вкладок
    const tabContents = document.querySelectorAll('#page-admin-subscription-edit .tab-content');
    tabContents.forEach(content => content.classList.remove('active'));
    
    // Активируем выбранную вкладку
    if (tabName === 'params') {
        const paramsBtn = document.querySelector('#page-admin-subscription-edit .tab-button[onclick*="params"]');
        if (paramsBtn) paramsBtn.classList.add('active');
        const paramsContent = document.getElementById('subscription-tab-params');
        if (paramsContent) paramsContent.classList.add('active');
    } else if (tabName === 'keys') {
        const keysBtn = document.querySelector('#page-admin-subscription-edit .tab-button[onclick*="keys"]');
        if (keysBtn) keysBtn.classList.add('active');
        const keysContent = document.getElementById('subscription-tab-keys');
        if (keysContent) keysContent.classList.add('active');
        // Загружаем ключи, если они еще не загружены
        if (currentSubscriptionServers && currentSubscriptionServers.length >= 0) {
            loadSubscriptionKeys(currentSubscriptionServers);
        }
    }
}

// Загрузка и отображение ключей подписки
function loadSubscriptionKeys(servers) {
    const keysListEl = document.getElementById('subscription-keys-list');
    if (!keysListEl) return;
    
    if (!servers || servers.length === 0) {
        keysListEl.innerHTML = `
            <div class="empty-state">
                <p>У этой подписки нет привязанных серверов</p>
            </div>
        `;
        return;
    }
    
    let html = '<div class="keys-list">';
    html += '<div class="keys-header"><h3>Ключи подписки</h3></div>';
    html += '<div class="keys-items">';
    
    servers.forEach((server, index) => {
        const serverName = escapeHtml(server.server_name || 'Неизвестный сервер');
        const clientEmail = escapeHtml(server.client_email || 'Не указан');
        
        html += `
            <div class="key-item">
                <div class="key-server">${serverName}</div>
                <div class="key-email">
                    <code class="key-email-code">${clientEmail}</code>
                    <button class="btn-copy-key" onclick="copyToClipboard('${clientEmail.replace(/'/g, "\\'")}', this)" title="Копировать">
                        📋
                    </button>
                </div>
            </div>
        `;
    });
    
    html += '</div>';
    html += `<div class="keys-summary">Всего ключей: ${servers.length}</div>`;
    html += '</div>';
    
    keysListEl.innerHTML = html;
}

// Функция копирования в буфер обмена
function copyToClipboard(text, button) {
    if (navigator.clipboard && navigator.clipboard.writeText) {
        navigator.clipboard.writeText(text).then(() => {
            const originalText = button.textContent;
            button.textContent = '✓';
            button.style.color = '#4caf50';
            setTimeout(() => {
                button.textContent = originalText;
                button.style.color = '';
            }, 2000);
        }).catch(err => {
            console.error('Ошибка копирования:', err);
            alert('Не удалось скопировать');
        });
    } else {
        // Fallback для старых браузеров
        const textArea = document.createElement('textarea');
        textArea.value = text;
        textArea.style.position = 'fixed';
        textArea.style.opacity = '0';
        document.body.appendChild(textArea);
        textArea.select();
        try {
            document.execCommand('copy');
            const originalText = button.textContent;
            button.textContent = '✓';
            button.style.color = '#4caf50';
            setTimeout(() => {
                button.textContent = originalText;
                button.style.color = '';
            }, 2000);
        } catch (err) {
            console.error('Ошибка копирования:', err);
            alert('Не удалось скопировать');
        }
        document.body.removeChild(textArea);
    }
}

// Возврат назад из редактирования подписки
function goBackFromSubscriptionEdit() {
    // Сбрасываем активную вкладку на "Параметры"
    switchSubscriptionTab('params');
    if (previousAdminPage === 'admin-user-detail') {
        // Нужно перезагрузить информацию о пользователе
        if (currentAdminUserDetailUserId) {
            showAdminUserDetail(currentAdminUserDetailUserId);
        } else {
            showPage('admin-users');
        }
    } else {
        showPage('admin-users');
    }
    currentEditingSubscriptionId = null;
}

// Показать форму создания подписки
function showCreateSubscriptionForm(userId) {
    currentCreatingSubscriptionUserId = userId;
    previousAdminPage = 'admin-user-detail';
    showPage('admin-create-subscription');
    
    // Очищаем форму
    document.getElementById('create-sub-name').value = '';
    document.getElementById('create-sub-expires-at').value = '';
    document.getElementById('create-sub-device-limit').value = '1';
    document.getElementById('create-sub-period').value = 'month';
    
    // Сбрасываем кнопку отправки, чтобы не оставалась «Создание...» при повторном открытии
    const form = document.getElementById('admin-create-subscription-form');
    if (form) {
        const submitBtn = form.querySelector('button[type="submit"]');
        if (submitBtn) {
            submitBtn.disabled = false;
            submitBtn.textContent = 'Создать';
        }
    }
}

// Возврат назад из создания подписки
function goBackFromCreateSubscription() {
    if (previousAdminPage === 'admin-user-detail' && currentCreatingSubscriptionUserId) {
        showAdminUserDetail(currentCreatingSubscriptionUserId);
    } else {
        showPage('admin-users');
    }
    currentCreatingSubscriptionUserId = null;
}

// Возврат назад из детальной информации о пользователе
function goBackFromUserDetail() {
    showPage('admin-users');
}

// Показать модальное окно подтверждения удаления пользователя
function showDeleteUserConfirm(userId) {
    const modal = document.getElementById('delete-user-confirm-modal');
    if (!modal) {
        // Создаем модальное окно, если его нет
        const modalHTML = `
            <div id="delete-user-confirm-modal" class="modal" style="display: none;">
                <div class="modal-content">
                    <h2>⚠️ Удаление пользователя</h2>
                    <p style="color: #ff6b6b; margin: 16px 0; line-height: 1.6;">
                        Вы уверены, что хотите удалить этого пользователя?<br><br>
                        Это действие удалит:
                        <ul style="margin: 12px 0; padding-left: 20px; color: #ccc;">
                            <li>Все подписки пользователя</li>
                            <li>Все клиенты на серверах</li>
                            <li>Все платежи</li>
                            <li>Все данные пользователя</li>
                        </ul>
                        <strong style="color: #ff6b6b;">Это действие нельзя отменить!</strong>
                    </p>
                    <div style="display: flex; gap: 12px; margin-top: 24px; align-items: stretch;">
                        <button class="btn-secondary" onclick="closeDeleteUserModal()" style="flex: 1; padding: 12px; border-radius: 8px; font-size: 14px; font-weight: 500; min-height: 44px; box-sizing: border-box; border: 1px solid #3a3a3a; display: flex; align-items: center; justify-content: center; margin: 0;">Отмена</button>
                        <button class="btn-danger" id="delete-user-confirm-btn" style="flex: 1; background: #d32f2f; color: #fff; border: 1px solid #d32f2f; padding: 12px; border-radius: 8px; cursor: pointer; font-size: 14px; font-weight: 500; min-height: 44px; box-sizing: border-box; display: flex; align-items: center; justify-content: center; margin: 0;">Удалить</button>
                    </div>
                </div>
            </div>
        `;
        document.body.insertAdjacentHTML('beforeend', modalHTML);
    }
    
    // Обновляем userId в кнопке подтверждения
    const confirmBtn = document.getElementById('delete-user-confirm-btn');
    if (confirmBtn) {
        confirmBtn.onclick = () => confirmDeleteUser(userId);
    }
    
    document.getElementById('delete-user-confirm-modal').style.display = 'flex';
}

// Закрыть модальное окно удаления пользователя
function closeDeleteUserModal() {
    const modal = document.getElementById('delete-user-confirm-modal');
    if (modal) {
        modal.style.display = 'none';
    }
    
    // Всегда сбрасывать состояние кнопки при закрытии модального окна
    const confirmBtn = document.getElementById('delete-user-confirm-btn');
    if (confirmBtn) {
        confirmBtn.disabled = false;
        confirmBtn.textContent = 'Удалить';
    }
}

// Подтвердить удаление пользователя
async function confirmDeleteUser(userId) {
    try {
        const confirmBtn = document.getElementById('delete-user-confirm-btn');
        if (confirmBtn) {
            confirmBtn.disabled = true;
            confirmBtn.textContent = 'Удаление...';
        }
        
        const response = await apiFetch(`/api/admin/user/${userId}/delete`, {
            method: 'POST',
            headers: {
                'Content-Type': 'application/json'
            },
            body: JSON.stringify({
                confirm: true
            })
        });
        
        if (!response.ok) {
            const errorData = await response.json();
            throw new Error(errorData.error || 'Ошибка удаления пользователя');
        }
        
        const data = await response.json();
        
        closeDeleteUserModal();
        
        // Показываем уведомление об успехе
        if (tg && tg.showAlert) {
            tg.showAlert(
                `Пользователь удален:\n` +
                `- Подписок: ${data.stats.subscriptions_deleted}\n` +
                `- Платежей: ${data.stats.payments_deleted}\n` +
                `- Серверов очищено: ${data.deleted_servers.length}`
            );
        }
        
        // Возвращаемся к списку пользователей
        setTimeout(() => {
            showPage('admin-users');
            loadAdminUsers(1, '');
        }, 500);
        
        // Убеждаемся, что кнопка сброшена после успешного удаления
        const confirmBtnAfter = document.getElementById('delete-user-confirm-btn');
        if (confirmBtnAfter) {
            confirmBtnAfter.disabled = false;
            confirmBtnAfter.textContent = 'Удалить';
        }
        
    } catch (error) {
        console.error('Ошибка удаления пользователя:', error);
        if (tg && tg.showAlert) {
            tg.showAlert(`Ошибка удаления пользователя: ${error.message}`);
        }
        
        // Всегда сбрасывать состояние кнопки при ошибке
        const confirmBtn = document.getElementById('delete-user-confirm-btn');
        if (confirmBtn) {
            confirmBtn.disabled = false;
            confirmBtn.textContent = 'Удалить';
        }
    }
}

// Создание подписки
async function createSubscription(event) {
    event.preventDefault();
    
    try {
        if (!currentCreatingSubscriptionUserId) {
            alert('Ошибка: ID пользователя не найден');
            return;
        }
        
        const form = event.target;
        const formData = {
            period: form.period.value,
            device_limit: parseInt(form.device_limit.value),
            name: form.name.value.trim() || null
        };
        
        // Если указана дата истечения, добавляем её
        if (form.expires_at.value) {
            formData.expires_at = Math.floor(new Date(form.expires_at.value).getTime() / 1000);
        }
        
        const submitBtn = form.querySelector('button[type="submit"]');
        submitBtn.disabled = true;
        submitBtn.textContent = 'Создание...';
        
        const response = await apiFetch(`/api/admin/user/${currentCreatingSubscriptionUserId}/create-subscription`, {
            method: 'POST',
            headers: {
                'Content-Type': 'application/json'
            },
            body: JSON.stringify({
                ...formData
            })
        });
        
        if (!response.ok) {
            const error = await response.json();
            throw new Error(error.error || 'Ошибка создания подписки');
        }
        
        const data = await response.json();
        
        let message = 'Подписка успешно создана!';
        if (data.failed_servers && data.failed_servers.length > 0) {
            message += `\n\nПредупреждение: не удалось создать клиентов на серверах: ${data.failed_servers.map(s => s.server).join(', ')}`;
        }
        
        alert(message);
        
        // Сбрасываем кнопку до навигации, чтобы при повторном открытии формы она была в нужном состоянии
        const formEl = event.target;
        const btn = formEl && formEl.querySelector('button[type="submit"]');
        if (btn) {
            btn.disabled = false;
            btn.textContent = 'Создать';
        }
        
        // Возвращаемся назад и обновляем информацию о пользователе
        goBackFromCreateSubscription();
    } catch (error) {
        console.error('Ошибка создания подписки:', error);
        alert('Ошибка создания: ' + error.message);
        const formEl = event.target;
        const submitBtn = formEl && formEl.querySelector('button[type="submit"]');
        if (submitBtn) {
            submitBtn.disabled = false;
            submitBtn.textContent = 'Создать';
        }
    }
}

// Подтверждение удаления подписки
function confirmDeleteSubscription() {
    if (!currentEditingSubscriptionId) {
        alert('Ошибка: ID подписки не найден');
        return;
    }
    
    const subscriptionName = document.getElementById('sub-name').value || `Подписка ${currentEditingSubscriptionId}`;
    
    if (confirm(`Вы уверены, что хотите удалить подписку "${subscriptionName}"?\n\nЭто действие необратимо. Подписка будет удалена из базы данных, а клиенты удалены со всех серверов.`)) {
        deleteSubscription();
    }
}

// Удаление подписки
async function deleteSubscription() {
    try {
        if (!currentEditingSubscriptionId) {
            alert('Ошибка: ID подписки не найден');
            return;
        }
        
        const deleteBtn = document.querySelector('.btn-danger');
        deleteBtn.disabled = true;
        deleteBtn.textContent = 'Удаление...';
        
        const response = await apiFetch(`/api/admin/subscription/${currentEditingSubscriptionId}/delete`, {
            method: 'POST',
            headers: {
                'Content-Type': 'application/json'
            },
            body: JSON.stringify({
                confirm: true
            })
        });
        
        if (!response.ok) {
            const error = await response.json();
            throw new Error(error.error || 'Ошибка удаления');
        }
        
        const data = await response.json();
        
        alert('Подписка успешно удалена!');
        
        // Возвращаемся назад
        goBackFromSubscriptionEdit();
    } catch (error) {
        console.error('Ошибка удаления подписки:', error);
        alert('Ошибка удаления: ' + error.message);
        const deleteBtn = document.querySelector('.btn-danger');
        deleteBtn.disabled = false;
        deleteBtn.textContent = 'Удалить подписку';
    }
}

// Вспомогательная функция для отображения ошибок
function showError(elementId, message) {
    const errorEl = document.getElementById(elementId);
    if (errorEl) {
        errorEl.style.display = 'block';
        errorEl.innerHTML = `<p>${escapeHtml(message)}</p>`;
    }
}

// Главный экран админ-панели (две карточки «Аналитика» и «Управление») — данных не грузим
function loadAdminStats() {
    const contentEl = document.getElementById('admin-stats-content');
    if (contentEl) contentEl.style.display = 'block';
}

// Загрузка страницы «Аналитика пользователей»
async function loadUsersAnalyticsPage() {
    try {
        const loadingEl = document.getElementById('admin-users-analytics-loading');
        const errorEl = document.getElementById('admin-users-analytics-error');
        const contentEl = document.getElementById('admin-users-analytics-content');
        if (loadingEl) loadingEl.style.display = 'block';
        if (errorEl) errorEl.style.display = 'none';
        if (contentEl) contentEl.style.display = 'none';
        
        const response = await apiFetch('/api/admin/stats', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' }
        });
        if (!response.ok) throw new Error('Ошибка загрузки');
        
        const data = await response.json();
        if (loadingEl) loadingEl.style.display = 'none';
        if (contentEl) contentEl.style.display = 'block';
        
        const totalEl = document.getElementById('users-analytics-total');
        const newEl = document.getElementById('users-analytics-new-30d');
        if (totalEl) totalEl.textContent = data.stats?.users?.total ?? 0;
        if (newEl) newEl.textContent = data.stats?.users?.new_30d ?? 0;
        
        const growthPeriodEl = document.getElementById('users-analytics-growth-period');
        const convPeriodEl = document.getElementById('users-analytics-conversion-period');
        const growthDays = growthPeriodEl ? parseInt(growthPeriodEl.value) || 30 : 30;
        const convDays = convPeriodEl ? parseInt(convPeriodEl.value) || 30 : 30;
        await loadUserGrowthChart(growthDays, 'users-analytics-growth-chart');
        await loadConversionChart(convDays, 'users-analytics-conversion-chart');
    } catch (error) {
        console.error('Ошибка загрузки аналитики пользователей:', error);
        const loadingEl = document.getElementById('admin-users-analytics-loading');
        if (loadingEl) loadingEl.style.display = 'none';
        showError('admin-users-analytics-error', 'Ошибка загрузки данных');
    }
}

function changeUsersAnalyticsGrowthPeriod() {
    const el = document.getElementById('users-analytics-growth-period');
    const days = el ? parseInt(el.value) || 30 : 30;
    loadUserGrowthChart(days, 'users-analytics-growth-chart');
}

function changeUsersAnalyticsConversionPeriod() {
    const el = document.getElementById('users-analytics-conversion-period');
    const days = el ? parseInt(el.value) || 30 : 30;
    loadConversionChart(days, 'users-analytics-conversion-chart');
}

// Загрузка страницы «Аналитика серверов»
async function loadServersAnalyticsPage() {
    try {
        const loadingEl = document.getElementById('admin-servers-analytics-loading');
        const errorEl = document.getElementById('admin-servers-analytics-error');
        const contentEl = document.getElementById('admin-servers-analytics-content');
        if (loadingEl) loadingEl.style.display = 'block';
        if (errorEl) errorEl.style.display = 'none';
        if (contentEl) contentEl.style.display = 'none';
        
        await loadServerLoadChart('servers-analytics-load-chart');
        
        if (loadingEl) loadingEl.style.display = 'none';
        if (contentEl) contentEl.style.display = 'block';
        
        if (serverLoadChartInterval) clearInterval(serverLoadChartInterval);
        serverLoadChartInterval = setInterval(() => {
            if (currentPage === 'admin-servers-analytics') {
                loadServerLoadChart('servers-analytics-load-chart');
            }
        }, 2 * 60 * 1000);
    } catch (error) {
        console.error('Ошибка загрузки аналитики серверов:', error);
        const loadingEl = document.getElementById('admin-servers-analytics-loading');
        if (loadingEl) loadingEl.style.display = 'none';
        showError('admin-servers-analytics-error', 'Ошибка загрузки данных');
    }
}

// Загрузка страницы «Финансы»
async function loadFinancePage() {
    try {
        const loadingEl = document.getElementById('admin-finance-loading');
        const errorEl = document.getElementById('admin-finance-error');
        const contentEl = document.getElementById('admin-finance-content');
        if (loadingEl) loadingEl.style.display = 'block';
        if (errorEl) errorEl.style.display = 'none';
        if (contentEl) contentEl.style.display = 'none';
        
        const response = await apiFetch('/api/admin/stats', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' }
        });
        if (!response.ok) throw new Error('Ошибка загрузки финансов');
        
        const data = await response.json();
        if (loadingEl) loadingEl.style.display = 'none';
        if (contentEl) contentEl.style.display = 'block';
        
        const revEl = document.getElementById('finance-revenue');
        const payEl = document.getElementById('finance-succeeded-payments');
        if (revEl) revEl.textContent = (data.stats.payments.revenue || 0).toLocaleString('ru-RU') + ' ₽';
        if (payEl) payEl.textContent = data.stats.payments.succeeded || 0;
        
        const mrr = data.stats.business?.mrr || 0;
        const mrrChange = data.stats.business?.mrr_change || 0;
        const mrrChangePercent = data.stats.business?.mrr_change_percent || 0;
        const mrrEl = document.getElementById('finance-mrr');
        const mrrChangeValEl = document.getElementById('finance-mrr-change-value');
        const mrrChangePctEl = document.getElementById('finance-mrr-change-percent');
        const mrrChangeEl = document.getElementById('finance-mrr-change');
        if (mrrEl) mrrEl.textContent = mrr.toLocaleString('ru-RU', { minimumFractionDigits: 0, maximumFractionDigits: 0 }) + ' ₽';
        if (mrrChangeValEl) mrrChangeValEl.textContent = (mrrChange >= 0 ? '+' : '') + mrrChange.toLocaleString('ru-RU', { minimumFractionDigits: 0, maximumFractionDigits: 0 }) + ' ₽';
        if (mrrChangePctEl) mrrChangePctEl.textContent = (mrrChange >= 0 ? '+' : '') + (mrrChangePercent || 0).toFixed(1) + '%';
        if (mrrChangeEl) {
            if (mrrChange > 0) mrrChangeEl.style.color = '#4caf50';
            else if (mrrChange < 0) mrrChangeEl.style.color = '#f44336';
            else mrrChangeEl.style.color = '#999';
        }
        
        const periodEl = document.getElementById('finance-revenue-trend-period');
        const days = periodEl ? parseInt(periodEl.value) || 30 : 30;
        await loadRevenueTrendChart(days, 'finance-revenue-trend-chart');
    } catch (error) {
        console.error('Ошибка загрузки финансов:', error);
        const loadingEl = document.getElementById('admin-finance-loading');
        if (loadingEl) loadingEl.style.display = 'none';
        showError('admin-finance-error', 'Ошибка загрузки финансов');
    }
}

// Переменные для хранения экземпляров графиков
let userGrowthChart = null;
let serverLoadChart = null;
let conversionChart = null;
let revenueTrendChart = null;
let notificationDeliveryChart = null;
let notificationAnalyticsChart = null;
let subscriptionDynamicsChart = null;
let subscriptionConversionChart = null;
let churnRateChart = null;

// Загрузка графика роста пользователей (chartCanvasId — для страницы «Аналитика пользователей»: 'users-analytics-growth-chart')
async function loadUserGrowthChart(days = 30, chartCanvasId) {
    const canvasId = chartCanvasId || 'user-growth-chart';
    try {
        const response = await apiFetch('/api/admin/charts/user-growth', {
            method: 'POST',
            headers: {
                'Content-Type': 'application/json'
            },
            body: JSON.stringify({ days: days })
        });
        
        if (!response.ok) {
            throw new Error('Ошибка загрузки данных графика');
        }
        
        const result = await response.json();
        if (!result.success || !result.data) {
            return;
        }
        
        const ctx = document.getElementById(canvasId);
        if (!ctx) {
            return;
        }
        
        // Уничтожаем предыдущий график, если он существует
        if (userGrowthChart) {
            userGrowthChart.destroy();
        }
        
        // Подготавливаем данные
        const labels = result.data.map(item => {
            const date = new Date(item.date);
            return date.toLocaleDateString('ru-RU', { day: '2-digit', month: '2-digit' });
        });
        const counts = result.data.map(item => item.count);
        
        // Создаем график новых пользователей (столбцы)
        userGrowthChart = new Chart(ctx, {
            type: 'bar',
            data: {
                labels: labels,
                datasets: [
                    {
                        label: 'Новых пользователей',
                        data: counts,
                        backgroundColor: 'rgba(75, 192, 192, 0.8)',
                        borderColor: 'rgb(75, 192, 192)',
                        borderWidth: 1
                    }
                ]
            },
            options: {
                responsive: true,
                maintainAspectRatio: false,
                plugins: {
                    legend: {
                        display: true,
                        position: 'bottom',
                        align: 'start',
                        labels: {
                            boxWidth: 12,
                            boxHeight: 12,
                            padding: 8,
                            usePointStyle: false,
                            font: {
                                size: 12
                            }
                        }
                    },
                    title: {
                        display: false
                    }
                },
                scales: {
                    y: {
                        type: 'linear',
                        display: true,
                        beginAtZero: true,
                        ticks: {
                            stepSize: 1
                        },
                        title: {
                            display: true,
                            text: 'Новых пользователей'
                        }
                    },
                    x: {
                        grid: {
                            display: false
                        }
                    }
                }
            }
        });
    } catch (error) {
        console.error('Ошибка загрузки графика роста пользователей:', error);
    }
}

// Загрузка графика конверсии (chartCanvasId — для страницы «Аналитика пользователей»: 'users-analytics-conversion-chart')
async function loadConversionChart(days = 30, chartCanvasId) {
    const canvasId = chartCanvasId || 'conversion-chart';
    try {
        const response = await apiFetch('/api/admin/charts/conversion', {
            method: 'POST',
            headers: {
                'Content-Type': 'application/json'
            },
            body: JSON.stringify({ days: days })
        });
        
        if (!response.ok) {
            throw new Error('Ошибка загрузки данных графика');
        }
        
        const result = await response.json();
        if (!result.success || !result.data) {
            return;
        }
        
        const ctx = document.getElementById(canvasId);
        if (!ctx) {
            return;
        }
        
        // Уничтожаем предыдущий график, если он существует
        if (conversionChart) {
            conversionChart.destroy();
        }
        
        // Подготавливаем данные
        const labels = result.data.map(item => {
            const date = new Date(item.date);
            return date.toLocaleDateString('ru-RU', { day: '2-digit', month: '2-digit' });
        });
        const conversions = result.data.map(item => item.conversion || 0);
        const newUsers = result.data.map(item => item.new_users || 0);
        const purchased = result.data.map(item => item.purchased || 0);
        
        // Создаем комбинированный график
        conversionChart = new Chart(ctx, {
            type: 'line',
            data: {
                labels: labels,
                datasets: [
                    {
                        label: 'Конверсия (%)',
                        data: conversions,
                        borderColor: 'rgb(75, 192, 192)',
                        backgroundColor: 'rgba(75, 192, 192, 0.2)',
                        tension: 0.4,
                        yAxisID: 'y',
                        fill: true,
                        pointRadius: 4,
                        pointHoverRadius: 6
                    },
                    {
                        label: 'Новых пользователей',
                        data: newUsers,
                        type: 'bar',
                        backgroundColor: 'rgba(255, 99, 132, 0.5)',
                        borderColor: 'rgba(255, 99, 132, 1)',
                        borderWidth: 1,
                        yAxisID: 'y1'
                    },
                    {
                        label: 'Купили подписку',
                        data: purchased,
                        type: 'bar',
                        backgroundColor: 'rgba(54, 162, 235, 0.5)',
                        borderColor: 'rgba(54, 162, 235, 1)',
                        borderWidth: 1,
                        yAxisID: 'y1'
                    }
                ]
            },
            options: {
                responsive: true,
                maintainAspectRatio: false,
                interaction: {
                    mode: 'index',
                    intersect: false
                },
                scales: {
                    y: {
                        type: 'linear',
                        display: true,
                        position: 'left',
                        title: {
                            display: true,
                            text: 'Конверсия (%)',
                            color: 'rgb(75, 192, 192)'
                        },
                        min: 0,
                        max: 100,
                        ticks: {
                            callback: function(value) {
                                return value + '%';
                            }
                        },
                        grid: {
                            drawOnChartArea: true
                        }
                    },
                    y1: {
                        type: 'linear',
                        display: true,
                        position: 'right',
                        title: {
                            display: true,
                            text: 'Количество пользователей',
                            color: 'rgb(255, 99, 132)'
                        },
                        min: 0,
                        grid: {
                            drawOnChartArea: false
                        }
                    },
                    x: {
                        grid: {
                            drawOnChartArea: false
                        }
                    }
                },
                plugins: {
                    legend: {
                        display: true,
                        position: 'bottom',
                        align: 'start',
                        labels: {
                            boxWidth: 12,
                            boxHeight: 12,
                            padding: 8,
                            usePointStyle: false,
                            font: {
                                size: 12
                            }
                        }
                    },
                    tooltip: {
                        callbacks: {
                            afterLabel: function(context) {
                                const index = context.dataIndex;
                                const item = result.data[index];
                                if (context.datasetIndex === 0) {
                                    // Для конверсии показываем детали
                                    return `Новых: ${item.new_users}, Купили: ${item.purchased}`;
                                }
                                return '';
                            }
                        }
                    },
                    title: {
                        display: false
                    }
                }
            }
        });
    } catch (error) {
        console.error('Ошибка загрузки графика конверсии:', error);
    }
}

// Изменение периода для графика конверсии
function changeConversionPeriod() {
    const select = document.getElementById('conversion-period');
    const days = parseInt(select.value);
    loadConversionChart(days);
}

// Загрузка графика динамики дохода (chartCanvasId — id canvas, для страницы «Финансы» передать 'finance-revenue-trend-chart')
async function loadRevenueTrendChart(days = 30, chartCanvasId) {
    const canvasId = chartCanvasId || 'revenue-trend-chart';
    try {
        const response = await apiFetch('/api/admin/charts/revenue-trend', {
            method: 'POST',
            headers: {
                'Content-Type': 'application/json'
            },
            body: JSON.stringify({ days: days })
        });
        
        if (!response.ok) {
            throw new Error('Ошибка загрузки данных графика');
        }
        
        const result = await response.json();
        if (!result.success || !result.data) {
            return;
        }
        
        const ctx = document.getElementById(canvasId);
        if (!ctx) {
            return;
        }
        
        // Уничтожаем предыдущий график, если он существует
        if (revenueTrendChart) {
            revenueTrendChart.destroy();
        }
        
        // Подготавливаем данные
        const labels = result.data.map(item => {
            const date = new Date(item.date + 'T00:00:00');
            return date.toLocaleDateString('ru-RU', { day: '2-digit', month: '2-digit' });
        });
        const revenues = result.data.map(item => item.revenue || 0);
        const paymentsCounts = result.data.map(item => item.payments_count || 0);
        
        // Создаем комбинированный график
        revenueTrendChart = new Chart(ctx, {
            type: 'line',
            data: {
                labels: labels,
                datasets: [
                    {
                        label: 'Доход (₽)',
                        data: revenues,
                        borderColor: 'rgb(75, 192, 192)',
                        backgroundColor: 'rgba(75, 192, 192, 0.2)',
                        tension: 0.4,
                        fill: true,
                        yAxisID: 'y',
                        pointRadius: 3,
                        pointHoverRadius: 5
                    },
                    {
                        label: 'Количество платежей',
                        data: paymentsCounts,
                        type: 'bar',
                        backgroundColor: 'rgba(255, 206, 86, 0.5)',
                        borderColor: 'rgba(255, 206, 86, 1)',
                        borderWidth: 1,
                        yAxisID: 'y1'
                    }
                ]
            },
            options: {
                responsive: true,
                maintainAspectRatio: false,
                interaction: {
                    mode: 'index',
                    intersect: false
                },
                scales: {
                    y: {
                        type: 'linear',
                        display: true,
                        position: 'left',
                        beginAtZero: true,
                        ticks: {
                            callback: function(value) {
                                return value.toLocaleString('ru-RU') + ' ₽';
                            }
                        },
                        grid: {
                            color: 'rgba(255, 255, 255, 0.1)',
                            drawOnChartArea: true
                        },
                        title: {
                            display: true,
                            text: 'Доход (₽)',
                            color: 'rgb(75, 192, 192)'
                        }
                    },
                    y1: {
                        type: 'linear',
                        display: true,
                        position: 'right',
                        beginAtZero: true,
                        ticks: {
                            stepSize: 1
                        },
                        grid: {
                            color: 'rgba(255, 255, 255, 0.05)',
                            drawOnChartArea: false
                        },
                        title: {
                            display: true,
                            text: 'Количество платежей',
                            color: 'rgb(255, 206, 86)'
                        }
                    },
                    x: {
                        grid: {
                            color: 'rgba(255, 255, 255, 0.1)'
                        }
                    }
                },
                plugins: {
                    legend: {
                        display: true,
                        position: 'bottom',
                        align: 'start',
                        labels: {
                            boxWidth: 12,
                            boxHeight: 12,
                            padding: 8,
                            font: {
                                size: 12
                            }
                        }
                    },
                    tooltip: {
                        callbacks: {
                            label: function(context) {
                                const index = context.dataIndex;
                                const item = result.data[index];
                                if (context.datasetIndex === 0) {
                                    return `Доход: ${item.revenue.toLocaleString('ru-RU')} ₽ (${item.payments_count} платежей)`;
                                } else {
                                    return `Платежей: ${item.payments_count}`;
                                }
                            }
                        }
                    }
                }
            }
        });
    } catch (error) {
        console.error('Ошибка загрузки графика динамики дохода:', error);
    }
}

// Изменение периода для графика динамики дохода (основная статистика)
function changeRevenueTrendPeriod() {
    const select = document.getElementById('revenue-trend-period');
    const days = parseInt(select.value);
    loadRevenueTrendChart(days);
}

// Изменение периода для графика динамики дохода на странице «Финансы»
function changeFinanceRevenueTrendPeriod() {
    const select = document.getElementById('finance-revenue-trend-period');
    const days = select ? parseInt(select.value) || 30 : 30;
    loadRevenueTrendChart(days, 'finance-revenue-trend-chart');
}

// Загрузка графика нагрузки на серверы (chartCanvasId — для страницы «Аналитика серверов»: 'servers-analytics-load-chart')
async function loadServerLoadChart(chartCanvasId) {
    const canvasId = chartCanvasId || 'server-load-chart';
    try {
        const response = await apiFetch('/api/admin/charts/server-load', {
            method: 'POST',
            headers: {
                'Content-Type': 'application/json'
            }
        });
        
        if (!response.ok) {
            throw new Error('Ошибка загрузки данных графика');
        }
        
        const result = await response.json();
        if (!result.success) {
            console.error('Ошибка в ответе API:', result);
            return;
        }
        
        if (!result.data) {
            console.warn('Нет данных в ответе API');
            return;
        }
        
        let ctx = document.getElementById(canvasId);
        if (!ctx) {
            console.error('Canvas элемент не найден');
            return;
        }
        
        // Уничтожаем предыдущий график, если он существует
        if (serverLoadChart) {
            serverLoadChart.destroy();
        }
        
        // Подготавливаем данные
        const serverData = result.data.servers || [];
        const locationData = result.data.locations || [];
        
        console.log('Данные серверов для графика:', serverData);
        
        if (serverData.length === 0) {
            console.warn('Нет данных о серверах для отображения');
            const parent = ctx.parentElement;
            const message = document.createElement('p');
            message.style.cssText = 'text-align: center; color: #999; padding: 20px;';
            message.textContent = 'Нет данных о нагрузке на серверы';
            parent.innerHTML = '';
            parent.appendChild(message);
            return;
        }
        
        // Восстанавливаем canvas, если он был удален
        if (!ctx.getContext) {
            const parent = document.getElementById(canvasId).parentElement;
            parent.innerHTML = '<canvas id="' + canvasId + '"></canvas>';
            ctx = document.getElementById(canvasId);
        }
        
        // Создаем график по серверам
        // Используем среднее значение за 24 часа для более стабильной картины нагрузки
        const serverLabels = serverData.map(item => item.display_name || item.server_name);
        const serverTotalActive = serverData.map(item => item.total_active || 0);
        const serverCurrentOnline = serverData.map(item => item.online_clients || 0);
        const serverAvgOnline = serverData.map(item => item.avg_online_24h || 0);
        const serverMaxOnline = serverData.map(item => item.max_online_24h || 0);
        const serverLoadPercentage = serverData.map(item => item.load_percentage || 0);
        
        // Определяем цвет столбцов по проценту загрузки
        const getLoadColor = (percentage) => {
            if (percentage < 50) {
                return 'rgba(75, 192, 192, 0.8)';   // Зеленый - норма
            } else if (percentage < 80) {
                return 'rgba(255, 206, 86, 0.8)';   // Желтый - внимание
            } else {
                return 'rgba(255, 99, 132, 0.8)';   // Красный - нужен новый сервер
            }
        };
        
        const avgColors = serverLoadPercentage.map(p => getLoadColor(p));
        
        serverLoadChart = new Chart(ctx, {
            type: 'bar',
            data: {
                labels: serverLabels,
                datasets: [
                    {
                        label: 'Среднее за 24ч',
                        data: serverAvgOnline,
                        backgroundColor: avgColors,
                        borderColor: avgColors.map(c => c.replace('0.8', '1')),
                        borderWidth: 2
                    },
                    {
                        label: 'Пик за 24ч',
                        data: serverMaxOnline,
                        backgroundColor: serverMaxOnline.map((_, i) => avgColors[i].replace('0.8', '0.3')),
                        borderColor: avgColors.map(c => c.replace('0.8', '1')),
                        borderWidth: 1,
                        borderDash: [3, 3]
                    },
                    {
                        label: 'Текущее',
                        data: serverCurrentOnline,
                        backgroundColor: serverCurrentOnline.map((_, i) => avgColors[i].replace('0.8', '0.5')),
                        borderColor: avgColors.map(c => c.replace('0.8', '1')),
                        borderWidth: 1,
                        borderDash: [5, 5]
                    }
                ]
            },
            options: {
                responsive: true,
                maintainAspectRatio: false,
                plugins: {
                    legend: {
                        display: true,
                        position: 'bottom',
                        align: 'start',
                        labels: {
                            boxWidth: 12,
                            boxHeight: 12,
                            padding: 8,
                            usePointStyle: false,
                            font: {
                                size: 12
                            }
                        }
                    },
                    title: {
                        display: true,
                        text: 'Нагрузка на канал серверов (среднее за 24ч, пик и текущее)',
                        font: {
                            size: 16
                        }
                    },
                    tooltip: {
                        callbacks: {
                            label: function(context) {
                                const index = context.dataIndex;
                                const item = serverData[index];
                                const datasetLabel = context.dataset.label;
                                let label = `${datasetLabel}: ${context.parsed.y}`;
                                
                                if (datasetLabel === 'Среднее за 24ч' && item) {
                                    if (item.load_percentage !== undefined) {
                                        label += ` (${item.load_percentage}% загрузки)`;
                                    }
                                    if (item.max_online_24h !== undefined && item.min_online_24h !== undefined) {
                                        label += ` | мин: ${item.min_online_24h}, макс: ${item.max_online_24h}`;
                                    }
                                    if (item.samples_24h) {
                                        label += ` [${item.samples_24h} измерений]`;
                                    }
                                } else if (datasetLabel === 'Пик за 24ч' && item) {
                                    label += ` (максимальная нагрузка)`;
                                } else if (datasetLabel === 'Текущее' && item && item.total_active !== undefined) {
                                    label += ` из ${item.total_active} активных`;
                                }
                                return label;
                            },
                            afterLabel: function(context) {
                                const index = context.dataIndex;
                                const item = serverData[index];
                                let info = [];
                                if (item && item.location) {
                                    info.push(`Локация: ${item.location}`);
                                }
                                if (item && item.load_percentage !== undefined) {
                                    let recommendation = '';
                                    if (item.load_percentage >= 80) {
                                        recommendation = '⚠️ Рекомендуется добавить сервер';
                                    } else if (item.load_percentage >= 50) {
                                        recommendation = '⚡ Следить за нагрузкой';
                                    }
                                    if (recommendation) {
                                        info.push(recommendation);
                                    }
                                }
                                return info.join('\n');
                            }
                        }
                    },
                    legend: {
                        display: true,
                        position: 'top'
                    }
                },
                scales: {
                    y: {
                        beginAtZero: true,
                        title: {
                            display: true,
                            text: 'Количество клиентов в онлайне'
                        },
                        ticks: {
                            stepSize: 1
                        },
                        stacked: false
                    },
                    x: {
                        ticks: {
                            maxRotation: 45,
                            minRotation: 45
                        }
                    }
                }
            }
        });
    } catch (error) {
        console.error('Ошибка загрузки графика нагрузки на серверы:', error);
    }
}

// Изменение периода для графика роста пользователей
function changeUserGrowthPeriod() {
    const select = document.getElementById('user-growth-period');
    const days = parseInt(select.value);
    loadUserGrowthChart(days); // Эта функция теперь создает оба графика
}

// Переменная для отслеживания полноэкранного режима
let fullscreenChartId = null;
let originalOrientation = null;

// Функция переключения полноэкранного режима
async function toggleFullscreen(chartId) {
    // Ищем контейнер графика разными способами
    let chartContainer = null;
    const canvas = document.getElementById(chartId);
    
    if (!canvas) {
        console.error('Canvas графика не найден:', chartId);
        showChartModal(chartId);
        return;
    }
    
    // Пробуем найти контейнер разными способами
    chartContainer = canvas.closest('div[style*="position: relative"]');
    if (!chartContainer) {
        chartContainer = canvas.parentElement;
    }
    if (!chartContainer) {
        chartContainer = canvas.closest('div');
    }
    
    if (!chartContainer) {
        console.error('Контейнер графика не найден');
        showChartModal(chartId);
        return;
    }
    
    // Проверяем, поддерживается ли Fullscreen API
    const isFullscreenSupported = document.fullscreenEnabled || 
                                  document.webkitFullscreenEnabled || 
                                  document.mozFullScreenEnabled || 
                                  document.msFullscreenEnabled;
    
    // На мобильных устройствах всегда используем модальное окно (Fullscreen API работает нестабильно)
    const isMobile = /Android|webOS|iPhone|iPad|iPod|BlackBerry|IEMobile|Opera Mini/i.test(navigator.userAgent);
    
    // Если Fullscreen API не поддерживается или на мобильных, используем модальное окно
    if (!isFullscreenSupported || isMobile) {
        showChartModal(chartId);
        return;
    }
    
    try {
        // Проверяем, находимся ли мы уже в полноэкранном режиме
        const isCurrentlyFullscreen = document.fullscreenElement || 
                                     document.webkitFullscreenElement || 
                                     document.mozFullScreenElement || 
                                     document.msFullscreenElement;
        
        if (isCurrentlyFullscreen && fullscreenChartId === chartId) {
            // Выходим из полноэкранного режима
            if (document.exitFullscreen) {
                await document.exitFullscreen();
            } else if (document.webkitExitFullscreen) {
                await document.webkitExitFullscreen();
            } else if (document.mozCancelFullScreen) {
                await document.mozCancelFullScreen();
            } else if (document.msExitFullscreen) {
                await document.msExitFullscreen();
            }
            
            // Восстанавливаем ориентацию экрана
            if (originalOrientation !== null && screen.orientation && screen.orientation.unlock) {
                try {
                    await screen.orientation.unlock();
                } catch (e) {
                    console.log('Не удалось разблокировать ориентацию:', e);
                }
            }
            
            fullscreenChartId = null;
            originalOrientation = null;
        } else {
            // Входим в полноэкранный режим
            // Сохраняем текущую ориентацию
            if (screen.orientation) {
                originalOrientation = screen.orientation.angle;
            }
            
            // Запрашиваем полноэкранный режим
            let fullscreenPromise = null;
            if (chartContainer.requestFullscreen) {
                fullscreenPromise = chartContainer.requestFullscreen();
            } else if (chartContainer.webkitRequestFullscreen) {
                fullscreenPromise = chartContainer.webkitRequestFullscreen();
            } else if (chartContainer.mozRequestFullScreen) {
                fullscreenPromise = chartContainer.mozRequestFullScreen();
            } else if (chartContainer.msRequestFullscreen) {
                fullscreenPromise = chartContainer.msRequestFullscreen();
            } else {
                // Если Fullscreen API не поддерживается, используем модальное окно
                showChartModal(chartId);
                return;
            }
            
            await fullscreenPromise;
            fullscreenChartId = chartId;
            
            // На мобильных устройствах разрешаем поворот экрана
            if (screen.orientation && screen.orientation.lock) {
                try {
                    // Пробуем установить landscape ориентацию для лучшего просмотра графиков
                    await screen.orientation.lock('landscape');
                } catch (e) {
                    // Если не удалось заблокировать, пробуем unlock для разрешения поворота
                    try {
                        await screen.orientation.unlock();
                    } catch (e2) {
                        console.log('Не удалось изменить ориентацию:', e2);
                    }
                }
            }
            
            // Обновляем размер графика после входа в полноэкранный режим
            setTimeout(() => {
                if ((chartId === 'user-growth-chart' || chartId === 'users-analytics-growth-chart') && userGrowthChart) {
                    userGrowthChart.resize();
                } else if ((chartId === 'conversion-chart' || chartId === 'users-analytics-conversion-chart') && conversionChart) {
                    conversionChart.resize();
                } else if ((chartId === 'server-load-chart' || chartId === 'servers-analytics-load-chart') && serverLoadChart) {
                    serverLoadChart.resize();
                }
            }, 200);
        }
    } catch (error) {
        console.error('Ошибка переключения полноэкранного режима:', error);
        // Если полноэкранный режим не поддерживается, показываем график в модальном окне
        showChartModal(chartId);
    }
}

// Функция показа графика в модальном окне (fallback для устройств без поддержки Fullscreen API)
function showChartModal(chartId) {
    const canvas = document.getElementById(chartId);
    if (!canvas) return;
    
    // Создаем модальное окно
    const modal = document.createElement('div');
    modal.style.cssText = `
        position: fixed;
        top: 0;
        left: 0;
        width: 100%;
        height: 100%;
        background: rgba(0, 0, 0, 0.95);
        z-index: 10000;
        display: flex;
        flex-direction: column;
        align-items: center;
        justify-content: center;
        padding: 20px;
    `;
    
    const closeBtn = document.createElement('button');
    closeBtn.textContent = '✕ Закрыть';
    closeBtn.style.cssText = `
        position: absolute;
        top: 20px;
        right: 20px;
        padding: 12px 24px;
        background: #2a2a2a;
        color: #fff;
        border: 1px solid #444;
        border-radius: 8px;
        cursor: pointer;
        font-size: 16px;
    `;
    // Проверяем, не открыто ли уже модальное окно
    const existingModal = document.getElementById('chart-fullscreen-modal');
    if (existingModal) {
        document.body.removeChild(existingModal);
        fullscreenChartId = null;
        if (originalOrientation !== null && screen.orientation && screen.orientation.unlock) {
            screen.orientation.unlock().catch(e => console.log('Не удалось разблокировать ориентацию:', e));
        }
        originalOrientation = null;
        return;
    }
    
    modal.id = 'chart-fullscreen-modal';
    modal.style.cssText = `
        position: fixed;
        top: 0;
        left: 0;
        width: 100vw;
        height: 100vh;
        background: rgba(0, 0, 0, 0.98);
        z-index: 10000;
        display: flex;
        flex-direction: column;
        align-items: center;
        justify-content: center;
        padding: 20px;
        box-sizing: border-box;
    `;
    
    closeBtn.style.zIndex = '10001';
    closeBtn.onclick = () => {
        // Уничтожаем Chart.js экземпляр перед удалением модального окна
        if (modal._fullscreenChart) {
            modal._fullscreenChart.destroy();
            modal._fullscreenChart = null;
        }
        
        if (document.body.contains(modal)) {
            document.body.removeChild(modal);
        }
        fullscreenChartId = null;
        // Восстанавливаем ориентацию
        if (originalOrientation !== null && screen.orientation && screen.orientation.unlock) {
            screen.orientation.unlock().catch(e => {
                console.log('Не удалось разблокировать ориентацию:', e);
            });
        }
        originalOrientation = null;
    };
    
    const chartWrapper = document.createElement('div');
    chartWrapper.style.cssText = `
        width: 100%;
        height: 100%;
        display: flex;
        flex-direction: column;
        align-items: center;
        justify-content: center;
        overflow: auto;
        -webkit-overflow-scrolling: touch;
    `;
    
    // Получаем оригинальный Chart.js экземпляр
    let originalChart = null;
    if ((chartId === 'user-growth-chart' || chartId === 'users-analytics-growth-chart') && userGrowthChart) {
        originalChart = userGrowthChart;
    } else if ((chartId === 'conversion-chart' || chartId === 'users-analytics-conversion-chart') && conversionChart) {
        originalChart = conversionChart;
    } else if ((chartId === 'server-load-chart' || chartId === 'servers-analytics-load-chart') && serverLoadChart) {
        originalChart = serverLoadChart;
    }
    
    if (!originalChart) {
        console.error('Не найден Chart.js экземпляр для', chartId);
        return;
    }
    
    // Создаем новый canvas для модального окна
    const clonedCanvas = document.createElement('canvas');
    clonedCanvas.id = chartId + '-fullscreen';
    
    // Устанавливаем размер canvas
    const containerWidth = window.innerWidth - 40;
    const containerHeight = window.innerHeight - 100;
    clonedCanvas.width = containerWidth * (window.devicePixelRatio || 1);
    clonedCanvas.height = Math.max(400, containerHeight) * (window.devicePixelRatio || 1);
    clonedCanvas.style.width = containerWidth + 'px';
    clonedCanvas.style.height = Math.max(400, containerHeight) + 'px';
    
    // Создаем контейнер для графика
    const clonedContainer = document.createElement('div');
    clonedContainer.style.cssText = `
        width: 100%;
        max-width: 100%;
        height: auto;
        min-height: 400px;
        display: flex;
        flex-direction: column;
        align-items: center;
        justify-content: center;
    `;
    clonedContainer.appendChild(clonedCanvas);
    
    // Создаем новый Chart.js экземпляр с конфигурацией оригинального
    const chartConfig = JSON.parse(JSON.stringify(originalChart.config));
    // Обновляем размеры для полноэкранного режима
    chartConfig.options.responsive = true;
    chartConfig.options.maintainAspectRatio = false;
    
    // Создаем новый график
    const fullscreenChart = new Chart(clonedCanvas, chartConfig);
    
    chartWrapper.appendChild(clonedContainer);
    modal.appendChild(closeBtn);
    modal.appendChild(chartWrapper);
    document.body.appendChild(modal);
    
    fullscreenChartId = chartId;
    
    // Сохраняем ссылку на полноэкранный график для очистки при закрытии
    modal._fullscreenChart = fullscreenChart;
    
    // Обновляем размер графика после создания модального окна
    setTimeout(() => {
        fullscreenChart.resize();
    }, 100);
    
    // На мобильных устройствах разрешаем поворот экрана
    if (screen.orientation && screen.orientation.unlock) {
        screen.orientation.unlock().catch(e => {
            console.log('Не удалось разблокировать ориентацию:', e);
        });
    }
}

// Обработчик выхода из полноэкранного режима
document.addEventListener('fullscreenchange', handleFullscreenChange);
document.addEventListener('webkitfullscreenchange', handleFullscreenChange);
document.addEventListener('mozfullscreenchange', handleFullscreenChange);
document.addEventListener('MSFullscreenChange', handleFullscreenChange);

function handleFullscreenChange() {
    const isFullscreen = document.fullscreenElement || 
                        document.webkitFullscreenElement || 
                        document.mozFullScreenElement || 
                        document.msFullscreenElement;
    
    if (!isFullscreen && fullscreenChartId) {
        // Восстанавливаем ориентацию при выходе из полноэкранного режима
        if (originalOrientation !== null && screen.orientation && screen.orientation.unlock) {
            screen.orientation.unlock().catch(e => {
                console.log('Не удалось разблокировать ориентацию:', e);
            });
        }
        
        fullscreenChartId = null;
        originalOrientation = null;
    }
}

// Предотвращаем закрытие приложения при скролле вверх
function preventCloseOnScroll() {
    let touchStartY = 0;
    let touchEndY = 0;
    let isScrolling = false;
    
    // Обработка начала касания
    document.addEventListener('touchstart', (e) => {
        touchStartY = e.touches[0].clientY;
        isScrolling = false;
    }, { passive: true });
    
    // Обработка движения
    document.addEventListener('touchmove', (e) => {
        if (!touchStartY) return;
        
        touchEndY = e.touches[0].clientY;
        const scrollTop = window.pageYOffset || document.documentElement.scrollTop;
        const isScrollingUp = touchEndY > touchStartY;
        
        // Если скроллим вверх и мы уже вверху страницы, предотвращаем закрытие
        if (isScrollingUp && scrollTop === 0) {
            // Разрешаем небольшой overscroll, но предотвращаем закрытие
            const overscroll = touchEndY - touchStartY;
            if (overscroll > 50) {
                // Если overscroll слишком большой, предотвращаем его
                e.preventDefault();
            }
        }
        
        isScrolling = true;
    }, { passive: false });
    
    // Обработка окончания касания
    document.addEventListener('touchend', () => {
        touchStartY = 0;
        touchEndY = 0;
        isScrolling = false;
    }, { passive: true });
}

// Загрузка статистики уведомлений
async function loadNotificationStats(days = 7) {
    try {
        document.getElementById('admin-notifications-loading').style.display = 'block';
        document.getElementById('admin-notifications-error').style.display = 'none';
        document.getElementById('admin-notifications-content').style.display = 'none';
        
        const response = await apiFetch('/api/admin/charts/notifications', {
            method: 'POST',
            headers: {
                'Content-Type': 'application/json'
            },
            body: JSON.stringify({ days: days })
        });
        
        if (!response.ok) {
            throw new Error('Ошибка загрузки статистики уведомлений');
        }
        
        const result = await response.json();
        if (!result.success || !result.data) {
            throw new Error('Некорректные данные');
        }
        
        const data = result.data;
        const stats = data.stats;
        
        // Обновляем карточки статистики
        document.getElementById('notifications-total-sent').textContent = stats.total_sent || 0;
        document.getElementById('notifications-success-count').textContent = stats.success_count || 0;
        document.getElementById('notifications-success-rate').textContent = (stats.success_rate || 0).toFixed(1) + '%';
        document.getElementById('notifications-blocked').textContent = stats.blocked_users || 0;
        
        // Эффективность (продления после уведомлений)
        const effectiveness = stats.effectiveness || {};
        const extensions = effectiveness['extended'] || 0;
        document.getElementById('notifications-effectiveness').textContent = extensions;
        
        document.getElementById('admin-notifications-loading').style.display = 'none';
        document.getElementById('admin-notifications-content').style.display = 'block';
        
        // Загружаем графики
        await loadNotificationDeliveryChart(data.daily);
        await loadNotificationAnalyticsChart(data.daily, stats.by_type || []);
        
    } catch (error) {
        console.error('Ошибка загрузки статистики уведомлений:', error);
        document.getElementById('admin-notifications-loading').style.display = 'none';
        showError('admin-notifications-error', 'Ошибка загрузки статистики уведомлений');
    }
}

// Загрузка графика доставки уведомлений
async function loadNotificationDeliveryChart(dailyData) {
    try {
        const ctx = document.getElementById('notification-delivery-chart');
        if (!ctx) {
            return;
        }
        
        if (notificationDeliveryChart) {
            notificationDeliveryChart.destroy();
        }
        
        const labels = dailyData.map(item => {
            const date = new Date(item.date + 'T00:00:00');
            return date.toLocaleDateString('ru-RU', { day: '2-digit', month: '2-digit' });
        });
        
        notificationDeliveryChart = new Chart(ctx, {
            type: 'bar',
            data: {
                labels: labels,
                datasets: [
                    {
                        label: 'Успешно доставлено',
                        data: dailyData.map(item => item.success || 0),
                        backgroundColor: 'rgba(75, 192, 192, 0.8)',
                        borderColor: 'rgb(75, 192, 192)',
                        borderWidth: 1,
                        yAxisID: 'y'
                    },
                    {
                        label: 'Не доставлено',
                        data: dailyData.map(item => item.failed || 0),
                        backgroundColor: 'rgba(255, 99, 132, 0.8)',
                        borderColor: 'rgb(255, 99, 132)',
                        borderWidth: 1,
                        yAxisID: 'y'
                    },
                    {
                        label: 'Процент успешности (%)',
                        data: dailyData.map(item => item.success_rate || 0),
                        type: 'line',
                        borderColor: 'rgb(153, 102, 255)',
                        backgroundColor: 'rgba(153, 102, 255, 0.2)',
                        tension: 0.4,
                        fill: false,
                        yAxisID: 'y1',
                        pointRadius: 3,
                        pointHoverRadius: 5
                    }
                ]
            },
            options: {
                responsive: true,
                maintainAspectRatio: false,
                interaction: {
                    mode: 'index',
                    intersect: false
                },
                plugins: {
                    legend: {
                        display: true,
                        position: 'bottom',
                        align: 'start',
                        labels: {
                            boxWidth: 12,
                            boxHeight: 12,
                            padding: 8,
                            font: { size: 12 }
                        }
                    },
                    tooltip: {
                        callbacks: {
                            label: function(context) {
                                const index = context.dataIndex;
                                const item = dailyData[index];
                                if (context.datasetIndex === 2) {
                                    return `Процент успешности: ${item.success_rate.toFixed(1)}% (Всего: ${item.total}, Успешно: ${item.success}, Не доставлено: ${item.failed})`;
                                }
                                return context.dataset.label + ': ' + context.parsed.y;
                            }
                        }
                    }
                },
                scales: {
                    y: {
                        type: 'linear',
                        display: true,
                        position: 'left',
                        beginAtZero: true,
                        ticks: {
                            stepSize: 1
                        },
                        title: {
                            display: true,
                            text: 'Количество уведомлений',
                            color: 'rgb(75, 192, 192)'
                        },
                        grid: {
                            color: 'rgba(255, 255, 255, 0.1)',
                            drawOnChartArea: true
                        }
                    },
                    y1: {
                        type: 'linear',
                        display: true,
                        position: 'right',
                        beginAtZero: true,
                        max: 100,
                        ticks: {
                            callback: function(value) {
                                return value + '%';
                            }
                        },
                        title: {
                            display: true,
                            text: 'Процент успешности (%)',
                            color: 'rgb(153, 102, 255)'
                        },
                        grid: {
                            color: 'rgba(255, 255, 255, 0.05)',
                            drawOnChartArea: false
                        }
                    },
                    x: {
                        ticks: {
                            maxRotation: 45,
                            minRotation: 45
                        },
                        grid: {
                            color: 'rgba(255, 255, 255, 0.1)'
                        }
                    }
                }
            }
        });
    } catch (error) {
        console.error('Ошибка загрузки графика доставки:', error);
    }
}

// Загрузка графика аналитики уведомлений (объединяет заблокированных и по типам)
async function loadNotificationAnalyticsChart(dailyData, byTypeData) {
    try {
        const ctx = document.getElementById('notification-analytics-chart');
        if (!ctx) {
            return;
        }
        
        if (notificationAnalyticsChart) {
            notificationAnalyticsChart.destroy();
        }
        
        const labels = dailyData.map(item => {
            const date = new Date(item.date + 'T00:00:00');
            return date.toLocaleDateString('ru-RU', { day: '2-digit', month: '2-digit' });
        });
        
        notificationAnalyticsChart = new Chart(ctx, {
            type: 'bar',
            data: {
                labels: labels,
                datasets: [
                    {
                        label: 'Не доставлено (включая заблокированных)',
                        data: dailyData.map(item => item.failed || 0),
                        backgroundColor: 'rgba(255, 99, 132, 0.8)',
                        borderColor: 'rgb(255, 99, 132)',
                        borderWidth: 1
                    }
                ]
            },
            options: {
                responsive: true,
                maintainAspectRatio: false,
                plugins: {
                    legend: {
                        display: true,
                        position: 'bottom',
                        align: 'start',
                        labels: {
                            boxWidth: 12,
                            boxHeight: 12,
                            padding: 8,
                            font: { size: 12 }
                        }
                    },
                    tooltip: {
                        callbacks: {
                            footer: function(tooltipItems) {
                                if (byTypeData && byTypeData.length > 0) {
                                    const typeNames = {
                                        'expiry_3d': 'За 3 дня до истечения',
                                        'expiry_1d': 'За 1 день до истечения',
                                        'expired': 'Истекла'
                                    };
                                    let footer = '\nПо типам:\n';
                                    byTypeData.forEach(item => {
                                        const type = item.notification_type || item.type || '';
                                        const typeName = typeNames[type] || type;
                                        footer += `${typeName}: ${item.total || item.count || 0}\n`;
                                    });
                                    return footer;
                                }
                                return '';
                            }
                        }
                    }
                },
                scales: {
                    y: {
                        beginAtZero: true,
                        ticks: {
                            stepSize: 1
                        },
                        title: {
                            display: true,
                            text: 'Количество не доставленных',
                            color: 'rgb(255, 99, 132)'
                        }
                    },
                    x: {
                        ticks: {
                            maxRotation: 45,
                            minRotation: 45
                        }
                    }
                }
            }
        });
    } catch (error) {
        console.error('Ошибка загрузки графика аналитики:', error);
    }
}

// Загрузка графика процента успешности (удалена - объединена с доставкой)
async function loadNotificationSuccessRateChart(dailyData) {
    try {
        const ctx = document.getElementById('notification-success-rate-chart');
        if (!ctx) {
            return;
        }
        
        if (notificationSuccessRateChart) {
            notificationSuccessRateChart.destroy();
        }
        
        const labels = dailyData.map(item => {
            const date = new Date(item.date + 'T00:00:00');
            return date.toLocaleDateString('ru-RU', { day: '2-digit', month: '2-digit' });
        });
        
        notificationSuccessRateChart = new Chart(ctx, {
            type: 'line',
            data: {
                labels: labels,
                datasets: [{
                    label: 'Процент успешности (%)',
                    data: dailyData.map(item => item.success_rate || 0),
                    borderColor: 'rgb(75, 192, 192)',
                    backgroundColor: 'rgba(75, 192, 192, 0.2)',
                    tension: 0.1,
                    fill: true
                }]
            },
            options: {
                responsive: true,
                maintainAspectRatio: false,
                plugins: {
                    legend: {
                        display: true,
                        position: 'bottom',
                        labels: {
                            boxWidth: 12,
                            boxHeight: 12,
                            padding: 8,
                            font: { size: 12 }
                        }
                    }
                },
                scales: {
                    y: {
                        beginAtZero: true,
                        max: 100,
                        ticks: {
                            callback: function(value) {
                                return value + '%';
                            }
                        }
                    },
                    x: {
                        ticks: {
                            maxRotation: 45,
                            minRotation: 45
                        }
                    }
                }
            }
        });
    } catch (error) {
        console.error('Ошибка загрузки графика успешности:', error);
    }
}

// Загрузка графика заблокированных пользователей
async function loadNotificationBlockedChart(dailyData) {
    try {
        const ctx = document.getElementById('notification-blocked-chart');
        if (!ctx) {
            return;
        }
        
        if (notificationBlockedChart) {
            notificationBlockedChart.destroy();
        }
        
        // Для этого графика нужно получить данные о заблокированных по дням
        // Пока используем общие данные, но можно улучшить API
        const labels = dailyData.map(item => {
            const date = new Date(item.date + 'T00:00:00');
            return date.toLocaleDateString('ru-RU', { day: '2-digit', month: '2-digit' });
        });
        
        // Показываем failed как заблокированных (можно улучшить API для разделения)
        notificationBlockedChart = new Chart(ctx, {
            type: 'bar',
            data: {
                labels: labels,
                datasets: [{
                    label: 'Не доставлено (включая заблокированных)',
                    data: dailyData.map(item => item.failed || 0),
                    backgroundColor: 'rgba(255, 99, 132, 0.8)',
                    borderColor: 'rgb(255, 99, 132)',
                    borderWidth: 1
                }]
            },
            options: {
                responsive: true,
                maintainAspectRatio: false,
                plugins: {
                    legend: {
                        display: true,
                        position: 'bottom',
                        labels: {
                            boxWidth: 12,
                            boxHeight: 12,
                            padding: 8,
                            font: { size: 12 }
                        }
                    }
                },
                scales: {
                    y: {
                        beginAtZero: true,
                        ticks: {
                            stepSize: 1
                        }
                    },
                    x: {
                        ticks: {
                            maxRotation: 45,
                            minRotation: 45
                        }
                    }
                }
            }
        });
    } catch (error) {
        console.error('Ошибка загрузки графика заблокированных:', error);
    }
}

// Загрузка графика по типам уведомлений
async function loadNotificationTypesChart(byTypeData) {
    try {
        const ctx = document.getElementById('notification-types-chart');
        if (!ctx) {
            return;
        }
        
        if (notificationTypesChart) {
            notificationTypesChart.destroy();
        }
        
        if (!byTypeData || byTypeData.length === 0) {
            // Если нет данных, показываем пустой график
            notificationTypesChart = new Chart(ctx, {
                type: 'pie',
                data: {
                    labels: [],
                    datasets: [{
                        data: []
                    }]
                },
                options: {
                    responsive: true,
                    maintainAspectRatio: false,
                    plugins: {
                        legend: {
                            display: true,
                            position: 'bottom'
                        }
                    }
                }
            });
            return;
        }
        
        // Форматируем названия типов
        const typeNames = {
            'expiry_3d': 'За 3 дня до истечения',
            'expiry_1d': 'За 1 день до истечения',
            'expired': 'Истекла'
        };
        
        const labels = byTypeData.map(item => {
            const type = item.notification_type || '';
            return typeNames[type] || type;
        });
        const data = byTypeData.map(item => item.total || 0);
        
        notificationTypesChart = new Chart(ctx, {
            type: 'pie',
            data: {
                labels: labels,
                datasets: [{
                    data: data,
                    backgroundColor: [
                        'rgba(75, 192, 192, 0.8)',
                        'rgba(255, 206, 86, 0.8)',
                        'rgba(255, 99, 132, 0.8)',
                        'rgba(153, 102, 255, 0.8)',
                        'rgba(255, 159, 64, 0.8)'
                    ],
                    borderColor: [
                        'rgb(75, 192, 192)',
                        'rgb(255, 206, 86)',
                        'rgb(255, 99, 132)',
                        'rgb(153, 102, 255)',
                        'rgb(255, 159, 64)'
                    ],
                    borderWidth: 1
                }]
            },
            options: {
                responsive: true,
                maintainAspectRatio: false,
                plugins: {
                    legend: {
                        display: true,
                        position: 'bottom',
                        labels: {
                            boxWidth: 12,
                            boxHeight: 12,
                            padding: 8,
                            font: { size: 12 }
                        }
                    }
                }
            }
        });
    } catch (error) {
        console.error('Ошибка загрузки графика по типам:', error);
    }
}

// Изменение периода для графика уведомлений
function changeNotificationsPeriod() {
    const select = document.getElementById('notifications-period');
    const days = parseInt(select.value);
    loadNotificationStats(days);
}

// Загружаем подписки при загрузке страницы
document.addEventListener('DOMContentLoaded', async () => {
    // Включаем защиту от закрытия при скролле вверх
    preventCloseOnScroll();
    
    // Если это веб-режим, проверяем токен
    if (isWebMode) {
        document.body.classList.add('web-mode');
        if (webAuthToken) {
            try {
                const response = await fetch('/api/auth/verify', {
                    method: 'POST',
                    headers: { 'Content-Type': 'application/json' },
                    body: JSON.stringify({ token: webAuthToken })
                });
                const result = await response.json();
                if (result.success) {
                    currentUserId = result.user_id;
                    showPage('subscriptions');
                    // Проверяем права админа для веб-сессии
                    checkAdminAccess();
                } else {
                    showPage('landing');
                }
            } catch (e) {
                showPage('landing');
            }
        } else {
            showPage('landing');
        }
    } else {
        // Режим Telegram
        await initTelegramFlow();
    }
    
    // Инициализируем навигацию с индикатором
    initNavIndicator();
});

async function initTelegramFlow() {
    // Регистрация пользователя при первом открытии мини-приложения
    try {
        const initData = tg.initData;
        if (initData) {
            const response = await fetch('/api/user/register', {
                method: 'POST',
                headers: {
                    'Content-Type': 'application/json'
                },
                body: JSON.stringify({ initData })
            });
            
            if (response.ok) {
                const data = await response.json();
                if (data.trial_created) {
                    console.log('Пробная подписка создана для нового пользователя');
                }
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
                checkAdminAccess();
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
                checkAdminAccess();
                return;
            }
        } else if (startapp === 'subscriptions') {
            showPage('subscriptions');
            await loadSubscriptions();
            checkAdminAccess();
            return;
        }
    }
    
    showPage('subscriptions');
    await checkAdminAccess();
}

// Обработчики веб-авторизации
async function handleWebLogin(event) {
    event.preventDefault();
    const username = document.getElementById('login-username').value;
    const password = document.getElementById('login-password').value;
    const remember = document.getElementById('login-remember').checked;
    
    const btn = event.target.querySelector('button[type="submit"]');
    const originalText = btn.textContent;
    btn.disabled = true;
    btn.textContent = 'Вход...';

    try {
        const response = await fetch('/api/auth/login', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ username, password, remember })
        });
        const result = await response.json();
        
        if (result.success) {
            webAuthToken = result.token;
            if (remember) {
                try {
                    localStorage.setItem('web_token', result.token);
                } catch (e) {
                    console.error('Failed to save token to localStorage:', e);
                }
            }
            currentUserId = result.user_id;
            var formEl = event.target;
            var successMsg = document.getElementById('login-success-msg');
            if (formEl && successMsg) {
                formEl.style.display = 'none';
                successMsg.style.display = 'block';
                successMsg.classList.add('auth-success-visible');
                setTimeout(function () {
                    showPage('subscriptions');
                    checkAdminAccess();
                }, 1500);
            } else {
                showPage('subscriptions');
                checkAdminAccess();
            }
        } else {
            var loginForm = document.getElementById('login-form');
            if (loginForm) {
                loginForm.classList.remove('form-shake');
                void loginForm.offsetHeight;
                loginForm.classList.add('form-shake');
                setTimeout(function () { loginForm.classList.remove('form-shake'); }, 400);
            }
            alert(result.error || 'Ошибка входа');
        }
    } catch (e) {
        var loginForm = document.getElementById('login-form');
        if (loginForm) {
            loginForm.classList.remove('form-shake');
            void loginForm.offsetHeight;
            loginForm.classList.add('form-shake');
            setTimeout(function () { loginForm.classList.remove('form-shake'); }, 400);
        }
        alert('Ошибка сети');
    } finally {
        btn.disabled = false;
        btn.textContent = originalText;
    }
}

async function handleWebRegister(event) {
    event.preventDefault();
    const username = document.getElementById('register-username').value;
    const password = document.getElementById('register-password').value;
    const confirm = document.getElementById('register-confirm').value;
    
    if (password !== confirm) {
        var registerForm = document.getElementById('register-form');
        if (registerForm) {
            registerForm.classList.remove('form-shake');
            void registerForm.offsetHeight;
            registerForm.classList.add('form-shake');
            setTimeout(function () { registerForm.classList.remove('form-shake'); }, 400);
        }
        alert('Пароли не совпадают');
        return;
    }

    const btn = event.target.querySelector('button[type="submit"]');
    const originalText = btn.textContent;
    btn.disabled = true;
    btn.textContent = 'Регистрация...';

    try {
        const response = await fetch('/api/auth/register', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ username, password })
        });
        const result = await response.json();
        
        if (result.success) {
            webAuthToken = result.token;
            try {
                localStorage.setItem('web_token', result.token);
            } catch (e) {
                console.error('Failed to save token to localStorage:', e);
            }
            currentUserId = result.user_id;
            var formEl = event.target;
            var successMsg = document.getElementById('register-success-msg');
            if (formEl && successMsg) {
                formEl.style.display = 'none';
                successMsg.style.display = 'block';
                successMsg.classList.add('auth-success-visible');
                setTimeout(function () {
                    showPage('subscriptions');
                    checkAdminAccess();
                }, 1500);
            } else {
                showPage('subscriptions');
                checkAdminAccess();
            }
        } else {
            var registerForm = document.getElementById('register-form');
            if (registerForm) {
                registerForm.classList.remove('form-shake');
                void registerForm.offsetHeight;
                registerForm.classList.add('form-shake');
                setTimeout(function () { registerForm.classList.remove('form-shake'); }, 400);
            }
            alert(result.error || 'Ошибка регистрации');
        }
    } catch (e) {
        var registerForm = document.getElementById('register-form');
        if (registerForm) {
            registerForm.classList.remove('form-shake');
            void registerForm.offsetHeight;
            registerForm.classList.add('form-shake');
            setTimeout(function () { registerForm.classList.remove('form-shake'); }, 400);
        }
        alert('Ошибка сети');
    } finally {
        btn.disabled = false;
        btn.textContent = originalText;
    }
}

// === НАСТРОЙКА ВЕБ-ДОСТУПА (ИЗ ТГ) ===

function showWebAccessModal() {
    // Получаем ID пользователя из initData (если мы в ТГ)
    let login = '-';
    if (tg.initDataUnsafe && tg.initDataUnsafe.user) {
        login = tg.initDataUnsafe.user.id;
    }
    
    document.getElementById('web-access-login-display').innerText = login;
    document.getElementById('web-access-password').value = '';
    showModal('web-access-modal');
}

async function handleWebAccessSetup(event) {
    event.preventDefault();
    const password = document.getElementById('web-access-password').value;
    
    if (password.length < 6) {
        alert('Пароль должен быть не менее 6 символов');
        return;
    }

    const btn = event.target.querySelector('button[type="submit"]');
    const originalText = btn.textContent;
    btn.disabled = true;
    btn.textContent = 'Сохранение...';

    try {
        const response = await fetch('/api/user/web-access/setup', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ 
                initData: tg.initData,
                password: password 
            })
        });
        const result = await response.json();
        
        if (result.success) {
            closeModal('web-access-modal');
            if (tg.showAlert) {
                tg.showAlert(result.message);
            } else {
                alert(result.message);
            }
        } else {
            alert(result.error || 'Ошибка при настройке');
        }
    } catch (e) {
        alert('Ошибка сети');
    } finally {
        btn.disabled = false;
        btn.textContent = originalText;
    }
}

async function refreshAboutAccount() {
    var loginEl = document.getElementById('about-login');
    var tgIdEl = document.getElementById('about-telegram-id');
    var unlinked = document.getElementById('link-telegram-unlinked');
    var linked = document.getElementById('link-telegram-linked');
    if (!loginEl || !tgIdEl) return;

    if (isWebMode) {
        if (!webAuthToken) {
            loginEl.textContent = '—';
            tgIdEl.textContent = '—';
            return;
        }
        try {
            var r = await apiFetch('/api/user/link-status', { method: 'GET' });
            var data = await r.json();
            if (data.success) {
                loginEl.textContent = data.username || data.user_id || '—';
                tgIdEl.textContent = data.telegram_id || '—';
                if (unlinked && linked) {
                    if (data.telegram_linked) {
                        unlinked.style.display = 'none';
                        linked.style.display = 'block';
                    } else {
                        unlinked.style.display = 'block';
                        linked.style.display = 'none';
                    }
                }
            } else {
                loginEl.textContent = '—';
                tgIdEl.textContent = '—';
                if (unlinked && linked) { unlinked.style.display = 'block'; linked.style.display = 'none'; }
            }
        } catch (e) {
            loginEl.textContent = '—';
            tgIdEl.textContent = '—';
            if (unlinked && linked) { unlinked.style.display = 'block'; linked.style.display = 'none'; }
        }
        return;
    }

    var tid = (tg.initDataUnsafe && tg.initDataUnsafe.user && tg.initDataUnsafe.user.id) ? String(tg.initDataUnsafe.user.id) : '—';
    loginEl.textContent = tid;
    tgIdEl.textContent = tid;
}

async function handleLinkTelegram(event) {
    if (event) event.preventDefault();
    if (!isWebMode || !webAuthToken) return;
    var btn = document.getElementById('link-telegram-btn');
    var originalText = btn ? btn.textContent : '';
    if (btn) { btn.disabled = true; btn.textContent = 'Переход...'; }
    try {
        var r = await apiFetch('/api/user/link-telegram/start', { method: 'POST' });
        var data = await r.json();
        if (data.success && data.link) {
            window.location.href = data.link;
            return;
        }
        alert(data.error || 'Ошибка привязки');
    } catch (e) {
        alert('Ошибка сети');
    } finally {
        if (btn) { btn.disabled = false; btn.textContent = originalText; }
    }
}

async function handleChangeLogin(event) {
    event.preventDefault();
    if (!isWebMode || !webAuthToken) return;
    var form = document.getElementById('form-change-login');
    var btn = form && form.querySelector('button[type="submit"]');
    var current = document.getElementById('change-login-current');
    var newLogin = document.getElementById('change-login-new');
    if (!current || !newLogin) return;
    var cur = (current.value || '').trim();
    var neu = (newLogin.value || '').trim().toLowerCase();
    if (!cur) { alert('Введите текущий пароль'); return; }
    if (neu.length < 3) { alert('Логин слишком короткий (минимум 3 символа)'); return; }
    if (btn) { btn.disabled = true; btn.textContent = '…'; }
    try {
        var r = await apiFetch('/api/user/change-login', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ current_password: cur, new_login: neu })
        });
        var data = await r.json();
        if (data.success) {
            current.value = '';
            newLogin.value = '';
            closeModal('change-login-modal');
            refreshAboutAccount();
            alert(data.message || 'Логин изменён');
        } else {
            alert(data.error || 'Ошибка смены логина');
        }
    } catch (e) {
        alert('Ошибка сети');
    } finally {
        if (btn) { btn.disabled = false; btn.textContent = 'Сменить логин'; }
    }
}

async function handleChangePassword(event) {
    event.preventDefault();
    if (!isWebMode || !webAuthToken) return;
    var form = document.getElementById('form-change-password');
    var btn = form && form.querySelector('button[type="submit"]');
    var current = document.getElementById('change-pw-current');
    var newPw = document.getElementById('change-pw-new');
    var confirm = document.getElementById('change-pw-confirm');
    if (!current || !newPw || !confirm) return;
    var cur = (current.value || '').trim();
    var neu = (newPw.value || '').trim();
    var conf = (confirm.value || '').trim();
    if (!cur) { alert('Введите текущий пароль'); return; }
    if (neu.length < 6) { alert('Новый пароль слишком короткий (минимум 6 символов)'); return; }
    if (neu !== conf) { alert('Пароли не совпадают'); return; }
    if (btn) { btn.disabled = true; btn.textContent = '…'; }
    try {
        var r = await apiFetch('/api/user/change-password', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ current_password: cur, new_password: neu })
        });
        var data = await r.json();
        if (data.success) {
            current.value = '';
            newPw.value = '';
            confirm.value = '';
            closeModal('change-password-modal');
            alert(data.message || 'Пароль изменён');
        } else {
            alert(data.error || 'Ошибка смены пароля');
        }
    } catch (e) {
        alert('Ошибка сети');
    } finally {
        if (btn) { btn.disabled = false; btn.textContent = 'Сменить пароль'; }
    }
}

// Загрузка статистики подписок
async function loadSubscriptionStats(days = 30) {
    try {
        document.getElementById('admin-subscriptions-loading').style.display = 'block';
        document.getElementById('admin-subscriptions-error').style.display = 'none';
        document.getElementById('admin-subscriptions-content').style.display = 'none';
        
        const [chartsResponse, statsResponse] = await Promise.all([
            apiFetch('/api/admin/charts/subscriptions', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ days: days })
            }),
            apiFetch('/api/admin/stats', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' }
            })
        ]);
        
        if (!chartsResponse.ok) throw new Error('Ошибка загрузки статистики подписок');
        const result = await chartsResponse.json();
        if (!result.success || !result.data) throw new Error('Неверный формат данных');
        
        const data = result.data;
        const types = data.types || {};
        
        document.getElementById('admin-subscriptions-loading').style.display = 'none';
        document.getElementById('admin-subscriptions-content').style.display = 'block';
        
        // Карточки из API подписок
        document.getElementById('subscriptions-trial').textContent = types.trial_active || 0;
        document.getElementById('subscriptions-purchased').textContent = types.purchased_active || 0;
        document.getElementById('subscriptions-conversion').textContent = (types.conversion_rate || 0).toFixed(1) + '%';
        document.getElementById('subscriptions-month').textContent = types.month_active || 0;
        document.getElementById('subscriptions-3month').textContent = types['3month_active'] || 0;
        document.getElementById('subscriptions-total-active').textContent = types.total_active || 0;
        
        // Истекшие и удалённые — из общей статистики
        if (statsResponse.ok) {
            const statsData = await statsResponse.json();
            const subs = statsData.stats?.subscriptions || {};
            const expiredEl = document.getElementById('subscriptions-expired');
            const deletedEl = document.getElementById('subscriptions-deleted');
            if (expiredEl) expiredEl.textContent = subs.expired ?? 0;
            if (deletedEl) deletedEl.textContent = subs.deleted ?? 0;
        }
        
        // Загружаем графики
        await loadSubscriptionDynamicsChart(data.dynamics || []);
        await loadSubscriptionConversionChart(data.conversion || {});
        await loadChurnRateChart(days);
        
    } catch (error) {
        console.error('Ошибка загрузки статистики подписок:', error);
        document.getElementById('admin-subscriptions-loading').style.display = 'none';
        showError('admin-subscriptions-error', 'Ошибка загрузки статистики подписок');
    }
}

// Загрузка графика типов подписок (круговая диаграмма)
async function loadSubscriptionTypesChart(typesData) {
    try {
        const ctx = document.getElementById('subscription-types-chart');
        if (!ctx) {
            return;
        }
        
        if (subscriptionTypesChart) {
            subscriptionTypesChart.destroy();
        }
        
        const trial = typesData.trial_active || 0;
        const purchased = typesData.purchased_active || 0;
        const total = trial + purchased;
        
        if (total === 0) {
            // Показываем пустой график
            subscriptionTypesChart = new Chart(ctx, {
                type: 'doughnut',
                data: {
                    labels: ['Нет данных'],
                    datasets: [{
                        data: [1],
                        backgroundColor: ['rgba(128, 128, 128, 0.5)']
                    }]
                },
                options: {
                    responsive: true,
                    maintainAspectRatio: false,
                    plugins: {
                        legend: {
                            position: 'bottom'
                        }
                    }
                }
            });
            return;
        }
        
        subscriptionTypesChart = new Chart(ctx, {
            type: 'doughnut',
            data: {
                labels: ['Пробные', 'Купленные'],
                datasets: [{
                    data: [trial, purchased],
                    backgroundColor: [
                        'rgba(255, 206, 86, 0.8)',
                        'rgba(75, 192, 192, 0.8)'
                    ],
                    borderColor: [
                        'rgb(255, 206, 86)',
                        'rgb(75, 192, 192)'
                    ],
                    borderWidth: 2
                }]
            },
            options: {
                responsive: true,
                maintainAspectRatio: false,
                plugins: {
                    legend: {
                        position: 'bottom',
                        labels: {
                            color: '#fff',
                            padding: 15,
                            font: {
                                size: 12
                            }
                        }
                    },
                    tooltip: {
                        callbacks: {
                            label: function(context) {
                                const label = context.label || '';
                                const value = context.parsed || 0;
                                const total = context.dataset.data.reduce((a, b) => a + b, 0);
                                const percentage = ((value / total) * 100).toFixed(1);
                                return `${label}: ${value} (${percentage}%)`;
                            }
                        }
                    }
                }
            }
        });
    } catch (error) {
        console.error('Ошибка загрузки графика типов подписок:', error);
    }
}

// Загрузка графика динамики подписок
async function loadSubscriptionDynamicsChart(dynamicsData) {
    try {
        const ctx = document.getElementById('subscription-dynamics-chart');
        if (!ctx) {
            return;
        }
        
        if (subscriptionDynamicsChart) {
            subscriptionDynamicsChart.destroy();
        }
        
        const labels = dynamicsData.map(item => {
            const date = new Date(item.date + 'T00:00:00');
            return date.toLocaleDateString('ru-RU', { day: '2-digit', month: '2-digit' });
        });
        
        subscriptionDynamicsChart = new Chart(ctx, {
            type: 'line',
            data: {
                labels: labels,
                datasets: [
                    {
                        label: 'Пробные (активные)',
                        data: dynamicsData.map(item => item.trial_active || 0),
                        borderColor: 'rgb(255, 206, 86)',
                        backgroundColor: 'rgba(255, 206, 86, 0.2)',
                        tension: 0.1,
                        fill: false,
                        borderWidth: 2
                    },
                    {
                        label: 'Купленные (активные)',
                        data: dynamicsData.map(item => item.purchased_active || 0),
                        borderColor: 'rgb(75, 192, 192)',
                        backgroundColor: 'rgba(75, 192, 192, 0.2)',
                        tension: 0.1,
                        fill: false,
                        borderWidth: 2
                    },
                    {
                        label: 'Пробные (созданные)',
                        data: dynamicsData.map(item => item.trial_created || 0),
                        borderColor: 'rgba(255, 206, 86, 0.5)',
                        backgroundColor: 'rgba(255, 206, 86, 0.1)',
                        tension: 0.1,
                        fill: false,
                        borderWidth: 1,
                        borderDash: [5, 5]
                    },
                    {
                        label: 'Купленные (созданные)',
                        data: dynamicsData.map(item => item.purchased_created || 0),
                        borderColor: 'rgba(75, 192, 192, 0.5)',
                        backgroundColor: 'rgba(75, 192, 192, 0.1)',
                        tension: 0.1,
                        fill: false,
                        borderWidth: 1,
                        borderDash: [5, 5]
                    }
                ]
            },
            options: {
                responsive: true,
                maintainAspectRatio: false,
                plugins: {
                    legend: {
                        position: 'top',
                        labels: {
                            color: '#fff'
                        }
                    }
                },
                scales: {
                    y: {
                        beginAtZero: true,
                        ticks: {
                            color: '#fff'
                        },
                        grid: {
                            color: 'rgba(255, 255, 255, 0.1)'
                        }
                    },
                    x: {
                        ticks: {
                            color: '#fff'
                        },
                        grid: {
                            color: 'rgba(255, 255, 255, 0.1)'
                        }
                    }
                }
            }
        });
    } catch (error) {
        console.error('Ошибка загрузки графика динамики подписок:', error);
    }
}

// Загрузка графика конверсии
async function loadSubscriptionConversionChart(conversionData) {
    try {
        const ctx = document.getElementById('subscription-conversion-chart');
        if (!ctx) {
            return;
        }
        
        if (subscriptionConversionChart) {
            subscriptionConversionChart.destroy();
        }
        
        const daily = conversionData.daily || [];
        const labels = daily.map(item => {
            const date = new Date(item.date + 'T00:00:00');
            return date.toLocaleDateString('ru-RU', { day: '2-digit', month: '2-digit' });
        });
        
        subscriptionConversionChart = new Chart(ctx, {
            type: 'line',
            data: {
                labels: labels,
                datasets: [
                    {
                        label: 'Конверсия (%)',
                        data: daily.map(item => item.conversion_rate || 0),
                        borderColor: 'rgb(153, 102, 255)',
                        backgroundColor: 'rgba(153, 102, 255, 0.2)',
                        tension: 0.4,
                        fill: true,
                        yAxisID: 'y',
                        pointRadius: 4,
                        pointHoverRadius: 6
                    },
                    {
                        label: 'Пробных пользователей',
                        data: daily.map(item => item.trial_users || 0),
                        type: 'bar',
                        backgroundColor: 'rgba(255, 206, 86, 0.5)',
                        borderColor: 'rgba(255, 206, 86, 1)',
                        borderWidth: 1,
                        yAxisID: 'y1'
                    },
                    {
                        label: 'Конвертировалось',
                        data: daily.map(item => item.converted || 0),
                        type: 'bar',
                        backgroundColor: 'rgba(75, 192, 192, 0.5)',
                        borderColor: 'rgba(75, 192, 192, 1)',
                        borderWidth: 1,
                        yAxisID: 'y1'
                    }
                ]
            },
            options: {
                responsive: true,
                maintainAspectRatio: false,
                interaction: {
                    mode: 'index',
                    intersect: false
                },
                plugins: {
                    legend: {
                        position: 'bottom',
                        align: 'start',
                        labels: {
                            color: '#fff',
                            boxWidth: 12,
                            boxHeight: 12,
                            padding: 8,
                            font: {
                                size: 12
                            }
                        }
                    },
                    tooltip: {
                        callbacks: {
                            afterLabel: function(context) {
                                const index = context.dataIndex;
                                const item = daily[index];
                                if (context.datasetIndex === 0) {
                                    return `Пробных: ${item.trial_users || 0}, Конвертировалось: ${item.converted || 0}`;
                                }
                                return '';
                            }
                        }
                    }
                },
                scales: {
                    y: {
                        type: 'linear',
                        display: true,
                        position: 'left',
                        beginAtZero: true,
                        max: 100,
                        ticks: {
                            color: '#fff',
                            callback: function(value) {
                                return value + '%';
                            }
                        },
                        grid: {
                            color: 'rgba(255, 255, 255, 0.1)',
                            drawOnChartArea: true
                        },
                        title: {
                            display: true,
                            text: 'Конверсия (%)',
                            color: 'rgb(153, 102, 255)'
                        }
                    },
                    y1: {
                        type: 'linear',
                        display: true,
                        position: 'right',
                        beginAtZero: true,
                        ticks: {
                            color: '#fff'
                        },
                        grid: {
                            color: 'rgba(255, 255, 255, 0.05)',
                            drawOnChartArea: false
                        },
                        title: {
                            display: true,
                            text: 'Количество пользователей',
                            color: 'rgb(255, 206, 86)'
                        }
                    },
                    x: {
                        ticks: {
                            color: '#fff'
                        },
                        grid: {
                            color: 'rgba(255, 255, 255, 0.1)'
                        }
                    }
                }
            }
        });
    } catch (error) {
        console.error('Ошибка загрузки графика конверсии:', error);
    }
}

// Изменение периода для динамики подписок
function changeSubscriptionsPeriod() {
    const select = document.getElementById('subscriptions-period');
    const days = parseInt(select.value);
    loadSubscriptionStats(days);
}

// Изменение периода для конверсии подписок
function changeConversionSubscriptionsPeriod() {
    const select = document.getElementById('conversion-subscriptions-period');
    const days = parseInt(select.value);
    loadSubscriptionStats(days);
}

// Загрузка графика Churn Rate
async function loadChurnRateChart(days = 30) {
    try {
        const response = await apiFetch('/api/admin/charts/churn-rate', {
            method: 'POST',
            headers: {
                'Content-Type': 'application/json'
            },
            body: JSON.stringify({ days: days })
        });
        
        if (!response.ok) {
            throw new Error('Ошибка загрузки данных графика');
        }
        
        const result = await response.json();
        if (!result.success || !result.data) {
            return;
        }
        
        const ctx = document.getElementById('churn-rate-chart');
        if (!ctx) {
            return;
        }
        
        // Уничтожаем предыдущий график, если он существует
        if (churnRateChart) {
            churnRateChart.destroy();
        }
        
        const churnData = result.data;
        const daily = churnData.daily || [];
        
        // Подготавливаем данные
        const labels = daily.map(item => {
            const date = new Date(item.date + 'T00:00:00');
            return date.toLocaleDateString('ru-RU', { day: '2-digit', month: '2-digit' });
        });
        
        // Создаем комбинированный график
        churnRateChart = new Chart(ctx, {
            type: 'line',
            data: {
                labels: labels,
                datasets: [
                    {
                        label: 'Churn Rate (%)',
                        data: daily.map(item => item.churn_rate || 0),
                        borderColor: 'rgb(255, 99, 132)',
                        backgroundColor: 'rgba(255, 99, 132, 0.2)',
                        tension: 0.4,
                        fill: true,
                        yAxisID: 'y',
                        pointRadius: 3,
                        pointHoverRadius: 5
                    },
                    {
                        label: 'Истекло подписок',
                        data: daily.map(item => item.expired_count || 0),
                        type: 'bar',
                        backgroundColor: 'rgba(255, 206, 86, 0.5)',
                        borderColor: 'rgba(255, 206, 86, 1)',
                        borderWidth: 1,
                        yAxisID: 'y1'
                    },
                    {
                        label: 'Продлено',
                        data: daily.map(item => item.renewed_count || 0),
                        type: 'bar',
                        backgroundColor: 'rgba(75, 192, 192, 0.5)',
                        borderColor: 'rgba(75, 192, 192, 1)',
                        borderWidth: 1,
                        yAxisID: 'y1'
                    }
                ]
            },
            options: {
                responsive: true,
                maintainAspectRatio: false,
                interaction: {
                    mode: 'index',
                    intersect: false
                },
                scales: {
                    y: {
                        type: 'linear',
                        display: true,
                        position: 'left',
                        beginAtZero: true,
                        max: 100,
                        ticks: {
                            callback: function(value) {
                                return value + '%';
                            }
                        },
                        grid: {
                            color: 'rgba(255, 255, 255, 0.1)',
                            drawOnChartArea: true
                        },
                        title: {
                            display: true,
                            text: 'Churn Rate (%)',
                            color: 'rgb(255, 99, 132)'
                        }
                    },
                    y1: {
                        type: 'linear',
                        display: true,
                        position: 'right',
                        beginAtZero: true,
                        ticks: {
                            stepSize: 1
                        },
                        grid: {
                            color: 'rgba(255, 255, 255, 0.05)',
                            drawOnChartArea: false
                        },
                        title: {
                            display: true,
                            text: 'Количество подписок',
                            color: 'rgb(255, 206, 86)'
                        }
                    },
                    x: {
                        grid: {
                            color: 'rgba(255, 255, 255, 0.1)'
                        }
                    }
                },
                plugins: {
                    legend: {
                        display: true,
                        position: 'bottom',
                        align: 'start',
                        labels: {
                            boxWidth: 12,
                            boxHeight: 12,
                            padding: 8,
                            font: {
                                size: 12
                            }
                        }
                    },
                    tooltip: {
                        callbacks: {
                            label: function(context) {
                                const index = context.dataIndex;
                                const item = daily[index];
                                if (context.datasetIndex === 0) {
                                    return `Churn Rate: ${item.churn_rate}% (Истекло: ${item.expired_count}, Продлено: ${item.renewed_count}, Не продлено: ${item.not_renewed_count})`;
                                } else if (context.datasetIndex === 1) {
                                    return `Истекло: ${item.expired_count}`;
                                } else {
                                    return `Продлено: ${item.renewed_count}`;
                                }
                            }
                        }
                    }
                }
            }
        });
    } catch (error) {
        console.error('Ошибка загрузки графика Churn Rate:', error);
    }
}

// Изменение периода для графика Churn Rate
function changeChurnRatePeriod() {
    const select = document.getElementById('churn-rate-period');
    const days = parseInt(select.value);
    loadChurnRateChart(days);
}

// ==================== РАССЫЛКА ====================

// Глобальные переменные для рассылки
let broadcastSelectedUsers = []; // Массив выбранных user_id
let broadcastUserSearchTimeout = null;
let broadcastSendMode = 'all'; // 'all' | 'selected'
let broadcastCurrentQuery = '';
let broadcastCurrentResults = []; // Последняя выдача API (объекты users)
let broadcastTotalUsers = 0; // Общее число пользователей из статистики

// Загрузка страницы рассылки
async function loadBroadcastPage() {
    const loadingEl = document.getElementById('admin-broadcast-loading');
    const errorEl = document.getElementById('admin-broadcast-error');
    const contentEl = document.getElementById('admin-broadcast-content');
    const recipientsCountEl = document.getElementById('broadcast-recipients-count');
    const resultEl = document.getElementById('broadcast-result');
    
    // Скрываем ошибки и результаты
    if (errorEl) errorEl.style.display = 'none';
    if (resultEl) resultEl.style.display = 'none';
    
    // Показываем загрузку
    if (loadingEl) loadingEl.style.display = 'flex';
    const loadingTextEl = document.getElementById('broadcast-loading-text');
    if (loadingTextEl) loadingTextEl.textContent = 'Загрузка данных...';
    if (contentEl) contentEl.style.display = 'none';
    
    try {
        // Получаем статистику для определения количества пользователей
        const statsResponse = await apiFetch('/api/admin/stats', {
            method: 'POST',
            headers: {
                'Content-Type': 'application/json'
            }
        });
        
        if (!statsResponse.ok) {
            throw new Error('Ошибка загрузки данных');
        }
        
        const statsData = await statsResponse.json();
        // Структура ответа: stats.users.total (как в loadAdminStats)
        const totalUsers = statsData.stats?.users?.total || 0;
        broadcastTotalUsers = totalUsers;
        
        // Сбрасываем выбор пользователей при загрузке страницы
        broadcastSelectedUsers = [];
        broadcastCurrentQuery = '';
        broadcastCurrentResults = [];
        
        // Инициализируем режим отправки
        const modeAll = document.getElementById('broadcast-mode-all');
        const modeSelected = document.getElementById('broadcast-mode-selected');
        if (modeAll && modeSelected) {
            modeAll.onchange = () => setBroadcastMode('all');
            modeSelected.onchange = () => setBroadcastMode('selected');
            modeAll.checked = true;
            modeSelected.checked = false;
        }
        setBroadcastMode('all');
        
        // Показываем количество получателей (исключая админов, но показываем общее количество)
        recipientsCountEl.textContent = totalUsers;
        
        // Скрываем загрузку и показываем контент
        loadingEl.style.display = 'none';
        contentEl.style.display = 'block';
        
    } catch (error) {
        console.error('Ошибка загрузки страницы рассылки:', error);
        loadingEl.style.display = 'none';
        errorEl.style.display = 'block';
        document.getElementById('broadcast-error-text').textContent = error.message || 'Ошибка загрузки данных';
    }
}

// Установка режима отправки (всем / выбранным)
function setBroadcastMode(mode) {
    broadcastSendMode = mode;
    const selectionDiv = document.getElementById('broadcast-user-selection');
    const hintEl = document.getElementById('broadcast-mode-hint');
    const searchInput = document.getElementById('broadcast-user-search');
    
    if (mode === 'selected') {
        if (selectionDiv) selectionDiv.style.display = 'block';
        if (hintEl) hintEl.textContent = 'Отправка только выбранным пользователям';
        // В режиме выбранных по умолчанию показываем пустой state до ввода поиска
        broadcastCurrentQuery = (searchInput?.value || '').trim();
        renderBroadcastUserResults();
    } else {
        if (selectionDiv) selectionDiv.style.display = 'none';
        broadcastSelectedUsers = [];
        broadcastCurrentQuery = '';
        broadcastCurrentResults = [];
        if (searchInput) searchInput.value = '';
        if (hintEl) hintEl.textContent = 'Отправка всем пользователям';
    }
    
    updateSelectedCount();
    updateBroadcastRecipientsCount();
    updateSendButtonState();
}

function renderBroadcastUserResults() {
    const listEl = document.getElementById('broadcast-users-list');
    if (!listEl) return;
    
    const query = (broadcastCurrentQuery || '').trim();
    if (!query) {
        listEl.innerHTML = '<div class="broadcast-empty-state" style="padding: 16px; text-align: center; color: #a0a0a0;">Введите ID для поиска</div>';
        return;
    }
    
    // Фильтруем: выбранные показываем только в чипах
    const usersToShow = (broadcastCurrentResults || []).filter(u => !broadcastSelectedUsers.includes(u.user_id));
    if (usersToShow.length === 0) {
        listEl.innerHTML = '<div style="padding: 16px; text-align: center; color: #a0a0a0;">Нет результатов</div>';
        return;
    }
    
    listEl.innerHTML = '';
    const qLower = query.toLowerCase();
    
    usersToShow.forEach(user => {
        const userCard = document.createElement('div');
        userCard.style.cssText = 'padding: 12px; border-bottom: 1px solid #3a3a3a; cursor: pointer; display: flex; align-items: center; gap: 12px; transition: background 0.2s;';
        userCard.style.background = 'transparent';
        
        userCard.onclick = () => toggleUserForBroadcast(user.user_id);
        
        // В этой модели чекбокс можно убрать, но оставляем как визуальный affordance (всегда unchecked)
        const checkbox = document.createElement('input');
        checkbox.type = 'checkbox';
        checkbox.checked = false;
        checkbox.style.cssText = 'width: 18px; height: 18px; cursor: pointer;';
        checkbox.onclick = (e) => {
            e.stopPropagation();
            toggleUserForBroadcast(user.user_id);
        };
        
        const userInfo = document.createElement('div');
        userInfo.style.cssText = 'flex: 1;';
        
        const idLine = highlightMatchRaw(`ID: ${String(user.user_id)}`, qLower);
        const subsText = `Подписок: ${user.subscriptions_count || 0}`;
        userInfo.innerHTML = `
            <div style="color: #f5f5f5; font-size: 14px; font-weight: 500; margin-bottom: 4px;">${idLine}</div>
            <div style="color: #a0a0a0; font-size: 12px;">${escapeHtml(subsText)}</div>
        `;
        
        userCard.appendChild(checkbox);
        userCard.appendChild(userInfo);
        listEl.appendChild(userCard);
    });
}

// Поиск пользователей для рассылки
async function searchUsersForBroadcast() {
    clearTimeout(broadcastUserSearchTimeout);
    const searchInput = document.getElementById('broadcast-user-search');
    const search = (searchInput?.value || '').trim();
    const listEl = document.getElementById('broadcast-users-list');
    
    broadcastCurrentQuery = search;
    
    // Пустой поиск — не дергаем API, показываем подсказку
    if (!search) {
        broadcastCurrentResults = [];
        renderBroadcastUserResults();
        return;
    }
    
    broadcastUserSearchTimeout = setTimeout(async () => {
        try {
            listEl.innerHTML = '<div style="padding: 16px; text-align: center; color: #a0a0a0;">Поиск...</div>';
            
            const response = await apiFetch('/api/admin/users', {
                method: 'POST',
                headers: {
                    'Content-Type': 'application/json'
                },
                body: JSON.stringify({
                    page: 1,
                    limit: 50, // Ограничиваем до 50 результатов
                    search
                })
            });
            
            if (!response.ok) {
                throw new Error('Ошибка поиска пользователей');
            }
            
            const data = await response.json();
            
            if (!data.users || data.users.length === 0) {
                listEl.innerHTML = '<div style="padding: 16px; text-align: center; color: #a0a0a0;">Пользователи не найдены</div>';
                return;
            }
            
            broadcastCurrentResults = data.users;
            renderBroadcastUserResults();
            
        } catch (error) {
            console.error('Ошибка поиска пользователей:', error);
            listEl.innerHTML = '<div style="padding: 16px; text-align: center; color: #cf7f7f;">Ошибка загрузки пользователей</div>';
        }
    }, 500);
}

// Переключение выбора пользователя
function toggleUserForBroadcast(userId) {
    const index = broadcastSelectedUsers.indexOf(userId);
    if (index === -1) {
        broadcastSelectedUsers.push(userId);
    } else {
        // В текущей UX модели повторный клик в выдаче не должен случаться, т.к. выбранный исчезает.
        broadcastSelectedUsers.splice(index, 1);
    }
    
    updateSelectedCount();
    updateBroadcastRecipientsCount();
    updateSendButtonState();
    renderBroadcastUserResults();
}

// Очистить выбор пользователей
function clearUserSelection() {
    broadcastSelectedUsers = [];
    updateSelectedCount();
    updateBroadcastRecipientsCount();
    updateSendButtonState();
    renderBroadcastUserResults();
}

// Обновить счетчик выбранных пользователей
function updateSelectedCount() {
    const countEl = document.getElementById('broadcast-selected-count');
    if (countEl) {
        countEl.textContent = broadcastSelectedUsers.length;
    }
    updateSelectedChips();
}

// Обновить счетчик получателей рассылки
function updateBroadcastRecipientsCount() {
    const recipientsCountEl = document.getElementById('broadcast-recipients-count');
    if (!recipientsCountEl) return;
    
    if (broadcastSendMode === 'selected') {
        recipientsCountEl.textContent = broadcastSelectedUsers.length;
    } else {
        recipientsCountEl.textContent = broadcastTotalUsers || '-';
    }
}

// Обновить состояние кнопки отправки
function updateSendButtonState() {
    const sendBtn = document.getElementById('broadcast-send-btn');
    if (!sendBtn) return;
    
    if (broadcastSendMode === 'selected' && broadcastSelectedUsers.length === 0) {
        sendBtn.disabled = true;
        sendBtn.textContent = 'Отправить рассылку';
    } else {
        sendBtn.disabled = false;
        sendBtn.textContent = 'Отправить рассылку';
    }
}

// Плашки выбранных пользователей
function updateSelectedChips() {
    const chipsEl = document.getElementById('broadcast-selected-chips');
    if (!chipsEl) return;
    
    chipsEl.innerHTML = '';
    if (broadcastSelectedUsers.length === 0) {
        chipsEl.style.display = 'none';
        return;
    }
    chipsEl.style.display = 'flex';
    
    broadcastSelectedUsers.forEach((userId) => {
        const chip = document.createElement('div');
        chip.className = 'chip';
        chip.innerHTML = `
            <span>${escapeHtml(userId)}</span>
            <button aria-label="Удалить" onclick="removeUserFromSelection('${userId}')">×</button>
        `;
        chipsEl.appendChild(chip);
    });
}

function removeUserFromSelection(userId) {
    const idx = broadcastSelectedUsers.indexOf(userId);
    if (idx > -1) {
        broadcastSelectedUsers.splice(idx, 1);
        updateSelectedCount();
        updateBroadcastRecipientsCount();
        updateSendButtonState();
        renderBroadcastUserResults();
    }
}

// Выбрать все в текущей выдаче
function selectAllBroadcastResults() {
    const usersToShow = (broadcastCurrentResults || []).filter(u => !broadcastSelectedUsers.includes(u.user_id));
    if (!usersToShow.length) return;
    usersToShow.forEach((u) => broadcastSelectedUsers.push(u.user_id));
    updateSelectedCount();
    updateBroadcastRecipientsCount();
    updateSendButtonState();
    renderBroadcastUserResults();
}

// Подсветка совпадений для сырого текста
function highlightMatchRaw(text, queryLower) {
    if (!queryLower) return escapeHtml(text);
    const lower = text.toLowerCase();
    const idx = lower.indexOf(queryLower);
    if (idx === -1) return escapeHtml(text);
    const before = text.slice(0, idx);
    const match = text.slice(idx, idx + queryLower.length);
    const after = text.slice(idx + queryLower.length);
    return `${escapeHtml(before)}<span class="highlight-match">${escapeHtml(match)}</span>${escapeHtml(after)}`;
}

// Отправка рассылки
async function sendBroadcast() {
    const messageEl = document.getElementById('broadcast-message');
    const sendBtn = document.getElementById('broadcast-send-btn');
    const loadingEl = document.getElementById('admin-broadcast-loading');
    const errorEl = document.getElementById('admin-broadcast-error');
    const resultEl = document.getElementById('broadcast-result');
    const contentEl = document.getElementById('admin-broadcast-content');
    
    const message = messageEl.value.trim();
    
    if (!message) {
        if (!isWebMode && tg?.showAlert) {
            tg.showAlert('Пожалуйста, введите текст сообщения');
        } else {
            alert('Пожалуйста, введите текст сообщения');
        }
        return;
    }
    
    const isSelectMode = broadcastSendMode === 'selected';
    
    if (isSelectMode && broadcastSelectedUsers.length === 0) {
        if (!isWebMode && tg?.showAlert) {
            tg.showAlert('Пожалуйста, выберите хотя бы одного пользователя');
        } else {
            alert('Пожалуйста, выберите хотя бы одного пользователя');
        }
        return;
    }
    
    // Формируем текст подтверждения
    let confirmText;
    if (isSelectMode) {
        confirmText = `Вы уверены, что хотите отправить рассылку ${broadcastSelectedUsers.length} выбранным пользователям?`;
    } else {
        confirmText = 'Вы уверены, что хотите отправить рассылку всем пользователям?';
    }
    
    if (!isWebMode && tg?.showConfirm) {
        const confirmed = await new Promise((resolve) => {
            tg.showConfirm(confirmText, (result) => resolve(result));
        });
        if (!confirmed) {
            return;
        }
    } else {
        if (!confirm(confirmText)) {
            return;
        }
    }
    
    // Блокируем кнопку и показываем загрузку
    sendBtn.disabled = true;
    sendBtn.textContent = 'Отправка...';
    loadingEl.style.display = 'flex';
    document.getElementById('broadcast-loading-text').textContent = 'Отправка рассылки...';
    errorEl.style.display = 'none';
    resultEl.style.display = 'none';
    contentEl.style.display = 'none';
    
    try {
        // Формируем тело запроса
        const requestBody = {
            message: message
        };
        
        // Если выбран режим выбора пользователей - добавляем user_ids
        if (isSelectMode && broadcastSelectedUsers.length > 0) {
            requestBody.user_ids = broadcastSelectedUsers;
        }
        
        const response = await apiFetch('/api/admin/broadcast', {
            method: 'POST',
            headers: {
                'Content-Type': 'application/json'
            },
            body: JSON.stringify(requestBody)
        });
        
        if (!response.ok) {
            const errorData = await response.json();
            throw new Error(errorData.error || 'Ошибка отправки рассылки');
        }
        
        const data = await response.json();
        
        // Показываем результат
        document.getElementById('broadcast-sent-count').textContent = data.sent || 0;
        document.getElementById('broadcast-failed-count').textContent = data.failed || 0;
        document.getElementById('broadcast-total-count').textContent = data.total || 0;
        
        resultEl.style.display = 'block';
        loadingEl.style.display = 'none';
        contentEl.style.display = 'block';
        
        // Очищаем поле сообщения
        messageEl.value = '';
        
        // Показываем уведомление (в вебе — alert, иначе tg.showAlert может вернуть WebAppMethodUnsupported)
        const resultMsg = `Рассылка завершена!\n\nОтправлено: ${data.sent}\nОшибок: ${data.failed}\nВсего: ${data.total}`;
        if (!isWebMode && tg?.showAlert) {
            tg.showAlert(resultMsg);
        } else {
            alert(resultMsg);
        }
        
    } catch (error) {
        console.error('Ошибка отправки рассылки:', error);
        loadingEl.style.display = 'none';
        errorEl.style.display = 'block';
        document.getElementById('broadcast-error-text').textContent = (error && error.message) || 'Ошибка отправки рассылки';
        contentEl.style.display = 'block';
    } finally {
        // Разблокируем кнопку
        sendBtn.disabled = false;
        sendBtn.textContent = 'Отправить рассылку';
    }
}

// Глобальные переменные для инструкций
let currentInstructionPlatform = null;
let currentInstructionStep = 0;
let currentInstructionSteps = [];

// Структура пошаговых инструкций
const instructionSteps = {
    android: {
        title: 'Android (v2RayTun, Happ)',
        steps: [
            {
                title: 'Шаг 1: Выберите приложение',
                content: `
                    <p>Выберите одно из приложений для Android:</p>
                    <ul style="margin: 12px 0; padding-left: 20px;">
                        <li style="margin-bottom: 8px;"><a href="https://play.google.com/store/apps/details?id=com.v2raytun.android" target="_blank" style="color: #4a9eff;">v2RayTun из Google Play</a></li>
                        <li style="margin-bottom: 8px;"><a href="https://play.google.com/store/search?q=happ+plus&c=apps" target="_blank" style="color: #4a9eff;">Happ из Google Play</a></li>
                    </ul>
                    <p>Скачайте и установите выбранное приложение на ваше устройство.</p>
                `
            },
            {
                title: 'Шаг 2: Получите ссылку на подписку',
                content: `
                    <p>В мини-приложении:</p>
                    <ol style="margin: 12px 0; padding-left: 20px;">
                        <li style="margin-bottom: 8px;">Нажмите на вкладку "Подписки"</li>
                        <li style="margin-bottom: 8px;">Выберите вашу подписку</li>
                        <li style="margin-bottom: 8px;">Нажмите кнопку "Копировать ссылку"</li>
                    </ol>
                    <p>Ссылка будет скопирована в буфер обмена.</p>
                `
            },
            {
                title: 'Шаг 3: Добавьте подписку в приложение',
                content: `
                    <p>В выбранном VPN-приложении:</p>
                    <ol style="margin: 12px 0; padding-left: 20px;">
                        <li style="margin-bottom: 8px;">Нажмите кнопку "+" (добавить)</li>
                        <li style="margin-bottom: 8px;">Выберите "Добавить из буфера обмена"</li>
                        <li style="margin-bottom: 8px;">Подписка будет автоматически импортирована</li>
                    </ol>
                `
            },
            {
                title: 'Шаг 4: Подключитесь к VPN',
                content: `
                    <p>После импорта подписки:</p>
                    <ol style="margin: 12px 0; padding-left: 20px;">
                        <li style="margin-bottom: 8px;">Выберите добавленный профиль</li>
                        <li style="margin-bottom: 8px;">Нажмите кнопку подключения</li>
                        <li style="margin-bottom: 8px;">Дождитесь установления соединения</li>
                    </ol>
                `
            },
            {
                title: 'Советы и рекомендации',
                content: `
                    <p><strong>Если VPN не подключается:</strong></p>
                    <ul style="margin: 12px 0; padding-left: 20px;">
                        <li style="margin-bottom: 8px;">Проверьте подключение к интернету</li>
                        <li style="margin-bottom: 8px;">Перезапустите VPN-приложение</li>
                        <li style="margin-bottom: 8px;">Перезагрузите устройство</li>
                        <li style="margin-bottom: 8px;">Скопируйте ссылку заново</li>
                    </ul>
                    <p><strong>Важно:</strong> Используйте только одну VPN-программу одновременно. Не делитесь своей ссылкой с другими пользователями.</p>
                `
            }
        ]
    },
    ios: {
        title: 'iOS (v2RayTun, Happ)',
        steps: [
            {
                title: 'Шаг 1: Выберите приложение',
                content: `
                    <p>Выберите одно из приложений для iPhone:</p>
                    <ul style="margin: 12px 0; padding-left: 20px;">
                        <li style="margin-bottom: 8px;"><a href="https://apps.apple.com/us/app/v2raytun/id6476628951?platform=iphone" target="_blank" style="color: #4a9eff;">v2RayTun из App Store</a></li>
                        <li style="margin-bottom: 8px;"><a href="https://apps.apple.com/ru/app/happ-proxy-utility-plus/id6746188973" target="_blank" style="color: #4a9eff;">Happ из App Store</a></li>
                    </ul>
                    <p>Скачайте и установите выбранное приложение на ваше устройство.</p>
                `
            },
            {
                title: 'Шаг 2: Получите ссылку на подписку',
                content: `
                    <p>В мини-приложении:</p>
                    <ol style="margin: 12px 0; padding-left: 20px;">
                        <li style="margin-bottom: 8px;">Нажмите на вкладку "Подписки"</li>
                        <li style="margin-bottom: 8px;">Выберите вашу подписку</li>
                        <li style="margin-bottom: 8px;">Нажмите кнопку "Копировать ссылку"</li>
                    </ol>
                `
            },
            {
                title: 'Шаг 3: Откройте VPN-приложение',
                content: `
                    <p>Откройте установленное VPN-приложение на вашем iPhone.</p>
                `
            },
            {
                title: 'Шаг 4: Добавьте подписку',
                content: `
                    <p>В VPN-приложении:</p>
                    <ol style="margin: 12px 0; padding-left: 20px;">
                        <li style="margin-bottom: 8px;">Нажмите кнопку "+" (добавить)</li>
                        <li style="margin-bottom: 8px;">Выберите "Добавить из буфера обмена"</li>
                        <li style="margin-bottom: 8px;">Подписка будет автоматически импортирована</li>
                    </ol>
                `
            },
            {
                title: 'Шаг 5: Подключитесь',
                content: `
                    <p>После импорта:</p>
                    <ol style="margin: 12px 0; padding-left: 20px;">
                        <li style="margin-bottom: 8px;">Выберите добавленный профиль</li>
                        <li style="margin-bottom: 8px;">Нажмите кнопку подключения</li>
                        <li style="margin-bottom: 8px;">Разрешите создание VPN-подключения при запросе системы</li>
                    </ol>
                    <p><strong>Важно:</strong> Не делитесь своей ссылкой с другими пользователями.</p>
                `
            }
        ]
    },
    windows: {
        title: 'Windows (v2RayTun, Happ)',
        steps: [
            {
                title: 'Шаг 1: Скачайте приложение',
                content: `
                    <p>Выберите и скачайте одно из приложений:</p>
                    <ul style="margin: 12px 0; padding-left: 20px;">
                        <li style="margin-bottom: 8px;"><a href="https://storage.v2raytun.com/v2RayTun_Setup.exe" target="_blank" style="color: #4a9eff;">v2RayTun для Windows</a></li>
                        <li style="margin-bottom: 8px;"><a href="https://github.com/Happ-proxy/happ-desktop/releases/latest/download/setup-Happ.x64.exe" target="_blank" style="color: #4a9eff;">Happ для Windows</a></li>
                    </ul>
                    <p>Установите приложение на ваш компьютер.</p>
                `
            },
            {
                title: 'Шаг 2: Получите ссылку на подписку',
                content: `
                    <p>В мини-приложении:</p>
                    <ol style="margin: 12px 0; padding-left: 20px;">
                        <li style="margin-bottom: 8px;">Нажмите на вкладку "Подписки"</li>
                        <li style="margin-bottom: 8px;">Выберите вашу подписку</li>
                        <li style="margin-bottom: 8px;">Нажмите кнопку "Копировать ссылку"</li>
                    </ol>
                `
            },
            {
                title: 'Шаг 3: Добавьте подписку в приложение',
                content: `
                    <p>В VPN-приложении:</p>
                    <ol style="margin: 12px 0; padding-left: 20px;">
                        <li style="margin-bottom: 8px;">Нажмите кнопку "+" (добавить)</li>
                        <li style="margin-bottom: 8px;">Выберите "Добавить из буфера обмена"</li>
                        <li style="margin-bottom: 8px;">Подписка будет автоматически импортирована</li>
                    </ol>
                `
            },
            {
                title: 'Шаг 4: Включите VPN',
                content: `
                    <p>После импорта:</p>
                    <ol style="margin: 12px 0; padding-left: 20px;">
                        <li style="margin-bottom: 8px;">Найдите добавленный профиль в списке</li>
                        <li style="margin-bottom: 8px;">Нажмите на переключатель или кнопку "Включить"</li>
                        <li style="margin-bottom: 8px;">Дождитесь установления соединения</li>
                    </ol>
                    <p><strong>Важно:</strong> Используйте только одну VPN-программу одновременно.</p>
                `
            }
        ]
    },
    macos: {
        title: 'macOS (v2RayTun, Happ)',
        steps: [
            {
                title: 'Шаг 1: Скачайте приложение',
                content: `
                    <p>Выберите и скачайте одно из приложений:</p>
                    <ul style="margin: 12px 0; padding-left: 20px;">
                        <li style="margin-bottom: 8px;"><a href="https://apps.apple.com/us/app/v2raytun/id6476628951?platform=mac" target="_blank" style="color: #4a9eff;">v2RayTun для Mac</a></li>
                        <li style="margin-bottom: 8px;"><a href="https://apps.apple.com/ru/app/happ-proxy-utility-plus/id6746188973?platform=mac" target="_blank" style="color: #4a9eff;">Happ для Mac</a></li>
                    </ul>
                    <p>Установите приложение на ваш Mac.</p>
                `
            },
            {
                title: 'Шаг 2: Получите ссылку на подписку',
                content: `
                    <p>В мини-приложении:</p>
                    <ol style="margin: 12px 0; padding-left: 20px;">
                        <li style="margin-bottom: 8px;">Нажмите на вкладку "Подписки"</li>
                        <li style="margin-bottom: 8px;">Выберите вашу подписку</li>
                        <li style="margin-bottom: 8px;">Нажмите кнопку "Копировать ссылку"</li>
                    </ol>
                `
            },
            {
                title: 'Шаг 3: Добавьте подписку',
                content: `
                    <p>В VPN-приложении:</p>
                    <ol style="margin: 12px 0; padding-left: 20px;">
                        <li style="margin-bottom: 8px;">Нажмите кнопку "+" (добавить)</li>
                        <li style="margin-bottom: 8px;">Выберите "Добавить из буфера обмена"</li>
                        <li style="margin-bottom: 8px;">Подписка будет автоматически импортирована</li>
                    </ol>
                `
            },
            {
                title: 'Шаг 4: Включите VPN',
                content: `
                    <p>После импорта:</p>
                    <ol style="margin: 12px 0; padding-left: 20px;">
                        <li style="margin-bottom: 8px;">Найдите добавленный профиль</li>
                        <li style="margin-bottom: 8px;">Нажмите на переключатель или кнопку "Включить"</li>
                        <li style="margin-bottom: 8px;">Дождитесь установления соединения</li>
                    </ol>
                    <p><strong>Важно:</strong> Используйте только одну VPN-программу одновременно.</p>
                `
            }
        ]
    },
    linux: {
        title: 'Linux (Happ)',
        steps: [
            {
                title: 'Шаг 1: Скачайте Happ',
                content: `
                    <p><a href="https://github.com/Happ-proxy/happ-desktop/releases/latest/download/Happ.linux.x64.deb" target="_blank" style="color: #4a9eff;">Скачайте Happ для Linux</a> и установите на ваш компьютер.</p>
                `
            },
            {
                title: 'Шаг 2: Получите ссылку на подписку',
                content: `
                    <p>В мини-приложении:</p>
                    <ol style="margin: 12px 0; padding-left: 20px;">
                        <li style="margin-bottom: 8px;">Нажмите на вкладку "Подписки"</li>
                        <li style="margin-bottom: 8px;">Выберите вашу подписку</li>
                        <li style="margin-bottom: 8px;">Нажмите кнопку "Копировать ссылку"</li>
                    </ol>
                `
            },
            {
                title: 'Шаг 3: Добавьте подписку',
                content: `
                    <p>В Happ:</p>
                    <ol style="margin: 12px 0; padding-left: 20px;">
                        <li style="margin-bottom: 8px;">Нажмите кнопку "+" (добавить)</li>
                        <li style="margin-bottom: 8px;">Выберите "Добавить из буфера обмена"</li>
                        <li style="margin-bottom: 8px;">Подписка будет автоматически импортирована</li>
                    </ol>
                `
            },
            {
                title: 'Шаг 4: Включите VPN',
                content: `
                    <p>После импорта:</p>
                    <ol style="margin: 12px 0; padding-left: 20px;">
                        <li style="margin-bottom: 8px;">Найдите добавленный профиль</li>
                        <li style="margin-bottom: 8px;">Нажмите на переключатель или кнопку "Включить"</li>
                        <li style="margin-bottom: 8px;">Дождитесь установления соединения</li>
                    </ol>
                `
            }
        ]
    },
    tv: {
        title: 'Android TV (v2RayTun, Happ)',
        steps: [
            {
                title: 'Шаг 1: Выберите приложение',
                content: `
                    <p>Выберите одно из приложений для Android TV:</p>
                    <ul style="margin: 12px 0; padding-left: 20px;">
                        <li style="margin-bottom: 8px;"><a href="https://play.google.com/store/apps/details?id=com.v2raytun.android" target="_blank" style="color: #4a9eff;">v2RayTun для Android TV</a></li>
                        <li style="margin-bottom: 8px;"><a href="https://play.google.com/store/apps/details?id=com.happproxy" target="_blank" style="color: #4a9eff;">Happ для Android TV</a></li>
                    </ul>
                `
            },
            {
                title: 'Шаг 2: Получите ссылку на подписку',
                content: `
                    <p>В мини-приложении на вашем телефоне:</p>
                    <ol style="margin: 12px 0; padding-left: 20px;">
                        <li style="margin-bottom: 8px;">Нажмите на вкладку "Подписки"</li>
                        <li style="margin-bottom: 8px;">Выберите вашу подписку</li>
                        <li style="margin-bottom: 8px;">Нажмите кнопку "Копировать ссылку"</li>
                    </ol>
                `
            },
            {
                title: 'Шаг 3: Добавьте подписку',
                content: `
                    <p>В VPN-приложении на Android TV:</p>
                    <ol style="margin: 12px 0; padding-left: 20px;">
                        <li style="margin-bottom: 8px;">Нажмите кнопку "+" (добавить)</li>
                        <li style="margin-bottom: 8px;">Выберите "Добавить из буфера обмена"</li>
                        <li style="margin-bottom: 8px;">Подписка будет автоматически импортирована</li>
                    </ol>
                `
            },
            {
                title: 'Шаг 4: Включите VPN',
                content: `
                    <p>После импорта:</p>
                    <ol style="margin: 12px 0; padding-left: 20px;">
                        <li style="margin-bottom: 8px;">Выберите добавленный профиль</li>
                        <li style="margin-bottom: 8px;">Нажмите на переключатель или кнопку "Включить"</li>
                        <li style="margin-bottom: 8px;">Дождитесь установления соединения</li>
                    </ol>
                `
            }
        ]
    },
    faq: {
        title: 'FAQ - Частые вопросы',
        steps: [
            {
                title: 'VPN не подключается',
                content: `
                    <p>Если VPN не подключается, попробуйте следующее:</p>
                    <ul style="margin: 12px 0; padding-left: 20px;">
                        <li style="margin-bottom: 8px;">Проверьте подключение к интернету</li>
                        <li style="margin-bottom: 8px;">Перезапустите VPN-приложение</li>
                        <li style="margin-bottom: 8px;">Перезагрузите устройство</li>
                        <li style="margin-bottom: 8px;">Скопируйте ссылку на подписку заново</li>
                        <li style="margin-bottom: 8px;">Убедитесь, что никому не передавали свою ссылку</li>
                        <li style="margin-bottom: 8px;">Отключите другие VPN-приложения</li>
                    </ul>
                `
            },
            {
                title: 'Не импортируется ссылка',
                content: `
                    <p>Если ссылка не импортируется:</p>
                    <ul style="margin: 12px 0; padding-left: 20px;">
                        <li style="margin-bottom: 8px;">Скопируйте ссылку полностью, от начала до конца</li>
                        <li style="margin-bottom: 8px;">Убедитесь, что ссылка начинается с "https://"</li>
                        <li style="margin-bottom: 8px;">Обновите VPN-приложение до последней версии</li>
                        <li style="margin-bottom: 8px;">Попробуйте скопировать ссылку еще раз</li>
                    </ul>
                `
            },
            {
                title: 'Мультисерверность',
                content: `
                    <p>Ваша подписка включает все доступные серверы сразу. Вы можете переключаться между серверами в настройках VPN-приложения.</p>
                `
            },
            {
                title: 'Нужна помощь?',
                content: `
                    <p>Если у вас возникли проблемы или вопросы, обратитесь в поддержку через Telegram.</p>
                `
            }
        ]
    }
};

// Функции для работы с модальным окном инструкций
function showInstructionModal(platform) {
    currentInstructionPlatform = platform;
    currentInstructionStep = 0;
    
    const instruction = instructionSteps[platform];
    if (!instruction) return;
    
    currentInstructionSteps = instruction.steps;
    
    document.getElementById('instruction-modal-title').textContent = instruction.title;
    document.getElementById('instruction-modal').style.display = 'flex';
    
    renderInstructionStep();
}

function renderInstructionStep() {
    const container = document.getElementById('instruction-steps-container');
    const step = currentInstructionSteps[currentInstructionStep];
    
    if (!step) return;
    
    container.innerHTML = `
        <div style="background: #222; border-radius: 12px; padding: 24px; margin-bottom: 16px;">
            <h3 style="color: #4a9eff; margin-bottom: 16px; font-size: 18px;">${step.title}</h3>
            <div style="color: #e0e0e0; line-height: 1.8; font-size: 15px;">
                ${step.content}
            </div>
        </div>
    `;
    
    // Обновляем индикатор шага
    document.getElementById('instruction-step-indicator').textContent = 
        `Шаг ${currentInstructionStep + 1} из ${currentInstructionSteps.length}`;
    
    // Управление кнопками
    const prevBtn = document.getElementById('instruction-prev-btn');
    const nextBtn = document.getElementById('instruction-next-btn');
    const closeBtn = document.getElementById('instruction-close-btn');
    
    prevBtn.style.display = currentInstructionStep > 0 ? 'block' : 'none';
    
    if (currentInstructionStep === currentInstructionSteps.length - 1) {
        nextBtn.style.display = 'none';
        closeBtn.style.display = 'block';
    } else {
        nextBtn.style.display = 'block';
        closeBtn.style.display = 'none';
    }
}

function nextInstructionStep() {
    if (currentInstructionStep < currentInstructionSteps.length - 1) {
        currentInstructionStep++;
        renderInstructionStep();
    }
}

function prevInstructionStep() {
    if (currentInstructionStep > 0) {
        currentInstructionStep--;
        renderInstructionStep();
    }
}

function closeInstructionModal() {
    document.getElementById('instruction-modal').style.display = 'none';
    currentInstructionPlatform = null;
    currentInstructionStep = 0;
    currentInstructionSteps = [];
}

// Функция для перемещения индикатора к активной кнопке
function moveNavIndicator(index) {
    const indicator = document.querySelector('.nav-glass-indicator');
    const navItems = document.querySelectorAll('.nav-item');
    const nav = document.querySelector('.bottom-nav');
    
    if (!indicator || !navItems[index] || !nav) return;
    
    const targetItem = navItems[index];
    
    const calculateAndSetPosition = () => {
        const navRect = nav.getBoundingClientRect();
        const itemRect = targetItem.getBoundingClientRect();
        
        // Фиксированная ширина индикатора из CSS
        const indicatorWidth = 56; 
        
        // Находим центр кнопки относительно навбара
        const itemCenterX = itemRect.left - navRect.left + (itemRect.width / 2);
        
        // Вычисляем позицию X для центрирования индикатора
        const x = itemCenterX - (indicatorWidth / 2);
        
        // Применяем позицию
        indicator.style.transform = `translateX(${x}px) translateY(-50%)`;
        
        // Сохраняем индекс для обновлений при ресайзе
        window.currentNavIndex = index;
    };
    
    requestAnimationFrame(calculateAndSetPosition);
}

// Добавляем обработчик изменения размера окна для навбара
window.addEventListener('resize', () => {
    if (typeof window.currentNavIndex !== 'undefined') {
        moveNavIndicator(window.currentNavIndex);
    }
});

// Инициализация навигации с индикатором
function initNavIndicator() {
    const navItems = document.querySelectorAll('.nav-item');
    const indicator = document.querySelector('.nav-glass-indicator');
    const nav = document.querySelector('.bottom-nav');
    
    if (!indicator || !nav) return;
    
    // Устанавливаем начальную позицию для активной кнопки
    const activeItem = document.querySelector('.nav-item.active');
    if (activeItem) {
        const activeIndex = Array.from(navItems).indexOf(activeItem);
        if (activeIndex >= 0) {
            moveNavIndicator(activeIndex);
        }
    } else {
        // Если нет активной кнопки, устанавливаем начальную позицию
        moveNavIndicator(0);
    }
    
    // Добавляем обработчики для перетаскивания
    let isDragging = false;
    let startX = 0;
    let startTransform = 0;
    
    nav.addEventListener('touchstart', (e) => {
        const touch = e.touches[0];
        const navRect = nav.getBoundingClientRect();
        const touchX = touch.clientX - navRect.left;
        
        // Проверяем, находится ли касание в области индикатора
        const indicatorRect = indicator.getBoundingClientRect();
        const indicatorLeft = indicatorRect.left - navRect.left;
        const indicatorRight = indicatorRect.right - navRect.left;
        
        if (touchX >= indicatorLeft && touchX <= indicatorRight) {
            isDragging = true;
            startX = touchX;
            const transform = indicator.style.transform;
            startTransform = transform ? parseFloat(transform.match(/translateX\(([^)]+)\)/)?.[1] || '0') : 0;
            indicator.style.transition = 'none';
            indicator.classList.add('moving');
        }
    });
    
    nav.addEventListener('touchmove', (e) => {
        if (!isDragging) return;
        
        e.preventDefault();
        const touch = e.touches[0];
        const navRect = nav.getBoundingClientRect();
        const touchX = touch.clientX - navRect.left;
        const deltaX = touchX - startX;
        const newTransform = startTransform + deltaX;
        
        // Ограничиваем перемещение в пределах бара
        const navWidth = nav.offsetWidth;
        const itemWidth = navWidth / navItems.length;
        const minX = 0;
        const maxX = navWidth - itemWidth;
        
        const clampedX = Math.max(minX, Math.min(maxX, newTransform));
        
        // Обновляем ширину индикатора при перетаскивании на основе ближайшей иконки
        const indicatorPadding = 8; // Отступ от краев островка
        const currentItemIndex = Math.round(clampedX / itemWidth);
        if (currentItemIndex >= 0 && currentItemIndex < navItems.length) {
            const currentItem = navItems[currentItemIndex];
            const currentItemRect = currentItem.getBoundingClientRect();
            indicator.style.width = `${currentItemRect.width - (indicatorPadding * 2)}px`;
        }
        
        // Добавляем отступ к позиции при перетаскивании
        const adjustedX = clampedX + indicatorPadding;
        indicator.style.transform = `translateX(${adjustedX}px) translateY(-50%) scale(1.05)`;
    });
    
    nav.addEventListener('touchend', (e) => {
        if (!isDragging) return;
        
        isDragging = false;
        indicator.style.transition = 'transform 0.3s cubic-bezier(0.4, 0, 0.2, 1), width 0.3s cubic-bezier(0.4, 0, 0.2, 1), scale 0.2s cubic-bezier(0.4, 0, 0.2, 1)';
        
        // "Примагничиваем" к ближайшей кнопке
        const navRect = nav.getBoundingClientRect();
        const touchX = e.changedTouches[0].clientX - navRect.left;
        const navWidth = nav.offsetWidth;
        const itemWidth = navWidth / navItems.length;
        const nearestIndex = Math.round(touchX / itemWidth);
        const clampedIndex = Math.max(0, Math.min(navItems.length - 1, nearestIndex));
        
        moveNavIndicator(clampedIndex);
        
        // Убираем класс moving после завершения анимации (moveNavIndicator уже добавит его снова)
        setTimeout(() => {
            indicator.classList.remove('moving');
        }, 400);
        
        // Активируем соответствующую кнопку
        const targetButton = navItems[clampedIndex];
        if (targetButton && targetButton.dataset && targetButton.dataset.page) {
            showPage(targetButton.dataset.page);
        } else if (targetButton && targetButton.id === 'admin-nav-button') {
            showPage('admin-stats');
        }
    });
    
    // Обработка кликов на кнопки
    navItems.forEach((item, index) => {
        item.addEventListener('click', () => {
            moveNavIndicator(index);
        });
    });
    
    // Эффект "жидкого стекла" при удержании
    let pressTimer = null;
    let isPressing = false;
    
    // Обработчики для десктопа (mouse)
    nav.addEventListener('mousedown', (e) => {
        const target = e.target.closest('.nav-item');
        if (!target) return;
        
        const indicatorRect = indicator.getBoundingClientRect();
        const navRect = nav.getBoundingClientRect();
        const mouseX = e.clientX - navRect.left;
        
        // Проверяем, находится ли клик в области индикатора
        const indicatorLeft = indicatorRect.left - navRect.left;
        const indicatorRight = indicatorRect.right - navRect.left;
        
        if (mouseX >= indicatorLeft && mouseX <= indicatorRight) {
            isPressing = true;
            pressTimer = setTimeout(() => {
                if (isPressing) {
                    indicator.classList.add('pressing');
                }
            }, 100); // Задержка перед активацией эффекта
        }
    });
    
    nav.addEventListener('mouseup', () => {
        if (pressTimer) {
            clearTimeout(pressTimer);
            pressTimer = null;
        }
        if (isPressing) {
            indicator.classList.remove('pressing');
            isPressing = false;
        }
    });
    
    nav.addEventListener('mouseleave', () => {
        if (pressTimer) {
            clearTimeout(pressTimer);
            pressTimer = null;
        }
        if (isPressing) {
            indicator.classList.remove('pressing');
            isPressing = false;
        }
    });
    
    // Обработчики для мобильных (touch)
    let touchPressTimer = null;
    let isTouchPressing = false;
    
    nav.addEventListener('touchstart', (e) => {
        const touch = e.touches[0];
        const navRect = nav.getBoundingClientRect();
        const touchX = touch.clientX - navRect.left;
        
        const indicatorRect = indicator.getBoundingClientRect();
        const indicatorLeft = indicatorRect.left - navRect.left;
        const indicatorRight = indicatorRect.right - navRect.left;
        
        if (touchX >= indicatorLeft && touchX <= indicatorRight && !isDragging) {
            isTouchPressing = true;
            touchPressTimer = setTimeout(() => {
                if (isTouchPressing) {
                    indicator.classList.add('pressing');
                }
            }, 150); // Немного больше задержка для touch
        }
    }, { passive: true });
    
    nav.addEventListener('touchend', () => {
        if (touchPressTimer) {
            clearTimeout(touchPressTimer);
            touchPressTimer = null;
        }
        if (isTouchPressing) {
            indicator.classList.remove('pressing');
            isTouchPressing = false;
        }
    }, { passive: true });
    
    nav.addEventListener('touchcancel', () => {
        if (touchPressTimer) {
            clearTimeout(touchPressTimer);
            touchPressTimer = null;
        }
        if (isTouchPressing) {
            indicator.classList.remove('pressing');
            isTouchPressing = false;
        }
    }, { passive: true });
}

// === УПРАВЛЕНИЕ СЕРВЕРАМИ И ГРУППАМИ (АДМИН) ===

let currentAdminGroups = [];
let currentAdminServers = [];
let currentSelectedGroupId = null;

// Загрузка страницы управления серверами
async function loadServerManagement() {
    const loadingEl = document.getElementById('admin-server-management-loading');
    const contentEl = document.getElementById('admin-server-management-content');
    
    if (loadingEl) loadingEl.style.display = 'block';
    if (contentEl) contentEl.style.display = 'none';

    try {
        await loadServerGroups();
        if (loadingEl) loadingEl.style.display = 'none';
        if (contentEl) contentEl.style.display = 'block';
    } catch (err) {
        console.error('Ошибка загрузки управления серверами:', err);
        if (loadingEl) loadingEl.style.display = 'none';
        alert('Ошибка при загрузке данных: ' + err.message);
    }
}

// Загрузка групп серверов
async function loadServerGroups() {
    console.log('Загрузка групп серверов...');
    const listEl = document.getElementById('admin-server-groups-list');
    
    try {
        const response = await apiFetch('/api/admin/server-groups', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ action: 'list' })
        });
        
        if (!response.ok) {
            throw new Error('Ошибка сети при получении групп');
        }
        
        const result = await response.json();
        console.log('Результат загрузки групп:', result);
        if (result.success) {
            currentAdminGroups = result.groups || [];
            const stats = result.stats || [];
            renderServerGroups(currentAdminGroups, stats);
        } else {
            throw new Error(result.error || 'Ошибка API');
        }
    } catch (err) {
        console.error('Ошибка в loadServerGroups:', err);
        if (listEl) {
            listEl.innerHTML = `<p class="error-text" style="color: #ff4444; text-align: center; padding: 20px;">Ошибка: ${err.message}</p>`;
        }
        throw err;
    }
}

// Отрисовка списка групп
function renderServerGroups(groups, stats) {
    console.log('Отрисовка групп:', groups, stats);
    const listEl = document.getElementById('admin-server-groups-list');
    if (!listEl) return;
    
    if (!groups || groups.length === 0) {
        listEl.innerHTML = '<p class="empty-hint" style="text-align: center; padding: 20px; color: #999;">Нет созданных групп серверов</p>';
        return;
    }

    listEl.innerHTML = groups.map(group => {
        const groupStats = (stats || []).find(s => s.id === group.id) || {};
        const safeName = escapeHtml(group.name);
        const isActive = currentSelectedGroupId === group.id;
        return `
            <div id="group-card-${group.id}" class="admin-user-card group-card ${isActive ? 'active' : ''}" onclick="loadServersInGroup(${group.id}, '${safeName.replace(/'/g, "\\'")}')">
                <div class="card-content-wrapper">
                    <div class="card-main-info">
                        <div class="card-title-row">
                            <span class="card-title">${safeName}</span>
                            <div class="card-badges">
                                ${group.is_default ? '<span class="badge-default">По умолчанию</span>' : ''}
                                ${!group.is_active ? '<span class="badge-inactive">Неактивна</span>' : ''}
                            </div>
                        </div>
                        <div class="card-description">${escapeHtml(group.description || 'Нет описания')}</div>
                        <div class="card-stats-row">
                            <span>Подписок: <b>${groupStats.active_subscriptions || 0}</b></span>
                            <span>Серверов: <b>${groupStats.active_servers || 0}</b></span>
                        </div>
                    </div>
                    <button class="btn-secondary card-action-btn" onclick="event.stopPropagation(); editServerGroup(${group.id})">Изменить</button>
                </div>
            </div>
        `;
    }).join('');
}

// Скрыть детали группы
function hideGroupDetail() {
    currentSelectedGroupId = null;
    document.getElementById('admin-group-detail').style.display = 'none';
    // Снимаем подсветку со всех карточек
    document.querySelectorAll('.group-card').forEach(card => card.classList.remove('active'));
}

// Показать модалку добавления группы
function showAddServerGroupModal() {
    console.log('Открытие модалки добавления группы');
    const titleEl = document.getElementById('server-group-modal-title');
    const idEl = document.getElementById('group-id-input');
    const nameEl = document.getElementById('group-name-input');
    const descEl = document.getElementById('group-desc-input');
    const defaultEl = document.getElementById('group-default-input');

    if (titleEl) titleEl.innerText = 'Добавить группу';
    if (idEl) idEl.value = '';
    if (nameEl) nameEl.value = '';
    if (descEl) descEl.value = '';
    if (defaultEl) defaultEl.checked = false;
    
    showModal('server-group-modal');
}

// Показать модалку редактирования группы
function editServerGroup(groupId) {
    const group = currentAdminGroups.find(g => g.id === groupId);
    if (!group) return;

    document.getElementById('server-group-modal-title').innerText = 'Редактировать группу';
    document.getElementById('group-id-input').value = group.id;
    document.getElementById('group-name-input').value = group.name;
    document.getElementById('group-desc-input').value = group.description || '';
    document.getElementById('group-default-input').checked = !!group.is_default;
    showModal('server-group-modal');
}

// Сохранение группы
async function saveServerGroup(event) {
    event.preventDefault();
    const id = document.getElementById('group-id-input').value;
    const name = document.getElementById('group-name-input').value;
    const description = document.getElementById('group-desc-input').value;
    const is_default = document.getElementById('group-default-input').checked ? 1 : 0;

    try {
        const url = id ? '/api/admin/server-group/update' : '/api/admin/server-groups';
        const body = {
            name, description, is_default,
            action: id ? undefined : 'add',
            id: id || undefined
        };

        const response = await apiFetch(url, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify(body)
        });
        const result = await response.json();
        if (result.success) {
            closeModal('server-group-modal');
            loadServerGroups();
        } else {
            alert('Ошибка: ' + result.error);
        }
    } catch (err) {
        console.error('Ошибка сохранения группы:', err);
        alert('Ошибка при сохранении');
    }
}

// Загрузка серверов в группе
async function loadServersInGroup(groupId, groupName) {
    // Если нажали на уже активную группу - скрываем её
    if (currentSelectedGroupId === groupId) {
        hideGroupDetail();
        return;
    }

    currentSelectedGroupId = groupId;
    
    // Подсветка активной карточки
    document.querySelectorAll('.group-card').forEach(card => card.classList.remove('active'));
    const activeCard = document.getElementById(`group-card-${groupId}`);
    if (activeCard) activeCard.classList.add('active');

    document.getElementById('admin-group-detail').style.display = 'block';
    
    const listEl = document.getElementById('admin-servers-in-group-list');
    listEl.innerHTML = '<div class="spinner"></div>';

    try {
        const response = await apiFetch('/api/admin/servers-config', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ action: 'list', group_id: groupId })
        });
        const result = await response.json();
        if (result.success) {
            currentAdminServers = result.servers;
            renderServersInGroup(result.servers);
            // Прокрутка к списку серверов
            document.getElementById('admin-group-detail').scrollIntoView({ behavior: 'smooth' });
        }
    } catch (err) {
        console.error('Ошибка загрузки серверов:', err);
        listEl.innerHTML = '<p class="error-text">Ошибка загрузки</p>';
    }
}

// Отрисовка списка серверов
function renderServersInGroup(servers) {
    const listEl = document.getElementById('admin-servers-in-group-list');
    if (!servers || servers.length === 0) {
        listEl.innerHTML = '<p class="empty-hint" style="text-align: center; padding: 20px; color: #999;">В этой группе пока нет серверов</p>';
        return;
    }

    listEl.innerHTML = servers.map(server => `
        <div class="admin-user-card server-card">
            <div class="card-content-wrapper">
                <div class="card-main-info">
                    <div class="card-title">${server.display_name || server.name}</div>
                    <div class="card-description">${server.host} | ${server.name}</div>
                </div>
                <div class="card-actions-row">
                    <button type="button" class="btn-secondary server-action-btn" onclick="event.stopPropagation(); editServerConfig(${server.id})" aria-label="Изменить сервер">Изменить</button>
                    <button type="button" class="btn-danger server-action-btn" onclick="event.stopPropagation(); deleteServerConfig(${server.id})" aria-label="Удалить сервер">Удалить</button>
                </div>
            </div>
        </div>
    `).join('');
}

// Показать модалку добавления сервера
function showAddServerConfigModal() {
    document.getElementById('server-config-modal-title').innerText = 'Добавить сервер';
    document.getElementById('server-id-input').value = '';
    document.getElementById('server-name-input').value = '';
    document.getElementById('server-display-input').value = '';
    document.getElementById('server-host-input').value = '';
    document.getElementById('server-login-input').value = '';
    document.getElementById('server-pass-input').value = '';
    document.getElementById('server-vpnhost-input').value = '';
    document.getElementById('server-subscription-port-input').value = '2096';
    document.getElementById('server-subscription-url-input').value = '';
    document.getElementById('server-client-flow-input').value = '';
    document.getElementById('server-map-label-input').value = '';
    document.getElementById('server-lat-input').value = '';
    document.getElementById('server-lng-input').value = '';
    showModal('server-config-modal');
}

// Показать модалку редактирования сервера
function editServerConfig(serverId) {
    const server = currentAdminServers.find(s => s.id === serverId);
    if (!server) return;

    document.getElementById('server-config-modal-title').innerText = 'Редактировать сервер';
    document.getElementById('server-id-input').value = server.id;
    document.getElementById('server-name-input').value = server.name;
    document.getElementById('server-display-input').value = server.display_name || '';
    document.getElementById('server-host-input').value = server.host;
    document.getElementById('server-login-input').value = server.login;
    document.getElementById('server-pass-input').value = server.password;
    document.getElementById('server-vpnhost-input').value = server.vpn_host || '';
    document.getElementById('server-subscription-port-input').value = server.subscription_port != null ? String(server.subscription_port) : '2096';
    document.getElementById('server-subscription-url-input').value = server.subscription_url || '';
    document.getElementById('server-client-flow-input').value = server.client_flow || '';
    document.getElementById('server-map-label-input').value = server.map_label || '';
    document.getElementById('server-lat-input').value = server.lat || '';
    document.getElementById('server-lng-input').value = server.lng || '';
    showModal('server-config-modal');
}

// Сохранение сервера
async function saveServerConfig(event) {
    event.preventDefault();
    const id = document.getElementById('server-id-input').value;
    const portVal = document.getElementById('server-subscription-port-input').value;
    const body = {
        group_id: currentSelectedGroupId,
        name: document.getElementById('server-name-input').value,
        display_name: document.getElementById('server-display-input').value,
        host: document.getElementById('server-host-input').value,
        login: document.getElementById('server-login-input').value,
        password: document.getElementById('server-pass-input').value,
        vpn_host: document.getElementById('server-vpnhost-input').value || null,
        subscription_port: portVal ? parseInt(portVal, 10) : null,
        subscription_url: document.getElementById('server-subscription-url-input').value || null,
        client_flow: document.getElementById('server-client-flow-input').value?.trim() || null,
        map_label: document.getElementById('server-map-label-input').value?.trim() || null,
        lat: document.getElementById('server-lat-input').value ? parseFloat(document.getElementById('server-lat-input').value) : null,
        lng: document.getElementById('server-lng-input').value ? parseFloat(document.getElementById('server-lng-input').value) : null,
        id: id || undefined,
        action: id ? undefined : 'add'
    };

    try {
        const url = id ? '/api/admin/server-config/update' : '/api/admin/servers-config';
        const response = await apiFetch(url, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify(body)
        });
        const result = await response.json();
        if (result.success) {
            closeModal('server-config-modal');
            const group = currentAdminGroups.find(g => g.id === currentSelectedGroupId);
            loadServersInGroup(currentSelectedGroupId, group.name);
            if (result.client_flow_changed && result.server_id) {
                if (confirm('Обновить flow у существующих клиентов на этом сервере?')) {
                    try {
                        const syncRes = await apiFetch('/api/admin/server-config/sync-flow', {
                            method: 'POST',
                            headers: { 'Content-Type': 'application/json' },
                            body: JSON.stringify({ server_id: result.server_id })
                        });
                        const syncData = await syncRes.json();
                        if (syncData.success) {
                            alert(`Обновлено клиентов: ${syncData.updated}${syncData.errors?.length ? '. Ошибки: ' + syncData.errors.slice(0, 3).join('; ') : ''}`);
                        } else {
                            alert('Ошибка синхронизации flow: ' + (syncData.error || 'unknown'));
                        }
                    } catch (e) {
                        console.error('sync-flow', e);
                        alert('Ошибка при синхронизации flow');
                    }
                }
            }
        } else {
            alert('Ошибка: ' + result.error);
        }
    } catch (err) {
        console.error('Ошибка сохранения сервера:', err);
        alert('Ошибка при сохранении');
    }
}

// Удаление сервера
async function deleteServerConfig(serverId) {
    if (!confirm('Вы уверены, что хотите удалить конфигурацию сервера? Это не удалит клиентов с самого сервера, но бот перестанет его использовать.')) return;

    try {
        const response = await apiFetch('/api/admin/server-config/delete', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ id: serverId })
        });
        const result = await response.json();
        if (result.success) {
            const group = currentAdminGroups.find(g => g.id === currentSelectedGroupId);
            loadServersInGroup(currentSelectedGroupId, group.name);
        } else {
            alert('Ошибка: ' + result.error);
        }
    } catch (err) {
        console.error('Ошибка удаления сервера:', err);
        alert('Ошибка при удалении');
    }
}

// Обновляем showPage для поддержки новой страницы
const originalShowPage = showPage;
showPage = function(pageName) {
    originalShowPage(pageName);
    if (pageName === 'admin-server-management') {
        loadServerManagement();
    }
};

// Синхронизация всех серверов
async function syncAllServers() {
    if (!confirm('Выполнить полную синхронизацию всех подписок с серверами? Это может занять некоторое время.')) return;
    
    tg.MainButton.setText('СИНХРОНИЗАЦИЯ...');
    tg.MainButton.show();
    tg.MainButton.disable();

    try {
        const response = await apiFetch('/api/admin/sync-all', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' }
        });
        const result = await response.json();
        if (result.success) {
            alert('Синхронизация завершена!\n' + 
                  'Проверено подписок: ' + result.stats.subscriptions_checked + '\n' +
                  'Создано клиентов: ' + result.stats.total_clients_created);
            loadServerGroups();
        } else {
            alert('Ошибка: ' + result.error);
        }
    } catch (err) {
        console.error('Ошибка синхронизации:', err);
        alert('Ошибка при выполнении синхронизации');
    } finally {
        tg.MainButton.hide();
    }
}
