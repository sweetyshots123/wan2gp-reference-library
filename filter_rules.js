// Reference Library 1.12.18 — shared library filters for both UIs (ReflibFilters).
// Favourites: one rule everywhere. An item is a favourite when it has the "favorita" tag (case-insensitive); the query
// filter is `fav: true`, which the core (imagelib._clean_filter) turns into that tag filter. The Galería's ♥ Favoritas
// view and the Media Library Explorador's ♥ Favoritas toggle both send it.
(function (root) {
    "use strict";
    const FAV_TAG = "favorita";
    const isFav = (tags) => (tags || []).some((t) => String(t || "").toLowerCase() === FAV_TAG);
    /** count of favourites from the library's tag list ([{tag, count|n}] or strings). */
    function favCount(tags) {
        let n = 0;
        for (const t of tags || []) { if (t && typeof t === "object" && String(t.tag || "").toLowerCase() === FAV_TAG) n += Number(t.count != null ? t.count : t.n) || 0; }
        return n;
    }
    /** the filter with favourites on / off (a copy; other keys untouched). */
    function withFav(f, on) { const o = Object.assign({}, f || {}); if (on) o.fav = true; else delete o.fav; return o; }
    /** tag add/remove payload to toggle one item's favourite. */
    const favToggle = (tags) => (isFav(tags) ? { remove: [FAV_TAG] } : { add: [FAV_TAG] });
    root.ReflibFilters = { version: 1, FAV_TAG, isFav, favCount, withFav, favToggle };
})(typeof globalThis !== "undefined" ? globalThis : window);
