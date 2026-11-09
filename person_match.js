// Reference Library 1.12.10 — shared person-name matching (Galería NameBox + Media Library Personas).
// Fold: lowercase + strip accents. Rank: exact fold, then prefix, then substring. Dedupes by fold.
// attach(): same ↑↓/Enter/Tab dropdown for vanilla DOM (Media Library); Galería React uses match/resolve.
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
    /**
     * Keyboard helper shared by Galería NameBox and Media Library attach().
     * Returns { hi, open, commit, close } patches; commit is the name to accept (or null).
     */
    function keyStep(key, st) {
        const hits = st.hits || [];
        let hi = st.hi | 0, open = !!st.open;
        const v = String(st.v || "");
        if (key === "ArrowDown" && hits.length) return { hi: (hi + 1) % hits.length, open: true, commit: null, close: false };
        if (key === "ArrowUp" && hits.length) return { hi: (hi - 1 + hits.length) % hits.length, open: true, commit: null, close: false };
        if ((key === "Enter" || key === "Tab") && v.trim()) {
            const pick = open && hits[hi] ? hits[hi] : v;
            return { hi: 0, open: false, commit: pick, close: true };
        }
        if (key === "Escape") return { hi: 0, open: false, commit: null, close: true };
        return null;
    }
    /**
     * Enhance a text <input> with the shared dropdown (Media Library Personas).
     * opts: { getNames: () => string[], onCommit: (name) => void, limit?: number }
     */
    function attach(input, opts) {
        if (!input || input._reflibPm) return input;
        const getNames = opts.getNames || (() => opts.names || []);
        const onCommit = opts.onCommit || function () {};
        const limit = opts.limit || 8;
        input._reflibPm = true;
        input.removeAttribute("list");
        input.setAttribute("autocomplete", "off");
        let wrap = input.parentElement;
        if (!wrap || !wrap.classList.contains("reflib-pm-wrap")) {
            wrap = document.createElement("span");
            wrap.className = "reflib-pm-wrap";
            input.parentNode.insertBefore(wrap, input);
            wrap.appendChild(input);
        }
        let ul = wrap.querySelector(".reflib-pm-sug");
        if (!ul) {
            ul = document.createElement("ul");
            ul.className = "reflib-pm-sug";
            ul.setAttribute("role", "listbox");
            wrap.appendChild(ul);
        }
        const st = { hi: 0, open: false };
        function names() { return getNames() || []; }
        function render() {
            const hits = match(input.value, names(), limit);
            st.hits = hits;
            if (!st.open || !String(input.value || "").trim() || !hits.length) {
                ul.hidden = true; ul.innerHTML = ""; return;
            }
            ul.hidden = false;
            ul.innerHTML = hits.map((n, i) =>
                `<li class="${i === st.hi ? "on" : ""}" role="option" data-i="${i}">${n.replace(/&/g, "&amp;").replace(/</g, "&lt;")}</li>`
            ).join("");
        }
        function commit(raw) {
            const name = resolve(raw != null ? raw : input.value, names());
            if (!name) return;
            input.value = "";
            st.open = false; st.hi = 0; render();
            onCommit(name);
        }
        input.addEventListener("input", () => { st.open = true; st.hi = 0; render(); });
        input.addEventListener("focus", () => { st.open = true; render(); });
        input.addEventListener("blur", () => {
            setTimeout(() => {
                st.open = false; render();
                const v = String(input.value || "").trim();
                if (v && names().some((n) => fold(n) === fold(v))) commit(v);
            }, 120);
        });
        input.addEventListener("keydown", (e) => {
            const hits = match(input.value, names(), limit);
            const step = keyStep(e.key, { hits, hi: st.hi, open: st.open, v: input.value });
            if (!step) return;
            e.preventDefault();
            st.hi = step.hi; st.open = step.open;
            if (step.commit) commit(step.commit);
            else render();
        });
        ul.addEventListener("mousedown", (e) => {
            const li = e.target.closest("li");
            if (!li) return;
            e.preventDefault();
            const hits = match(input.value, names(), limit);
            commit(hits[+li.dataset.i] || li.textContent);
        });
        return input;
    }
    root.ReflibPersonMatch = { version: 2, fold, match, resolve, keyStep, attach };
})(typeof globalThis !== "undefined" ? globalThis : window);
