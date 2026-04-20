(function () {
    function create(ctx) {
        var authFeature = window.DarallaAuthFeature.create({
            onRemoveAuthToken: ctx.onRemoveAuthToken,
            setCurrentUserId: ctx.setCurrentUserId,
            showPage: ctx.showPage,
            getPlatform: ctx.getPlatform,
            apiFetch: ctx.apiFetch
        });

        var authFormsFeature = window.DarallaAuthFormsFeature.create({
            setAuthToken: ctx.setAuthToken,
            setWebAuthToken: ctx.setWebAuthToken,
            setCurrentUserId: ctx.setCurrentUserId,
            showPage: ctx.showPage,
            checkAdminAccess: ctx.checkAdminAccess,
            showFormMessage: ctx.showFormMessage
        });

        var authAccountFeature = window.DarallaAuthAccountFeature.create({
            apiFetch: ctx.apiFetch,
            appShowAlert: ctx.appShowAlert,
            showFormMessage: ctx.showFormMessage,
            showModal: ctx.showModal,
            closeModal: ctx.closeModal,
            platform: ctx.platform,
            getTgInitData: ctx.getTgInitData,
            getWebAuthToken: ctx.getWebAuthToken,
            updateProfileCard: ctx.updateProfileCard,
            setProfileAvatarFromInitData: ctx.setProfileAvatarFromInitData,
            loadProfileAvatar: ctx.loadProfileAvatar
        });

        var subscriptionsFeature = window.DarallaSubscriptionsFeature.create({
            escapeHtml: ctx.escapeHtml,
            formatTimeRemaining: ctx.formatTimeRemaining,
            apiFetch: ctx.apiFetch,
            platform: ctx.platform,
            initTelegramFlow: ctx.initTelegramFlow,
            showPage: ctx.showPage,
            setCurrentSubscriptionDetail: ctx.setCurrentSubscriptionDetail,
            onBuySubscription: ctx.onBuySubscription
        });

        var adminUsersFeature = window.DarallaAdminUsersFeature.create({
            setCurrentCreatingSubscriptionUserId: ctx.setCurrentCreatingSubscriptionUserId,
            getCurrentCreatingSubscriptionUserId: ctx.getCurrentCreatingSubscriptionUserId,
            setPreviousAdminPage: ctx.setPreviousAdminPage,
            getPreviousAdminPage: ctx.getPreviousAdminPage,
            showPage: ctx.showPage,
            showAdminUserDetail: ctx.showAdminUserDetail
        });

        var adminUsersListFeature = window.DarallaAdminUsersListFeature.create({
            apiFetch: ctx.apiFetch,
            buildHash: ctx.buildHash,
            escapeHtml: ctx.escapeHtml,
            showError: ctx.showError,
            showPage: ctx.showPage,
            setPreviousAdminPage: ctx.setPreviousAdminPage,
            setCurrentAdminUserDetailUserId: ctx.setCurrentAdminUserDetailUserId,
            getCurrentAdminUserSearch: ctx.getCurrentAdminUserSearch,
            setCurrentAdminUserPage: ctx.setCurrentAdminUserPage,
            setCurrentAdminUserSearch: ctx.setCurrentAdminUserSearch
        });

        var adminUsersActionsFeature = window.DarallaAdminUsersActionsFeature.create({
            apiFetch: ctx.apiFetch,
            platform: ctx.platform,
            showPage: ctx.showPage,
            loadAdminUsers: ctx.loadAdminUsers
        });

        var adminSubscriptionEditFeature = window.DarallaAdminSubscriptionEditFeature.create({
            apiFetch: ctx.apiFetch,
            appShowAlert: ctx.appShowAlert,
            appShowConfirm: ctx.appShowConfirm,
            showPage: ctx.showPage,
            showModal: ctx.showModal,
            escapeHtml: ctx.escapeHtml,
            copyTextToClipboard: ctx.copyTextToClipboard,
            getCurrentPage: ctx.getCurrentPage,
            getCurrentEditingSubscriptionId: ctx.getCurrentEditingSubscriptionId,
            setCurrentEditingSubscriptionId: ctx.setCurrentEditingSubscriptionId,
            getOriginalSubscriptionData: ctx.getOriginalSubscriptionData,
            setOriginalSubscriptionData: ctx.setOriginalSubscriptionData,
            getCurrentSubscriptionServers: ctx.getCurrentSubscriptionServers,
            setCurrentSubscriptionServers: ctx.setCurrentSubscriptionServers,
            getPreviousAdminPage: ctx.getPreviousAdminPage,
            setPreviousAdminPage: ctx.setPreviousAdminPage,
            getCurrentAdminSubscriptionsPage: ctx.getCurrentAdminSubscriptionsPage,
            getCurrentAdminSubscriptionsStatus: ctx.getCurrentAdminSubscriptionsStatus,
            getCurrentAdminSubscriptionsOwnerQuery: ctx.getCurrentAdminSubscriptionsOwnerQuery,
            getCurrentAdminUserDetailUserId: ctx.getCurrentAdminUserDetailUserId,
            showAdminUserDetail: ctx.showAdminUserDetail
        });

        var adminSubscriptionCreateFeature = window.DarallaAdminSubscriptionCreateFeature.create({
            apiFetch: ctx.apiFetch,
            appShowAlert: ctx.appShowAlert,
            getCurrentCreatingSubscriptionUserId: ctx.getCurrentCreatingSubscriptionUserId,
            goBackFromCreateSubscription: ctx.goBackFromCreateSubscription
        });

        var adminStatsDashboardFeature = window.DarallaAdminStatsDashboardFeature.create({
            apiFetch: ctx.apiFetch,
            escapeHtml: ctx.escapeHtml,
            getCurrentPage: ctx.getCurrentPage,
            getServerLoadChartInterval: ctx.getServerLoadChartInterval,
            setServerLoadChartInterval: ctx.setServerLoadChartInterval,
            getDashRevenueChart: ctx.getDashRevenueChart,
            setDashRevenueChart: ctx.setDashRevenueChart
        });

        var adminBroadcastFeature = window.DarallaAdminBroadcastFeature.create({
            apiFetch: ctx.apiFetch,
            appShowConfirm: ctx.appShowConfirm,
            platform: ctx.platform,
            escapeHtml: ctx.escapeHtml
        });

        var serversFeature = window.DarallaServersFeature.createList({
            apiFetch: ctx.apiFetch,
            loadServerMap: ctx.loadServerMap,
            escapeHtml: ctx.escapeHtml
        });

        var eventsFeature = window.DarallaEventsFeature.create({
            apiFetch: ctx.apiFetch,
            renderEventCard: ctx.renderEventCard,
            moveNavIndicator: ctx.moveNavIndicator,
            getEventDetailLeaderboardTimer: ctx.getEventDetailLeaderboardTimer,
            setEventDetailLeaderboardTimer: ctx.setEventDetailLeaderboardTimer,
            showPage: ctx.showPage,
            isEventLive: ctx.isEventLive,
            getEventDaysText: ctx.getEventDaysText,
            getEventIcons: ctx.getEventIcons,
            escapeHtml: ctx.escapeHtml,
            buildLeaderboardHtml: ctx.buildLeaderboardHtml,
            copyTextToClipboard: ctx.copyTextToClipboard,
            appShowAlert: ctx.appShowAlert,
            showModal: ctx.showModal
        });

        var notificationsFeature = window.DarallaNotificationsFeature.create({
            apiFetch: ctx.apiFetch,
            escapeHtml: ctx.escapeHtml,
            notifCardPreviewText: ctx.notifCardPreviewText,
            notifTriggerLabel: ctx.notifTriggerLabel,
            notifFormatHours: ctx.notifFormatHours,
            getNotifEventLabels: ctx.getNotifEventLabels,
            notifParseTemplate: ctx.notifParseTemplate,
            setRepeatData: ctx.setRepeatData,
            setNotifTriggerFromHours: ctx.setNotifTriggerFromHours,
            onNotifRuleEventTypeChange: ctx.onNotifRuleEventTypeChange,
            updateNotifPreview: ctx.updateNotifPreview,
            showModal: ctx.showModal,
            setNotifRuleEditingId: ctx.setNotifRuleEditingId,
            getNotifRuleEditingId: ctx.getNotifRuleEditingId,
            setNotifSelectedTriggerHours: ctx.setNotifSelectedTriggerHours,
            getNotifTriggerHours: ctx.getNotifTriggerHours,
            getRepeatData: ctx.getRepeatData,
            buildNotifTemplate: ctx.buildNotifTemplate,
            closeNotificationRuleForm: ctx.closeNotificationRuleForm,
            appShowAlert: ctx.appShowAlert,
            appShowConfirm: ctx.appShowConfirm
        });

        var paymentsFeature = window.DarallaPaymentsFeature.create({
            setCurrentPaymentData: ctx.setCurrentPaymentData,
            getCurrentPaymentData: ctx.getCurrentPaymentData,
            setCurrentExtendSubscriptionId: ctx.setCurrentExtendSubscriptionId,
            getCurrentExtendSubscriptionId: ctx.getCurrentExtendSubscriptionId,
            setCurrentPaymentPeriod: ctx.setCurrentPaymentPeriod,
            getCurrentPaymentPeriod: ctx.getCurrentPaymentPeriod,
            appShowAlert: ctx.appShowAlert,
            showPage: ctx.showPage,
            apiFetch: ctx.apiFetch,
            isHttpUrl: ctx.isHttpUrl,
            getReferralCodeFromCurrentPage: ctx.getReferralCodeFromCurrentPage,
            showFormMessage: ctx.showFormMessage,
            hideFormMessage: ctx.hideFormMessage,
            removePaymentResultSubline: ctx.removePaymentResultSubline,
            ensurePaymentResultSubline: ctx.ensurePaymentResultSubline,
            showAppToast: ctx.showAppToast,
            loadSubscriptions: ctx.loadSubscriptions,
            openPaymentUrl: ctx.openPaymentUrl
        });

        var adminCommerceFeature = window.DarallaAdminCommerceFeature.create({
            apiFetch: ctx.apiFetch,
            loadPrices: ctx.loadPrices
        });

        var adminServersFeature = window.DarallaAdminServersFeature.create({
            getCurrentAdminGroups: ctx.getCurrentAdminGroups,
            setCurrentAdminGroups: ctx.setCurrentAdminGroups,
            getCurrentAdminServers: ctx.getCurrentAdminServers,
            setCurrentAdminServers: ctx.setCurrentAdminServers,
            getCurrentSelectedGroupId: ctx.getCurrentSelectedGroupId,
            setCurrentSelectedGroupId: ctx.setCurrentSelectedGroupId,
            getAdminServerReorderMode: ctx.getAdminServerReorderMode,
            setAdminServerReorderMode: ctx.setAdminServerReorderMode,
            apiFetch: ctx.apiFetch,
            appShowAlert: ctx.appShowAlert,
            appShowConfirm: ctx.appShowConfirm,
            showModal: ctx.showModal,
            closeModal: ctx.closeModal,
            showPage: ctx.showPage,
            escapeHtml: ctx.escapeHtml,
            platform: ctx.platform
        });

        return {
            authFeature: authFeature,
            authFormsFeature: authFormsFeature,
            authAccountFeature: authAccountFeature,
            subscriptionsFeature: subscriptionsFeature,
            adminUsersFeature: adminUsersFeature,
            adminUsersListFeature: adminUsersListFeature,
            adminUsersActionsFeature: adminUsersActionsFeature,
            adminSubscriptionEditFeature: adminSubscriptionEditFeature,
            adminSubscriptionCreateFeature: adminSubscriptionCreateFeature,
            adminStatsDashboardFeature: adminStatsDashboardFeature,
            adminBroadcastFeature: adminBroadcastFeature,
            serversFeature: serversFeature,
            eventsFeature: eventsFeature,
            notificationsFeature: notificationsFeature,
            paymentsFeature: paymentsFeature,
            adminCommerceFeature: adminCommerceFeature,
            adminServersFeature: adminServersFeature
        };
    }

    window.DarallaAppComposition = { create: create };
})();
