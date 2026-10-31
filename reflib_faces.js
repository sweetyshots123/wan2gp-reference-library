// 1.10.0 Reference Library: Personas (iPhone-Photos-style people) in the classic explorer.
// All logic is server-side (reflib_core/faces.py, face_* / person_* shared actions, FACES_API.md); the Galería calls the
// same actions. This file only draws: the Personas panel, cluster / person pages, the "Is this also X?" card and bbox overlays.
(function () {
    "use strict";
    const RL = window.referenceLibrary;
    if (!RL || !RL.extend || RL.facesLoaded) return;
    RL.facesLoaded = true;
    const S = {
        en: { open: "People", title: "People", persons: "People", none_p: "Nobody named yet: name a group of faces below.", clusters: "Unnamed faces", none_c: "No groups yet. Compute faces (Find similar → Compute faces) and press «Group faces».", none_c2: "No unnamed groups of {m}+ faces right now ({a} single faces). Press «Regroup all» or lower «Grouping strictness».",
              run: "Group faces", regroup: "Regroup all", thr: "Grouping strictness", thr_tip: "Higher = only very similar faces go together (more, smaller groups)", status: "{f} faces · {u} unnamed · {c} groups · {p} people",
              running: "Grouping {d} / {t}…", name_ph: "Name…", name: "Name", merge: "Merge selected ({n})", back: "← Back", faces_n: "{n} faces", items_n: "{n} photos", vids_n: "{n} videos", back_personas: "← People",
              ask: "Is this also {x}?", yes: "Yes", no: "No", no_more: "No more suggestions for {x}.", rename: "Rename", del: "Forget person", del_ok: "Forgot {x} (photos are kept)", undo: "Undo",
              cover: "Use as cover", remove: "Not {x}", split: "Move to new group ({n})", assign_to: "Assign selected to…", show: "Show photos", merge_into: "Merge into…",
              assigned: "{n} faces assigned to {x}", rejected: "OK, not {x}", rv_title: "Suggestions for {x} ({n})", rv_tip: "Click to discard · Shift+click discards a range", rv_cut: "Discard below", rv_ok: "Add the remaining {n}", rv_none: "Discard all", rv_none_q: "Discard all {n} suggestions? They will not be suggested again.", rv_done: "{a} added · {r} discarded", rv_open: "Open photo", faces_btn: "Faces", faces_tip: "Show detected faces and who they are", no_index: "No faces computed for this face model yet.",
              video: "Video", at: "at {t}", seg: "{a}–{b}", open_at: "Open at {t}",
              close: "Close", del_q: "Forget {x}? Photos are never deleted; the persona tag is removed.", rename_q: "New name for {x}:", err: "Error: {e}", unknown: "?" },
        es: { open: "Personas", title: "Personas", persons: "Personas", none_p: "Aún no hay nadie con nombre: pon nombre a un grupo de caras de abajo.", clusters: "Caras sin nombre", none_c: "Aún no hay grupos. Calcula las caras (Buscar similares → Calcular caras) y pulsa «Agrupar caras».", none_c2: "Ahora no hay grupos sin nombre de {m} o más caras ({a} caras sueltas). Pulsa «Reagrupar todo» o baja la «Exigencia al agrupar».",
              run: "Agrupar caras", regroup: "Reagrupar todo", thr: "Exigencia al agrupar", thr_tip: "Más alto = solo se juntan caras muy parecidas (más grupos, más pequeños)", status: "{f} caras · {u} sin nombre · {c} grupos · {p} personas",
              running: "Agrupando {d} / {t}…", name_ph: "Nombre…", name: "Nombrar", merge: "Unir seleccionados ({n})", back: "← Volver", faces_n: "{n} caras", items_n: "{n} fotos", vids_n: "{n} vídeos", back_personas: "← Personas",
              ask: "¿Es esta también {x}?", yes: "Sí", no: "No", no_more: "No hay más sugerencias para {x}.", rename: "Renombrar", del: "Olvidar persona", del_ok: "{x} olvidada (las fotos se conservan)", undo: "Deshacer",
              cover: "Usar como portada", remove: "No es {x}", split: "Mover a un grupo nuevo ({n})", assign_to: "Asignar seleccionadas a…", show: "Ver fotos", merge_into: "Unir con…",
              assigned: "{n} caras asignadas a {x}", rejected: "Vale, no es {x}", rv_title: "Sugerencias para {x} ({n})", rv_tip: "Clic para descartar · Mayús+clic descarta un rango", rv_cut: "Descartar por debajo de", rv_ok: "Añadir las {n} restantes", rv_none: "Descartar todas", rv_none_q: "¿Descartar las {n} sugerencias? No se volverán a sugerir.", rv_done: "{a} añadida(s) · {r} descartada(s)", rv_open: "Abrir foto", faces_btn: "Caras", faces_tip: "Muestra las caras detectadas y de quién son", no_index: "Aún no hay caras calculadas con este modelo de caras.",
              video: "Vídeo", at: "en {t}", seg: "{a}–{b}", open_at: "Abrir en {t}",
              close: "Cerrar", del_q: "¿Olvidar a {x}? Las fotos nunca se borran; se quita la etiqueta de persona.", rename_q: "Nuevo nombre para {x}:", err: "Error: {e}", unknown: "?" },
    };
    const lang = () => (RL.lang && RL.lang() === "es" ? "es" : "en");
    const ft = (k, p = {}) => String((S[lang()] || S.en)[k] ?? S.en[k] ?? k).replace(/\{(\w+)\}/g, (m, n) => (p[n] ?? m));
    const esc = RL.esc;
    const ilib = () => RL.ilibState();
    const call = (req) => RL.sendIlib(req).then(r => { if (r && r.ok === false) { RL.toast(r.code === "faces_no_index" ? ft("no_index") : (r.code ? r.error : ft("err", { e: r.error || r.message || "?" })), "warn"); throw r; } return r; });
    const thumbs = new Map();
    function needThumbs(hs) {
        const cache = ilib().thumbs, want = [...new Set(hs)].filter(h => !thumbs.has(h) && !(cache && cache.get(h)));
        const out = [];
        for (let i = 0; i < want.length; i += 24) out.push(RL.sendIlib({ action: "thumbs", hashes: want.slice(i, i + 24) }).then(r => Object.entries((r && r.thumbs) || {}).forEach(([h, d]) => thumbs.set(h, d))).catch(() => {}));
        return Promise.all(out);
    }
    const thumb = h => thumbs.get(h) || (ilib().thumbs && ilib().thumbs.get(h)) || "";
    // a face tile: thumbnail cropped to the bbox (CSS background), or the whole thumbnail when no bbox is known
    const fmtT = (t) => { const s = Math.max(0, Number(t) || 0), m = Math.floor(s / 60), r = Math.floor(s % 60); return m + ":" + String(r).padStart(2, "0"); };
    function faceChips(f) {
        if ((f.kind || "image") !== "video") return "";
        const chips = [];
        chips.push(`<span class="reflib-fc-vbadge" title="${esc(ft("video"))}">🎬</span>`);
        const segs = f.segments || [];
        if (segs.length) segs.slice(0, 4).forEach(sg => {
            const a = fmtT(sg.t0), b = fmtT(sg.t1);
            chips.push(`<span class="reflib-fc-tchip" data-f="openat" data-hash="${esc(f.hash)}" data-t="${sg.t0}" title="${esc(ft("open_at", { t: a }))}">${a === b ? a : ft("seg", { a, b })}</span>`);
        });
        else if (f.best_t != null || f.t != null) {
            const t = f.best_t != null ? f.best_t : f.t;
            chips.push(`<span class="reflib-fc-tchip" data-f="openat" data-hash="${esc(f.hash)}" data-t="${t}" title="${esc(ft("open_at", { t: fmtT(t) }))}">${fmtT(t)}</span>`);
        }
        return `<div class="reflib-fc-vmeta">${chips.join("")}</div>`;
    }
    function face(f, cls = "", extra = "") {
        // shared face_thumb route (same URL as the Galería): server-side square crop, whole image when no bbox
        const meta = faceChips(f);
        const open = (f.kind === "video" && (f.best_t != null || f.t != null))
            ? ` data-f="openat" data-hash="${esc(f.hash)}" data-t="${f.best_t != null ? f.best_t : f.t}"` : "";
        if (f.thumb) return `<div class="reflib-fc-face ${cls}${f.kind === "video" ? " vid" : ""}" data-face="${esc(f.id)}" style="background-image:url('${esc(f.thumb)}')" ${extra}${open}>${meta}</div>`;
        const src = thumb(f.hash);
        let st = `background-image:url('${src}')`;
        if (f.bbox && f.w && f.h) {
            const [x, y, w, hh] = f.bbox, s = Math.max(w, hh) * 1.4, cx = x + w / 2, cy = y + hh / 2;
            const bx = Math.max(0, Math.min(f.w - s, cx - s / 2)), by = Math.max(0, Math.min(f.h - s, cy - s / 2));
            st += `;background-size:${(f.w / s) * 100}% ${(f.h / s) * 100}%;background-position:${f.w > s ? (bx / (f.w - s)) * 100 : 50}% ${f.h > s ? (by / (f.h - s)) * 100 : 50}%`;
        }
        return `<div class="reflib-fc-face ${cls}${f.kind === "video" ? " vid" : ""}" data-face="${esc(f.id)}" style="${st}" ${extra}${open}>${meta}</div>`;
    }
    function openAt(hash, t, kind) {
        // 1.12.2: hide the Personas panel while the preview is shown; "← Personas" (or the preview ×) brings it back.
        // Cards not on the current explorer page open directly through RL.ilibShowPreview.
        try {
            const st = RL.ilibState && RL.ilibState();
            if (!st || !st.root) return;
            if (pan) { pan.style.display = "none"; backBtn(st.root); }
            const card = st.root.querySelector(`.reflib-ib-card[data-hash="${CSS.escape(hash)}"]`);
            if (card) card.click();
            if (RL.ilibShowPreview) RL.ilibShowPreview(hash, { kind: kind || "video", best_t: t != null ? Number(t) : null });
            const seek = () => {
                const v = st.root.querySelector(".reflib-ib-pvmedia");
                if (v && typeof v.currentTime === "number") {
                    const go = () => { try { v.currentTime = Math.max(0, Number(t) || 0); } catch (e) {} };
                    if (v.readyState >= 1) go(); else v.addEventListener("loadedmetadata", go, { once: true });
                    return true;
                }
                return false;
            };
            if (t != null && !seek()) { let n = 0; const iv = setInterval(() => { if (seek() || ++n > 40) clearInterval(iv); }, 100); }
        } catch (e) {}
    }
    function showPan() {
        const b = document.querySelector(".reflib-fc-back"); if (b) b.remove();
        if (pan) pan.style.display = "";
    }
    function backBtn(root) {
        const modal = root.querySelector(".reflib-ib-modal") || root;
        if (modal.querySelector(".reflib-fc-back")) return;
        const b = document.createElement("button");
        b.type = "button"; b.className = "reflib-ib-btn reflib-fc-back"; b.textContent = ft("back_personas");
        b.addEventListener("click", showPan);
        modal.appendChild(b);
        const x = e => { if (e.target.closest && e.target.closest('[data-act="pvclose"]')) { modal.removeEventListener("click", x, true); showPan(); } };
        modal.addEventListener("click", x, true);
    }
    let pan = null, view = { p: "home" }, sel = new Set(), poll = null;
    function open() {
        close();
        pan = document.createElement("div");
        pan.className = "reflib-fc-pan"; pan.setAttribute("role", "dialog");
        const root = ilib().root && ilib().root.querySelector(".reflib-ib-modal");
        (root || document.body).appendChild(pan);
        pan.addEventListener("click", onClick);
        pan.addEventListener("change", onChange);
        pan.addEventListener("keydown", e => {   // 1.12.0: suggestions grid keys (shared ReflibReview.key: arrows, x/Delete, Enter)
            const c = e.target.closest && e.target.closest(".reflib-fc-rvc");
            if (!c || !rv) return;
            const cells = [...c.parentNode.children], i = cells.indexOf(c), cols = Math.max(1, cells.filter(x => x.offsetTop === cells[0].offsetTop).length);
            const r = window.ReflibReview.key(e.key, i, cells.length, cols); if (!r) return;
            e.preventDefault(); e.stopPropagation();
            if (r.op === "move") cells[r.to].focus();
            else if (r.op === "discard") { window.ReflibReview.click(rv, rv.faces.map(f => f.id), i, { shift: e.shiftKey }); rv.focus = i; draw(); }
            else if (r.op === "confirm") review(false);
        });
        pan.addEventListener("keydown", e => { if (e.key === "Enter" && e.target.dataset.f === "nm") { e.preventDefault(); nameCluster(e.target.dataset.c, e.target.value); } });
        view = { p: "home" }; sel.clear(); draw();
    }
    function close() { if (poll) clearInterval(poll); poll = null; const bb = document.querySelector(".reflib-fc-back"); if (bb) bb.remove(); if (pan) pan.remove(); pan = null; }
    const shell = (body, title) => `<div class="reflib-fc-box"><div class="reflib-fc-head">${view.p !== "home" ? `<button type="button" class="reflib-ib-btn" data-f="back">${esc(ft("back"))}</button>` : ""}<b>${esc(title)}</b><button type="button" class="reflib-fc-x" data-f="close" title="${esc(ft("close"))}">×</button></div>${body}</div>`;
    async function draw() {
        if (!pan) return;
        try {
            if (view.p === "home") await drawHome();
            else if (view.p === "cluster") await drawCluster();
            else if (view.p === "person") await drawPerson();
        } catch (e) { /* toast already shown */ }
    }
    async function drawHome() {
        const [st, pl, cl] = await Promise.all([call({ action: "face_status" }), call({ action: "person_list" }), call({ action: "face_clusters", limit: 60, faces_per: 1 })]);
        const s = st.faces, cs = cl.clusters || [], ps = pl.persons || [];
        await needThumbs([...ps.filter(p => p.cover).map(p => p.cover.hash), ...cs.filter(c => c.cover).map(c => c.cover.hash)]);
        if (!pan) return;
        const thr = s.threshold || 0.42;
        pan.innerHTML = shell(`<div class="reflib-fc-bar"><span class="reflib-fc-muted">${esc(ft("status", { f: s.faces, u: s.unassigned, c: s.clusters, p: s.persons }))}</span>
            <label title="${esc(ft("thr_tip"))}">${esc(ft("thr"))} <input type="range" min="0.25" max="0.7" step="0.01" value="${thr}" data-f="thr"><b>${Math.round(thr * 100)}%</b></label>
            <button type="button" class="reflib-ib-btn reflib-ib-primary" data-f="run">${esc(ft("run"))}</button><button type="button" class="reflib-ib-btn" data-f="regroup">${esc(ft("regroup"))}</button>
            ${s.running ? `<span>${esc(ft("running", { d: s.done, t: s.total }))}</span>` : ""}</div>
          <h4>${esc(ft("persons"))}</h4>
          <div class="reflib-fc-persons">${ps.length ? ps.map(p => `<button type="button" class="reflib-fc-person" data-f="person" data-p="${esc(p.id)}">${p.cover ? face(p.cover, "round") : `<div class="reflib-fc-face round"></div>`}<span>${esc(p.name)}</span><i>${esc(ft("faces_n", { n: p.count }))}</i></button>`).join("") : `<div class="reflib-fc-muted">${esc(ft("none_p"))}</div>`}</div>
          <h4>${esc(ft("clusters"))} ${sel.size > 1 ? `<button type="button" class="reflib-ib-btn" data-f="cmerge">${esc(ft("merge", { n: sel.size }))}</button>` : ""}</h4>
          <div class="reflib-fc-clusters">${cs.length ? cs.map(c => `<div class="reflib-fc-cluster${sel.has(c.id) ? " on" : ""}" data-c="${esc(c.id)}">
              <input type="checkbox" data-f="csel" data-c="${esc(c.id)}" ${sel.has(c.id) ? "checked" : ""}>
              <button type="button" class="reflib-fc-open" data-f="cluster" data-c="${esc(c.id)}">${c.cover ? face(c.cover, "round") : ""}<i>${esc(ft("faces_n", { n: c.size }))}</i></button>
              <span class="reflib-fc-nm"><input type="text" list="reflib-fc-names" placeholder="${esc(ft("name_ph"))}" data-f="nm" data-c="${esc(c.id)}"><button type="button" class="reflib-ib-btn" data-f="name" data-c="${esc(c.id)}">${esc(ft("name"))}</button></span></div>`).join("") : `<div class="reflib-fc-muted">${esc(s.faces ? ft("none_c2", { m: s.min_cluster || 2, a: s.unassigned }) : ft("none_c"))}</div>`}</div>
          <datalist id="reflib-fc-names">${ps.map(p => `<option value="${esc(p.name)}">`).join("")}</datalist>`, ft("title"));
        if (s.running && !poll) poll = setInterval(() => call({ action: "face_status" }).then(r => { if (!r.faces.running) { clearInterval(poll); poll = null; draw(); } }).catch(() => {}), 1500);
    }
    async function drawCluster() {
        const r = await call({ action: "face_cluster_faces", cluster: view.c, limit: 400 });
        const pl = await call({ action: "person_list" });
        await needThumbs(r.faces.map(f => f.hash));
        if (!pan) return;
        pan.innerHTML = shell(`<div class="reflib-fc-bar"><span class="reflib-fc-nm"><input type="text" list="reflib-fc-names" placeholder="${esc(ft("name_ph"))}" data-f="nm" data-c="${esc(view.c)}"><button type="button" class="reflib-ib-btn reflib-ib-primary" data-f="name" data-c="${esc(view.c)}">${esc(ft("name"))}</button></span>
            ${sel.size ? `<button type="button" class="reflib-ib-btn" data-f="split">${esc(ft("split", { n: sel.size }))}</button>` : ""}</div>
          <div class="reflib-fc-grid">${r.faces.map(f => face(f, sel.has(f.id) ? "on" : "", `data-f="fsel"`)).join("")}</div>
          <datalist id="reflib-fc-names">${(pl.persons || []).map(p => `<option value="${esc(p.name)}">`).join("")}</datalist>`, ft("faces_n", { n: r.total }));
    }
    async function drawPerson() {
        const [r, sg, pl] = await Promise.all([call({ action: "person_get", person: view.id, limit: 400 }), call({ action: "face_suggest", person: view.id, limit: 40 }), call({ action: "person_list" })]);
        const p = r.person, sug = sg.faces || [];   // 1.11.1: all suggestions as a grid (review_rules.js, person_review)
        if (!rv || rv.pid !== p.id) rv = { pid: p.id, discard: new Set(), anchor: -1, cut: 0 };
        rv.faces = sug;
        await needThumbs([...r.faces.map(f => f.hash), ...sug.map(f => f.hash)]);
        if (!pan) return;
        const others = (pl.persons || []).filter(x => x.id !== p.id);
        pan.innerHTML = shell(`<div class="reflib-fc-bar"><span class="reflib-fc-muted">${esc(ft("faces_n", { n: p.count }))} · ${esc(p.photos != null ? ft("items_n", { n: p.photos }) + (p.videos ? " · " + ft("vids_n", { n: p.videos }) : "") : ft("items_n", { n: p.items }))} · ${esc(p.tag)}</span>
            <button type="button" class="reflib-ib-btn" data-f="show">${esc(ft("show"))}</button><button type="button" class="reflib-ib-btn" data-f="rename">${esc(ft("rename"))}</button>
            ${others.length ? `<select data-f="pmerge"><option value="">${esc(ft("merge_into"))}</option>${others.map(o => `<option value="${esc(o.id)}">${esc(o.name)}</option>`).join("")}</select>` : ""}
            <button type="button" class="reflib-ib-btn reflib-fc-danger" data-f="pdel">${esc(ft("del"))}</button></div>
          ${sug.length ? reviewHtml(p) : `<div class="reflib-fc-ask"><span class="reflib-fc-muted">${esc(ft("no_more", { x: p.name }))}</span></div>`}
          ${sel.size ? `<div class="reflib-fc-bar"><button type="button" class="reflib-ib-btn" data-f="unassign">${esc(ft("remove", { x: p.name }))} (${sel.size})</button><button type="button" class="reflib-ib-btn" data-f="split">${esc(ft("split", { n: sel.size }))}</button>${sel.size === 1 ? `<button type="button" class="reflib-ib-btn" data-f="cover">${esc(ft("cover"))}</button>` : ""}</div>` : ""}
          <div class="reflib-fc-grid">${r.faces.map(f => face(f, (sel.has(f.id) ? "on " : "") + (p.cover && p.cover.id === f.id ? "cov" : ""), `data-f="fsel"`)).join("")}</div>`, p.name);
        view.name = p.name; view.tag = p.tag;
        if (rv && rv.focus != null) { const c = pan.querySelectorAll(".reflib-fc-rvc")[rv.focus]; if (c) c.focus(); rv.focus = null; }
    }
    let rv = null;
    function reviewHtml(p) {
        const RR = window.ReflibReview, pl = RR.plan(rv.faces, rv.discard, rv.cut), low = new Set(rv.cut ? RR.below(rv.faces, rv.cut) : []);
        return `<div class="reflib-fc-rv"><div class="reflib-fc-bar"><b>${esc(ft("rv_title", { x: p.name, n: rv.faces.length }))}</b><span class="reflib-fc-muted">${esc(ft("rv_tip"))}</span>
            <label>${esc(ft("rv_cut"))} <input type="range" min="0" max="100" value="${rv.cut}" data-f="rvcut"> ${rv.cut}%</label>
            <button type="button" class="reflib-ib-btn reflib-ib-primary" data-f="rvok" ${pl.accept.length ? "" : "disabled"}>${esc(ft("rv_ok", { n: pl.accept.length }))}</button>
            <button type="button" class="reflib-ib-btn" data-f="rvnone">${esc(ft("rv_none"))}</button></div>
          <div class="reflib-fc-grid">${rv.faces.map((f, i) => `<div class="reflib-fc-rvc ${rv.discard.has(f.id) || low.has(f.id) ? "off" : ""}" tabindex="0" data-f="rvt" data-i="${i}">${face(f).replace(/ data-f="openat" data-hash="[^"]*" data-t="[^"]*"/, "")}<span>${Math.round((f.score || 0) * 100)}%</span>
            <button type="button" class="reflib-fc-rvx" data-f="rvt" data-i="${i}" title="×">×</button><button type="button" class="reflib-fc-rvo" data-f="openat" data-hash="${esc(f.hash)}" data-kind="${esc(f.kind || "image")}" data-t="${f.best_t ?? f.t ?? ""}" title="${esc(ft("rv_open"))}">↗</button></div>`).join("")}</div></div>`;
    }
    function review(all) {
        const pl = all ? { accept: [], reject: rv.faces.map(f => f.id) } : window.ReflibReview.plan(rv.faces, rv.discard, rv.cut), pid = rv.pid;
        call({ action: "person_review", person: pid, accept: pl.accept, reject: pl.reject }).then(r => {
            const ua = (r && r.accepted_all) || pl.accept, ur = (r && r.rejected_all) || pl.reject;   // 1.12.2: undo every frame of a video
            RL.toast(ft("rv_done", { a: pl.accept.length, r: pl.reject.length }), "ok", [{ label: ft("undo"), onClick: () => (ua.length ? call({ action: "face_unassign", faces: ua }) : Promise.resolve())
                .then(() => ur.length && call({ action: "face_unreject", person: pid, faces: ur })).then(() => pan && draw()).catch(() => {}) }], 15000);
            rv = null; draw();
        }).catch(() => {});
    }
    function nameCluster(c, name) {
        name = String(name || "").trim(); if (!name) return;
        call({ action: "face_assign", name, clusters: [c] }).then(r => { RL.toast(ft("assigned", { n: r.assigned, x: r.person.name }), "ok"); sel.clear(); view = { p: "person", id: r.person.id }; draw(); }).catch(() => {});
    }
    function onChange(e) {
        const k = e.target.dataset.f;
        if (k === "thr") call({ action: "face_settings", settings: { face_cluster_threshold: +e.target.value } }).then(() => call({ action: "face_cluster_run" })).then(draw).catch(() => {});
        else if (k === "csel") { e.target.checked ? sel.add(e.target.dataset.c) : sel.delete(e.target.dataset.c); draw(); }
        else if (k === "rvcut" && rv) { rv.cut = +e.target.value; draw(); }
        else if (k === "pmerge" && e.target.value) call({ action: "face_merge", persons: [view.id, e.target.value], into: e.target.value }).then(r => { view = { p: "person", id: r.person.id }; draw(); }).catch(() => {});
    }
    function onClick(e) {
        if (e.target === pan) { close(); return; }
        const b = e.target.closest("[data-f]"); if (!b) return;
        const k = b.dataset.f;
        if (k === "close") close();
        else if (k === "back") { view = { p: "home" }; sel.clear(); draw(); }
        else if (k === "run" || k === "regroup") call({ action: "face_cluster_run", full: k === "regroup" }).then(draw).catch(() => {});
        else if (k === "person") { view = { p: "person", id: b.dataset.p }; sel.clear(); draw(); }
        else if (k === "cluster") { view = { p: "cluster", c: b.dataset.c }; sel.clear(); draw(); }
        else if (k === "name") nameCluster(b.dataset.c, (pan.querySelector(`input[data-f="nm"][data-c="${CSS.escape(b.dataset.c)}"]`) || {}).value);
        else if (k === "cmerge") call({ action: "face_merge", clusters: [...sel] }).then(() => { sel.clear(); draw(); }).catch(() => {});
        else if (k === "fsel") { const id = b.dataset.face; sel.has(id) ? sel.delete(id) : sel.add(id); draw(); }
        else if (k === "split") call(Object.assign({ action: "face_split", faces: [...sel] }, view.p === "person" ? { person: view.id } : { cluster: view.c })).then(r => { sel.clear(); view = { p: "cluster", c: r.cluster }; draw(); }).catch(() => {});
        else if (k === "unassign") call({ action: "face_unassign", faces: [...sel] }).then(() => call({ action: "face_reject", person: view.id, faces: [...sel] })).then(() => { sel.clear(); draw(); }).catch(() => {});
        else if (k === "cover") call({ action: "person_set_cover", person: view.id, face: [...sel][0] }).then(() => { sel.clear(); draw(); }).catch(() => {});
        else if (k === "rvt" && rv) { window.ReflibReview.click(rv, rv.faces.map(f => f.id), +b.dataset.i, { shift: e.shiftKey }); draw(); }
        else if (k === "rvok" && rv) review(false);
        else if (k === "rvnone" && rv) { if (confirm(ft("rv_none_q", { n: rv.faces.length }))) review(true); }
        else if (k === "rename") { const n = prompt(ft("rename_q", { x: view.name }), view.name); if (n && n.trim()) call({ action: "person_rename", person: view.id, name: n.trim() }).then(r => { view = { p: "person", id: r.person.id }; draw(); }).catch(() => {}); }
        else if (k === "pdel") { if (!confirm(ft("del_q", { x: view.name }))) return; const nm = view.name;
            call({ action: "person_delete", person: view.id }).then(r => { RL.toast(ft("del_ok", { x: nm }), "ok", [{ label: ft("undo"), onClick: () => call({ action: "person_undo_delete", undo_token: r.undo_token }).then(x => { if (pan) { view = { p: "person", id: x.person.id }; draw(); } }).catch(() => {}) }], 15000); view = { p: "home" }; draw(); }).catch(() => {}); }
        else if (k === "show") { const f = ilib().f, tag = view.tag; close(); f.tags.clear(); f.tags.add(tag); RL.ilibRefresh(); }
        else if (k === "openat") { openAt(b.dataset.hash, b.dataset.t === "" ? null : b.dataset.t, b.dataset.kind); }
    }
    // bbox overlay on the explorer preview ("Faces" button in the details panel)
    function overlay(h) {
        const img = ilib().root && ilib().root.querySelector(".reflib-ib-pv-img img"); if (!img) return;
        const box = img.parentElement;
        const old = box.querySelector(".reflib-fc-ov"); if (old) { old.remove(); return; }
        Promise.all([call({ action: "face_for_item", hash: h }), call({ action: "person_list" })]).then(([r, pl]) => {
            const it = (r.items || {})[h]; if (!it) return;
            const names = new Map((pl.persons || []).map(p => [p.id, p.name]));
            if (box.querySelector(".reflib-fc-ov")) return;
            const ov = document.createElement("div"); ov.className = "reflib-fc-ov";
            ov.innerHTML = it.faces.map(f => f.box ? `<div class="reflib-fc-bb" style="left:${100 * f.box[0]}%;top:${100 * f.box[1]}%;width:${100 * f.box[2]}%;height:${100 * f.box[3]}%"><span>${esc(names.get(f.person) || ft("unknown"))}</span></div>` : "").join("")
                + `<div class="reflib-fc-ovlist">${it.faces.map((f, i) => `<span>${i + 1}: ${esc(names.get(f.person) || ft("unknown"))}</span>`).join("")}</div>`;
            if (getComputedStyle(box).position === "static") box.style.position = "relative";
            box.appendChild(ov);
            RL.facesPlace(ov, img, box);
            // keep aligned: image load, resize of image/box, window resize, fullscreen
            const upd = () => { if (!ov.isConnected || !img.isConnected) return stop(); RL.facesPlace(ov, img, box); };
            const ro = window.ResizeObserver ? new ResizeObserver(upd) : null;
            if (ro) { ro.observe(img); ro.observe(box); }
            const evs = [[img, "load"], [window, "resize"], [document, "fullscreenchange"]];
            evs.forEach(([t, e]) => t.addEventListener(e, upd));
            const stop = () => { if (ro) ro.disconnect(); evs.forEach(([t, e]) => t.removeEventListener(e, upd)); };
        }).catch(() => {});
    }
    // Rendered picture rect inside <img> (object-fit contain/fill), as % of the container box.
    function facesRect(img, box) {
        const bw = box.clientWidth, bh = box.clientHeight, ew = img.clientWidth, eh = img.clientHeight;
        if (!bw || !bh || !ew || !eh) return null;
        const nw = img.naturalWidth, nh = img.naturalHeight, fit = getComputedStyle(img).objectFit;
        let w = ew, h = eh;
        if (nw && nh && (fit === "contain" || fit === "scale-down")) {
            const k = Math.min(ew / nw, eh / nh, fit === "scale-down" ? 1 : Infinity); w = nw * k; h = nh * k;
        }
        const ir = img.getBoundingClientRect(), br = box.getBoundingClientRect();
        const sx = br.width / bw || 1, sy = br.height / bh || 1;   // css transforms (zoom)
        const x = (ir.left - br.left) / sx - box.clientLeft + (ew - w) / 2, y = (ir.top - br.top) / sy - box.clientTop + (eh - h) / 2;
        return { left: 100 * x / bw, top: 100 * y / bh, width: 100 * w / bw, height: 100 * h / bh };
    }
    RL.facesPlace = (ov, img, box) => {
        const r = (img.complete && img.naturalWidth) ? facesRect(img, box) : null;
        ov.style.visibility = r ? "" : "hidden";   // not loaded yet: wait for the load event
        if (r) Object.assign(ov.style, { left: r.left + "%", top: r.top + "%", width: r.width + "%", height: r.height + "%" });
    };
    RL.facesRect = facesRect;
    const isImg = it => !it.kind || it.kind === "image" || it.kind === "video";  // 1.12.0: videos have faces too
    const itemOf = h => (ilib().q.items || []).find(x => x && x.hash === h) || {};
    RL.extend({
        details: (h) => isImg(itemOf(h)) ? `<button type="button" class="reflib-ib-btn" data-act="facesov" data-hash="${esc(h)}" title="${esc(ft("faces_tip"))}">☺ ${esc(ft("faces_btn"))}</button>` : "",
        act: (act, el) => {
            if (act === "facesopen") { open(); return true; }
            if (act === "facesov") { overlay(el.dataset.hash); return true; }
            return false;
        },
    });
    // "People" button in the explorer header (re-added when the explorer redraws its header)
    function mountBtn() {
        const head = ilib().root && ilib().root.querySelector(".reflib-ib-head");
        if (!head || head.querySelector(".reflib-fc-openbtn")) return;
        const b = document.createElement("button"); b.type = "button"; b.className = "reflib-ib-btn reflib-fc-openbtn"; b.dataset.act = "facesopen";
        b.textContent = "☺ " + ft("open"); b.addEventListener("click", e => { e.stopPropagation(); open(); });
        const t = head.querySelector(".reflib-ib-title"); t && t.nextSibling ? head.insertBefore(b, t.nextSibling) : head.appendChild(b);
    }
    setInterval(() => { try { mountBtn(); const b = document.querySelector(".reflib-fc-openbtn"); if (b) b.textContent = "☺ " + ft("open"); } catch (e) {} }, 1000);
    RL.facesOpen = open;
    const css = document.createElement("style");
    css.textContent = `
.reflib-fc-back { position: absolute; left: 12px; bottom: 12px; z-index: 61; }
.reflib-fc-pan { position: absolute; inset: 0; z-index: 60; display: flex; align-items: center; justify-content: center; background: rgba(0,0,0,.45); }
.reflib-fc-box { width: min(1100px, 96%); height: 92%; overflow: auto; box-sizing: border-box; padding: 14px 16px; border-radius: 10px; display: flex; flex-direction: column; gap: 10px;
  background: var(--background-fill-primary, #fff); color: var(--body-text-color, #111); border: 1px solid var(--border-color-primary, #d1d5db); box-shadow: 0 10px 40px rgba(0,0,0,.35); font-size: 13px; }
.reflib-fc-box h4 { margin: 6px 0 0; display: flex; gap: 10px; align-items: center; }
.reflib-fc-head { display: flex; gap: 10px; align-items: center; font-size: 16px; }
.reflib-fc-head b { flex: 1; }
.reflib-fc-x { background: none; border: 0; font-size: 20px; cursor: pointer; color: inherit; }
.reflib-fc-bar { display: flex; flex-wrap: wrap; gap: 10px; align-items: center; }
.reflib-fc-bar label { display: inline-flex; gap: 6px; align-items: center; }
.reflib-fc-muted { opacity: .72; }
.reflib-fc-face { width: 88px; height: 88px; border-radius: 8px; background: rgba(127,127,127,.25) center / cover no-repeat; flex: none; border: 2px solid transparent; box-sizing: border-box; cursor: pointer; }
.reflib-fc-face.round { border-radius: 50%; width: 96px; height: 96px; }
.reflib-fc-face.big { width: 160px; height: 160px; border-radius: 12px; cursor: default; }
.reflib-fc-face.on { border-color: #3b82f6; box-shadow: 0 0 0 2px #3b82f6; }
.reflib-fc-face.cov { border-color: #f59e0b; }
.reflib-fc-persons, .reflib-fc-clusters, .reflib-fc-grid { display: flex; flex-wrap: wrap; gap: 12px; }
.reflib-fc-person, .reflib-fc-open { background: none; border: 0; color: inherit; cursor: pointer; display: flex; flex-direction: column; align-items: center; gap: 4px; padding: 4px; }
.reflib-fc-person i, .reflib-fc-open i { font-style: normal; font-size: 11px; opacity: .7; }
.reflib-fc-cluster { position: relative; display: flex; flex-direction: column; align-items: center; gap: 4px; padding: 6px; border-radius: 10px; border: 1px solid var(--border-color-primary, #d1d5db); }
.reflib-fc-cluster.on { border-color: #3b82f6; background: rgba(59,130,246,.12); }
.reflib-fc-cluster input[type=checkbox] { position: absolute; top: 6px; left: 6px; }
.reflib-fc-nm { display: inline-flex; gap: 4px; }
.reflib-fc-nm input, .reflib-fc-bar select { width: 110px; background: var(--input-background-fill, transparent); color: inherit; border: 1px solid var(--border-color-primary, #d1d5db); border-radius: 6px; padding: 3px 6px; }
.reflib-fc-bar select { width: auto; }
.reflib-fc-ask { display: flex; gap: 16px; align-items: center; padding: 12px; border-radius: 12px; background: var(--background-fill-secondary, #f3f4f6); }
.reflib-fc-ask b { font-size: 15px; }
.reflib-fc-yn { display: flex; gap: 8px; margin-top: 8px; }
.reflib-fc-rvc { position: relative; cursor: pointer; text-align: center; font-size: 12px; transition: opacity .2s; }
.reflib-fc-rvc:focus { outline: 2px solid #3b82f6; outline-offset: 2px; }
.reflib-fc-rvc .reflib-fc-rvx, .reflib-fc-rvc .reflib-fc-rvo { position: absolute; top: 2px; width: 20px; height: 20px; padding: 0; border: 0; border-radius: 50%; background: rgba(0,0,0,.6); color: #fff; cursor: pointer; font-size: 12px; line-height: 20px; }
.reflib-fc-rvc .reflib-fc-rvx { right: 2px; } .reflib-fc-rvc .reflib-fc-rvo { left: 2px; }
.reflib-fc-rvc.off { opacity: .4; } .reflib-fc-rvc.off .reflib-fc-face { outline: 3px solid #e5484d; filter: grayscale(1); }
.reflib-fc-rvc.off::after { content: "✕"; position: absolute; left: 50%; top: 20%; transform: translateX(-50%); font-size: 30px; color: #e5484d; pointer-events: none; }
.reflib-fc-danger { color: #dc2626; }
.dark .reflib-fc-danger { color: #f87171; }
.reflib-fc-ov { position: absolute; pointer-events: none; }
.reflib-fc-bb { position: absolute; border: 2px solid #facc15; border-radius: 4px; box-shadow: 0 0 0 1px rgba(0,0,0,.6); }
.reflib-fc-bb span { position: absolute; left: -2px; top: 100%; background: #facc15; color: #111; font-size: 11px; padding: 0 4px; border-radius: 0 0 4px 4px; white-space: nowrap; }
.reflib-fc-ovlist { position: absolute; left: 4px; bottom: 4px; display: flex; gap: 6px; flex-wrap: wrap; }
.reflib-fc-ovlist span { background: rgba(0,0,0,.7); color: #fff; font-size: 11px; padding: 1px 6px; border-radius: 4px; }
.reflib-fc-face.vid { position: relative; }
.reflib-fc-vmeta { position: absolute; left: 4px; right: 4px; bottom: 4px; display: flex; flex-wrap: wrap; gap: 3px; pointer-events: auto; z-index: 2; }
.reflib-fc-vbadge { background: rgba(0,0,0,.65); color: #fff; font-size: 11px; line-height: 1; padding: 2px 4px; border-radius: 4px; }
.reflib-fc-tchip { background: rgba(0,0,0,.65); color: #fff; font-size: 10px; line-height: 1.2; padding: 2px 5px; border-radius: 4px; cursor: pointer; }
.reflib-fc-tchip:hover { background: rgba(30,90,200,.85); }
@media (prefers-color-scheme: dark) {
  .reflib-fc-vbadge, .reflib-fc-tchip { background: rgba(0,0,0,.75); }
}
`;
    document.head.appendChild(css);
    document.addEventListener("keydown", e => { if (pan && e.key === "Escape") { e.stopPropagation(); close(); } }, true);
})();
