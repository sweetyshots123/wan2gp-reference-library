// 1.11.1: shared rules for reviewing a person's suggestions as a grid (Galería Faces.tsx and Media Library reflib_faces.js).
// Everything starts kept; the user discards the wrong ones and confirms the rest in one person_review call.
// Clicks reuse selection_rules.js (ReflibSelection): Shift = discard the range from the anchor, otherwise toggle.
(function (g) {
    "use strict";
    // state: {discard:Set<id>, anchor:number}; ids: ordered face ids; returns the new anchor
    function click(state, ids, idx, ev) {
        const RS = g.ReflibSelection;
        const r = RS ? RS.boxClick(state.anchor, idx, { shift: !!ev.shift }) : { op: "toggle", anchor: idx };
        if (r.op === "range") {
            const [lo, hi] = RS.rangeBounds(r.from, r.to, ids.length - 1);
            for (let k = lo; k <= hi; k++) state.discard.add(ids[k]);
        } else { const id = ids[idx]; state.discard.has(id) ? state.discard.delete(id) : state.discard.add(id); }
        state.anchor = r.anchor !== undefined ? r.anchor : idx;
        return state;
    }
    // discard everything strictly below `pct` (0-100) similarity; raising it again brings them back unless discarded by hand
    function below(faces, pct) { return faces.filter(f => f.score != null && f.score * 100 < pct).map(f => f.id); }
    function plan(faces, discard, cut) {
        const low = new Set(cut ? below(faces, cut) : []);
        const accept = [], reject = [];
        for (const f of faces) (discard.has(f.id) || low.has(f.id) ? reject : accept).push(f.id);
        return { accept, reject };
    }
    // keyboard: arrows move the focus in a grid of `cols`, x / Delete discard, Enter confirm
    function key(k, focus, n, cols) {
        if (k === "ArrowRight") return { op: "move", to: Math.min(n - 1, focus + 1) };
        if (k === "ArrowLeft") return { op: "move", to: Math.max(0, focus - 1) };
        if (k === "ArrowDown") return { op: "move", to: Math.min(n - 1, focus + cols) };
        if (k === "ArrowUp") return { op: "move", to: Math.max(0, focus - cols) };
        if (k === "x" || k === "X" || k === "Delete") return { op: "discard" };
        if (k === "Enter") return { op: "confirm" };
        return null;
    }
    g.ReflibReview = { click, below, plan, key };
})(typeof globalThis !== "undefined" ? globalThis : window);
