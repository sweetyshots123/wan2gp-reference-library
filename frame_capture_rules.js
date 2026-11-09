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
    root.ReflibFrameCapture = { version: 1, EVENT, shouldNavigate, stayHash, toastText, resumePlayback, keepOpen };
})(typeof globalThis !== "undefined" ? globalThis : window);
