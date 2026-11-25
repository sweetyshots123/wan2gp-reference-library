// Reference Library 1.12.8 / 1.12.27 — standalone Media Library: which WanGP/Gradio-bridge actions stay hidden,
// the one-time translated notice if something still calls the bridge, and the once-only page banner.
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

    // 1.12.27: the standalone page banner is also a once-only notice, but persisted
    // in localStorage so a reload does not show it again (same rule as other hints).
    const PAGE_NOTICE_KEY = "reflib_standalone_notice_seen";
    function getStore(store) {
        if (store !== undefined) return store;
        try { return root.localStorage || null; } catch (e) { return null; }
    }
    function pageNoticeMessage(lang) {
        const es = String(lang || "").toLowerCase().startsWith("es");
        return es
            ? "Media Library independiente. Acciones de WanGP (añadir a referencias, vídeo de control, historial…) están ocultas aquí."
            : "Standalone Media Library. WanGP actions (add to references, control video, history…) are hidden here.";
    }
    /** First visit returns true and records the flag; later visits return false. */
    function takePageNotice(store) {
        const st = getStore(store);
        try {
            if (st && st.getItem(PAGE_NOTICE_KEY) === "1") return false;
            if (st) st.setItem(PAGE_NOTICE_KEY, "1");
            return true;
        } catch (e) { return true; }
    }
    function resetPageNotice(store) {
        const st = getStore(store);
        try { if (st) st.removeItem(PAGE_NOTICE_KEY); } catch (e) {}
    }
    root.ReflibStandalone = {
        version: 1,
        PAGE_NOTICE_KEY,
        isStandalone,
        showWanBridgeActions,
        bridgeMissingMessage,
        takeBridgeNotice,
        resetNotices,
        pageNoticeMessage,
        takePageNotice,
        resetPageNotice,
        _state: state,
    };
})(typeof globalThis !== "undefined" ? globalThis : window);
