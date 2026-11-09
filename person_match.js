// Reference Library 1.12.9 — shared person-name matching (Galería NameBox + Media Library Personas).
// Fold: lowercase + strip accents. Rank: exact fold, then prefix, then substring. Dedupes by fold.
(function (root) {
    "use strict";
    function fold(s) {
        return String(s || "").normalize("NFKD").replace(/[\u0300-\u036f]/g, "").trim().toLowerCase();
    }
    function match(query, names, limit) {
        const q = fold(query);
        const lim = Math.max(1, Math.min(50, Number(limit) || 12));
        if (!q) return [];
        const pref = [], sub = [], seen = new Set();
        for (const name of names || []) {
            const fn = fold(name);
            if (!fn || seen.has(fn)) continue;
            if (fn === q) { pref.unshift(name); seen.add(fn); continue; }
            if (fn.startsWith(q)) { pref.push(name); seen.add(fn); }
            else if (fn.includes(q)) { sub.push(name); seen.add(fn); }
        }
        return pref.concat(sub).slice(0, lim);
    }
    /** Canonical existing name if fold-equal, else the trimmed typed value (new person). */
    function resolve(query, names) {
        const q = fold(query);
        if (!q) return "";
        for (const name of names || []) if (fold(name) === q) return name;
        return String(query || "").trim();
    }
    root.ReflibPersonMatch = { version: 1, fold, match, resolve };
})(typeof globalThis !== "undefined" ? globalThis : window);
