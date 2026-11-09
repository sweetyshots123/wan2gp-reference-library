// Reference Library 1.12.8 — standalone Media Library: which WanGP/Gradio-bridge actions stay hidden,
// and the one-time translated notice if something still calls the bridge.
(function (root) {
    "use strict";
    const state = { shown: false };
    function isStandalone(flag) {
        if (flag != null) return !!flag;
        try { return !!(typeof globalThis !== "undefined" && globalThis.__REFLIB_STANDALONE__); } catch (e) { return false; }
    }
    /** Send-to-refs / control video / history reuse need the Gradio bridge — hide in standalone. */
    function showWanBridgeActions(standalone) {
        return !isStandalone(standalone);
    }
    function bridgeMissingMessage(lang) {
        const es = String(lang || "").toLowerCase().startsWith("es");
        return es
            ? "Esta acción necesita WanGP (pestaña Reference Library en el generador). Ábrela desde WanGP para usarla."
            : "This action needs WanGP (Reference Library tab in the generator). Open it from WanGP to use it.";
    }
    /** First call returns the message; later calls return null (one-time notice). */
    function takeBridgeNotice(lang, st) {
        const s = st || state;
        if (s.shown) return null;
        s.shown = true;
        return bridgeMissingMessage(lang);
    }
    function resetNotices(st) { (st || state).shown = false; }
    root.ReflibStandalone = {
        version: 1,
        isStandalone,
        showWanBridgeActions,
        bridgeMissingMessage,
        takeBridgeNotice,
        resetNotices,
        _state: state,
    };
})(typeof globalThis !== "undefined" ? globalThis : window);
