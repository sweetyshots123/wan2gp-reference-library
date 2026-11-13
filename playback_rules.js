// Reference Library 1.12.7 — resume-playback rules shared by Media Library, Galería and the
// standalone Media Library page. Pure helpers; positions are stored via playback_get / playback_set.
(function (root) {
    "use strict";
    const DEFAULT_MIN_S = 300, HEAD_S = 5, TAIL_S = 5, TAIL_FRAC = 0.95;
    function minS(v) {
        const n = Number(v);
        if (!isFinite(n) || n < 0) return DEFAULT_MIN_S;
        return Math.max(0, Math.min(86400, n));
    }
    function shouldTrack(duration, t, minSeconds) {
        const dur = Number(duration) || 0, pos = Number(t) || 0, thr = minS(minSeconds);
        if (!(dur > thr) || pos < 0) return false;
        if (pos < HEAD_S) return false;
        if (pos > dur - TAIL_S || pos >= dur * TAIL_FRAC) return false;
        return true;
    }
    function fmt(t) {
        t = Math.max(0, Math.floor(Number(t) || 0));
        const h = Math.floor(t / 3600), m = Math.floor((t % 3600) / 60), s = t % 60;
        if (h) return h + ":" + String(m).padStart(2, "0") + ":" + String(s).padStart(2, "0");
        return m + ":" + String(s).padStart(2, "0");
    }
    function offerLabels(t, lang) {
        const es = String(lang || "").toLowerCase().startsWith("es");
        const mm = fmt(t);
        return {
            continue: es ? ("Seguir desde " + mm) : ("Continue from " + mm),
            restart: es ? "Empezar desde el principio" : "Start from the beginning",
            tip: es ? "Solo en vídeos largos; no aparece cerca del inicio ni del final."
                    : "Only on long videos; not near the start or the end.",
        };
    }
    /** 1.12.12: a resume offer {hash, t} only applies to the item it was fetched for (stepping to another video
     *  must never show / act on the previous one). Returns t or null. Shared by Galería and Media Library. */
    function offerFor(offer, hash) {
        if (!offer || hash == null || hash === "") return null;
        if (String(offer.hash) !== String(hash)) return null;
        const t = Number(offer.t);
        return isFinite(t) ? t : null;
    }
    // 1.12.15: "this browser can't play this video" is a property of what the <video> has loaded NOW, never a
    // sticky flag: the same element is reused across items (1.12.11, fullscreen), so a previous item's MediaError
    // must not leak onto a video that plays. Only decode / unsupported-source errors (MEDIA_ERR_DECODE = 3,
    // MEDIA_ERR_SRC_NOT_SUPPORTED = 4) or loaded metadata without a picture (videoWidth 0) count; network (2) and
    // aborted (1) loads are not a codec problem. Re-evaluate on UNPLAYABLE_EVENTS.
    const UNPLAYABLE_EVENTS = ["error", "emptied", "loadstart", "loadedmetadata", "loadeddata", "canplay", "playing"];
    function unplayable(v) {
        if (!v) return false;
        const e = v.error;
        if (e) return e.code === 3 || e.code === 4;
        if (!v.currentSrc && !v.getAttribute?.("src")) return false;
        return (v.readyState || 0) >= 1 && !v.videoWidth;
    }
    root.ReflibPlayback = {
        version: 1, DEFAULT_MIN_S, HEAD_S, TAIL_S, TAIL_FRAC,
        minS, shouldTrack, fmt, offerLabels, offerFor, unplayable, UNPLAYABLE_EVENTS,
    };
})(typeof globalThis !== "undefined" ? globalThis : window);
