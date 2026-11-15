// Reference Library 1.12.18+ (chips) - compact chip rows shared by the Media Library filter rows (Colecciones /
// Etiquetas, reference_library.js) and the Galería tag facets row (gallery/src/ChipRow.tsx imports this file).
// Pure, no DOM (tests/test_chip_rules.mjs):
//  · arrange(items): active chips first (always on the first, visible line, even collapsed), then the groups —
//    plain tags, then people (persona: / modelo:, shown without the prefix) — each most used first.
//  · match(item, q): accent/case-insensitive filter on the shown label or the full tag.
//  · hiddenCount(tops, firstTop): chips laid out below the first line (from their offsetTop) → the "+N" toggle.
//  · isOpen / setOpen: expanded state per row in localStorage ("reflib_chips_open_<row>"), same key in both UIs.
(function (root) {
    "use strict";
    const PEOPLE = ["persona:", "modelo:"];
    const fold = (v) => String(v || "").normalize("NFKD").replace(/[\u0300-\u036f]/g, "").toLowerCase();
    function split(tag) {
        const t = String(tag || ""), l = t.toLowerCase();
        const p = PEOPLE.find((x) => l.startsWith(x));
        return p ? { group: "people", name: t.slice(p.length).trim() } : { group: "", name: t };
    }
    function arrange(items) {
        // items: [{ id, label, count, active, fixed? }]; fixed = keep in front in the given order (e.g. "Todas", "Sin colección")
        const fixed = [], act = [], rest = [];
        items.forEach((x, i) => { const o = Object.assign({ i }, x); (x.fixed ? fixed : x.active ? act : rest).push(o); });
        const byCount = (a, b) => (b.count || 0) - (a.count || 0) || (fold(a.label) < fold(b.label) ? -1 : fold(a.label) > fold(b.label) ? 1 : a.i - b.i);
        const grp = (x) => (x.group === "people" ? 1 : 0);
        act.sort(byCount);
        rest.sort((a, b) => grp(a) - grp(b) || byCount(a, b));
        return fixed.concat(act, rest);
    }
    function tagItems(tags, isActive) {
        // tags: [{ tag, count }] → items with the people prefix moved into the group
        return (tags || []).map((x) => { const s = split(x.tag); return { id: x.tag, label: s.name, group: s.group, count: x.count || 0, active: !!isActive(x.tag) }; });
    }
    function match(item, q) {
        const f = fold(q).trim();
        return !f || item.active || item.fixed || fold(item.label).includes(f) || fold(item.id).includes(f);
    }
    function hiddenCount(tops, firstTop) {
        if (!tops.length) return 0;
        const t0 = firstTop == null ? Math.min.apply(null, tops) : firstTop;
        return tops.filter((t) => t > t0 + 2).length;
    }
    const KEY = (row) => "reflib_chips_open_" + row;
    function isOpen(store, row) { try { return (store || root.localStorage).getItem(KEY(row)) === "1"; } catch (e) { return false; } }
    function setOpen(store, row, on) { try { (store || root.localStorage).setItem(KEY(row), on ? "1" : "0"); } catch (e) {} }
    root.ReflibChips = { version: 1, PEOPLE, fold, split, arrange, tagItems, match, hiddenCount, isOpen, setOpen, KEY, LINES_OPEN: 3 };
})(typeof globalThis !== "undefined" ? globalThis : window);
