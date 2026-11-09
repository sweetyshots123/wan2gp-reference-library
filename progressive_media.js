// Reference Library 1.12.9 — progressive full-res upgrade (shared rules).
// Show whatever is already on screen (thumb / medium preview); decode full-res async; swap without resetting zoom.
(function (root) {
    "use strict";
    function loadDecode(url) {
        const img = new Image();
        let dead = false;
        img.decoding = "async";
        img.src = url || "";
        const p = (img.decode ? img.decode() : new Promise((res, rej) => { img.onload = () => res(); img.onerror = rej; }))
            .then(() => !dead, () => !dead && img.complete && img.naturalWidth > 0);
        return { p, abort() { dead = true; try { img.src = ""; } catch (e) {} } };
    }
    /** Decide display URL: prefer full when ready, else medium, else thumb. Never block on full. */
    function pick(urls) {
        const u = urls || {};
        return u.full || u.medium || u.thumb || null;
    }
    root.ReflibProgressive = { version: 1, loadDecode, pick };
})(typeof globalThis !== "undefined" ? globalThis : window);
