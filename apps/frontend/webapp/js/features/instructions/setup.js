(function () {
    // Глобальные переменные для инструкций
    var currentInstructionPlatform = null;
    var currentInstructionStep = 0;
    var currentInstructionSteps = [];

    // Структура пошаговых инструкций
    var instructionSteps = {
        android: {
            title: 'Android (Happ)',
            steps: [
                {
                    title: 'Шаг 1: Установите приложение',
                    content: `
                    <p>Установите Happ для Android:</p>
                    <ul style="margin: 12px 0; padding-left: 20px;">
                        <li style="margin-bottom: 8px;"><a href="https://play.google.com/store/search?q=happ+plus&c=apps" target="_blank" class="instruction-link">Happ из Google Play</a></li>
                    </ul>
                    <p>Если ссылка на Happ недоступна, смените регион в магазине приложений (Google Play) и попробуйте снова.</p>
                    <p>Скачайте и установите приложение на ваше устройство.</p>
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
            title: 'iOS (Happ)',
            steps: [
                {
                    title: 'Шаг 1: Установите приложение',
                    content: `
                    <p>Установите Happ для iPhone:</p>
                    <ul style="margin: 12px 0; padding-left: 20px;">
                        <li style="margin-bottom: 8px;"><a href="https://apps.apple.com/ru/app/happ-proxy-utility-plus/id6746188973" target="_blank" class="instruction-link">Happ из App Store</a></li>
                    </ul>
                    <p>Если ссылка на Happ недоступна, смените регион в магазине приложений (App Store) и попробуйте снова.</p>
                    <p>Скачайте и установите приложение на ваше устройство.</p>
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
            title: 'Windows (Happ)',
            steps: [
                {
                    title: 'Шаг 1: Скачайте приложение',
                    content: `
                    <p>Скачайте Happ для Windows:</p>
                    <ul style="margin: 12px 0; padding-left: 20px;">
                        <li style="margin-bottom: 8px;"><a href="https://github.com/Happ-proxy/happ-desktop/releases/latest/download/setup-Happ.x64.exe" target="_blank" class="instruction-link">Happ для Windows</a></li>
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
            title: 'macOS (Happ)',
            steps: [
                {
                    title: 'Шаг 1: Скачайте приложение',
                    content: `
                    <p>Скачайте Happ для Mac:</p>
                    <ul style="margin: 12px 0; padding-left: 20px;">
                        <li style="margin-bottom: 8px;"><a href="https://apps.apple.com/ru/app/happ-proxy-utility-plus/id6746188973?platform=mac" target="_blank" class="instruction-link">Happ для Mac</a></li>
                    </ul>
                    <p>Если ссылка на Happ недоступна, смените регион в магазине приложений (App Store) и попробуйте снова.</p>
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
                    <p><a href="https://github.com/Happ-proxy/happ-desktop/releases/latest/download/Happ.linux.x64.deb" target="_blank" class="instruction-link">Скачайте Happ для Linux</a> и установите на ваш компьютер.</p>
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
            title: 'Android TV (Happ)',
            steps: [
                {
                    title: 'Шаг 1: Установите приложение',
                    content: `
                    <p>Установите Happ для Android TV:</p>
                    <ul style="margin: 12px 0; padding-left: 20px;">
                        <li style="margin-bottom: 8px;"><a href="https://play.google.com/store/apps/details?id=com.happproxy" target="_blank" class="instruction-link">Happ для Android TV</a></li>
                    </ul>
                    <p>Если ссылка на Happ недоступна, смените регион в магазине приложений (Google Play) и попробуйте снова.</p>
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
                    <p style="margin-top: 14px;"><a href="/support" target="_blank" rel="noopener noreferrer" class="instruction-link">Написать в поддержку @DarallaSupport</a></p>
                `
                }
            ]
        }
    };

    var instructionsModalFeature = window.DarallaInstructionsModalFeature.create({
        getInstructionStepsMap: function () { return instructionSteps; },
        getCurrentInstructionPlatform: function () { return currentInstructionPlatform; },
        setCurrentInstructionPlatform: function (value) { currentInstructionPlatform = value; },
        getCurrentInstructionStep: function () { return currentInstructionStep; },
        setCurrentInstructionStep: function (value) { currentInstructionStep = value; },
        getCurrentInstructionSteps: function () { return currentInstructionSteps; },
        setCurrentInstructionSteps: function (value) { currentInstructionSteps = value; }
    });

    window.showInstructionModal = function (platform) { return instructionsModalFeature.showInstructionModal(platform); };
    window.renderInstructionStep = function () { return instructionsModalFeature.renderInstructionStep(); };
    window.nextInstructionStep = function () { return instructionsModalFeature.nextInstructionStep(); };
    window.prevInstructionStep = function () { return instructionsModalFeature.prevInstructionStep(); };
    window.closeInstructionModal = function () { return instructionsModalFeature.closeInstructionModal(); };
})();
