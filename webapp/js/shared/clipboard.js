(function () {
    function copyTextToClipboardExec(value) {
        var ta = document.createElement('textarea');
        ta.value = value;
        ta.setAttribute('readonly', '');
        ta.style.position = 'fixed';
        ta.style.left = '-9999px';
        document.body.appendChild(ta);
        ta.select();
        var ok = false;
        try {
            ok = document.execCommand('copy');
        } catch (e) {
            ok = false;
        }
        document.body.removeChild(ta);
        return ok;
    }

    function copyTextToClipboard(text) {
        var value = String(text == null ? '' : text);
        if (navigator.clipboard && navigator.clipboard.writeText) {
            return navigator.clipboard.writeText(value).then(function () {
                return true;
            }).catch(function () {
                return copyTextToClipboardExec(value);
            });
        }
        return Promise.resolve(copyTextToClipboardExec(value));
    }

    window.DarallaClipboard = window.DarallaClipboard || {};
    window.DarallaClipboard.copyTextToClipboard = copyTextToClipboard;
    window.DarallaClipboard.copyTextToClipboardExec = copyTextToClipboardExec;
})();
