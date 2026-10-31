// Reference Library 1.11.0 - wheel → photo stepping shared by the Galería viewer (gallery/src/viewerNav.ts imports
// this same file) and available to the Media Library (prepend like selection_rules.js if it navigates with the wheel).
// Pure, no DOM. 1 wheel notch = exactly 1 photo: no skipped, lost or drifting steps.
//  · deltaMode LINE (1): units are lines; the notch is the smallest |deltaY| seen (usually 3, or 1).
//  · deltaMode PIXEL (0): the notch is calibrated per stepper as the smallest "notch-sized" |deltaY| seen
//    (>= NOTCH_MIN px; usually 100 or 120, also 150 etc. with display scaling). A first event that is a multiple of
//    120 / 100 (fast spin: 240, 360…) snaps to 120 / 100. Smaller deltas (trackpad, high-res wheels) accumulate
//    toward one notch of the calibrated (or default 100 px) size.
//  · deltaMode PAGE (2): 1 page = 1 notch.
//  · Accumulate, step once per whole notch, keep the remainder; reset on direction change or after IDLE_MS idle.
//  · Never throttles: an event worth N notches (fast spin) returns N.
(function (root) {
    "use strict";
    const IDLE_MS = 150, NOTCH_MIN = 50, DEFAULT_PX = 100;
    function snap(a) { return a % 120 === 0 ? 120 : a % 100 === 0 ? 100 : a; }
    function create() {
        const notch = { 0: 0, 1: 0, 2: 1 };
        let acc = 0, mode = -1, last = -Infinity;
        function push(deltaY, deltaMode, now) {
            const m = deltaMode === 1 || deltaMode === 2 ? deltaMode : 0;
            const a = Math.abs(deltaY);
            if (!a) return 0;
            if (now - last > IDLE_MS || m !== mode || (acc && Math.sign(deltaY) !== Math.sign(acc))) acc = 0;
            last = now; mode = m;
            if (m === 1) notch[1] = notch[1] ? Math.min(notch[1], a) : a;
            else if (m === 0 && a >= NOTCH_MIN) notch[0] = notch[0] ? Math.min(notch[0], a) : snap(a);
            const size = notch[m] || DEFAULT_PX;
            acc += deltaY;
            const n = Math.trunc((acc + Math.sign(acc) * 1e-6 * size) / size);   // tolerate float noise (119.99999)
            acc -= n * size;
            if (Math.abs(acc) < 1e-6 * size) acc = 0;
            return n;
        }
        return { push, reset() { acc = 0; }, notch: (m) => notch[m || 0] || (m ? notch[m] : 0) };
    }
    root.ReflibWheel = { version: 1, create, IDLE_MS, NOTCH_MIN, DEFAULT_PX };
})(typeof globalThis !== "undefined" ? globalThis : window);
