(function () {
    function create() {
        function bindFeature(feature, methodNames) {
            var bound = {};
            methodNames.forEach(function (methodName) {
                bound[methodName] = function () {
                    return feature[methodName].apply(feature, arguments);
                };
            });
            return bound;
        }

        return {
            bindFeature: bindFeature
        };
    }

    window.DarallaAppActions = { create: create };
})();
