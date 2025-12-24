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
    if (pageName !== 'subscription-detail') {
        const navItems = document.querySelectorAll('.nav-item');
        if (pageName === 'subscriptions') {
            navItems[0]?.classList.add('active');
        } else if (pageName === 'servers') {
            navItems[1]?.classList.add('active');
        } else if (pageName === 'about') {
            navItems[2]?.classList.add('active');
        }
    }
    
    currentPage = pageName;
    
    // Загружаем данные для страницы
    if (pageName === 'subscriptions') {
        loadSubscriptions();
    } else if (pageName === 'servers') {
        loadServers();
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
                
                ${sub.status === 'active' && sub.days_remaining > 0 ? `
                    <div class="detail-info-item full-width">
                        <div class="detail-info-label">Осталось дней</div>
                        <div class="detail-info-value days-highlight">${sub.days_remaining}</div>
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
                <div class="info-label">Устройств</div>
                <div class="info-value">${sub.device_limit}</div>
            </div>
            <div class="info-item">
                <div class="info-label">Создана</div>
                <div class="info-value">${sub.created_at_formatted}</div>
            </div>
            <div class="info-item">
                <div class="info-label">${sub.status === 'active' ? 'Истекает' : 'Истекла'}</div>
                <div class="info-value">${sub.expires_at_formatted}</div>
            </div>
        </div>
        
        ${sub.status === 'active' && sub.days_remaining > 0 ? `
            <div class="days-badge">
                <span class="info-label">Осталось дней</span>
                <span class="days-remaining">${sub.days_remaining}</span>
            </div>
        ` : ''}
        
        <div class="card-arrow">→</div>
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

// Загружаем подписки при загрузке страницы
document.addEventListener('DOMContentLoaded', () => {
    showPage('subscriptions');
});
