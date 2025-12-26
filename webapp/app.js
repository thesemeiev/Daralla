// Telegram Web App API
const tg = window.Telegram.WebApp;

// Инициализация Telegram Web App
tg.ready();
tg.expand();

// Устанавливаем цветовую схему
tg.setHeaderColor('#1a1a1a');
tg.setBackgroundColor('#1a1a1a');

// Текущая страница
let currentPage = 'subscriptions';

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
        await loadServerLoadChart();
    } catch (error) {
        console.error('Ошибка загрузки статистики:', error);
        document.getElementById('admin-stats-loading').style.display = 'none';
        showError('admin-stats-error', 'Ошибка загрузки статистики');
    }
}

// Переменные для хранения экземпляров графиков
let userGrowthChart = null;
let serverLoadChart = null;

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
                        position: 'top'
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
                        display: false
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

// Загружаем подписки при загрузке страницы
document.addEventListener('DOMContentLoaded', async () => {
    showPage('subscriptions');
    
    // Проверяем права админа
    await checkAdminAccess();
});
