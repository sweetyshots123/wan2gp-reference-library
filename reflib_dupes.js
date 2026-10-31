// 1.11.0 Reference Library: Duplicates in the classic explorer. All logic is server-side (reflib_core/dupes.py,
// dup_scan / dup_status / dup_groups / dup_resolve, DUPES_API.md); the Galería «Duplicados» page calls the same actions.
// Deleting uses the explorer's own delete flow (forget_plan dialog → forget, or delete_all for library-owned copies).
(function () {
    "use strict";
    const RL = window.referenceLibrary;
    if (!RL || !RL.extend || RL.dupesLoaded) return;
    RL.dupesLoaded = true;
    const S = {
        en: { open: "Duplicates", title: "Duplicates", scan: "Find duplicates", status: "{h} photos analysed · {g} groups · {w} recoverable", running: "Analysing {d} / {t}…",
              thr: "Similarity", thr_tip: "Allowed difference (pHash bits): 0 = identical only, higher = also crops / recompressions", all: "All", exact: "Identical", near: "Near-identical",
              transfer: "Move tags", transfer_tip: "Move tags, favorites and people to the copy that is kept", keepall: "Keep the largest in all groups", keep: "Keep marked",
              g_exact: "Identical", g_near: "Near-identical (difference {d})", copies: "{n} copies", rec: "{w} recoverable", big: "Largest", small: "Smallest", ia: "AI", video: "Video",
              k: "✓ Keep", l: "Remove", in_col: "in a collection", tags: "{n} tag(s)", none: "No duplicates at this similarity.", first: "Press «Find duplicates» to analyse your photos.",
              q_all: "Keep the largest copy in {g} group(s) and remove the other {n}?\n\nIdentical copies of the same file go to the Recycle Bin; for the rest the usual delete dialog opens.", q_tr: "\nTags, favorites and people move to the kept copy.", q_one: "Keep the selected copy and remove the other {n}?\n\nIdentical copies of the same file go to the Recycle Bin; for the rest the usual delete dialog opens.", q_del: "Remove {n} item(s) from the library? You can undo it.",
              recycled: "{n} identical copies sent to the Recycle Bin", more: "More groups", close: "Close", err: "Error: {e}" },
        es: { open: "Duplicados", title: "Duplicados", scan: "Buscar duplicados", status: "{h} fotos analizadas · {g} grupos · {w} recuperables", running: "Analizando {d} / {t}…",
              thr: "Parecido", thr_tip: "Diferencia permitida (bits de pHash): 0 = solo idénticas, más alto = también recortes / recompresiones", all: "Todos", exact: "Idénticos", near: "Casi iguales",
              transfer: "Pasar etiquetas", transfer_tip: "Mueve etiquetas, favoritos y personas a la copia que se conserva", keepall: "Conservar la más grande en todos", keep: "Conservar la marcada",
              g_exact: "Idénticos", g_near: "Casi iguales (diferencia {d})", copies: "{n} copias", rec: "{w} recuperables", big: "Más grande", small: "Más pequeña", ia: "IA", video: "Vídeo",
              k: "✓ Conservar", l: "Quitar", in_col: "en colección", tags: "{n} etiqueta(s)", none: "No hay duplicados con este parecido.", first: "Pulsa «Buscar duplicados» para analizar las fotos.",
              q_all: "¿Conservar la copia más grande en {g} grupo(s) y quitar las otras {n}?\n\nLas copias idénticas del mismo archivo van a la Papelera; para el resto se abre el diálogo de borrado de siempre.", q_tr: "\nLas etiquetas, favoritos y personas pasan a la copia que se conserva.", q_one: "¿Conservar la copia elegida y quitar las otras {n}?\n\nLas copias idénticas del mismo archivo van a la Papelera; para el resto se abre el diálogo de borrado de siempre.", q_del: "¿Quitar {n} elemento(s) de la librería? Se puede deshacer.",
              recycled: "{n} copia(s) idénticas enviadas a la Papelera", more: "Ver más grupos", close: "Cerrar", err: "Error: {e}" },
    };
    const lang = () => (RL.lang && RL.lang() === "es" ? "es" : "en");
    const dt = (k, p = {}) => String((S[lang()] || S.en)[k] ?? S.en[k] ?? k).replace(/\{(\w+)\}/g, (m, n) => (p[n] ?? m));
    const esc = RL.esc;
    const ilib = () => RL.ilibState();
    const call = (req) => RL.sendIlib(req).then(r => { if (r && r.ok === false) { RL.toast(dt("err", { e: r.error || r.message || "?" }), "warn"); throw r; } return r; });
    const fmtB = b => b >= 1048576 ? (b / 1048576).toFixed(1) + " MB" : Math.max(1, Math.round(b / 1024)) + " KB";
    const fmtD = t => t ? new Date(t * 1000).toLocaleString(lang() === "es" ? "es-ES" : "en-GB", { dateStyle: "short", timeStyle: "short" }) : "";
    const thumbs = new Map();
    function needThumbs(hs) {
        const want = [...new Set(hs)].filter(h => !thumbs.has(h)), out = [];
        for (let i = 0; i < want.length; i += 24) out.push(RL.sendIlib({ action: "thumbs", hashes: want.slice(i, i + 24) }).then(r => Object.entries((r && r.thumbs) || {}).forEach(([h, d]) => thumbs.set(h, d))).catch(() => {}));
        return Promise.all(out);
    }
    let pan = null, st = null, data = null, poll = null;
    const V = { thr: Number(localStorage.getItem("reflib.dupthr") || 6), kind: "", limit: 30, transfer: true, keep: {} };
    function planOf(g, k) {
        const keep = g.rows[k];
        if (g.same_item) return { keep: keep.hash, drop: [], copies: g.rows.filter((_, i) => i !== k).map(r => r.path) };
        return { keep: keep.hash, drop: [...new Set(g.rows.filter(r => r.hash !== keep.hash).map(r => r.hash))], copies: [] };
    }
    function open() {
        close();
        pan = document.createElement("div"); pan.className = "reflib-fc-pan reflib-dp-pan"; pan.setAttribute("role", "dialog");
        const root = ilib().root && ilib().root.querySelector(".reflib-ib-modal");
        (root || document.body).appendChild(pan);
        pan.addEventListener("click", onClick); pan.addEventListener("input", onInput); pan.addEventListener("change", onInput);
        refresh();
    }
    function close() { if (pan) pan.remove(); pan = null; clearTimeout(poll); }
    function refresh() {
        clearTimeout(poll);
        Promise.all([call({ action: "dup_status" }), call({ action: "dup_groups", threshold: V.thr, kind: V.kind, limit: V.limit })]).then(([s, g]) => {
            st = s.dupes; data = g;
            return needThumbs((g.groups || []).flatMap(x => x.rows.map(r => r.hash)));
        }).then(draw).catch(() => draw());
    }
    function draw() {
        if (!pan) return;
        const gs = (data && data.groups) || [];
        const stat = st ? dt("status", { h: st.hashed, g: data ? data.count : 0, w: fmtB((data && data.waste) || 0) }) + (st.running ? " · " + dt("running", { d: st.done, t: st.total }) : "") : "…";
        const seg = [["", "all"], ["exact", "exact"], ["near", "near"]].map(([k, l]) => `<button type="button" class="reflib-ib-btn ${V.kind === k ? "on" : ""}" data-dp="kind" data-k="${k}">${esc(dt(l))}</button>`).join("");
        const grp = g => { const k = V.keep[g.id] ?? g.keep; return `<div class="reflib-dp-g"><div class="reflib-dp-gh"><b>${esc(g.kind === "exact" ? dt("g_exact") : dt("g_near", { d: g.dist }))}</b> · ${esc(dt("copies", { n: g.rows.length }))} · ${esc(dt("rec", { w: fmtB(g.waste) }))}
            <button type="button" class="reflib-ib-btn" data-dp="keep1" data-g="${esc(g.id)}">${esc(dt("keep"))}</button></div><div class="reflib-dp-rows">${g.rows.map((r, i) => `
            <div class="reflib-dp-r ${i === k ? "keep" : ""}" data-dp="pick" data-g="${esc(g.id)}" data-i="${i}"><div class="reflib-dp-img" style="background-image:url('${thumbs.get(r.hash) || ""}')">
              <span class="reflib-dp-bd">${i === g.biggest ? `<i class="big">${esc(dt("big"))}</i>` : ""}${i === g.smallest && g.rows.length > 1 ? `<i class="small">${esc(dt("small"))}</i>` : ""}${r.origin === "ai" ? `<i class="ia">${esc(dt("ia"))}</i>` : ""}${r.video ? `<i class="video">▶ ${esc(dt("video"))}</i>` : ""}</span></div>
              <div><b>${r.w} × ${r.h}</b> ${r.mp} MP<br>${fmtB(r.bytes)} · ${esc(r.fmt)}<br>${r.video ? esc([r.dur != null ? r.dur + " s" : "", r.codec, r.fps ? r.fps + " fps" : ""].filter(Boolean).join(" · ")) + "<br>" : ""}<span class="reflib-fc-muted">${esc(fmtD(r.date))}</span><br>
              <span class="reflib-fc-muted reflib-dp-path" title="${esc(r.path)}">${esc(r.dir)}</span><br><span class="reflib-fc-muted">${esc(r.name)}${r.tags ? " · " + esc(dt("tags", { n: r.tags })) : ""}${r.in_library ? " · " + esc(dt("in_col")) : ""}</span>
              <div class="reflib-dp-k">${esc(i === k ? dt("k") : dt("l"))}</div></div></div>`).join("")}</div></div>`; };
        pan.innerHTML = `<div class="reflib-fc-box"><div class="reflib-fc-head"><b>${esc(dt("title"))}</b><button type="button" class="reflib-fc-x" data-dp="close" title="${esc(dt("close"))}">×</button></div>
          <div class="reflib-fc-bar"><span class="reflib-fc-muted">${esc(stat)}</span>
            <button type="button" class="reflib-ib-btn" data-dp="scan" ${st && st.running ? "disabled" : ""}>↻ ${esc(dt("scan"))}</button>
            <label title="${esc(dt("thr_tip"))}">${esc(dt("thr"))} <input type="range" min="0" max="16" value="${V.thr}" data-dp="thr"> <span>${V.thr}</span></label>
            <span>${seg}</span>
            <label title="${esc(dt("transfer_tip"))}"><input type="checkbox" data-dp="transfer" ${V.transfer ? "checked" : ""}> ${esc(dt("transfer"))}</label>
            <button type="button" class="reflib-ib-btn reflib-ib-danger" data-dp="keepall" ${gs.length ? "" : "disabled"}>${esc(dt("keepall"))}</button></div>
          ${gs.length ? gs.map(grp).join("") : `<div class="reflib-fc-muted">${esc(st && st.hashed ? dt("none") : dt("first"))}</div>`}
          ${data && gs.length < data.count ? `<button type="button" class="reflib-ib-btn" data-dp="more">${esc(dt("more"))}</button>` : ""}</div>`;
        if (st && st.running) poll = setTimeout(refresh, 1200);
    }
    async function apply(gs, pick) {
        // 1.11.0: tags move (dup_transfer) only after the delete succeeded; cancelling leaves everything as it was
        const drop = [], moves = []; let rec = 0;
        for (const g of gs) {
            try { const r = await call(Object.assign({ action: "dup_resolve", transfer: V.transfer }, planOf(g, pick(g)))); drop.push(...(r.drop || [])); rec += r.recycled || 0; if (r.tags && r.tags.length) moves.push({ keep: r.keep, tags: r.tags }); }
            catch (e) {}
        }
        if (rec) RL.toast(dt("recycled", { n: rec }), "info");
        const done = async () => { for (const m of moves) await call(Object.assign({ action: "dup_transfer" }, m)).catch(() => null); if (RL.ilibRefresh) try { RL.ilibRefresh(); } catch (e) {} refresh(); };
        if (drop.length) {
            const p = await RL.sendIlib({ action: "forget_plan", hashes: drop }).catch(() => null);
            if (p && p.plan && p.plan.n > 0 && RL.forgetOpen) { close(); RL.forgetOpen(drop, done); return; }
            if (!window.confirm(dt("q_del", { n: drop.length }))) { refresh(); return; }
            const r = await RL.sendIlib({ action: "delete_all", hashes: drop }).catch(() => null);
            if (r && r.ok !== false) await done(); else refresh();
            return;
        }
        if (RL.ilibRefresh) try { RL.ilibRefresh(); } catch (e) {}
        refresh();
    }
    const groupById = id => ((data && data.groups) || []).find(g => g.id === id);
    function onClick(e) {
        const b = e.target.closest("[data-dp]"); if (!b) { if (e.target === pan) close(); return; }
        const a = b.dataset.dp;
        if (a === "close") close();
        else if (a === "scan") call({ action: "dup_scan" }).then(refresh).catch(() => {});
        else if (a === "kind") { V.kind = b.dataset.k; refresh(); }
        else if (a === "more") { V.limit += 30; refresh(); }
        else if (a === "pick") { V.keep[b.dataset.g] = +b.dataset.i; draw(); }
        else if (a === "keep1") { const g = groupById(b.dataset.g); if (g && window.confirm(dt("q_one", { n: g.rows.length - 1 }) + (V.transfer ? dt("q_tr") : ""))) apply([g], () => V.keep[g.id] ?? g.keep); }
        else if (a === "keepall") {
            const gs = (data && data.groups) || []; if (!gs.length) return;
            const n = gs.reduce((s, g) => s + g.rows.length - 1, 0);
            if (window.confirm(dt("q_all", { g: gs.length, n }) + (V.transfer ? dt("q_tr") : ""))) apply(gs, g => g.keep);
        }
    }
    let thrT = null;
    function onInput(e) {
        const el = e.target;
        if (el.dataset.dp === "thr") { V.thr = +el.value; localStorage.setItem("reflib.dupthr", String(V.thr)); const s = el.nextElementSibling; if (s) s.textContent = V.thr; clearTimeout(thrT); thrT = setTimeout(refresh, 250); }
        else if (el.dataset.dp === "transfer") V.transfer = el.checked;
    }
    RL.extend({ act: (act) => { if (act === "dupesopen") { open(); return true; } return false; } });
    function mountBtn() {
        const head = ilib().root && ilib().root.querySelector(".reflib-ib-head");
        if (!head || head.querySelector(".reflib-dp-openbtn")) return;
        const b = document.createElement("button"); b.type = "button"; b.className = "reflib-ib-btn reflib-dp-openbtn"; b.dataset.act = "dupesopen";
        b.textContent = "⧉ " + dt("open"); b.addEventListener("click", e => { e.stopPropagation(); open(); });
        const ref = head.querySelector(".reflib-fc-openbtn") || head.querySelector(".reflib-ib-title");
        ref && ref.nextSibling ? head.insertBefore(b, ref.nextSibling) : head.appendChild(b);
    }
    setInterval(() => { try { mountBtn(); const b = document.querySelector(".reflib-dp-openbtn"); if (b) b.textContent = "⧉ " + dt("open"); } catch (e) {} }, 1000);
    RL.dupesOpen = open;
    const css = document.createElement("style");
    css.textContent = `
.reflib-dp-g { border: 1px solid var(--border-color-primary, #d1d5db); border-radius: 10px; padding: 8px 10px; }
.reflib-dp-gh { display: flex; gap: 8px; align-items: center; margin-bottom: 6px; } .reflib-dp-gh button { margin-left: auto; }
.reflib-dp-rows { display: flex; gap: 10px; overflow-x: auto; }
.reflib-dp-r { flex: 0 0 220px; border: 2px solid transparent; border-radius: 8px; padding: 6px; cursor: pointer; font-size: 12px; line-height: 1.45; }
.reflib-dp-r.keep { border-color: #22c55e; background: rgba(34,197,94,.08); }
.reflib-dp-img { position: relative; height: 160px; border-radius: 6px; background: rgba(127,127,127,.15) center / contain no-repeat; margin-bottom: 4px; }
.reflib-dp-bd { position: absolute; top: 4px; left: 4px; display: flex; gap: 4px; }
.reflib-dp-bd i { font-style: normal; font-size: 11px; padding: 0 5px; border-radius: 4px; }
.reflib-dp-bd .big { background: #22c55e; color: #fff; } .reflib-dp-bd .small { background: #f59e0b; color: #111; } .reflib-dp-bd .ia { background: #7c3aed; color: #fff; } .reflib-dp-bd .video { background: #0ea5e9; color: #fff; }
.reflib-dp-r b { font-size: 14px; } .reflib-dp-k { font-weight: 600; margin-top: 3px; } .reflib-dp-r.keep .reflib-dp-k { color: #22c55e; }
.reflib-dp-path { display: inline-block; max-width: 100%; overflow: hidden; text-overflow: ellipsis; white-space: nowrap; direction: rtl; text-align: left; }`;
    document.head.appendChild(css);
    document.addEventListener("keydown", e => { if (pan && e.key === "Escape") { e.stopPropagation(); close(); } }, true);
})();
