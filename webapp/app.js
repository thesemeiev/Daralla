// Telegram Web App API
const tg = window.Telegram.WebApp;

// Инициализация Telegram Web App
tg.ready();
tg.expand();

// Устанавливаем цветовую схему
tg.setHeaderColor('#3390ec');
tg.setBackgroundColor('#ffffff');

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
    
    const statusClass = sub.status === 'active' ? 'active' : 'expired';
    const statusText = sub.status === 'active' ? 'Активна' : 
                      sub.status === 'expired' ? 'Истекла' : 
                      sub.status === 'trial' ? 'Пробная' : sub.status;
    
    const periodText = sub.period === '3month' ? '3 месяца' : 
                      sub.period === 'month' ? '1 месяц' : 
                      sub.period === 'trial' ? 'Пробная' : sub.period;
    
    card.innerHTML = `
        <div class="subscription-header">
            <div class="subscription-name">${escapeHtml(sub.name)}</div>
            <div class="subscription-status ${statusClass}">${statusText}</div>
        </div>
        
        <div class="subscription-info">
            <div class="info-item">
                <div class="info-label">Период</div>
                <div class="info-value">${periodText}</div>
            </div>
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
            <div style="margin-top: 12px; padding: 8px; background: var(--tg-theme-secondary-bg-color, #f0f0f0); border-radius: 8px; text-align: center;">
                <span class="info-label">Осталось дней:</span>
                <span class="days-remaining">${sub.days_remaining}</span>
            </div>
        ` : ''}
        
        ${sub.status === 'active' ? `
            <div class="subscription-actions">
                <button class="action-button primary" onclick="copySubscriptionLink('${sub.token}')">
                    📋 Копировать ссылку
                </button>
            </div>
        ` : ''}
    `;
    
    return card;
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
    loadSubscriptions();
});

// Обновляем подписки при возврате на страницу (если Telegram Web App поддерживает)
if (tg.onEvent) {
    tg.onEvent('viewportChanged', () => {
        // Можно добавить логику обновления при изменении viewport
    });
}

