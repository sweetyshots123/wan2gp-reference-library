// Reference Library 1.12.11 — keep fullscreen across next/prev (shared by Galería Viewer + Media Library lightbox).
// Root cause: the browser's native fullscreen belongs to the <video> element; navigating replaces / unmounts it,
// so the browser leaves fullscreen. Fix: fullscreen lives on a STABLE viewer container (Galería .stage,
// Media Library .reflib-ib-lightbox). If the native video button put the <video> itself in fullscreen, we move
// fullscreen to the container (needs a user gesture: done before navigating from a key/button, and tried on
// fullscreenchange). Esc is left to the browser while fullscreen is active (it exits fullscreen, not the viewer).
(function (root) {
    "use strict";
    function fsEl(doc) {
        doc = doc || (typeof document !== "undefined" ? document : null);
        if (!doc) return null;
        return doc.fullscreenElement || doc.webkitFullscreenElement || null;
    }
    function isActive(doc) { return !!fsEl(doc); }
    function contains(container, el) {
        if (!container || !el) return false;
        if (container === el) return true;
        try { return typeof container.contains === "function" && container.contains(el); } catch (e) { return false; }
    }
    /** Fullscreen is on this viewer (container itself or something inside it). */
    function owns(container, doc) { return contains(container, fsEl(doc)); }
    /** Fullscreen is on a child (e.g. the <video>) that navigation will replace → should move to the container. */
    function needsPromote(container, doc) {
        const el = fsEl(doc);
        return !!el && el !== container && contains(container, el);
    }
    function _req(el) {
        if (!el) return Promise.reject(new Error("no_element"));
        const f = el.requestFullscreen || el.webkitRequestFullscreen;
        if (!f) return Promise.reject(new Error("fullscreen_unsupported"));
        try {
            const r = f.call(el);
            return r && typeof r.then === "function" ? r : Promise.resolve();
        } catch (e) { return Promise.reject(e); }
    }
    function _exit(doc) {
        doc = doc || document;
        const f = doc.exitFullscreen || doc.webkitExitFullscreen;
        if (!f) return Promise.resolve();
        try { const r = f.call(doc); return r && typeof r.then === "function" ? r : Promise.resolve(); } catch (e) { return Promise.reject(e); }
    }
    /** Move fullscreen from a child to the stable container. Never throws; resolves true when promoted. */
    function promote(container, doc) {
        if (!needsPromote(container, doc)) return Promise.resolve(false);
        return _req(container).then(() => true, () => false);
    }
    /** Call right BEFORE next/prev (inside the key/click handler, so it counts as a user gesture). */
    function beforeNavigate(container, doc) { return promote(container, doc); }
    /** Run a navigation step keeping fullscreen: when a child (the <video>) is fullscreen, first move fullscreen to
     *  the container and only THEN run fn (removing the fullscreen <video> before the move completes drops
     *  fullscreen — verified in Chrome). Otherwise fn runs synchronously. Returns whatever fn returns (or a Promise). */
    function navigate(container, fn, doc) {
        if (!needsPromote(container, doc)) return fn();
        return promote(container, doc).then(() => fn(), () => fn());
    }
    /** Toggle fullscreen on the container (viewer button). */
    function toggle(container, doc) {
        if (owns(container, doc)) return _exit(doc).then(() => false, () => false);
        return _req(container).then(() => true, () => false);
    }
    /** What Esc should do in a viewer: while fullscreen, leave it to the browser (exit fullscreen only). */
    function escAction(doc) { return isActive(doc) ? "exit-fullscreen" : "close"; }
    /** Subscribe to fullscreen changes; returns an unsubscribe fn. */
    function onChange(doc, cb) {
        doc = doc || document;
        const h = () => { try { cb(fsEl(doc)); } catch (e) {} };
        doc.addEventListener("fullscreenchange", h);
        doc.addEventListener("webkitfullscreenchange", h);
        return () => { doc.removeEventListener("fullscreenchange", h); doc.removeEventListener("webkitfullscreenchange", h); };
    }
    /** Keep a viewer: whenever a child goes fullscreen (native video button / double-click), try to move it to
     *  the container right away (works while the click's user activation is still valid). Returns unsubscribe. */
    function keep(container, doc) {
        doc = doc || document;
        return onChange(doc, () => { if (needsPromote(container, doc)) promote(container, doc); });
    }
    root.ReflibFullscreen = { version: 1, fsEl, isActive, owns, needsPromote, promote, beforeNavigate, navigate, toggle, escAction, onChange, keep };
})(typeof globalThis !== "undefined" ? globalThis : window);
