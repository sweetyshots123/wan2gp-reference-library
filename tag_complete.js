// Reference Library 1.12.17 — tag input autocomplete, shared by the Galería and the Media Library (ReflibTagComplete).
// Pure rules (norm / rank / completion / inline) + a small DOM controller (attach) used by both "add tags" fields.
// - Inline completion: typing at the end completes with the first existing tag that starts with the typed text
//   (case- and accent-insensitive); the completed part is selected, so typing on replaces it. Tab accepts it; Enter
//   accepts it and adds as before. Deleting (Backspace / Delete / cut) never re-completes.
// - Suggestion list: prefix matches first, then word-start matches, then other "contains" matches.
(function (root) {
    "use strict";
    const norm = (s) => String(s == null ? "" : s).normalize("NFD").replace(/[\u0300-\u036f]/g, "").toLowerCase();
    const SEP = /[\s\-_/+.:()&|·]/;
    const LIST_SEP = /[,;]/;

    /** tags matching `typed`: prefix, then word start, then contains (stable within each group). */
    function rank(typed, tags, limit, exclude) {
        const q = norm(typed).trim();
        if (!q) return [];
        const ex = new Set((exclude || []).map(norm));
        const g = [[], [], []], seen = new Set();
        for (const t of tags || []) {
            const n = norm(t);
            if (seen.has(n) || ex.has(n)) continue;
            seen.add(n);
            let i = n.indexOf(q);
            if (i < 0) continue;
            if (i === 0) { g[0].push(t); continue; }
            let word = false;
            for (; i > 0; i = n.indexOf(q, i + 1)) if (SEP.test(n[i - 1])) { word = true; break; }
            g[word ? 1 : 2].push(t);
        }
        const out = g[0].concat(g[1], g[2]);
        return limit ? out.slice(0, limit) : out;
    }

    /** first tag that starts with `typed` (and is longer), in the given order. */
    function completion(typed, tags, exclude) {
        const q = norm(typed);
        if (!q.trim()) return null;
        const ex = new Set((exclude || []).map(norm));
        for (const t of tags || []) { const n = norm(t); if (n.length > q.length && n.startsWith(q) && !ex.has(n)) return t; }
        return null;
    }

    /** number of characters of `tag` that cover `typed` (accents may change lengths). */
    function prefixLen(tag, typed) {
        const q = norm(typed);
        for (let k = 0; k <= tag.length; k++) if (norm(tag.slice(0, k)).length >= q.length) return k;
        return tag.length;
    }

    /** the comma/semicolon-separated segment the caret is in: {start, end, text} (leading spaces skipped). */
    function segment(value, caret) {
        const v = String(value || ""), c = caret == null ? v.length : caret;
        let s = c; while (s > 0 && !LIST_SEP.test(v[s - 1])) s--;
        while (s < c && /\s/.test(v[s])) s++;
        let e = c; while (e < v.length && !LIST_SEP.test(v[e])) e++;
        return { start: s, end: e, text: v.slice(s, c) };
    }
    const others = (value, seg) => (value.slice(0, seg.start) + "," + value.slice(seg.end)).split(LIST_SEP).map((x) => x.trim()).filter(Boolean);

    /** inline completion after an input event: {value, selStart, selEnd, tag} or null. Only for insertions at the end. */
    function inline(value, caret, inputType, tags) {
        const v = String(value || "");
        if (!/^insert/.test(String(inputType || "")) || /^insertFromPaste|^insertLineBreak/.test(inputType)) return null;
        if (caret !== v.length) return null;
        const seg = segment(v, caret);
        if (!seg.text.trim()) return null;
        const t = completion(seg.text, tags, others(v, seg));
        if (!t) return null;
        const nv = v.slice(0, seg.start) + t;
        return { value: nv, selStart: seg.start + prefixLen(t, seg.text), selEnd: nv.length, tag: t };
    }

    /** replace the caret's segment with `tag` -> {value, caret}. */
    function accept(value, caret, tag) {
        const v = String(value || ""), seg = segment(v, caret);
        const nv = v.slice(0, seg.start) + tag + v.slice(seg.end);
        return { value: nv, caret: seg.start + tag.length };
    }

    // ---- DOM controller ----
    let css = false;
    function style() {
        if (css || typeof document === "undefined") return; css = true;
        const s = document.createElement("style");
        s.textContent = ".reflib-tc-list{position:fixed;z-index:100000;max-height:240px;overflow:auto;background:#1f2329;color:#e8e8e8;border:1px solid #444;border-radius:6px;box-shadow:0 6px 18px rgba(0,0,0,.4);font:13px system-ui,sans-serif;padding:3px 0;min-width:160px}" +
            ".reflib-tc-list div{padding:4px 10px;cursor:pointer;white-space:nowrap}.reflib-tc-list div.on,.reflib-tc-list div:hover{background:#3a4250}.reflib-tc-list b{font-weight:600;color:#fff}";
        document.head.appendChild(s);
    }
    const lists = new Map();   // key -> list element (one per field kind; a re-rendered input replaces it)
    function esc(s) { return String(s).replace(/[&<>"]/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;" }[c])); }
    function mark(t, q) {
        const qq = norm(q).trim(), i = norm(t).indexOf(qq);
        if (i < 0 || !qq) return esc(t);
        let k0 = 0; while (k0 < t.length && norm(t.slice(0, k0)).length < i) k0++;
        const k1 = k0 + prefixLen(t.slice(k0), qq);
        return esc(t.slice(0, k0)) + "<b>" + esc(t.slice(k0, k1)) + "</b>" + esc(t.slice(k1));
    }

    /** attach(input, getTags, {key, limit, onPick}) — idempotent per input element. */
    function attach(input, getTags, opts) {
        if (!input || input.__reflibTC) return input && input.__reflibTC;
        opts = opts || {};
        style();
        const key = opts.key || "tags";
        const old = lists.get(key); if (old) old.remove();
        const list = document.createElement("div"); list.className = "reflib-tc-list"; list.style.display = "none";
        list.setAttribute("role", "listbox"); list.dataset.key = key;
        document.body.appendChild(list); lists.set(key, list);
        let items = [], on = -1, inl = null;
        const tags = () => { try { return getTags() || []; } catch (e) { return []; } };
        function hide() { list.style.display = "none"; items = []; on = -1; }
        function show() {
            if (!input.isConnected) { list.remove(); return; }
            const v = input.value, c = input.selectionStart == null ? v.length : input.selectionStart;
            const seg = segment(v, c);
            items = rank(seg.text, tags(), opts.limit || 8, others(v, seg));
            if (!items.length || document.activeElement !== input) { hide(); return; }
            on = -1;
            list.innerHTML = items.map((t, i) => `<div data-i="${i}" role="option">${mark(t, seg.text)}</div>`).join("");
            const r = input.getBoundingClientRect();
            list.style.left = r.left + "px"; list.style.top = (r.bottom + 2) + "px"; list.style.minWidth = Math.max(160, r.width) + "px";
            list.style.display = "";
        }
        function hi(i) { on = i; [...list.children].forEach((el, k) => el.classList.toggle("on", k === i)); const el = list.children[i]; if (el && el.scrollIntoView) el.scrollIntoView({ block: "nearest" }); }
        function pick(t) {
            const c = inl ? inl.selStart : input.selectionStart;
            const r = accept(input.value, c, t);
            input.value = r.value; input.setSelectionRange(r.caret, r.caret); inl = null; hide();
            input.dispatchEvent(new Event("change", { bubbles: true }));
            if (opts.onPick) opts.onPick(t);
        }
        const inlineActive = () => inl && input.value === inl.value && input.selectionStart === inl.selStart && input.selectionEnd === inl.selEnd && inl.selEnd > inl.selStart;
        input.addEventListener("input", (e) => {
            inl = null;
            const r = inline(input.value, input.selectionStart, e.inputType, tags());
            if (r) { input.value = r.value; input.setSelectionRange(r.selStart, r.selEnd); inl = r; }
            show();
        });
        input.addEventListener("keydown", (e) => {
            const open = list.style.display !== "none" && items.length;
            if (e.key === "ArrowDown" && open) { e.preventDefault(); hi(Math.min(items.length - 1, on + 1)); return; }
            if (e.key === "ArrowUp" && open) { e.preventDefault(); hi(Math.max(-1, on - 1)); return; }
            if (e.key === "Escape") { if (inlineActive()) { e.preventDefault(); input.value = input.value.slice(0, inl.selStart) + input.value.slice(inl.selEnd); input.setSelectionRange(inl.selStart, inl.selStart); inl = null; } if (open) { e.preventDefault(); e.stopPropagation(); hide(); } return; }
            if ((e.key === "Enter" || e.key === "Tab") && open && on >= 0) { e.preventDefault(); e.stopPropagation(); pick(items[on]); return; }
            if (e.key === "Tab" && inlineActive()) { e.preventDefault(); const n = input.value.length; input.setSelectionRange(n, n); inl = null; hide(); return; }
            if (e.key === "Enter" && inlineActive()) { const n = input.value.length; input.setSelectionRange(n, n); inl = null; hide(); /* the field's own Enter adds it */ }
            if (e.key === "Enter") hide();
        });
        input.addEventListener("blur", () => setTimeout(hide, 120));
        input.addEventListener("focus", () => { if (input.value) show(); });
        list.addEventListener("mousedown", (e) => { e.preventDefault(); const d = e.target.closest("div[data-i]"); if (d) pick(items[+d.dataset.i]); });
        const api = { hide, show, get items() { return items.slice(); }, get inline() { return inl; }, list };
        input.__reflibTC = api;
        return api;
    }

    root.ReflibTagComplete = { version: 1, norm, rank, completion, prefixLen, segment, inline, accept, attach };
})(typeof globalThis !== "undefined" ? globalThis : window);
