// Telegram Web App API
const tg = window.Telegram.WebApp;

// Инициализация Telegram Web App
tg.ready();
tg.expand();

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
    
    // Активируем нужный пункт навигации (если это не детальная страница)
    if (pageName !== 'subscription-detail' && pageName !== 'admin-user-detail' && pageName !== 'admin-subscription-edit') {
        const navItems = document.querySelectorAll('.nav-item');
        if (pageName === 'subscriptions') {
            navItems[0]?.classList.add('active');
        } else if (pageName === 'servers') {
            navItems[1]?.classList.add('active');
        } else if (pageName === 'about') {
            navItems[2]?.classList.add('active');
        } else if (pageName === 'admin-stats' && document.getElementById('admin-nav-button')) {
            document.getElementById('admin-nav-button').classList.add('active');
        } else if (pageName === 'admin-users' && document.getElementById('admin-nav-button')) {
            document.getElementById('admin-nav-button').classList.add('active');
        }
    }
    
    currentPage = pageName;
    
    // Загружаем данные для страницы
    if (pageName === 'subscriptions') {
        loadSubscriptions();
    } else if (pageName === 'servers') {
        loadServers();
    } else if (pageName === 'admin-users') {
        loadAdminUsers(1, currentAdminUserSearch);
    } else if (pageName === 'admin-stats') {
        loadAdminStats();
    }
}

// Функция показа детальной информации о подписке
function showSubscriptionDetail(sub) {
    const pageEl = document.getElementById('page-subscription-detail');
    const nameEl = document.getElementById('detail-subscription-name');
    const contentEl = document.getElementById('subscription-detail-content');
    
    nameEl.textContent = escapeHtml(sub.name);
    
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
                    <div class="detail-info-value">${escapeHtml(sub.name)}</div>
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
            
            ${sub.status === 'active' ? `
                <div class="detail-actions">
                    <button class="action-button" onclick="copySubscriptionLink('${sub.token}')">
                        Копировать ссылку подписки
                    </button>
                </div>
            ` : ''}
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
    const subscriptionsListEl = document.getElementById('subscriptions-list');
    
    // Показываем загрузку
    loadingEl.style.display = 'block';
    errorEl.style.display = 'none';
    emptyEl.style.display = 'none';
    subscriptionsEl.style.display = 'none';
    
    try {
        // Получаем initData от Telegram
        const initData = tg.initData;
        if (!initData) {
            throw new Error('initData не доступен');
        }
        
        // Запрашиваем подписки через API
        const response = await fetch(`/api/subscriptions?initData=${encodeURIComponent(initData)}`);
        
        if (!response.ok) {
            throw new Error(`HTTP error! status: ${response.status}`);
        }
        
        const data = await response.json();
        
        if (!data.success) {
            throw new Error(data.error || 'Ошибка получения данных');
        }
        
        // Скрываем загрузку
        loadingEl.style.display = 'none';
        
        // Обновляем статистику
        document.getElementById('total-count').textContent = data.total || 0;
        document.getElementById('active-count').textContent = data.active || 0;
        
        if (!data.subscriptions || data.subscriptions.length === 0) {
            // Нет подписок
            emptyEl.style.display = 'block';
        } else {
            // Показываем подписки
            subscriptionsEl.style.display = 'block';
            renderSubscriptions(data.subscriptions);
        }
        
    } catch (error) {
        console.error('Ошибка загрузки подписок:', error);
        loadingEl.style.display = 'none';
        errorEl.style.display = 'block';
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
    
    loadingEl.style.display = 'block';
    errorEl.style.display = 'none';
    contentEl.style.display = 'none';
    
    try {
        const initData = tg.initData;
        if (!initData) {
            throw new Error('initData не доступен');
        }
        
        const response = await fetch(`/api/servers?initData=${encodeURIComponent(initData)}`);
        
        if (!response.ok) {
            throw new Error(`HTTP error! status: ${response.status}`);
        }
        
        const data = await response.json();
        
        if (!data.success) {
            throw new Error(data.error || 'Ошибка получения данных');
        }
        
        loadingEl.style.display = 'none';
        contentEl.style.display = 'block';
        
        // Загружаем карту серверов
        loadServerMap();
        
        if (!data.servers || data.servers.length === 0) {
            listEl.innerHTML = '<div class="empty"><p>Серверы не найдены</p></div>';
        } else {
            renderServers(data.servers);
        }
        
    } catch (error) {
        console.error('Ошибка загрузки серверов:', error);
        loadingEl.style.display = 'none';
        errorEl.style.display = 'block';
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
        this.centerX = canvas.width / 2;
        this.centerY = canvas.height / 2;
        // Увеличиваем радиус для более реалистичного отображения расстояний между точками
        this.radius = Math.min(canvas.width, canvas.height) * 0.5;
        
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
                this.zoom = Math.max(0.5, Math.min(3, this.zoom)); // Увеличиваем максимум до 3x
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
            this.zoom = Math.max(0.5, Math.min(2, this.zoom));
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
        
        // Горизонтальное вращение (влево-вправо) - инвертируем направление
        this.rotation -= deltaX * 0.01;
        
        // Вертикальное вращение (вверх-вниз) - ограничиваем угол наклона
        this.pitch += deltaY * 0.01;
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
        const x = this.centerX + scaledRadius * x3d;
        const y = this.centerY - scaledRadius * yRotated; // Инвертируем Y для правильной ориентации
        
        // Проверяем видимость (точка видна, если она на передней стороне сферы)
        // Учитываем увеличенный радиус при зуме для проверки границ
        const maxDistance = Math.max(this.canvas.width, this.canvas.height) * 0.6 * this.zoom;
        const visible = zRotated >= 0 && 
                       Math.abs(x - this.centerX) < maxDistance && 
                       Math.abs(y - this.centerY) < maxDistance;
        
        return { x, y, visible };
    }
    
    // Упрощенные границы основных стран/регионов
    drawCountryBorders(ctx) {
        ctx.strokeStyle = '#555';
        ctx.lineWidth = 1.5 / this.zoom;
        ctx.globalAlpha = 0.7;
        
        // Европа - упрощенные границы
        const europeBorders = [
            // Западная Европа
            [[50, -10], [50, 5], [51, 8], [52, 10], [53, 8], [54, 6], [55, 2], [56, -2], [57, -5], [58, -8], [60, -10], [62, -8], [65, -5], [70, 0], [72, 10], [71, 20], [70, 25], [68, 30], [65, 32], [60, 30], [55, 25], [50, 20], [48, 15], [47, 10], [46, 5], [45, 0], [44, -5], [45, -10], [50, -10]],
            // Восточная Европа / Россия
            [[60, 20], [60, 30], [65, 35], [70, 40], [75, 45], [80, 50], [75, 60], [70, 70], [65, 80], [60, 100], [55, 110], [50, 120], [45, 130], [40, 140], [45, 150], [50, 160], [55, 170], [60, 180], [60, -180], [60, -170], [60, -160], [60, -150], [60, -140], [60, -130], [60, -120], [60, -110], [60, -100], [60, -90], [60, -80], [60, -70], [60, -60], [60, -50], [60, -40], [60, -30], [60, -20], [60, -10], [60, 0], [60, 10], [60, 20]]
        ];
        
        // Азия - упрощенные границы
        const asiaBorders = [
            [[30, 100], [35, 110], [40, 120], [45, 130], [50, 140], [45, 150], [40, 160], [35, 170], [30, 180], [30, -180], [30, -170], [30, -160], [30, -150], [30, -140], [30, -130], [30, -120], [30, -110], [30, -100], [30, -90], [30, -80], [30, -70], [30, -60], [30, -50], [30, -40], [30, -30], [30, -20], [30, -10], [30, 0], [30, 10], [30, 20], [30, 30], [30, 40], [30, 50], [30, 60], [30, 70], [30, 80], [30, 90], [30, 100]]
        ];
        
        // Северная Америка
        const northAmericaBorders = [
            [[70, -170], [70, -160], [70, -150], [70, -140], [70, -130], [70, -120], [70, -110], [70, -100], [70, -90], [70, -80], [70, -70], [65, -60], [60, -50], [55, -40], [50, -30], [45, -20], [40, -10], [35, 0], [30, 10], [25, 20], [20, 30], [15, 40], [20, 50], [25, 60], [30, 70], [35, 80], [40, 90], [45, 100], [50, 110], [55, 120], [60, 130], [65, 140], [70, 150], [75, 160], [80, 170], [75, 180], [70, -180], [70, -170]]
        ];
        
        // Южная Америка
        const southAmericaBorders = [
            [[10, -80], [5, -70], [0, -60], [-5, -50], [-10, -40], [-15, -30], [-20, -20], [-25, -10], [-30, 0], [-35, 10], [-40, 20], [-45, 30], [-50, 40], [-55, 50], [-60, 60], [-55, 70], [-50, 80], [-45, 90], [-40, 100], [-35, 110], [-30, 120], [-25, 130], [-20, 140], [-15, 150], [-10, 160], [-5, 170], [0, 180], [5, -180], [10, -170], [10, -160], [10, -150], [10, -140], [10, -130], [10, -120], [10, -110], [10, -100], [10, -90], [10, -80]]
        ];
        
        // Африка
        const africaBorders = [
            [[35, -20], [30, -10], [25, 0], [20, 10], [15, 20], [10, 30], [5, 40], [0, 50], [-5, 60], [-10, 70], [-15, 80], [-20, 90], [-25, 100], [-30, 110], [-35, 120], [-30, 130], [-25, 140], [-20, 150], [-15, 160], [-10, 170], [-5, 180], [0, -180], [5, -170], [10, -160], [15, -150], [20, -140], [25, -130], [30, -120], [35, -110], [35, -100], [35, -90], [35, -80], [35, -70], [35, -60], [35, -50], [35, -40], [35, -30], [35, -20]]
        ];
        
        // Объединяем все границы
        const allBorders = [...europeBorders, ...asiaBorders, ...northAmericaBorders, ...southAmericaBorders, ...africaBorders];
        
        // Рисуем границы
        allBorders.forEach(border => {
            ctx.beginPath();
            let firstPoint = true;
            for (let i = 0; i < border.length; i++) {
                const [lat, lng] = border[i];
                const pos = this.latLngToXY(lat, lng);
                if (pos.visible) {
                    if (firstPoint) {
                        ctx.moveTo(pos.x - this.centerX, pos.y - this.centerY);
                        firstPoint = false;
                    } else {
                        ctx.lineTo(pos.x - this.centerX, pos.y - this.centerY);
                    }
                } else {
                    // Если точка невидима, начинаем новую линию
                    firstPoint = true;
                }
            }
            ctx.stroke();
        });
        
        ctx.globalAlpha = 1.0;
    }
    
    draw() {
        const ctx = this.ctx;
        const width = this.canvas.width;
        const height = this.canvas.height;
        
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
        
        // Рисуем границы стран
        this.drawCountryBorders(ctx);
        
        ctx.restore();
        
        // Рисуем точки серверов
        this.servers.forEach(server => {
            if (!server.lat || !server.lng) return;
            
            const pos = this.latLngToXY(server.lat, server.lng);
            if (!pos.visible) return;
            
            // Определяем цвет и размер (фиксированный размер, не масштабируется с зумом)
            let color = '#4CAF50'; // Зеленый
            let size = 6;
            
            if (server.usage_percentage > 50) {
                color = '#FF5722'; // Красный
                size = 10;
            } else if (server.usage_percentage > 25) {
                color = '#FFC107'; // Желтый
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
            
            // Подпись сервера
            const label = server.location || server.display_name || server.server_name || '';
            if (label) {
                // Размер шрифта фиксированный, не масштабируется с зумом
                const fontSize = 10;
                ctx.font = `${fontSize}px Arial, sans-serif`;
                ctx.textAlign = 'left';
                ctx.textBaseline = 'middle';
                
                // Измеряем размер текста
                const textMetrics = ctx.measureText(label);
                const textWidth = textMetrics.width;
                const textHeight = fontSize;
                // Padding фиксированный
                const padding = 4;
                
                // Позиция подписи (справа от точки)
                const labelX = pos.x + size + padding;
                const labelY = pos.y;
                
                // Рисуем полупрозрачный фон для читаемости
                ctx.fillStyle = 'rgba(0, 0, 0, 0.7)';
                ctx.fillRect(
                    Math.floor(labelX - padding),
                    Math.floor(labelY - textHeight / 2 - padding),
                    Math.floor(textWidth + padding * 2),
                    Math.floor(textHeight + padding * 2)
                );
                
                // Рисуем текст
                ctx.fillStyle = '#fff';
                ctx.fillText(label, Math.floor(labelX), Math.floor(labelY));
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
        
        const initData = tg.initData;
        if (!initData) {
            return;
        }
        
        // Запрашиваем данные о серверах
        const response = await fetch(`/api/user/server-usage?initData=${encodeURIComponent(initData)}`);
        
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
        
        // Создаем canvas
        const canvas = document.createElement('canvas');
        canvas.width = mapContainer.clientWidth;
        canvas.height = mapContainer.clientHeight;
        canvas.style.width = '100%';
        canvas.style.height = '100%';
        canvas.style.cursor = 'grab';
        canvas.style.imageRendering = 'pixelated'; // Пиксельный стиль
        mapContainer.appendChild(canvas);
        
        // Обрабатываем изменение размера
        const resizeObserver = new ResizeObserver(() => {
            canvas.width = mapContainer.clientWidth;
            canvas.height = mapContainer.clientHeight;
            if (serverGlobe) {
                serverGlobe.centerX = canvas.width / 2;
                serverGlobe.centerY = canvas.height / 2;
                serverGlobe.radius = Math.min(canvas.width, canvas.height) * 0.5;
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
async function checkAdminAccess() {
    try {
        // Пробуем получить initData разными способами
        let initData = tg.initData;
        
        // Если initData нет, пробуем получить из initDataUnsafe
        if (!initData && tg.initDataUnsafe) {
            // Формируем initData из initDataUnsafe
            const user = tg.initDataUnsafe.user;
            if (user) {
                const authDate = Math.floor(Date.now() / 1000);
                initData = `user=${JSON.stringify(user)}&auth_date=${authDate}`;
            }
        }
        
        if (!initData) {
            console.warn('initData недоступен, пробуем позже...');
            // Пробуем еще раз через небольшую задержку
            setTimeout(async () => {
                await checkAdminAccess();
            }, 1000);
            return false;
        }
        
        console.log('Проверка прав админа, initData:', initData.substring(0, 50) + '...');
        
        const response = await fetch(`/api/admin/check?initData=${encodeURIComponent(initData)}`, {
            method: 'POST',
            headers: {
                'Content-Type': 'application/json'
            },
            body: JSON.stringify({ initData })
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
    adminButton.onclick = () => {
        console.log('Переход в админ-панель');
        showPage('admin-stats');
    };
    adminButton.innerHTML = '<span class="nav-label">Админ</span>';
    
    nav.appendChild(adminButton);
    console.log('Кнопка админ-панели успешно добавлена');
}

// Загрузка списка пользователей
async function loadAdminUsers(page = 1, search = '') {
    try {
        const initData = tg.initData;
        if (!initData) {
            showError('admin-users-error', 'Ошибка авторизации');
            return;
        }
        
        document.getElementById('admin-users-loading').style.display = 'block';
        document.getElementById('admin-users-error').style.display = 'none';
        document.getElementById('admin-users-content').style.display = 'none';
        
        const response = await fetch('/api/admin/users', {
            method: 'POST',
            headers: {
                'Content-Type': 'application/json'
            },
            body: JSON.stringify({
                initData,
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
        const initData = tg.initData;
        if (!initData) {
            alert('Ошибка авторизации');
            return;
        }
        
        previousAdminPage = 'admin-users';
        showPage('admin-user-detail');
        
        document.getElementById('admin-user-detail-loading').style.display = 'block';
        document.getElementById('admin-user-detail-content').innerHTML = '';
        
        const response = await fetch(`/api/admin/user/${userId}`, {
            method: 'POST',
            headers: {
                'Content-Type': 'application/json'
            },
            body: JSON.stringify({ initData })
        });
        
        if (!response.ok) {
            throw new Error('Ошибка загрузки информации о пользователе');
        }
        
        const data = await response.json();
        
        document.getElementById('admin-user-detail-loading').style.display = 'none';
        document.getElementById('admin-user-detail-title').textContent = `Пользователь ${userId}`;
        
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
                <button class="btn-primary" onclick="showCreateSubscriptionForm('${escapeHtml(data.user.user_id)}')" style="width: 100%;">Создать подписку</button>
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
async function showAdminSubscriptionEdit(subId) {
    try {
        const initData = tg.initData;
        if (!initData) {
            alert('Ошибка авторизации');
            return;
        }
        
        previousAdminPage = 'admin-user-detail';
        currentEditingSubscriptionId = subId;
        showPage('admin-subscription-edit');
        
        document.getElementById('admin-subscription-edit-loading').style.display = 'block';
        document.getElementById('admin-subscription-edit-content').style.display = 'none';
        
        const response = await fetch(`/api/admin/subscription/${subId}`, {
            method: 'POST',
            headers: {
                'Content-Type': 'application/json'
            },
            body: JSON.stringify({ initData })
        });
        
        if (!response.ok) {
            throw new Error('Ошибка загрузки подписки');
        }
        
        const data = await response.json();
        const sub = data.subscription;
        
        document.getElementById('admin-subscription-edit-loading').style.display = 'none';
        document.getElementById('admin-subscription-edit-content').style.display = 'block';
        
        // Заполняем форму
        document.getElementById('sub-name').value = sub.name || '';
        document.getElementById('sub-device-limit').value = sub.device_limit || 1;
        document.getElementById('sub-status').value = sub.status || 'active';
        
        // Конвертируем timestamp в datetime-local формат
        const expiresDate = new Date(sub.expires_at * 1000);
        const year = expiresDate.getFullYear();
        const month = String(expiresDate.getMonth() + 1).padStart(2, '0');
        const day = String(expiresDate.getDate()).padStart(2, '0');
        const hours = String(expiresDate.getHours()).padStart(2, '0');
        const minutes = String(expiresDate.getMinutes()).padStart(2, '0');
        document.getElementById('sub-expires-at').value = `${year}-${month}-${day}T${hours}:${minutes}`;
    } catch (error) {
        console.error('Ошибка загрузки подписки:', error);
        document.getElementById('admin-subscription-edit-loading').style.display = 'none';
        alert('Ошибка загрузки подписки');
    }
}

// Сохранение изменений подписки
async function saveSubscriptionChanges(event) {
    event.preventDefault();
    
    try {
        const initData = tg.initData;
        if (!initData) {
            alert('Ошибка авторизации');
            return;
        }
        
        if (!currentEditingSubscriptionId) {
            alert('Ошибка: ID подписки не найден');
            return;
        }
        
        const form = event.target;
        const formData = {
            name: form.name.value,
            device_limit: parseInt(form.device_limit.value),
            status: form.status.value,
            expires_at: Math.floor(new Date(form.expires_at.value).getTime() / 1000)
        };
        
        const response = await fetch(`/api/admin/subscription/${currentEditingSubscriptionId}/update`, {
            method: 'POST',
            headers: {
                'Content-Type': 'application/json'
            },
            body: JSON.stringify({
                initData,
                ...formData
            })
        });
        
        if (!response.ok) {
            const error = await response.json();
            throw new Error(error.error || 'Ошибка сохранения');
        }
        
        const data = await response.json();
        
        alert('Изменения сохранены!');
        
        // Возвращаемся назад
        goBackFromSubscriptionEdit();
    } catch (error) {
        console.error('Ошибка сохранения подписки:', error);
        alert('Ошибка сохранения: ' + error.message);
    }
}

// Синхронизация подписки
async function syncSubscription() {
    try {
        const initData = tg.initData;
        if (!initData) {
            alert('Ошибка авторизации');
            return;
        }
        
        if (!currentEditingSubscriptionId) {
            alert('Ошибка: ID подписки не найден');
            return;
        }
        
        const syncBtn = document.querySelector('.btn-sync');
        syncBtn.disabled = true;
        syncBtn.textContent = 'Синхронизация...';
        
        const response = await fetch(`/api/admin/subscription/${currentEditingSubscriptionId}/sync`, {
            method: 'POST',
            headers: {
                'Content-Type': 'application/json'
            },
            body: JSON.stringify({ initData })
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

// Возврат назад из редактирования подписки
function goBackFromSubscriptionEdit() {
    if (previousAdminPage === 'admin-user-detail') {
        // Нужно перезагрузить информацию о пользователе
        const titleEl = document.getElementById('admin-user-detail-title');
        if (titleEl) {
            const userId = titleEl.textContent.replace('Пользователь ', '');
            showAdminUserDetail(userId);
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

// Создание подписки
async function createSubscription(event) {
    event.preventDefault();
    
    try {
        const initData = tg.initData;
        if (!initData) {
            alert('Ошибка авторизации');
            return;
        }
        
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
        
        const response = await fetch(`/api/admin/user/${currentCreatingSubscriptionUserId}/create-subscription`, {
            method: 'POST',
            headers: {
                'Content-Type': 'application/json'
            },
            body: JSON.stringify({
                initData,
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
        
        // Возвращаемся назад и обновляем информацию о пользователе
        goBackFromCreateSubscription();
    } catch (error) {
        console.error('Ошибка создания подписки:', error);
        alert('Ошибка создания: ' + error.message);
        const form = event.target;
        const submitBtn = form.querySelector('button[type="submit"]');
        submitBtn.disabled = false;
        submitBtn.textContent = 'Создать';
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
        const initData = tg.initData;
        if (!initData) {
            alert('Ошибка авторизации');
            return;
        }
        
        if (!currentEditingSubscriptionId) {
            alert('Ошибка: ID подписки не найден');
            return;
        }
        
        const deleteBtn = document.querySelector('.btn-danger');
        deleteBtn.disabled = true;
        deleteBtn.textContent = 'Удаление...';
        
        const response = await fetch(`/api/admin/subscription/${currentEditingSubscriptionId}/delete`, {
            method: 'POST',
            headers: {
                'Content-Type': 'application/json'
            },
            body: JSON.stringify({
                initData,
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

// Загрузка статистики
async function loadAdminStats() {
    try {
        const initData = tg.initData;
        if (!initData) {
            showError('admin-stats-error', 'Ошибка авторизации');
            return;
        }
        
        document.getElementById('admin-stats-loading').style.display = 'block';
        document.getElementById('admin-stats-error').style.display = 'none';
        document.getElementById('admin-stats-content').style.display = 'none';
        
        const response = await fetch('/api/admin/stats', {
            method: 'POST',
            headers: {
                'Content-Type': 'application/json'
            },
            body: JSON.stringify({ initData })
        });
        
        if (!response.ok) {
            throw new Error('Ошибка загрузки статистики');
        }
        
        const data = await response.json();
        
        document.getElementById('admin-stats-loading').style.display = 'none';
        document.getElementById('admin-stats-content').style.display = 'block';
        
        // Обновляем статистику
        document.getElementById('stats-total-users').textContent = data.stats.users.total || 0;
        document.getElementById('stats-new-users-30d').textContent = data.stats.users.new_30d || 0;
        document.getElementById('stats-active-subs').textContent = data.stats.subscriptions.active || 0;
        document.getElementById('stats-total-subs').textContent = data.stats.subscriptions.total || 0;
        document.getElementById('stats-expired-subs').textContent = data.stats.subscriptions.expired || 0;
        document.getElementById('stats-canceled-subs').textContent = data.stats.subscriptions.canceled || 0;
        document.getElementById('stats-revenue').textContent = (data.stats.payments.revenue || 0).toLocaleString('ru-RU') + ' ₽';
        document.getElementById('stats-succeeded-payments').textContent = data.stats.payments.succeeded || 0;
        
        // Загружаем графики
        await loadUserGrowthChart();
        await loadConversionChart();
        await loadServerLoadChart();
        
        // Запускаем автоматическое обновление графика каждые 2 минуты
        if (serverLoadChartInterval) {
            clearInterval(serverLoadChartInterval);
        }
        serverLoadChartInterval = setInterval(() => {
            if (currentPage === 'admin-stats') {
                loadServerLoadChart();
            }
        }, 2 * 60 * 1000); // 2 минуты
    } catch (error) {
        console.error('Ошибка загрузки статистики:', error);
        document.getElementById('admin-stats-loading').style.display = 'none';
        showError('admin-stats-error', 'Ошибка загрузки статистики');
    }
}

// Переменные для хранения экземпляров графиков
let userGrowthChart = null;
let serverLoadChart = null;
let conversionChart = null;

// Загрузка графика роста пользователей
async function loadUserGrowthChart(days = 30) {
    try {
        const initData = tg.initData;
        if (!initData) {
            return;
        }
        
        const response = await fetch('/api/admin/charts/user-growth', {
            method: 'POST',
            headers: {
                'Content-Type': 'application/json'
            },
            body: JSON.stringify({ initData, days: days })
        });
        
        if (!response.ok) {
            throw new Error('Ошибка загрузки данных графика');
        }
        
        const result = await response.json();
        if (!result.success || !result.data) {
            return;
        }
        
        const ctx = document.getElementById('user-growth-chart');
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
        const cumulative = result.data.map(item => item.cumulative);
        
        // Создаем график
        userGrowthChart = new Chart(ctx, {
            type: 'line',
            data: {
                labels: labels,
                datasets: [
                    {
                        label: 'Новых пользователей',
                        data: counts,
                        borderColor: 'rgb(75, 192, 192)',
                        backgroundColor: 'rgba(75, 192, 192, 0.2)',
                        tension: 0.1,
                        yAxisID: 'y'
                    },
                    {
                        label: 'Всего пользователей (накопительно)',
                        data: cumulative,
                        borderColor: 'rgb(255, 99, 132)',
                        backgroundColor: 'rgba(255, 99, 132, 0.2)',
                        tension: 0.1,
                        yAxisID: 'y1'
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
                        position: 'left',
                        title: {
                            display: true,
                            text: 'Новых пользователей'
                        }
                    },
                    y1: {
                        type: 'linear',
                        display: true,
                        position: 'right',
                        title: {
                            display: true,
                            text: 'Всего пользователей'
                        },
                        grid: {
                            drawOnChartArea: false
                        }
                    }
                }
            }
        });
    } catch (error) {
        console.error('Ошибка загрузки графика роста пользователей:', error);
    }
}

// Загрузка графика конверсии
async function loadConversionChart(days = 30) {
    try {
        const initData = tg.initData;
        if (!initData) {
            return;
        }
        
        const response = await fetch('/api/admin/charts/conversion', {
            method: 'POST',
            headers: {
                'Content-Type': 'application/json'
            },
            body: JSON.stringify({ initData, days: days })
        });
        
        if (!response.ok) {
            throw new Error('Ошибка загрузки данных графика');
        }
        
        const result = await response.json();
        if (!result.success || !result.data) {
            return;
        }
        
        const ctx = document.getElementById('conversion-chart');
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

// Загрузка графика нагрузки на серверы
async function loadServerLoadChart() {
    try {
        const initData = tg.initData;
        if (!initData) {
            return;
        }
        
        const response = await fetch('/api/admin/charts/server-load', {
            method: 'POST',
            headers: {
                'Content-Type': 'application/json'
            },
            body: JSON.stringify({ initData })
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
        
        const ctx = document.getElementById('server-load-chart');
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
            // Показываем сообщение об отсутствии данных, но сохраняем canvas
            const parent = ctx.parentElement;
            const message = document.createElement('p');
            message.style.cssText = 'text-align: center; color: #999; padding: 20px;';
            message.textContent = 'Нет данных о нагрузке на серверы';
            parent.innerHTML = '';
            parent.appendChild(message);
            return;
        }
        
        // Восстанавливаем canvas, если он был удален
        if (!ctx || !ctx.getContext) {
            const parent = document.getElementById('server-load-chart').parentElement;
            parent.innerHTML = '<canvas id="server-load-chart"></canvas>';
            ctx = document.getElementById('server-load-chart');
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
    loadUserGrowthChart(days);
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
                if (chartId === 'user-growth-chart' && userGrowthChart) {
                    userGrowthChart.resize();
                } else if (chartId === 'conversion-chart' && conversionChart) {
                    conversionChart.resize();
                } else if (chartId === 'server-load-chart' && serverLoadChart) {
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
    if (chartId === 'user-growth-chart' && userGrowthChart) {
        originalChart = userGrowthChart;
    } else if (chartId === 'conversion-chart' && conversionChart) {
        originalChart = conversionChart;
    } else if (chartId === 'server-load-chart' && serverLoadChart) {
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

// Загружаем подписки при загрузке страницы
document.addEventListener('DOMContentLoaded', async () => {
    // Включаем защиту от закрытия при скролле вверх
    preventCloseOnScroll();
    
    showPage('subscriptions');
    
    // Проверяем права админа
    await checkAdminAccess();
});
