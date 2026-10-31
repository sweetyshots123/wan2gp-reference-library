// 1.8.4 Reference Library: pose / face similarity in the classic explorer ("Buscar similares").
// All logic lives server-side (reflib_core/similarity.py, sim_* ilib actions); this only draws the dialog and
// shows a result as a normal explorer result set ({sim: sid} filter: chips, sorting and back/forward work).
(function () {
    "use strict";
    const RL = window.referenceLibrary;
    if (!RL || !RL.extend || RL.simLoaded) return;
    RL.simLoaded = true;
    const S = {
        en: { find: "Find similar", find_tip: "Find images with a similar pose and/or face", find_sel: "Find similar ({n})", title: "Find similar images",
              q_n: "{n} query images", drop: "Drop photos here or click to add (they are not saved in the library)", mode: "Compare", m_pose: "Pose", m_face: "Face", m_both: "Both",
              w: "Pose weight", thr: "Minimum similarity", agg: "Several query images", a_any: "Like any of them", a_avg: "Like all of them (average)",
              mirror: "Ignore left / right (mirrored poses match)", go: "Search", cancel: "Close", idx: "Index: {i} of {l} images · {p} people · {f} faces",
              build: "Compute poses and faces", rebuild: "Recompute all", pause: "Pause", resume: "Resume", stop: "Stop", run: "Computing {d} / {t}… {ms} ms per image",
              wait_busy: "waiting: WanGP is generating", wait_paused: "paused", dl: "downloading model {m}…", chip: "Similar to {n} · {m}", chip_files: "{n} photos",
              none: "No query image has a detected person or face for this mode", no_q: "Choose or drop at least one image", engine: "Similarity engine error: {e}", env: "The similarity environment is not set up (Python with onnxruntime; see README «Similarity models»). {e}",
              found: "{n} similar images ({ms} ms)", unindexed: "Not computed yet: the first search computes the query images (this can take a few seconds)",
              face_lic: "Face model: {m}", score: "Similarity {s}%",
              fm: "Face model", fm_done: "{n} of {l} images", fm_dl: "not downloaded · {mb} MB, downloads on first use", faces_build: "Compute faces ({m})",
              fm_lic: "Licence: {l}", fm_fb: "{m} could not load, using SFace instead ({e})", dlp: "Downloading {m}: {d} / {t} MB ({p}%)",
              fm_switch: "Each model keeps its own face index: switching back is instant once computed." },
        es: { find: "Buscar similares", find_tip: "Busca imágenes con una pose y/o cara parecida", find_sel: "Buscar similares ({n})", title: "Buscar imágenes similares",
              q_n: "{n} imágenes de consulta", drop: "Suelta fotos aquí o haz clic para añadir (no se guardan en la biblioteca)", mode: "Comparar", m_pose: "Pose", m_face: "Cara", m_both: "Ambas",
              w: "Peso de la pose", thr: "Similitud mínima", agg: "Varias imágenes de consulta", a_any: "Parecidas a cualquiera", a_avg: "Parecidas a todas (media)",
              mirror: "Ignorar izquierda / derecha (las poses en espejo coinciden)", go: "Buscar", cancel: "Cerrar", idx: "Índice: {i} de {l} imágenes · {p} personas · {f} caras",
              build: "Calcular poses y caras", rebuild: "Recalcular todo", pause: "Pausar", resume: "Reanudar", stop: "Detener", run: "Calculando {d} / {t}… {ms} ms por imagen",
              wait_busy: "en espera: WanGP está generando", wait_paused: "en pausa", dl: "descargando el modelo {m}…", chip: "Similares a {n} · {m}", chip_files: "{n} fotos",
              none: "Ninguna imagen de consulta tiene una persona o cara detectada para este modo", no_q: "Elige o suelta al menos una imagen", engine: "Error del motor de similitud: {e}", env: "El entorno de similitud no está configurado (Python con onnxruntime; ver README «Similarity models»). {e}",
              found: "{n} imágenes similares ({ms} ms)", unindexed: "Aún sin calcular: la primera búsqueda calcula las imágenes de consulta (puede tardar unos segundos)",
              face_lic: "Modelo de caras: {m}", score: "Similitud {s}%",
              fm: "Modelo de caras", fm_done: "{n} de {l} imágenes", fm_dl: "sin descargar · {mb} MB, se descarga al usarlo", faces_build: "Calcular caras ({m})",
              fm_lic: "Licencia: {l}", fm_fb: "{m} no se pudo cargar, se usa SFace ({e})", dlp: "Descargando {m}: {d} / {t} MB ({p}%)",
              fm_switch: "Cada modelo guarda su propio índice de caras: volver a uno ya calculado es instantáneo." },
    };
    const lang = () => (RL.lang && RL.lang() === "es" ? "es" : "en");
    const st = (k, p = {}) => String((S[lang()] || S.en)[k] ?? S.en[k] ?? k).replace(/\{(\w+)\}/g, (m, n) => (p[n] ?? m));
    const esc = RL.esc;
    const ilib = () => RL.ilibState();
    const opts = (() => { try { return Object.assign({ mode: "both", w_pose: 0.5, threshold: 0, agg: "any", mirror: true }, JSON.parse(localStorage.getItem("reflib_sim") || "{}")); } catch (e) { return { mode: "both", w_pose: 0.5, threshold: 0, agg: "any", mirror: true }; } })();
    const saveOpts = () => { try { localStorage.setItem("reflib_sim", JSON.stringify(opts)); } catch (e) {} };
    let dlg = null, poll = null, labels = {};
    try { labels = JSON.parse(sessionStorage.getItem("reflib_sim_labels") || "{}"); } catch (e) {}
    const btn = (cls, act, h, n) => `<button type="button" class="${cls} reflib-sim-btn" data-act="${act}" ${h ? `data-hash="${esc(h)}"` : ""} title="${esc(st("find_tip"))}">⧉ ${esc(n ? st("find_sel", { n }) : st("find"))}</button>`;
    const itemOf = h => (ilib().q.items || []).find(x => x && x.hash === h) || {};
    const isImg = it => !it.kind || it.kind === "image";

    function open(hashes) {
        close();
        const files = [];
        dlg = document.createElement("div");
        dlg.className = "reflib-sim-dlg"; dlg.setAttribute("role", "dialog");
        const root = ilib().root && ilib().root.querySelector(".reflib-ib-modal");
        (root || document.body).appendChild(dlg);
        const thumbs = () => hashes.slice(0, 12).map(h => `<img src="${esc(ilib().thumbs.get(h) || "")}" alt="">`).join("") + files.map(f => `<img src="${esc(f.data)}" alt="">`).join("");
        const draw = () => {
            dlg.innerHTML = `<div class="reflib-sim-box"><div class="reflib-sim-head">${esc(st("title"))}<button type="button" class="reflib-sim-x" data-s="close">×</button></div>
              <div class="reflib-sim-qs">${thumbs()}<span>${esc(st("q_n", { n: hashes.length + files.length }))}</span></div>
              <label class="reflib-sim-drop" data-s="drop">${esc(st("drop"))}<input type="file" accept="image/*" multiple hidden></label>
              <div class="reflib-sim-row"><span>${esc(st("mode"))}</span><span class="reflib-sim-seg">${["pose", "face", "both"].map(m => `<button type="button" data-s="mode" data-v="${m}" class="${opts.mode === m ? "on" : ""}">${esc(st("m_" + m))}</button>`).join("")}</span></div>
              <div class="reflib-sim-row" ${opts.mode === "both" ? "" : "hidden"}><span>${esc(st("w"))}</span><input type="range" min="0" max="1" step="0.05" value="${opts.w_pose}" data-s="w"><b>${Math.round(opts.w_pose * 100)}%</b></div>
              <div class="reflib-sim-row"><span>${esc(st("thr"))}</span><input type="range" min="0" max="0.95" step="0.05" value="${opts.threshold}" data-s="thr"><b>${Math.round(opts.threshold * 100)}%</b></div>
              <div class="reflib-sim-row" ${hashes.length + files.length > 1 ? "" : "hidden"}><span>${esc(st("agg"))}</span><select data-s="agg"><option value="any" ${opts.agg === "any" ? "selected" : ""}>${esc(st("a_any"))}</option><option value="avg" ${opts.agg === "avg" ? "selected" : ""}>${esc(st("a_avg"))}</option></select></div>
              <label class="reflib-sim-row reflib-sim-chk" ${opts.mode === "face" ? "hidden" : ""}><input type="checkbox" data-s="mirror" ${opts.mirror ? "checked" : ""}> ${esc(st("mirror"))}</label>
              <div class="reflib-sim-fm"></div>
              <div class="reflib-sim-status"></div>
              <div class="reflib-sim-foot"><button type="button" class="reflib-ib-btn" data-s="close">${esc(st("cancel"))}</button><button type="button" class="reflib-ib-btn reflib-ib-primary" data-s="go">${esc(st("go"))}</button></div></div>`;
            fmSig = ""; status();
        };
        const addFiles = list => {
            [...list].filter(f => /^image\//.test(f.type)).slice(0, 12 - files.length).forEach(f => {
                const r = new FileReader(); r.onload = () => { files.push({ name: f.name, data: r.result }); draw(); }; r.readAsDataURL(f);
            });
        };
        dlg.addEventListener("click", e => {
            const b = e.target.closest("[data-s]"); if (!b) { if (e.target === dlg) close(); return; }
            const k = b.dataset.s;
            if (k === "close") close();
            else if (k === "mode") { opts.mode = b.dataset.v; saveOpts(); draw(); }
            else if (k === "go") go(hashes, files, b);
            else if (k === "build" || k === "rebuild") RL.sendIlib({ action: "sim_index", all: true, force: k === "rebuild" }).then(status);
            else if (k === "faces") RL.sendIlib({ action: "sim_index", all: true, faces_only: true }).then(status);
            else if (k === "pause") RL.sendIlib({ action: "sim_pause", paused: b.dataset.v === "1" }).then(status);
            else if (k === "stop") RL.sendIlib({ action: "sim_cancel" }).then(status);
        });
        dlg.addEventListener("input", e => {
            const k = e.target.dataset.s;
            if (k === "w") opts.w_pose = +e.target.value; else if (k === "thr") opts.threshold = +e.target.value; else return;
            e.target.nextElementSibling.textContent = Math.round(+e.target.value * 100) + "%"; saveOpts();
        });
        dlg.addEventListener("change", e => {
            const k = e.target.dataset.s;
            if (k === "fm") { fmSig = ""; RL.sendIlib({ action: "sim_settings", settings: { face_model: e.target.value } }).then(status); return; }
            if (k === "agg") opts.agg = e.target.value; else if (k === "mirror") opts.mirror = e.target.checked; else if (e.target.type === "file") addFiles(e.target.files); else return;
            saveOpts();
        });
        dlg.addEventListener("dragover", e => { e.preventDefault(); e.stopPropagation(); });
        dlg.addEventListener("drop", e => { e.preventDefault(); e.stopPropagation(); if (e.dataTransfer && e.dataTransfer.files) addFiles(e.dataTransfer.files); });
        draw();
        poll = setInterval(status, 1500);
    }
    let fmSig = "";
    function close() { if (poll) clearInterval(poll); poll = null; if (dlg) dlg.remove(); dlg = null; }
    function status() {
        const host = dlg && dlg.querySelector(".reflib-sim-status"); if (!host) return Promise.resolve();
        return RL.sendIlib({ action: "sim_status" }).then(r => {
            if (!r || !r.ok || !dlg) return;
            const s = r.sim || r, ix = s.index || {}, run = s.running && !s.paused;
            const wait = s.paused ? st("wait_paused") : s.waiting === "busy" ? st("wait_busy") : String(s.waiting || "").startsWith("download:") ? st("dl", { m: s.waiting.slice(9) }) : "";
            const pct = s.total ? Math.round(100 * s.done / s.total) : 0;
            const dl = s.download, mb = v => (v / 1e6).toFixed(0);
            const dlTxt = dl ? st("dlp", { m: dl.file, d: mb(dl.done), t: mb(dl.total), p: dl.total ? Math.round(100 * dl.done / dl.total) : 0 }) : "";
            const fms = s.face_models || [], sel = s.face_model_setting || s.face_model, cur = fms.find(m => m.id === sel) || {};
            const fmHost = dlg.querySelector(".reflib-sim-fm");
            const sig = JSON.stringify([lang(), sel, s.face_model, s.face_fallback, s.library, fms.map(m => [m.images, m.downloaded])]);
            if (fmHost && sig !== fmSig) {
                fmSig = sig;
                fmHost.innerHTML = `<label>${esc(st("fm"))} <select data-s="fm">${fms.map(m => `<option value="${esc(m.id)}"${m.id === sel ? " selected" : ""}>${esc(m.label)} — ${esc(m.downloaded ? st("fm_done", { n: m.images, l: s.library || 0 }) : st("fm_dl", { mb: m.mb }))}</option>`).join("")}</select></label>`
                    + `<div class="reflib-sim-lic">${esc(st("fm_lic", { l: cur.license || "" }))}</div><div class="reflib-sim-lic">${esc(st("fm_switch"))}</div>`
                    + (s.face_fallback ? `<div class="reflib-sim-err">${esc(st("fm_fb", { m: cur.label || sel, e: s.face_fallback }))}</div>` : "");
            }
            host.innerHTML = `<div>${esc(st("idx", { i: ix.images || 0, l: s.library || 0, p: ix.persons || 0, f: ix.faces || 0 }))} · <span class="reflib-sim-lic">${esc(st("face_lic", { m: s.face_model }))}</span></div>`
                + (s.running ? `<div class="reflib-sim-prog"><i style="width:${pct}%"></i></div><div>${esc(st("run", { d: s.done, t: s.total, ms: s.per_image_ms || "…" }))} ${wait ? "· " + esc(wait) : ""}</div>` : "")
                + (dlTxt ? `<div class="reflib-sim-dl">${esc(dlTxt)}</div><div class="reflib-sim-prog"><i style="width:${dl.total ? Math.round(100 * dl.done / dl.total) : 0}%"></i></div>` : "")
                + (s.error ? `<div class="reflib-sim-err">${esc(s.env_missing ? st("env", { e: s.error }) : s.error)}</div>` : "")
                + `<div class="reflib-sim-acts">${s.running ? `<button type="button" class="reflib-ib-btn" data-s="pause" data-v="${s.paused ? 0 : 1}">${esc(st(s.paused ? "resume" : "pause"))}</button><button type="button" class="reflib-ib-btn" data-s="stop">${esc(st("stop"))}</button>`
                    : `<button type="button" class="reflib-ib-btn" data-s="build">${esc(st("build"))}</button>${ix.images ? `<button type="button" class="reflib-ib-btn" data-s="faces">${esc(st("faces_build", { m: (cur.label || sel || "").split(" (")[0] }))}</button>` : ""}${ix.images ? `<button type="button" class="reflib-ib-btn" data-s="rebuild">${esc(st("rebuild"))}</button>` : ""}`}</div>`;
            void run;
        }).catch(() => {});
    }
    function go(hashes, files, b) {
        if (!hashes.length && !files.length) { RL.toast(st("no_q"), "warn"); return; }
        b.disabled = true;
        const t0 = Date.now();
        const req = Object.assign({ action: "sim_search", files, mode: opts.mode, w_pose: opts.w_pose, threshold: opts.threshold, agg: opts.agg, mirror: opts.mirror, slow: true }, { hashes });
        RL.sendIlib(req).then(r => {
            b.disabled = false;
            if (!r || !r.ok) { RL.toast(r && r.error === "no_query" ? st("none") : r && r.error === "no_query_input" ? st("no_q") : (r && r.env_missing ? st("env", { e: r.detail || "" }) : st("engine", { e: (r && (r.detail || r.error)) || "?" })), "warn"); return; }
            labels[r.sid] = st("chip", { n: hashes.length && !files.length ? (hashes.length === 1 ? (itemOf(hashes[0]).name || "1") : hashes.length) : files.length && !hashes.length ? st("chip_files", { n: files.length }) : hashes.length + files.length, m: st("m_" + opts.mode) });
            try { sessionStorage.setItem("reflib_sim_labels", JSON.stringify(labels)); } catch (e) {}
            close();
            const f = ilib().f;
            f.cols.clear(); f.none = false; f.node = null; f.tags.clear(); f.atags.clear(); f.xtags.clear(); f.ranges = {}; f.q = ""; f.jst = ""; f.kind = ""; f.hasmask = false; f.missing = false; f.recent = false; f.used = false;
            f.sim = r.sid;
            const qi = ilib().root && ilib().root.querySelector(".reflib-ib-q"); if (qi) qi.value = "";
            RL.ilibRefresh();
            RL.toast(st("found", { n: r.n, ms: Date.now() - t0 }), "info");
        }).catch(e => { b.disabled = false; RL.toast(st("engine", { e: String((e && e.message) || e) }), "error"); });
    }
    RL.extend({
        ctx: (h, it) => isImg(it) ? btn("reflib-ib-ctxitem", "simfind", h) : "",
        details: (h) => {
            const it = itemOf(h);
            if (!isImg(it)) return "";
            return btn("reflib-ib-btn", "simfind", h) + (it.sim != null ? `<span class="reflib-sim-score">${esc(st("score", { s: Math.round(it.sim * 100) }))}</span>` : "");
        },
        selbar: (n) => n > 1 && n <= 50 && !ilib().sel.all ? btn("reflib-ib-btn", "simfindsel", "", n) : "",
        chips: (f) => f.sim ? [`<span class="reflib-ib-fchip sim">⧉ ${esc(labels[f.sim] || st("find"))}<button type="button" data-act="simclear" title="×">×</button></span>`] : [],
        clear: (f) => { f.sim = ""; },
        navLabel: (f) => f.sim ? "⧉ " + (labels[f.sim] || st("find")) : "",
        act: (act, el) => {
            if (act === "simfind") { open([el.dataset.hash]); return true; }
            if (act === "simfindsel") { open([...ilib().sel].slice(0, 50)); return true; }
            if (act === "simclear") { ilib().f.sim = ""; RL.ilibRefresh(); return true; }
            return false;
        },
    });
    RL.simOpen = open;
    const css = document.createElement("style");
    css.textContent = `
.reflib-sim-dlg { position: absolute; inset: 0; z-index: 60; display: flex; align-items: center; justify-content: center; background: rgba(0,0,0,.45); }
.reflib-sim-box { width: min(560px, 94%); max-height: 92%; overflow: auto; box-sizing: border-box; padding: 14px 16px; border-radius: 10px; display: flex; flex-direction: column; gap: 10px;
  background: var(--background-fill-primary, #fff); color: var(--body-text-color, #111); border: 1px solid var(--border-color-primary, #d1d5db); box-shadow: 0 10px 40px rgba(0,0,0,.35); font-size: 13px; }
.reflib-sim-head { display: flex; justify-content: space-between; font-weight: 600; font-size: 15px; }
.reflib-sim-x { background: none; border: 0; font-size: 18px; cursor: pointer; color: inherit; }
.reflib-sim-qs { display: flex; flex-wrap: wrap; gap: 6px; align-items: center; }
.reflib-sim-qs img { width: 56px; height: 56px; object-fit: cover; border-radius: 6px; border: 1px solid var(--border-color-primary, #d1d5db); }
.reflib-sim-qs span { opacity: .75; margin-left: 4px; }
.reflib-sim-drop { display: block; padding: 10px; text-align: center; border: 2px dashed var(--border-color-primary, #9ca3af); border-radius: 8px; cursor: pointer; opacity: .85; }
.reflib-sim-row { display: flex; align-items: center; gap: 10px; }
.reflib-sim-row[hidden] { display: none; }
.reflib-sim-row > span:first-child { min-width: 150px; opacity: .85; }
.reflib-sim-row input[type=range] { flex: 1; }
.reflib-sim-row select { flex: 1; background: var(--input-background-fill, transparent); color: inherit; border: 1px solid var(--border-color-primary, #d1d5db); border-radius: 6px; padding: 3px; }
.reflib-sim-seg { display: inline-flex; border: 1px solid var(--border-color-primary, #d1d5db); border-radius: 6px; overflow: hidden; }
.reflib-sim-seg button { background: none; border: 0; padding: 4px 14px; cursor: pointer; color: inherit; }
.reflib-sim-seg button.on { background: #3b82f6; color: #fff; }
.reflib-sim-fm { display: flex; flex-direction: column; gap: 4px; font-size: 12px; }
.reflib-sim-fm select { max-width: 100%; background: var(--input-background-fill, transparent); color: inherit; border: 1px solid var(--border-color-primary, #ccc); border-radius: 6px; padding: 2px 4px; }
.reflib-sim-dl { font-size: 12px; }
.reflib-sim-status { padding: 8px; border-radius: 8px; background: var(--background-fill-secondary, #f3f4f6); display: flex; flex-direction: column; gap: 6px; }
.reflib-sim-prog { height: 6px; border-radius: 3px; background: rgba(127,127,127,.3); overflow: hidden; }
.reflib-sim-prog i { display: block; height: 100%; background: #3b82f6; }
.reflib-sim-acts { display: flex; gap: 6px; }
.reflib-sim-err { color: #dc2626; }
.dark .reflib-sim-err { color: #f87171; }
.reflib-sim-lic { opacity: .7; }
.reflib-sim-foot { display: flex; justify-content: flex-end; gap: 8px; }
.reflib-sim-score { margin-left: 6px; font-size: 12px; opacity: .8; }
.reflib-ib-fchip.sim { background: rgba(59,130,246,.18); }`;
    document.head.appendChild(css);
    document.addEventListener("keydown", e => { if (dlg && e.key === "Escape") { e.stopPropagation(); close(); } }, true);
})();
