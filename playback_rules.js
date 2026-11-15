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
    // 1.12.19: a video that needs a cached transcode (mp4v, …). play = original | ready | preparing | failed
    const PREPARE_POLL_MS = 400;
    function playReply(r) {
        const play = (r && r.play) || (r && r.rendering ? "preparing" : (r && r.url ? "original" : "failed"));
        return {
            play,
            url: (r && r.url) || null,
            preparing: play === "preparing",
            failed: play === "failed",
            ready: play === "original" || play === "ready",
            codec: (r && r.codec) || "",
            progress: r && r.progress != null ? Number(r.progress) : null,
            error: (r && r.error) || null,
            rendering: !!(r && (r.rendering || play === "preparing")),
        };
    }
    function playLabels(lang) {
        const es = String(lang || "").toLowerCase().startsWith("es");
        return {
            preparing: es ? "Preparando vídeo…" : "Preparing video…",
            preparingTip: es ? "Se está convirtiendo a un formato que este navegador puede reproducir. El archivo original no se modifica."
                            : "Converting to a format this browser can play. The original file is not modified.",
            unplayable: es ? "Este navegador no puede reproducir este vídeo (códec no compatible, p. ej. mp4v / MPEG-4 Part 2)."
                           : "This browser cannot play this video (unsupported codec, e.g. mp4v / MPEG-4 Part 2).",
        };
    }
    function showPreparing(s, v) {
        if (!s || !s.preparing) return false;
        if (v && !unplayable(v) && (v.videoWidth || 0) > 0 && (v.readyState || 0) >= 2) return false;
        return true;
    }
    function showUnplayable(s, v) {
        if (s && s.preparing) return false;
        if (s && s.failed) return true;
        return unplayable(v);
    }
    /** Poll fetchReply() while preparing. onState(s) receives the playReply. If `video` is given and the URL
     *  changes (stream → finished cache), currentTime is kept. Returns a cancel function. */
    function watchPlay(fetchReply, onState, video) {
        let gone = false, lastUrl = null, timer = null;
        const tick = async () => {
            if (gone) return;
            let s;
            try { s = playReply(await fetchReply()); } catch (e) { s = playReply(null); }
            if (gone) return;
            const url = s.url;
            if (video && url && lastUrl && url !== lastUrl && (video.currentTime || 0) > 0.05) {
                const t = video.currentTime, paused = video.paused;
                const on = () => {
                    try { if (isFinite(t)) video.currentTime = t; } catch (e) {}
                    if (!paused) video.play().catch(function () {});
                    video.removeEventListener("loadedmetadata", on);
                };
                video.addEventListener("loadedmetadata", on);
            }
            if (url) lastUrl = url;
            try { onState(s); } catch (e) {}
            if (s.preparing && !gone) timer = setTimeout(tick, PREPARE_POLL_MS);
        };
        tick();
        return () => { gone = true; if (timer) clearTimeout(timer); };
    }
    root.ReflibPlayback = {
        version: 2, DEFAULT_MIN_S, HEAD_S, TAIL_S, TAIL_FRAC, PREPARE_POLL_MS,
        minS, shouldTrack, fmt, offerLabels, offerFor, unplayable, UNPLAYABLE_EVENTS,
        playReply, playLabels, showPreparing, showUnplayable, watchPlay,
    };
})(typeof globalThis !== "undefined" ? globalThis : window);
