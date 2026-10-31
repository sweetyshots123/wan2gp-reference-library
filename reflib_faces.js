// 1.10.0 Reference Library: Personas (iPhone-Photos-style people) in the classic explorer.
// All logic is server-side (reflib_core/faces.py, face_* / person_* shared actions, FACES_API.md); the Galería calls the
// same actions. This file only draws: the Personas panel, cluster / person pages, the "Is this also X?" card and bbox overlays.
(function () {
    "use strict";
    const RL = window.referenceLibrary;
    if (!RL || !RL.extend || RL.facesLoaded) return;
    RL.facesLoaded = true;
    const S = {
        en: { open: "People", title: "People", persons: "People", none_p: "Nobody named yet: name a group of faces below.", clusters: "Unnamed faces", none_c: "No groups yet. Compute faces (Find similar → Compute faces) and press «Group faces».",
              run: "Group faces", regroup: "Regroup all", thr: "Grouping strictness", thr_tip: "Higher = only very similar faces go together (more, smaller groups)", status: "{f} faces · {u} unnamed · {c} groups · {p} people",
              running: "Grouping {d} / {t}…", name_ph: "Name…", name: "Name", merge: "Merge selected ({n})", back: "← Back", faces_n: "{n} faces", items_n: "{n} photos",
              ask: "Is this also {x}?", yes: "Yes", no: "No", no_more: "No more suggestions for {x}.", rename: "Rename", del: "Forget person", del_ok: "Forgot {x} (photos are kept)", undo: "Undo",
              cover: "Use as cover", remove: "Not {x}", split: "Move to new group ({n})", assign_to: "Assign selected to…", show: "Show photos", merge_into: "Merge into…",
              assigned: "{n} faces assigned to {x}", rejected: "OK, not {x}", faces_btn: "Faces", faces_tip: "Show detected faces and who they are", no_index: "No faces computed for this face model yet.",
              close: "Close", del_q: "Forget {x}? Photos are never deleted; the persona tag is removed.", rename_q: "New name for {x}:", err: "Error: {e}", unknown: "?" },
        es: { open: "Personas", title: "Personas", persons: "Personas", none_p: "Aún no hay nadie con nombre: pon nombre a un grupo de caras de abajo.", clusters: "Caras sin nombre", none_c: "Aún no hay grupos. Calcula las caras (Buscar similares → Calcular caras) y pulsa «Agrupar caras».",
              run: "Agrupar caras", regroup: "Reagrupar todo", thr: "Exigencia al agrupar", thr_tip: "Más alto = solo se juntan caras muy parecidas (más grupos, más pequeños)", status: "{f} caras · {u} sin nombre · {c} grupos · {p} personas",
              running: "Agrupando {d} / {t}…", name_ph: "Nombre…", name: "Nombrar", merge: "Unir seleccionados ({n})", back: "← Volver", faces_n: "{n} caras", items_n: "{n} fotos",
              ask: "¿Es esta también {x}?", yes: "Sí", no: "No", no_more: "No hay más sugerencias para {x}.", rename: "Renombrar", del: "Olvidar persona", del_ok: "{x} olvidada (las fotos se conservan)", undo: "Deshacer",
              cover: "Usar como portada", remove: "No es {x}", split: "Mover a un grupo nuevo ({n})", assign_to: "Asignar seleccionadas a…", show: "Ver fotos", merge_into: "Unir con…",
              assigned: "{n} caras asignadas a {x}", rejected: "Vale, no es {x}", faces_btn: "Caras", faces_tip: "Muestra las caras detectadas y de quién son", no_index: "Aún no hay caras calculadas con este modelo de caras.",
              close: "Cerrar", del_q: "¿Olvidar a {x}? Las fotos nunca se borran; se quita la etiqueta de persona.", rename_q: "Nuevo nombre para {x}:", err: "Error: {e}", unknown: "?" },
    };
    const lang = () => (RL.lang && RL.lang() === "es" ? "es" : "en");
    const ft = (k, p = {}) => String((S[lang()] || S.en)[k] ?? S.en[k] ?? k).replace(/\{(\w+)\}/g, (m, n) => (p[n] ?? m));
    const esc = RL.esc;
    const ilib = () => RL.ilibState();
    const call = (req) => RL.sendIlib(req).then(r => { if (r && r.ok === false) { RL.toast(r.error === "faces_no_index" ? ft("no_index") : ft("err", { e: r.error || r.message || "?" }), "warn"); throw r; } return r; });
    const thumbs = new Map();
    function needThumbs(hs) {
        const cache = ilib().thumbs, want = [...new Set(hs)].filter(h => !thumbs.has(h) && !(cache && cache.get(h)));
        const out = [];
        for (let i = 0; i < want.length; i += 24) out.push(RL.sendIlib({ action: "thumbs", hashes: want.slice(i, i + 24) }).then(r => Object.entries((r && r.thumbs) || {}).forEach(([h, d]) => thumbs.set(h, d))).catch(() => {}));
        return Promise.all(out);
    }
    const thumb = h => thumbs.get(h) || (ilib().thumbs && ilib().thumbs.get(h)) || "";
    // a face tile: thumbnail cropped to the bbox (CSS background), or the whole thumbnail when no bbox is known
    function face(f, cls = "", extra = "") {
        const src = thumb(f.hash);
        let st = `background-image:url('${src}')`;
        if (f.bbox && f.w && f.h) {
            const [x, y, w, hh] = f.bbox, s = Math.max(w, hh) * 1.4, cx = x + w / 2, cy = y + hh / 2;
            const bx = Math.max(0, Math.min(f.w - s, cx - s / 2)), by = Math.max(0, Math.min(f.h - s, cy - s / 2));
            st += `;background-size:${(f.w / s) * 100}% ${(f.h / s) * 100}%;background-position:${f.w > s ? (bx / (f.w - s)) * 100 : 50}% ${f.h > s ? (by / (f.h - s)) * 100 : 50}%`;
        }
        return `<div class="reflib-fc-face ${cls}" data-face="${esc(f.id)}" style="${st}" ${extra}></div>`;
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
        pan.addEventListener("keydown", e => { if (e.key === "Enter" && e.target.dataset.f === "nm") { e.preventDefault(); nameCluster(e.target.dataset.c, e.target.value); } });
        view = { p: "home" }; sel.clear(); draw();
    }
    function close() { if (poll) clearInterval(poll); poll = null; if (pan) pan.remove(); pan = null; }
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
              <span class="reflib-fc-nm"><input type="text" list="reflib-fc-names" placeholder="${esc(ft("name_ph"))}" data-f="nm" data-c="${esc(c.id)}"><button type="button" class="reflib-ib-btn" data-f="name" data-c="${esc(c.id)}">${esc(ft("name"))}</button></span></div>`).join("") : `<div class="reflib-fc-muted">${esc(ft("none_c"))}</div>`}</div>
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
        const [r, sg, pl] = await Promise.all([call({ action: "person_get", person: view.id, limit: 400 }), call({ action: "face_suggest", person: view.id, limit: 1 }), call({ action: "person_list" })]);
        const p = r.person, s = (sg.faces || [])[0];
        await needThumbs([...r.faces.map(f => f.hash), ...(s ? [s.hash] : [])]);
        if (!pan) return;
        const others = (pl.persons || []).filter(x => x.id !== p.id);
        pan.innerHTML = shell(`<div class="reflib-fc-bar"><span class="reflib-fc-muted">${esc(ft("faces_n", { n: p.count }))} · ${esc(ft("items_n", { n: p.items }))} · ${esc(p.tag)}</span>
            <button type="button" class="reflib-ib-btn" data-f="show">${esc(ft("show"))}</button><button type="button" class="reflib-ib-btn" data-f="rename">${esc(ft("rename"))}</button>
            ${others.length ? `<select data-f="pmerge"><option value="">${esc(ft("merge_into"))}</option>${others.map(o => `<option value="${esc(o.id)}">${esc(o.name)}</option>`).join("")}</select>` : ""}
            <button type="button" class="reflib-ib-btn reflib-fc-danger" data-f="pdel">${esc(ft("del"))}</button></div>
          <div class="reflib-fc-ask">${s ? `${face(s, "big")}<div><b>${esc(ft("ask", { x: p.name }))}</b><div class="reflib-fc-muted">${Math.round(s.score * 100)}%</div>
              <div class="reflib-fc-yn"><button type="button" class="reflib-ib-btn reflib-ib-primary" data-f="yes" data-face="${esc(s.id)}">${esc(ft("yes"))}</button><button type="button" class="reflib-ib-btn" data-f="no" data-face="${esc(s.id)}">${esc(ft("no"))}</button></div></div>`
              : `<span class="reflib-fc-muted">${esc(ft("no_more", { x: p.name }))}</span>`}</div>
          ${sel.size ? `<div class="reflib-fc-bar"><button type="button" class="reflib-ib-btn" data-f="unassign">${esc(ft("remove", { x: p.name }))} (${sel.size})</button><button type="button" class="reflib-ib-btn" data-f="split">${esc(ft("split", { n: sel.size }))}</button>${sel.size === 1 ? `<button type="button" class="reflib-ib-btn" data-f="cover">${esc(ft("cover"))}</button>` : ""}</div>` : ""}
          <div class="reflib-fc-grid">${r.faces.map(f => face(f, (sel.has(f.id) ? "on " : "") + (p.cover && p.cover.id === f.id ? "cov" : ""), `data-f="fsel"`)).join("")}</div>`, p.name);
        view.name = p.name; view.tag = p.tag;
    }
    function nameCluster(c, name) {
        name = String(name || "").trim(); if (!name) return;
        call({ action: "face_assign", name, clusters: [c] }).then(r => { RL.toast(ft("assigned", { n: r.assigned, x: r.person.name }), "ok"); sel.clear(); view = { p: "person", id: r.person.id }; draw(); }).catch(() => {});
    }
    function onChange(e) {
        const k = e.target.dataset.f;
        if (k === "thr") call({ action: "face_settings", settings: { face_cluster_threshold: +e.target.value } }).then(() => call({ action: "face_cluster_run" })).then(draw).catch(() => {});
        else if (k === "csel") { e.target.checked ? sel.add(e.target.dataset.c) : sel.delete(e.target.dataset.c); draw(); }
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
        else if (k === "yes") call({ action: "face_confirm", person: view.id, faces: [b.dataset.face] }).then(draw).catch(() => {});
        else if (k === "no") call({ action: "face_reject", person: view.id, faces: [b.dataset.face] }).then(() => { RL.toast(ft("rejected", { x: view.name }), "info"); draw(); }).catch(() => {});
        else if (k === "rename") { const n = prompt(ft("rename_q", { x: view.name }), view.name); if (n && n.trim()) call({ action: "person_rename", person: view.id, name: n.trim() }).then(r => { view = { p: "person", id: r.person.id }; draw(); }).catch(() => {}); }
        else if (k === "pdel") { if (!confirm(ft("del_q", { x: view.name }))) return; const nm = view.name;
            call({ action: "person_delete", person: view.id }).then(r => { RL.toast(ft("del_ok", { x: nm }), "ok", [{ label: ft("undo"), onClick: () => call({ action: "person_undo_delete", undo_token: r.undo_token }).then(x => { if (pan) { view = { p: "person", id: x.person.id }; draw(); } }).catch(() => {}) }], 15000); view = { p: "home" }; draw(); }).catch(() => {}); }
        else if (k === "show") { const f = ilib().f, tag = view.tag; close(); f.tags.clear(); f.tags.add(tag); RL.ilibRefresh(); }
    }
    // bbox overlay on the explorer preview ("Faces" button in the details panel)
    function overlay(h) {
        const img = ilib().root && ilib().root.querySelector(".reflib-ib-pv-img img"); if (!img) return;
        const box = img.parentElement;
        const old = box.querySelector(".reflib-fc-ov"); if (old) { old.remove(); return; }
        Promise.all([call({ action: "face_for_item", hash: h }), call({ action: "person_list" })]).then(([r, pl]) => {
            const it = (r.items || {})[h]; if (!it) return;
            const names = new Map((pl.persons || []).map(p => [p.id, p.name]));
            const ov = document.createElement("div"); ov.className = "reflib-fc-ov";
            const ir = img.getBoundingClientRect(), br = box.getBoundingClientRect();
            Object.assign(ov.style, { left: (ir.left - br.left) + "px", top: (ir.top - br.top) + "px", width: ir.width + "px", height: ir.height + "px" });
            ov.innerHTML = it.faces.map(f => f.bbox && it.w ? `<div class="reflib-fc-bb" style="left:${100 * f.bbox[0] / it.w}%;top:${100 * f.bbox[1] / it.h}%;width:${100 * f.bbox[2] / it.w}%;height:${100 * f.bbox[3] / it.h}%"><span>${esc(names.get(f.person) || ft("unknown"))}</span></div>` : "").join("")
                + `<div class="reflib-fc-ovlist">${it.faces.map((f, i) => `<span>${i + 1}: ${esc(names.get(f.person) || ft("unknown"))}</span>`).join("")}</div>`;
            box.style.position = "relative"; box.appendChild(ov);
        }).catch(() => {});
    }
    const isImg = it => !it.kind || it.kind === "image";
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
.reflib-fc-danger { color: #dc2626; }
.dark .reflib-fc-danger { color: #f87171; }
.reflib-fc-ov { position: absolute; pointer-events: none; }
.reflib-fc-bb { position: absolute; border: 2px solid #facc15; border-radius: 4px; box-shadow: 0 0 0 1px rgba(0,0,0,.6); }
.reflib-fc-bb span { position: absolute; left: -2px; top: 100%; background: #facc15; color: #111; font-size: 11px; padding: 0 4px; border-radius: 0 0 4px 4px; white-space: nowrap; }
.reflib-fc-ovlist { position: absolute; left: 4px; bottom: 4px; display: flex; gap: 6px; flex-wrap: wrap; }
.reflib-fc-ovlist span { background: rgba(0,0,0,.7); color: #fff; font-size: 11px; padding: 1px 6px; border-radius: 4px; }`;
    document.head.appendChild(css);
    document.addEventListener("keydown", e => { if (pan && e.key === "Escape") { e.stopPropagation(); close(); } }, true);
})();
