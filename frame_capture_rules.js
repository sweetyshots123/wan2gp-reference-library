// Reference Library 1.12.6 — frame-capture stay rules shared by Media Library (reference_library.js,
// prepended by plugin.py) and the Galería (gallery/src imports this same file). Pure helpers, no DOM.
// After Vidosser saves a frame into the library (CustomEvent "vidosser:frame-saved"), both UIs must:
//   · stay on the media that was open (same hash / same viewer position)
//   · never navigate to the new frame hash
//   · show at most a brief toast
//   · prefer resuming playback if it was playing before Vidosser paused for the exact frame
(function (root) {
    "use strict";
    const EVENT = "vidosser:frame-saved";
    function shouldNavigate(_detail) { return false; }
    function stayHash(currentHash, _detail) { return currentHash || null; }
    function toastText(detail, lang) {
        const name = detail && detail.name ? String(detail.name) : "";
        const es = String(lang || "").toLowerCase().startsWith("es");
        if (es) return name ? ("Fotograma guardado: " + name) : "Fotograma guardado";
        return name ? ("Frame saved: " + name) : "Frame saved";
    }
    function resumePlayback(wasPlaying) { return !!wasPlaying; }
    // Soft refresh of the grid is fine; the open viewer / lightbox / preview must keep currentHash.
    function keepOpen(currentHash, detail) {
        return { navigate: false, hash: stayHash(currentHash, detail), toast: true };
    }
    // 1.12.13: viewer pin. A refresh (frame capture, rev poll, another tab) may insert items before the open one,
    // so the same index now holds another item. The pin {hash, idx} only follows USER navigation (viewer index
    // changed); a refresh never re-pins. pinLocate() moves the viewer to the pinned hash in the same update as the
    // store write; if the pinned item is not in the loaded rows it keeps showing it (override) until index_of answers.
    function pinFollow(pin, viewer, hashAtViewer) {
        if (viewer == null) return null;
        if (pin && pin.idx === viewer) return pin;            // same index: a refresh, never re-pin
        if (hashAtViewer) return { hash: String(hashAtViewer), idx: viewer };
        return pin || null;                                   // target row not loaded yet (pin.idx !== viewer: no override)
    }
    function pinLocate(pin, viewer, entries) {
        if (!pin || viewer == null || pin.idx !== viewer) return { index: viewer, override: false, lookup: false };
        let at = null, found = null;
        for (const [i, h] of entries || []) { if (h === pin.hash) { if (i === viewer) at = i; else if (found == null) found = i; } }
        if (at != null) return { index: viewer, override: false, lookup: false };
        if (found != null) return { index: found, override: false, lookup: false };
        return { index: viewer, override: true, lookup: true };
    }
    /** 1.12.13: the viewer already shows the item to stay on → re-index only, never re-open (re-opening = new <video>). */
    function sameOpen(shownHash, keepHash) { return !!shownHash && !!keepHash && String(shownHash) === String(keepHash); }
    // 1.12.14: play intent, ONE implementation for both UIs. Vidosser pauses the video for the exact frame just
    // before saving, so a pause in the last WANT_MS still counts as "was playing"; an older pause (the user's) does not.
    const WANT_MS = 2000;
    const clock = () => (typeof performance !== "undefined" && performance.now ? performance.now() : Date.now());
    function notePlay(el) { if (el) { el._reflibWantUntil = Infinity; el._reflibWantPlay = true; } }
    function notePause(el, now) { if (el) { el._reflibWantUntil = (now == null ? clock() : now) + WANT_MS; el._reflibWantPlay = false; } }
    function wantPlay(el, now) {
        if (!el) return false;
        const t = now == null ? clock() : now, u = el._reflibWantUntil;
        if (u === Infinity) return true;
        if (typeof u === "number" && t < u) return true;
        return !el.paused && !el.ended;
    }
    function trackIntent(el) {
        if (!el || !el.addEventListener) return () => {};
        if (!el.paused && !el.ended) notePlay(el);
        const onPlay = () => notePlay(el), onPause = () => notePause(el);
        el.addEventListener("play", onPlay); el.addEventListener("pause", onPause);
        return () => { el.removeEventListener("play", onPlay); el.removeEventListener("pause", onPause); };
    }
    root.ReflibFrameCapture = { version: 3, EVENT, shouldNavigate, stayHash, toastText, resumePlayback, keepOpen, pinFollow, pinLocate, sameOpen,
        WANT_MS, notePlay, notePause, wantPlay, trackIntent };
})(typeof globalThis !== "undefined" ? globalThis : window);
