// Reference Library 1.12.17 (ml-wheel) - viewer rules shared by the Galería viewer (gallery/src/viewerNav.ts imports this
// file) and the Media Library lightbox (prepended to reference_library.js by plugin.py build_js). Pure, no DOM
// (tests/test_viewer_rules.mjs; real code in tests/test_browser_mlwheel.mjs for both UIs).
//  · wheelIntent: Ctrl/⌘ + wheel = zoom, zoomed (and pannable) = pan, otherwise step to previous / next with ReflibWheel
//    (wheel_rules.js, 1 notch = 1 item). Galería: transform pan; ML: native scroll of the 1:1 stage.
//  · zoomAt: zoom to cursor for a translate+scale transform centred on the stage (Galería): x' = p - (p - x)·k.
//  · zoomScroll: the same invariant for a scrollable stage (ML 1:1): the image point under the cursor stays under it.
//  · navZoom: zoom state after moving to another item = Fit (both UIs; the ML used to keep 1:1 across items).
//  · fitSize: the size the <img> must have in "Ajustar" / "1:1" from the ORIGINAL dimensions, whatever progressive stage
//    is loaded (220 px thumb → 1024 px preview → full file). Before 1.12.17 the CSS only capped (max-width/max-height),
//    so the img rendered at the intrinsic size of the thumb / medium preview ("la foto se queda pequeña") until the full
//    file decoded. Aspect comes from the loaded pixels (EXIF-oriented by the browser), the scale from the original's
//    long side (orientation-proof: PIL's im.size is pre-rotation). Unknown original = fill the box (photos are almost
//    always larger than the screen; corrected as soon as the preview reply brings width/height). Never upscales a
//    known original beyond 1:1, like the Galería (max-width/height: 100%).
(function (root) {
    "use strict";
    function fitSize(o) {
        // o: { natW, natH (loaded pixels), origW, origH (0 = unknown), boxW, boxH, one (1:1) }
        const nw = +o.natW || 0, nh = +o.natH || 0;
        if (!nw || !nh) return null;
        const ow = +o.origW || 0, oh = +o.origH || 0;
        const long = Math.max(ow, oh);
        const scaleNat = long ? long / Math.max(nw, nh) : 0;   // loaded px → original px
        const w0 = scaleNat ? nw * scaleNat : nw, h0 = scaleNat ? nh * scaleNat : nh;   // original size, oriented like the pixels
        if (o.one) return { w: Math.round(w0), h: Math.round(h0) };
        const bw = Math.max(1, +o.boxW || 1), bh = Math.max(1, +o.boxH || 1);
        let s = Math.min(bw / w0, bh / h0);
        if (long) s = Math.min(s, 1);
        return { w: Math.max(1, Math.round(w0 * s)), h: Math.max(1, Math.round(h0 * s)) };
    }
    function zoomScroll(o) {
        // o: { cx, cy (cursor, client px), imgRect {left, top, width, height} BEFORE the zoom, stageRect {left, top},
        //      newOffLeft, newOffTop (img offset inside the stage's scroll area AFTER the zoom), newW, newH }
        const r = o.imgRect;
        const fx = r.width ? Math.min(1, Math.max(0, (o.cx - r.left) / r.width)) : 0.5;
        const fy = r.height ? Math.min(1, Math.max(0, (o.cy - r.top) / r.height)) : 0.5;
        return { left: o.newOffLeft + fx * o.newW - (o.cx - o.stageRect.left), top: o.newOffTop + fy * o.newH - (o.cy - o.stageRect.top), fx, fy };
    }
    function wheelIntent(o) {
        // o: { ctrl, zoomed, canPan, prevented }
        if (o.prevented) return "none";   // another handler (e.g. a video player plugin) took it
        if (o.ctrl) return "zoom";
        if (o.zoomed && o.canPan) return "pan";
        return "step";
    }
    const FIT = Object.freeze({ s: 1, x: 0, y: 0 });
    function zoomAt(o, factor, px, py, min, max) {
        // o: {s, x, y} (translate px + scale, origin = stage centre); px, py: cursor relative to the stage centre
        const lo = min == null ? 1 : min, hi = max == null ? 12 : max;
        const s = Math.min(hi, Math.max(lo, o.s * factor));
        if (s === 1) return { s: 1, x: 0, y: 0 };
        const k = s / o.s;
        return { s, x: px - (px - o.x) * k, y: py - (py - o.y) * k };
    }
    function navZoom() { return { s: FIT.s, x: FIT.x, y: FIT.y }; }   // every navigation lands in Fit
    root.ReflibViewer = { version: 1, fitSize, zoomScroll, wheelIntent, zoomAt, navZoom, FIT };
})(typeof globalThis !== "undefined" ? globalThis : window);
