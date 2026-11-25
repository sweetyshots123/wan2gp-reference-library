// Reference Library 1.12.27 — shared explorer & Galería view-state persistence, stale-filter pruning, and reset rules
// (ReflibViewState). Loaded in plugin.py's shared JS tuple (vanilla Media Library) and imported by gallery/src/App.tsx.
// Pure, no DOM required (tests/test_view_state_rules.mjs).
(function (root) {
    "use strict";
    const KEYS = {
        ml: "reflib_ml_view_state",
        gal: "reflib_gal_view_state",
        remember: "reflib_remember_state",
    };
    const SORTS = ["date_desc", "date_asc", "name_asc", "name_desc"];
    const KINDS = ["image", "video", "audio", "mask"];
    const GAL_KINDS = ["image", "video", "audio"];
    const ORIGINS = ["ai", "real"];
    const JST_KEYS = ["queued", "processing", "done", "failed", "local", "never"];
    const CHIP_KINDS = ["persona", "tag", "col", "text", "auto"];

    const fold = (v) => String(v || "").normalize("NFKD").replace(/[\u0300-\u036f]/g, "").toLowerCase();
    const uniqStr = (arr) => {
        const out = [], seen = new Set();
        for (const x of arr || []) {
            const s = String(x || "");
            if (s && !seen.has(s)) { seen.add(s); out.push(s); }
        }
        return out;
    };
    const cleanSort = (v, def) => (SORTS.includes(v) ? v : (SORTS.includes(def) ? def : "date_desc"));
    const cleanOrigins = (arr) => {
        const out = uniqStr(arr).filter((x) => ORIGINS.includes(x)).sort();
        return out.length >= 2 ? [] : out;
    };
    const cleanRanges = (obj) => {
        const out = {};
        if (!obj || typeof obj !== "object" || Array.isArray(obj)) return out;
        for (const [k, v] of Object.entries(obj)) {
            if (!k || !Array.isArray(v) || v.length < 2) continue;
            const a = Number(v[0]), b = Number(v[1]);
            if (Number.isFinite(a) && Number.isFinite(b)) out[String(k)] = [a, b];
        }
        return out;
    };
    const cleanChipQ = (obj) => {
        const out = {};
        if (!obj || typeof obj !== "object" || Array.isArray(obj)) return out;
        for (const [k, v] of Object.entries(obj)) {
            const s = typeof v === "string" ? v : "";
            if (k && s) out[String(k)] = s;
        }
        return out;
    };

    function getStore(store) {
        if (store !== undefined) return store;
        try { return root.localStorage || null; } catch (e) { return null; }
    }
    function loadRaw(store, key) {
        const st = getStore(store);
        if (!st) return null;
        try {
            const raw = st.getItem(key);
            if (!raw) return null;
            const parsed = JSON.parse(raw);
            return parsed && typeof parsed === "object" && !Array.isArray(parsed) ? parsed : null;
        } catch (e) { return null; }
    }
    function saveRaw(store, key, data) {
        const st = getStore(store);
        if (!st) return false;
        try { st.setItem(key, JSON.stringify(data)); return true; } catch (e) { return false; }
    }
    function clearRaw(store, key) {
        const st = getStore(store);
        if (!st) return false;
        try { st.removeItem(key); return true; } catch (e) { return false; }
    }

    function shouldRemember(settings, store) {
        if (typeof settings === "boolean") return settings;
        if (settings && typeof settings.browser_remember_state === "boolean") return settings.browser_remember_state;
        if (settings && typeof settings.remember_state === "boolean") return settings.remember_state;
        const st = getStore(store);
        if (st) {
            try {
                const v = st.getItem(KEYS.remember);
                if (v === "0") return false;
                if (v === "1") return true;
            } catch (e) {}
        }
        return true;
    }
    function syncRememberFlag(store, on) {
        const st = getStore(store);
        const keep = on !== false;
        if (st) {
            try { st.setItem(KEYS.remember, keep ? "1" : "0"); } catch (e) {}
        }
        if (!keep) {
            clearML(st);
            clearGal(st);
        }
        return keep;
    }

    // ---- Media Library (vanilla JS explorer) ----
    function mlDefaultFilter() {
        return {
            cols: [], none: false, folders: [], tags: [], q: "",
            node: null, sub: true, recent: false, used: false,
            atags: [], xtags: [], ranges: {}, jst: "",
            kind: "", hasmask: false, missing: false, origins: [], fav: false, sim: "",
        };
    }
    function mlDefaultState(defaultSort) {
        return {
            v: 1,
            f: mlDefaultFilter(),
            sort: cleanSort(defaultSort, "date_desc"),
            recentPages: 1,
            expanded: [],
            chipQ: {},
            atOpen: [],
            scroll: 0,
            treeScroll: 0,
        };
    }
    function mlNormalize(raw, defaultSort) {
        const base = mlDefaultState(defaultSort);
        if (!raw || typeof raw !== "object") return base;
        const rf = raw.f && typeof raw.f === "object" ? raw.f : {};
        const f = mlDefaultFilter();
        f.cols = uniqStr(rf.cols);
        f.none = !!rf.none;
        f.folders = uniqStr(rf.folders);
        f.tags = uniqStr(rf.tags).map((t) => fold(t)).filter(Boolean);
        f.q = typeof rf.q === "string" ? rf.q : "";
        f.sub = rf.sub !== false;
        f.used = !!rf.used;
        f.recent = !!rf.recent && !f.used;
        if (!f.recent && !f.used && rf.node && typeof rf.node === "object" && rf.node.fid) {
            f.node = { fid: String(rf.node.fid), rel: String(rf.node.rel || "") };
        }
        f.atags = uniqStr(rf.atags);
        f.xtags = uniqStr(rf.xtags);
        f.ranges = cleanRanges(rf.ranges);
        f.jst = JST_KEYS.includes(rf.jst) ? rf.jst : "";
        f.kind = KINDS.includes(rf.kind) ? rf.kind : "";
        f.hasmask = !!rf.hasmask;
        f.missing = !!rf.missing;
        f.origins = cleanOrigins(rf.origins);
        f.fav = !!rf.fav;
        f.sim = "";   // similarity sessions are ephemeral in server memory
        const sort = f.used && raw.sort === "used" ? "used" : cleanSort(raw.sort, defaultSort);
        const rp = Math.max(1, Math.min(100, Math.round(Number(raw.recentPages) || 1)));
        const expanded = uniqStr(raw.expanded);
        const chipQ = cleanChipQ(raw.chipQ);
        const atOpen = uniqStr(raw.atOpen);
        const scroll = Math.max(0, Math.round(Number(raw.scroll) || 0));
        const treeScroll = Math.max(0, Math.round(Number(raw.treeScroll) || 0));
        return { v: 1, f, sort, recentPages: rp, expanded, chipQ, atOpen, scroll, treeScroll };
    }
    function mlFromState(src, defaultSort) {
        const s = src || {};
        const f = s.f || {};
        const toArr = (v) => (v instanceof Set ? [...v] : Array.isArray(v) ? v : []);
        return mlNormalize({
            f: {
                cols: toArr(f.cols),
                none: !!f.none,
                folders: toArr(f.folders),
                tags: toArr(f.tags),
                q: f.q || "",
                node: f.node || null,
                sub: f.sub !== false,
                recent: !!f.recent,
                used: !!f.used,
                atags: toArr(f.atags),
                xtags: toArr(f.xtags),
                ranges: f.ranges || {},
                jst: f.jst || "",
                kind: f.kind || "",
                hasmask: !!f.hasmask,
                missing: !!f.missing,
                origins: toArr(f.origins),
                fav: !!f.fav,
                sim: "",
            },
            sort: s.sort,
            recentPages: s.recentPages,
            expanded: toArr(s.expanded),
            chipQ: s.chipQ || {},
            atOpen: toArr(s.atOpen),
            scroll: s.scroll,
            treeScroll: s.treeScroll,
        }, defaultSort);
    }
    function folderRelMap(meta, fid) {
        if (meta && meta.tree && meta.tree[fid]) return meta.tree[fid];
        if (meta && Array.isArray(meta.folders)) {
            const fld = meta.folders.find((x) => x && String(x.id || "") === fid);
            if (fld && fld.tree && typeof fld.tree === "object") {
                const map = {};
                const walk = (n) => {
                    if (!n || typeof n !== "object") return;
                    if (typeof n.rel === "string") map[n.rel] = n;
                    if (Array.isArray(n.children)) for (const ch of n.children) walk(ch);
                };
                walk(fld.tree);
                return map;
            }
        }
        return null;
    }
    function mlPruneStale(state, meta) {
        const st = mlNormalize(state);
        if (!meta || typeof meta !== "object") return { state: st, changed: false };
        let changed = false;
        const f = st.f;
        if (Array.isArray(meta.collections)) {
            const cols = new Set(meta.collections.map((c) => c && String(c.id || "")).filter(Boolean));
            const next = f.cols.filter((c) => cols.has(c));
            if (next.length !== f.cols.length) { f.cols = next; changed = true; }
        }
        if (Array.isArray(meta.folders)) {
            const fids = new Set(meta.folders.map((x) => x && String(x.id || "")).filter(Boolean));
            const nextFolders = f.folders.filter((id) => fids.has(id));
            if (nextFolders.length !== f.folders.length) { f.folders = nextFolders; changed = true; }
            if (f.node && !fids.has(f.node.fid)) { f.node = null; changed = true; }
            const nextExp = st.expanded.filter((key) => {
                const bar = String(key).indexOf("|");
                const fid = bar >= 0 ? key.slice(0, bar) : key;
                const rel = bar >= 0 ? key.slice(bar + 1) : "";
                if (!fids.has(fid)) return false;
                const branch = rel ? folderRelMap(meta, fid) : null;
                if (rel && branch && !(rel in branch)) return false;
                return true;
            });
            if (nextExp.length !== st.expanded.length) { st.expanded = nextExp; changed = true; }
        }
        if (f.node && f.node.rel) {
            const branch = folderRelMap(meta, f.node.fid);
            if (branch && !(f.node.rel in branch)) {
                const parts = f.node.rel.split("/").filter(Boolean);
                let found = null;
                for (let k = parts.length - 1; k >= 0; k--) {
                    const rel = parts.slice(0, k).join("/");
                    if (rel in branch) { found = { fid: f.node.fid, rel }; break; }
                }
                f.node = found;
                changed = true;
            }
        }
        if (Array.isArray(meta.tags)) {
            const tset = new Set(meta.tags.map((t) => fold(typeof t === "string" ? t : (t && t.tag))).filter(Boolean));
            const nextTags = f.tags.filter((t) => tset.has(fold(t)));
            if (nextTags.length !== f.tags.length) { f.tags = nextTags; changed = true; }
        }
        return { state: st, changed };
    }
    function mlHasActiveFilters(f, chipQ, sort, defaultSort) {
        const s = f || {};
        const count = (v) => (v instanceof Set ? v.size : Array.isArray(v) ? v.length : 0);
        if (String(s.q || "").trim()) return true;
        if (count(s.cols) || s.none || count(s.folders) || count(s.tags)) return true;
        if (s.node || s.sub === false || s.recent || s.used) return true;
        if (count(s.atags) || count(s.xtags) || Object.keys(s.ranges || {}).length || s.jst) return true;
        if (s.kind || s.hasmask || s.missing || count(s.origins) || s.fav || s.sim) return true;
        if (chipQ && Object.values(chipQ).some((v) => String(v || "").trim())) return true;
        if (sort) {
            const def = cleanSort(defaultSort, "date_desc");
            if (sort !== def && !(s.used && sort === "used") && !(s.sim && sort === "sim")) return true;
        }
        return false;
    }
    function loadML(store, defaultSort) {
        const raw = loadRaw(store, KEYS.ml);
        return raw ? mlNormalize(raw, defaultSort) : null;
    }
    function saveML(store, state, defaultSort) {
        return saveRaw(store, KEYS.ml, mlFromState(state, defaultSort));
    }
    function clearML(store) {
        return clearRaw(store, KEYS.ml);
    }

    // ---- Galería (React SPA) ----
    function galDefaultState(defaultSort) {
        return {
            v: 1,
            route: "#/",
            text: "",
            chips: [],
            kinds: [],
            origins: [],
            sort: cleanSort(defaultSort, "date_desc"),
            extraTags: [],
            chipQ: {},
            af: { atags: [], xtags: [], ranges: {}, jst: "" },
            afOpen: [],
            fpanel: false,
            fopen: true,
            manage: false,
            size: 220,
            scroll: 0,
        };
    }
    function galNormalize(raw, defaultSort) {
        const base = galDefaultState(defaultSort);
        if (!raw || typeof raw !== "object") return base;
        const route = typeof raw.route === "string" && raw.route.startsWith("#/") ? raw.route : "#/";
        const text = typeof raw.text === "string" ? raw.text : "";
        const chips = Array.isArray(raw.chips) ? raw.chips.filter((c) =>
            c && typeof c === "object" && CHIP_KINDS.includes(c.k) && typeof c.v === "string" && c.v.length > 0
        ).map((c) => ({ k: c.k, v: c.v, label: typeof c.label === "string" && c.label ? c.label : c.v })) : [];
        const kinds = uniqStr(raw.kinds).filter((k) => GAL_KINDS.includes(k));
        const origins = cleanOrigins(raw.origins);
        const sort = cleanSort(raw.sort, defaultSort);
        const extraTags = uniqStr(raw.extraTags);
        const chipQ = cleanChipQ(raw.chipQ);
        const raf = raw.af && typeof raw.af === "object" ? raw.af : {};
        const af = {
            atags: uniqStr(raf.atags),
            xtags: uniqStr(raf.xtags),
            ranges: cleanRanges(raf.ranges),
            jst: JST_KEYS.includes(raf.jst) ? raf.jst : "",
        };
        const afOpen = uniqStr(raw.afOpen);
        const fpanel = !!raw.fpanel;
        const fopen = raw.fopen !== false;
        const manage = !!raw.manage;
        const sizeNum = Number(raw.size);
        const size = Number.isFinite(sizeNum) ? Math.max(120, Math.min(420, Math.round(sizeNum))) : 220;
        const scroll = Math.max(0, Math.round(Number(raw.scroll) || 0));
        return { v: 1, route, text, chips, kinds: kinds.length >= 3 ? [] : kinds, origins, sort, extraTags, chipQ, af, afOpen, fpanel, fopen, manage, size, scroll };
    }
    function resolveStartupRoute(currentHash, savedRoute, remember) {
        const cur = String(currentHash || "");
        if (remember === false) return cur || "#/";
        if ((!cur || cur === "#" || cur === "#/") && typeof savedRoute === "string" && savedRoute.startsWith("#/") && savedRoute !== "#/" && savedRoute !== "#/similares") {
            return savedRoute;
        }
        return cur || "#/";
    }
    function galPruneStale(state, meta, hasSimRef) {
        const st = galNormalize(state);
        if (!meta || typeof meta !== "object") return { state: st, changed: false };
        let changed = false;
        const cols = Array.isArray(meta.collections) ? new Set(meta.collections.map((c) => c && String(c.id || "")).filter(Boolean)) : null;
        const fids = Array.isArray(meta.folders) ? new Set(meta.folders.map((x) => x && String(x.id || "")).filter(Boolean)) : null;
        const tset = Array.isArray(meta.tags) ? new Set(meta.tags.map((t) => fold(typeof t === "string" ? t : (t && t.tag))).filter(Boolean)) : null;

        const nextChips = st.chips.filter((c) => {
            if (c.k === "col" && cols) return cols.has(c.v);
            if ((c.k === "tag" || c.k === "persona") && tset) return tset.has(fold(c.v));
            return true;
        });
        if (nextChips.length !== st.chips.length) { st.chips = nextChips; changed = true; }

        if (tset) {
            const nextExtra = st.extraTags.filter((t) => tset.has(fold(t)));
            if (nextExtra.length !== st.extraTags.length) { st.extraTags = nextExtra; changed = true; }
        }

        const parts = st.route.replace(/^#\/?/, "").split("/").map((x) => {
            try { return decodeURIComponent(x || ""); } catch (e) { return x || ""; }
        });
        const [a, b, c] = parts;
        if (a === "coleccion" && b && cols && !cols.has(b)) {
            st.route = "#/"; changed = true;
        } else if (a === "carpeta" && b && fids) {
            if (!fids.has(b)) {
                st.route = "#/carpetas"; changed = true;
            } else if (c) {
                const branch = folderRelMap(meta, b);
                if (branch && !(c in branch)) {
                    const segs = c.split("/").filter(Boolean);
                    let found = null;
                    for (let k = segs.length - 1; k >= 0; k--) {
                        const rel = segs.slice(0, k).join("/");
                        if (rel in branch) { found = rel; break; }
                    }
                    st.route = found != null ? `#/carpeta/${encodeURIComponent(b)}/${encodeURIComponent(found)}` : "#/carpetas";
                    changed = true;
                }
            }
        } else if (a === "tag" && b && tset && !tset.has(fold(b))) {
            st.route = "#/"; changed = true;
        } else if (a === "similares" && hasSimRef === false) {
            st.route = "#/"; changed = true;
        }
        return { state: st, changed };
    }
    function galHasActiveFilters(state, defaultSort) {
        const s = galNormalize(state, defaultSort);
        const def = cleanSort(defaultSort, "date_desc");
        if (s.route && s.route !== "#/") return true;
        if (s.text.trim()) return true;
        if (s.chips.length || s.kinds.length || s.origins.length || s.extraTags.length) return true;
        if (Object.values(s.chipQ).some((v) => String(v || "").trim())) return true;
        if (s.af.atags.length || s.af.xtags.length || Object.keys(s.af.ranges).length || s.af.jst) return true;
        if (s.sort !== def) return true;
        return false;
    }
    function loadGal(store, defaultSort) {
        const raw = loadRaw(store, KEYS.gal);
        return raw ? galNormalize(raw, defaultSort) : null;
    }
    function saveGal(store, state, defaultSort) {
        return saveRaw(store, KEYS.gal, galNormalize(state, defaultSort));
    }
    function clearGal(store) {
        return clearRaw(store, KEYS.gal);
    }

    root.ReflibViewState = {
        version: 1,
        KEYS,
        SORTS,
        shouldRemember,
        syncRememberFlag,
        loadRaw,
        saveRaw,
        clearRaw,
        mlDefaultFilter,
        mlDefaultState,
        mlNormalize,
        mlFromState,
        mlPruneStale,
        mlHasActiveFilters,
        loadML,
        saveML,
        clearML,
        galDefaultState,
        galNormalize,
        resolveStartupRoute,
        galPruneStale,
        galHasActiveFilters,
        loadGal,
        saveGal,
        clearGal,
    };
})(typeof globalThis !== "undefined" ? globalThis : window);
