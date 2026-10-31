// Reference Library 1.9.6-simperf - selection rules shared by the Media Library (reference_library.js, prepended by
// plugin.py) and the Galería (gallery/src/Selection.ts imports this same file). Pure functions, no DOM:
// each returns what to do and the new anchor; the UI applies it to its own selection set.
(function (root) {
    "use strict";
    // Click on a card. ev = {shift, ctrl} (ctrl = Ctrl or Cmd); isSelected = card already in the selection.
    //  shift + anchor        -> range anchor..idx (Ctrl+Shift adds to the selection, Shift alone replaces it)
    //  ctrl                  -> toggle the card, anchor = idx
    //  plain, not selected   -> select only this card ("single"), anchor = idx, then preview
    //  plain, selected       -> keep the selection ("keep"), anchor = idx, then preview
    function cardClick(anchor, idx, isSelected, ev) {
        if (ev.shift && anchor >= 0) return { op: "range", from: anchor, to: idx, additive: !!ev.ctrl, anchor: anchor };
        if (ev.ctrl) return { op: "toggle", anchor: idx };
        return { op: isSelected ? "keep" : "single", anchor: idx, preview: true };
    }
    // Click on a card's select circle / checkbox: toggle without opening; Shift = additive range from the anchor.
    function boxClick(anchor, idx, ev) {
        if (ev.shift && anchor >= 0 && anchor !== idx) return { op: "range", from: anchor, to: idx, additive: true, anchor: idx };
        return { op: "toggle", anchor: idx };
    }
    // Inclusive index bounds of a range, capped at max items.
    function rangeBounds(from, to, max) {
        const a = Math.max(0, Math.min(from, to)), b = Math.max(0, Math.max(from, to));
        return [a, Math.min(b, a + (max || 50000) - 1)];
    }
    // Keys: Ctrl/Cmd+A -> select every matching item; Esc -> clear when something is selected.
    function key(ev, hasSelection) {
        if ((ev.ctrl) && (ev.key === "a" || ev.key === "A")) return { op: "all" };
        if (ev.key === "Escape" && hasSelection) return { op: "clear" };
        return null;
    }
    // Apply an op to a Set of hashes; hashesOf(a, b) gives the hashes for an index range (sync).
    function apply(set, r, hash, hashesOf) {
        if (r.op === "toggle") { set.has(hash) ? set.delete(hash) : set.add(hash); }
        else if (r.op === "single") { set.clear(); set.add(hash); }
        else if (r.op === "clear") set.clear();
        else if (r.op === "range" && hashesOf) { if (!r.additive) set.clear(); const [a, b] = rangeBounds(r.from, r.to); hashesOf(a, b).forEach((h) => set.add(h)); }
        return set;
    }
    root.ReflibSelection = { version: 1, cardClick, boxClick, rangeBounds, key, apply };
})(typeof globalThis !== "undefined" ? globalThis : window);
