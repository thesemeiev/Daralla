(function () {
    function create(initial) {
        var defaults = {
            webAuthToken: null,
            currentUserId: null,
            isWebMode: false,
            currentSubscriptionDetail: null,
            currentPage: 'subscriptions',
            serverLoadChartInterval: null,
            notifRuleEditingId: null,
            notifSelectedTriggerHours: null,
            currentExtendSubscriptionId: null,
            currentPaymentData: null,
            currentPaymentPeriod: null,
            currentPaymentGateway: 'yookassa',
            isAdmin: false,
            currentAdminUserPage: 1,
            currentAdminUserSearch: '',
            currentAdminUserDetailUserId: null,
            currentEditingSubscriptionId: null,
            previousAdminPage: 'admin-users',
            currentCreatingSubscriptionUserId: null,
            currentAdminSubscriptionsPage: 1,
            currentAdminSubscriptionsStatus: '',
            currentAdminSubscriptionsOwnerQuery: '',
            adminSubscriptionsSearchTimeout: null,
            originalSubscriptionData: null,
            currentSubscriptionServers: [],
            dashRevenueChart: null,
            currentAdminGroups: [],
            currentAdminServers: [],
            currentSelectedGroupId: null,
            adminServerReorderMode: false
        };
        return Object.assign(defaults, initial || {});
    }

    window.DarallaAppState = { create: create };
})();
