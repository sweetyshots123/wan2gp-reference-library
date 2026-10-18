// Reference Library __REFLIB_VERSION__ - named collections for WanGP Reference Images.
(() => {
    if (window.referenceLibrary && window.referenceLibrary.version) return;
    const VERSION = "__REFLIB_VERSION__";
    let cfg = __REFLIB_SETTINGS__;
    const log = (...a) => console.log("[Reference Library]", ...a);
    const I18N = {
        en: {
            error: "Error: {e}",
            tab_missing: "Could not open the Reference Library tab",
            settings_applied: "Settings applied",
            undo: "Undo",
            tip_dd: "Collection to load into Reference Images",
            tip_apply: "Load the selected collection into Reference Images",
            tip_save: "Save the current Reference Images as a new collection",
            tip_update: "Overwrite the selected collection with the current Reference Images",
            tip_manage: "Open the Reference Library tab",
            tip_name_ok: "Save (Enter)",
            tip_name_cancel: "Cancel (Esc)",
            chips_label: "Prompts:",
            chip_tip: "Use this prompt (replaces the prompt box)",
            apply_failed: "Could not load the collection: {e}",
            tip_vdd: "Video from the library to load into Control Video",
            tip_vload: "Load the selected video into Control Video",
            tip_vsave: "Save the current Control Video in the video library",
            tip_vmanage: "Open the video library (Reference Library tab)",
            control_hidden: "Control Video isn't shown right now. Pick a Control Video mode for this model first.",
            vapply_failed: "Could not load the video: {e}",
            vadd_failed: "Could not add the video to the library: {e}",
            rename_col: "Rename the collection (or double-click)",
            rename_video: "Rename the video (or double-click)",
            rename_col_ph: "Rename collection…",
            rename_video_ph: "Rename video…",
            need_name: "Enter a name for the collection",
            need_vname: "Enter a name for the video",
        },
        es: {
            error: "Error: {e}",
            tab_missing: "No se pudo abrir la pestaña Reference Library",
            settings_applied: "Ajustes aplicados",
            undo: "Deshacer",
            tip_dd: "Colección que se carga en Referencias",
            tip_apply: "Cargar la colección elegida en Referencias",
            tip_save: "Guardar las Referencias actuales como una colección nueva",
            tip_update: "Sobrescribir la colección elegida con las Referencias actuales",
            tip_manage: "Abrir la pestaña Reference Library",
            tip_name_ok: "Guardar (Intro)",
            tip_name_cancel: "Cancelar (Esc)",
            chips_label: "Prompts:",
            chip_tip: "Usar este prompt (sustituye el cuadro de prompt)",
            apply_failed: "No se pudo cargar la colección: {e}",
            tip_vdd: "Vídeo de la librería que se carga en Vídeo de control",
            tip_vload: "Cargar el vídeo elegido en Vídeo de control",
            tip_vsave: "Guardar el Vídeo de control actual en la librería de vídeos",
            tip_vmanage: "Abrir la librería de vídeos (pestaña Reference Library)",
            control_hidden: "Vídeo de control no se muestra ahora. Elige primero un modo de vídeo de control para este modelo.",
            vapply_failed: "No se pudo cargar el vídeo: {e}",
            vadd_failed: "No se pudo añadir el vídeo a la librería: {e}",
            rename_col: "Renombrar la colección (o doble clic)",
            rename_video: "Renombrar el vídeo (o doble clic)",
            rename_col_ph: "Renombrar colección…",
            rename_video_ph: "Renombrar vídeo…",
            need_name: "Escribe un nombre para la colección",
            need_vname: "Escribe un nombre para el vídeo",
        },
    };
    const browserLang = () => String(navigator.language || (navigator.languages && navigator.languages[0]) || "");
    const lang = () => (cfg.language === "en" || cfg.language === "es") ? cfg.language
        : (browserLang().toLowerCase().startsWith("es") ? "es" : "en");
    function t(key, params = {}) {
        const table = I18N[lang()] || I18N.en;
        const text = key in table ? table[key] : (I18N.en[key] ?? key);
        return text.replace(/\{(\w+)\}/g, (m, k) => (k in params ? String(params[k]) : m));
    }

    const style = document.createElement("style");
    style.id = "reflib-style";
    style.textContent = `
/* Bottom-right corner: top-centre is shared by Dragger / Cropper / Prompt Library toasts and bottom-centre by Vidosser.
   Newest at the bottom, older ones stack upwards. Above Cropper's dialog (10050) and the other plugins' toasts. */
.reflib-toasts { position: fixed; right: 20px; bottom: 20px; z-index: 10090;
  display: flex; flex-direction: column; align-items: flex-end; gap: 8px; pointer-events: none; max-width: min(92vw, 520px);
  max-height: calc(100vh - 40px); overflow: hidden; }
.reflib-toast { pointer-events: auto; display: flex; align-items: center; gap: 12px; padding: 10px 16px; border-radius: 10px;
  font: 500 14px/1.35 system-ui, sans-serif; color: #fff; background: #0f766e; box-shadow: 0 6px 22px rgba(0,0,0,.35);
  opacity: 1; transition: opacity .3s; white-space: pre-line; }
.reflib-toast[data-kind="error"] { background: #b91c1c; }
.reflib-toast[data-kind="info"] { background: #1f2937; border: 1px solid #374151; }
.reflib-toast.hiding { opacity: 0; }
.reflib-toast button { all: unset; cursor: pointer; padding: 4px 10px; border-radius: 6px; background: rgba(255,255,255,.18);
  font-weight: 700; white-space: nowrap; }
.reflib-toast button:hover { background: rgba(255,255,255,.3); }
`;
    style.textContent += __REFLIB_CSS__;
    document.head.appendChild(style);

    // ---- bar: "Save as…" inline row + tooltips ----
    const TABS = ["generate", "edit"];
    // p = "bar" (Reference Images bar) or "vbar" (video bar under Control Video)
    const kindOf = (p) => (p === "vbar" ? "vbar" : "bar");
    function nameRow(tab, p) { return document.getElementById(`reflib_${kindOf(p)}_name_row_${tab}`); }
    function nameInput(tab, p) {
        const root = document.getElementById(`reflib_${kindOf(p)}_name_${tab}`);
        return root && (root.querySelector("input, textarea") || (/^(INPUT|TEXTAREA)$/.test(root.tagName) ? root : null));
    }
    function openNameRow(tab, p) {
        const row = nameRow(tab, p);
        if (!row) return false;
        row.dataset.open = "1";
        setTimeout(() => { const i = nameInput(tab, p); if (i) { i.focus(); i.select && i.select(); } }, 30);
        return true;
    }
    function closeNameRow(tab, p) {
        const row = nameRow(tab, p);
        if (row) delete row.dataset.open;
        return true;
    }
    function toggleNameRow(tab, p) {
        const row = nameRow(tab, p);
        if (row && row.dataset.open === "1") return closeNameRow(tab, p);
        return openNameRow(tab, p);
    }
    function afterSave(tab, raw, p) {
        let data = raw;
        try { data = typeof raw === "string" ? JSON.parse(raw || "{}") : raw; } catch (_) { return; }
        if (data && data.ok) closeNameRow(tab, p);
        else { const i = nameInput(tab, p); if (i) i.focus(); }
    }
    document.addEventListener("keydown", (e) => {
        if (e.key !== "Escape" || !e.target || !e.target.closest) return;
        const row = e.target.closest("[id^='reflib_bar_name_row_'], [id^='reflib_vbar_name_row_']");
        if (!row || row.dataset.open !== "1") return;
        const p = row.id.startsWith("reflib_vbar_") ? "vbar" : "bar";
        const tab = row.id.replace(`reflib_${p}_name_row_`, "");
        const cancel = document.getElementById(`reflib_${p}_name_cancel_${tab}`);
        e.preventDefault();
        e.stopPropagation();
        if (cancel) cancel.click(); else closeNameRow(tab, p);
    }, true);
    function applyTooltips() {
        for (const tab of TABS) {
            for (const [suffix, key] of [["apply", "tip_apply"], ["save", "tip_save"], ["update", "tip_update"],
                                         ["manage", "tip_manage"], ["name_ok", "tip_name_ok"], ["name_cancel", "tip_name_cancel"],
                                         ["dd", "tip_dd"]]) {
                const el = document.getElementById(`reflib_bar_${suffix}_${tab}`);
                if (!el) continue;
                const tip = t(key);
                const target = suffix === "dd" ? (el.querySelector("input") || el) : el;
                if (target.getAttribute("title") !== tip) target.setAttribute("title", tip);
            }
            for (const [suffix, key] of [["load", "tip_vload"], ["save", "tip_vsave"], ["manage", "tip_vmanage"],
                                         ["name_ok", "tip_name_ok"], ["name_cancel", "tip_name_cancel"], ["dd", "tip_vdd"]]) {
                const el = document.getElementById(`reflib_vbar_${suffix}_${tab}`);
                if (!el) continue;
                const tip = t(key);
                const target = suffix === "dd" ? (el.querySelector("input") || el) : el;
                if (target.getAttribute("title") !== tip) target.setAttribute("title", tip);
            }
        }
    }
    setInterval(applyTooltips, 1500);
    // The video bar follows the Control Video block: hidden whenever WanGP hides that input.
    function controlBlock(tab) { return document.querySelector(".reflib-vt-" + tab); }
    function controlVisible(tab) {
        // Shown by WanGP for the current model/mode (an inactive main tab doesn't count as hidden).
        let el = controlBlock(tab);
        if (!el) return false;
        while (el && el !== document.body) {
            if (el.getAttribute && el.getAttribute("role") === "tabpanel") return true;
            if (el.classList.contains("hidden") || getComputedStyle(el).display === "none") return false;
            el = el.parentElement;
        }
        return true;
    }
    function syncVideoBars() {
        for (const tab of TABS) {
            const bar = document.getElementById("reflib_vbar_" + tab);
            const el = controlBlock(tab);
            if (!bar || !el) continue;
            // Only compare with the block itself: when the whole form is hidden both are, so nothing changes.
            const hidden = el.classList.contains("hidden") || getComputedStyle(el).display === "none";
            if (hidden && bar.dataset.targetHidden !== "1") bar.dataset.targetHidden = "1";
            else if (!hidden && bar.dataset.targetHidden) delete bar.dataset.targetHidden;
        }
    }
    setInterval(syncVideoBars, 400);

    function ensureToasts() {
        let box = document.querySelector(".reflib-toasts");
        if (!box) {
            box = document.createElement("div");
            box.className = "reflib-toasts";
            document.body.appendChild(box);
        }
        return box;
    }
    function toast(text, kind, buttons, durationMs) {
        if (!text) return;
        if (kind !== "error" && kind !== "info" && !(buttons && buttons.length) && cfg.toasts === false) return;
        const el = document.createElement("div");
        el.className = "reflib-toast";
        el.dataset.kind = kind || "ok";
        const span = document.createElement("span");
        span.textContent = text;
        el.appendChild(span);
        for (const b of buttons || []) {
            const btn = document.createElement("button");
            btn.textContent = b.label;
            btn.addEventListener("click", () => { try { b.onClick(); } catch (e) {} el.remove(); });
            el.appendChild(btn);
        }
        const box = ensureToasts();
        box.appendChild(el);
        // Keep the stack short: drop the oldest plain messages first, never a toast that still offers a button.
        while (box.children.length > 5) {
            const old = [...box.children].find(c => c !== el && !c.querySelector("button")) || box.firstElementChild;
            if (!old || old === el) break;
            old.remove();
        }
        const ms = Math.max(1000, Math.min(60000, Number(durationMs) || Number(cfg.toast_ms) || 3500));
        setTimeout(() => { el.classList.add("hiding"); setTimeout(() => el.remove(), 350); }, ms);
    }
    function setText(elemId, value) {
        const root = document.getElementById(elemId);
        if (!root) return false;
        const ta = root.tagName === "TEXTAREA" ? root : root.querySelector("textarea");
        if (!ta) return false;
        const setter = Object.getOwnPropertyDescriptor(HTMLTextAreaElement.prototype, "value")?.set;
        if (setter) setter.call(ta, value); else ta.value = value;
        ta.dispatchEvent(new Event("input", { bubbles: true }));
        return true;
    }
    // ---- events for other plugins (Prompt Library) ----
    function emit(name, detail) {
        try { window.dispatchEvent(new CustomEvent(name, { detail })); } catch (e) { log("event failed", name, e); }
    }
    const applied = {};  // tab -> {id, prompts, active}
    function chipsHost(tab) {
        const root = document.getElementById("reflib_bar_chips_" + tab);
        if (!root) return null;
        let box = root.querySelector(":scope .reflib-chips");
        if (!box) {
            box = document.createElement("div");
            box.className = "reflib-chips";
            root.appendChild(box);
        }
        return box;
    }
    function renderChips(tab) {
        const box = chipsHost(tab);
        if (!box) return;
        const st = applied[tab];
        box.textContent = "";
        if (!st || !st.prompts || !st.prompts.length) return;
        const label = document.createElement("span");
        label.className = "reflib-chips-label";
        label.textContent = t("chips_label");
        box.appendChild(label);
        for (const p of st.prompts) {
            const b = document.createElement("button");
            b.type = "button";
            b.className = "reflib-chip" + (st.active === p.id ? " active" : "");
            b.dataset.pid = p.id;
            b.dataset.tab = tab;
            b.title = `${p.title}\n${t("chip_tip")}`;
            const span = document.createElement("span");
            span.className = "reflib-chip-text";
            span.textContent = p.title;
            b.appendChild(span);
            box.appendChild(b);
        }
    }
    function applyPrompt(tab, pid, auto) {
        const st = applied[tab] || {};
        st.active = pid;
        applied[tab] = st;
        renderChips(tab);
        emit("promptlib:apply", { id: pid, source: "reference-library", collection_id: st.id || null, tab, auto: !!auto });
    }
    document.addEventListener("click", (e) => {
        const chip = e.target && e.target.closest && e.target.closest(".reflib-chip");
        if (!chip) return;
        e.preventDefault();
        applyPrompt(chip.dataset.tab || "generate", chip.dataset.pid, false);
    });
    function onApplied(data) {
        const tab = data.tab || "generate";
        const a = data.applied;
        emit("reflib:applied", { id: a.id, name: a.name, count: a.count, tab });
        const prompts = Array.isArray(data.prompts) ? data.prompts : [];
        applied[tab] = { id: a.id, prompts, active: null };
        renderChips(tab);
        // Only "apply_first" may change the prompt box automatically; "offer" never does.
        if (data.prompt_mode === "apply_first" && prompts.length) applyPrompt(tab, prompts[0].id, true);
    }
    let refreshTimer = null;
    function refreshPrompts() {
        clearTimeout(refreshTimer);
        refreshTimer = setTimeout(() => {
            const btn = document.getElementById("reflib_prompts_refresh");
            if (btn) btn.click();
        }, 250);
    }
    function promptsRefreshed(raw) {
        let data;
        try { data = typeof raw === "string" ? JSON.parse(raw || "{}") : raw; } catch (_) { return; }
        if (!data) return;
        for (const tab of ["generate", "edit"]) {
            const info = (data.bars || {})[tab];
            const prev = applied[tab];
            if (!prev) continue; // only chips this page created are refreshed
            if (!info || !data.available || info.id !== prev.id) {
                prev.prompts = []; renderChips(tab);
                continue;
            }
            const active = prev && prev.id === info.id && (info.prompts || []).some(p => p.id === prev.active) ? prev.active : null;
            applied[tab] = { id: info.id, prompts: info.prompts || [], active };
            renderChips(tab);
        }
    }
    window.addEventListener("promptlib:changed", refreshPrompts);
    window.addEventListener("reflib:apply", (e) => {
        const d = (e && e.detail) || {};
        if (!d.id) return;
        const req = { action: "apply", collection_id: String(d.id), target: "generate:image_refs" };
        if (d.mode === "replace" || d.mode === "append") req.mode = d.mode;
        sendBridge(req).catch(err => toast(t("apply_failed", { e: (err && err.message) || err }), "error"));
    });

    let vreloadTimer = null;

    // ---- inline rename with a pencil (1.3.0), same look and behaviour as Prompt Library ----
    const PEN_SVG = '<svg viewBox="0 0 24 24" aria-hidden="true"><path d="M4 20h4L19 9l-4-4L4 16v4ZM13.5 6.5l4 4" fill="none" stroke="currentColor" stroke-width="2.2" stroke-linejoin="round"/></svg>';
    // Dropdown labels are built by the plugin: collections "Name (N)", videos "Name · duration[ · W×H]".
    function nameFromLabel(kind, label) {
        label = String(label || "");
        if (kind === "col") { const m = label.match(/^(.*) \((\d+)\)$/); return m ? m[1] : ""; }
        const m = label.match(/^(.*?) · (–|\d+(?:\.\d+)? s|\d+(?::\d\d){1,2})(?: · \d+×\d+)?$/);
        return m ? m[1] : "";
    }
    function renameTargets() {
        const out = [];
        for (const tab of TABS) {
            out.push({ scope: "bar", tab, kind: "col", id: "reflib_bar_dd_" + tab });
            out.push({ scope: "vbar", tab, kind: "video", id: "reflib_vbar_dd_" + tab });
        }
        out.push({ scope: "mgr", tab: "generate", kind: "col", id: "reflib_mgr_dd" });
        return out;
    }
    function mountPencils() {
        for (const spec of renameTargets()) {
            const root = document.getElementById(spec.id);
            const input = root && root.querySelector("input");
            if (!input) continue;
            const wrap = input.closest(".wrap") || input.parentElement;
            if (!wrap) continue;
            let pen = wrap.querySelector(":scope > .reflib-pen");
            if (!pen) {
                wrap.classList.add("reflib-renamable");
                pen = document.createElement("button");
                pen.type = "button";
                pen.className = "reflib-pen";
                pen.innerHTML = PEN_SVG;
                pen.addEventListener("mousedown", (e) => { e.preventDefault(); e.stopPropagation(); });
                pen.addEventListener("click", (e) => {
                    e.preventDefault(); e.stopPropagation();
                    const st = wrap.__reflibRename;
                    if (st) st.finish(true); else startRename(spec, wrap, input);
                });
                input.addEventListener("dblclick", (e) => {
                    if (wrap.__reflibRename || !nameFromLabel(spec.kind, input.value)) return;
                    e.preventDefault();
                    startRename(spec, wrap, input);
                });
                wrap.appendChild(pen);
            }
            const tip = t(spec.kind === "col" ? "rename_col" : "rename_video");
            if (pen.title !== tip) { pen.title = tip; pen.setAttribute("aria-label", tip); }
            if (!wrap.__reflibRename) wrap.classList.toggle("reflib-has-current", !!nameFromLabel(spec.kind, input.value));
        }
        // Videos section: the selected video's name in the details line.
        const meta = document.querySelector("#reflib_vmgr_meta .reflib-vmeta[data-vid]");
        const nameEl = meta && meta.querySelector(".reflib-vinfo-name");
        if (nameEl && !meta.querySelector(".reflib-pen") && !meta.querySelector(".reflib-rename-field")) {
            nameEl.classList.add("reflib-renamable-text");
            const pen = document.createElement("button");
            pen.type = "button";
            pen.className = "reflib-pen reflib-pen-inline";
            pen.innerHTML = PEN_SVG;
            pen.title = t("rename_video");
            pen.setAttribute("aria-label", t("rename_video"));
            const start = (e) => { e.preventDefault(); startInlineRename(meta, nameEl); };
            pen.addEventListener("click", start);
            nameEl.addEventListener("dblclick", start);
            nameEl.insertAdjacentElement("afterend", pen);
        }
    }
    setInterval(mountPencils, 600);
    function sendRename(req) {
        req = Object.assign({ rid: Math.random().toString(16).slice(2) }, req);
        setText("reflib_rename_req", JSON.stringify(req));
        const btn = document.getElementById("reflib_rename_btn");
        if (btn) btn.click();
    }
    function renameResponse(raw) {
        handleToast(raw);
        setTimeout(mountPencils, 200);
    }
    function startRename(spec, wrap, input) {
        const old = nameFromLabel(spec.kind, input.value);
        if (!old || wrap.__reflibRename) return;
        const field = document.createElement("input");
        field.type = "text";
        field.className = "reflib-rename-field";
        field.value = old;
        field.placeholder = t(spec.kind === "col" ? "rename_col_ph" : "rename_video_ph");
        field.setAttribute("spellcheck", "false");
        wrap.classList.add("reflib-renaming");
        wrap.appendChild(field);
        let done = false;
        const st = {
            finish(save, fromBlur) {
                if (done) return;
                const name = field.value.replace(/\s+/g, " ").trim();
                if (save && !name && !fromBlur) { toast(t(spec.kind === "col" ? "need_name" : "need_vname"), "error"); field.focus(); return; }
                done = true;
                wrap.__reflibRename = null;
                field.remove();
                wrap.classList.remove("reflib-renaming");
                if (save && name && name !== old) sendRename({ scope: spec.scope, tab: spec.tab, name });
            },
        };
        wrap.__reflibRename = st;
        field.addEventListener("keydown", (e) => {
            if (e.key === "Enter") { e.preventDefault(); e.stopPropagation(); st.finish(true); }
            else if (e.key === "Escape") { e.preventDefault(); e.stopPropagation(); st.finish(false); }
        });
        field.addEventListener("blur", () => setTimeout(() => { if (document.activeElement !== field) st.finish(true, true); }, 120));
        field.focus();
        field.select();
    }
    function startInlineRename(meta, nameEl) {
        if (meta.querySelector(".reflib-rename-field")) return;
        const old = nameEl.textContent;
        const vid = meta.dataset.vid;
        const field = document.createElement("input");
        field.type = "text";
        field.className = "reflib-rename-field reflib-rename-inline";
        field.value = old;
        field.placeholder = t("rename_video_ph");
        field.setAttribute("spellcheck", "false");
        const pen = meta.querySelector(".reflib-pen");
        nameEl.style.display = "none";
        if (pen) pen.style.display = "none";
        meta.classList.add("reflib-renaming");
        nameEl.insertAdjacentElement("afterend", field);
        let done = false;
        const finish = (save, fromBlur) => {
            if (done) return;
            const name = field.value.replace(/\s+/g, " ").trim();
            if (save && !name && !fromBlur) { toast(t("need_vname"), "error"); field.focus(); return; }
            done = true;
            field.remove();
            nameEl.style.display = "";
            if (pen) pen.style.display = "";
            meta.classList.remove("reflib-renaming");
            if (save && name && name !== old) { nameEl.textContent = name; sendRename({ scope: "vmgr", vid, name }); }
        };
        field.addEventListener("keydown", (e) => {
            if (e.key === "Enter") { e.preventDefault(); e.stopPropagation(); finish(true); }
            else if (e.key === "Escape") { e.preventDefault(); e.stopPropagation(); finish(false); }
        });
        field.addEventListener("blur", () => setTimeout(() => { if (document.activeElement !== field) finish(true, true); }, 120));
        field.focus();
        field.select();
    }
    let reloadTimer = null;
    function reloadLists() {
        clearTimeout(reloadTimer);
        reloadTimer = setTimeout(() => { const b = document.getElementById("reflib_reload"); if (b) b.click(); }, 300);
    }
    function reloadVideos() {
        clearTimeout(vreloadTimer);
        vreloadTimer = setTimeout(() => { const b = document.getElementById("reflib_vreload"); if (b) b.click(); }, 300);
    }
    function handleToast(raw) {
        if (!raw) return;
        let data = raw;
        if (typeof raw === "string") {
            try { data = JSON.parse(raw); } catch (_) { toast(raw, "info"); return; }
        }
        if (!data || typeof data !== "object") return;
        if (data.ok !== false) {
            try {
                if (data.changed) {
                    const detail = { reason: data.changed.reason, id: data.changed.id || null };
                    if (data.changed.kind) detail.kind = data.changed.kind;
                    emit("reflib:changed", detail);
                    if (data.changed.kind === "video") reloadVideos();
                    else if (data.reload) reloadLists();
                }
                if (data.applied) onApplied(data);
                if (data.vapplied) emit("reflib:video-applied", data.vapplied);
                if (data.prompts_changed) refreshPrompts();
            } catch (e) { log("event handling failed", e); }
        }
        if (data.ok === false) { toast(data.error || t("error", { e: "unknown" }), "error"); return; }
        if (data.armed && data.disarm_button) {
            clearTimeout(window.__reflibVDisarm);
            window.__reflibVDisarm = setTimeout(() => { const b = document.getElementById(data.disarm_button); if (b) b.click(); }, 5300);
        }
        if (data.quiet) return;
        const text = data.toast || data.message;
        if (!text) return;
        const kind = data.kind || "ok";
        const buttons = [];
        if (data.undo_token) {
            buttons.push({
                label: data.undo_label || t("undo"),
                onClick: () => {
                    setText("reflib_undo_req", JSON.stringify({ undo_token: data.undo_token }));
                    const btn = document.getElementById(data.undo_button || "reflib_undo_delete");
                    if (btn) btn.click();
                },
            });
        }
        if (data.offer_token) {
            const tab = data.tab || "generate";
            buttons.push({
                label: data.offer_label || "Save",
                onClick: () => sendBridge({ action: data.offer_kind === "image" ? "image_offer_accept" : "video_offer_accept",
                                            token: data.offer_token, target: `${tab}:video_guide` })
                    .catch(err => toast(t("vadd_failed", { e: (err && err.message) || err }), "error")),
            });
        }
        toast(text, kind, buttons, data.sticky_ms);
    }
    // ---- video library: load requests (manager / reflib:video-apply) and adds (reflib:video-add) ----
    function loadVideoRequest(req) {
        const tab = String((req && req.target) || "generate:video_guide").split(":")[0];
        if (!controlVisible(tab)) {
            toast(t("control_hidden"), "error");
            return Promise.resolve({ ok: false, error: "control_hidden" });
        }
        return sendBridge(Object.assign({ action: "video_load", target: `${tab}:video_guide` }, req))
            .catch(err => toast(t("vapply_failed", { e: (err && err.message) || err }), "error"));
    }
    window.addEventListener("reflib:video-apply", (e) => {
        const d = (e && e.detail) || {};
        if (!d.id) return;
        loadVideoRequest({ action: "video_load", video_id: String(d.id), target: "generate:video_guide" });
    });
    window.addEventListener("reflib:video-add", (e) => {
        const d = (e && e.detail) || {};
        if (!d.path) return;
        const req = { action: "video_add", path: String(d.path), source: String(d.source || "manual"), target: "generate:video_guide" };
        if (d.name) req.name = String(d.name);
        if (d.meta && typeof d.meta === "object") req.meta = d.meta;
        sendBridge(req).catch(err => toast(t("vadd_failed", { e: (err && err.message) || err }), "error"));
    });

    const pending = new Map();
    function bridgeButton(target) {
        return document.getElementById("reflib_bridge_" + String(target || "").replace(":", "_"));
    }
    function sendBridge(req) {
        req = Object.assign({ id: Math.random().toString(16).slice(2), lang: lang() }, req || {});
        const target = req.target || "generate:image_refs";
        req.target = target;
        setText("reflib_bridge_req", JSON.stringify(req));
        const btn = bridgeButton(target);
        if (!btn) {
            toast(t("error", { e: "bridge missing (reload)" }), "error");
            return Promise.reject(new Error("bridge missing"));
        }
        return new Promise((resolve, reject) => {
            const timer = setTimeout(() => { pending.delete(req.id); reject(new Error("timeout")); }, 60000);
            pending.set(req.id, { resolve, reject, timer });
            btn.click();
        });
    }
    function bridgeResponse(raw) {
        let data;
        try { data = typeof raw === "string" ? JSON.parse(raw || "{}") : raw; } catch (_) { return; }
        if (!data || !data.id) { handleToast(raw); return; }
        const p = pending.get(data.id);
        if (p) { clearTimeout(p.timer); pending.delete(data.id); p.resolve(data); }
        handleToast(data);
    }

    function openTab(section) {
        const tabs = [...document.querySelectorAll('button[role="tab"], .tab-nav button')];
        let hit = tabs.find(b => /^\s*Reference Library\s*$/i.test((b.textContent || "").trim()));
        if (!hit) hit = [...document.querySelectorAll("button, [role='tab']")].find(b => (b.textContent || "").trim() === "Reference Library");
        if (hit) {
            hit.click();
            if (section === "videos") {
                setTimeout(() => {
                    const panel = document.getElementById("reflib_vsec") || document.getElementById("reflib_vmgr_panel");
                    if (panel) panel.scrollIntoView({ block: "start", behavior: "smooth" });
                }, 350);
            }
            return true;
        }
        toast(t("tab_missing"), "error");
        return false;
    }

    // ---- live language (same pattern as Dragger 1.1.0) ----
    let tabLang = null, localizeWatch = null, tabRequest = null, serverSettingsLoaded = false;
    function localizeTab(force) {
        const want = lang();
        if (!force && tabLang === want) return true;
        const button = document.getElementById("reflib_localize");
        if (!button) return false;
        tabLang = want;
        tabRequest = serverSettingsLoaded ? want : null;
        clearTimeout(localizeWatch);
        let tries = 0;
        const click = () => {
            button.click();
            if (++tries < 8) localizeWatch = setTimeout(click, 1500);
        };
        localizeWatch = setTimeout(click, 30);
        return true;
    }
    function applySettings(json, source) {
        let next;
        try { next = typeof json === "string" ? JSON.parse(json) : json; } catch (e) { return; }
        if (!next || typeof next !== "object") return;
        const fromServer = source === true;
        if (fromServer) {
            clearTimeout(localizeWatch);
            if (serverSettingsLoaded) return;
            serverSettingsLoaded = true;
        }
        cfg = next;
        if (fromServer || source === "saved") tabLang = lang(); else localizeTab(false);
        if (source === "saved") toast(t("settings_applied"), "ok");
        applyTooltips();
        for (const tab of Object.keys(applied)) renderChips(tab);
        log("settings applied, language:", lang());
    }
    (function initTab(tries) {
        if (localizeTab(true) || tries > 600) return;
        setTimeout(() => initTab(tries + 1), 100);
    })(0);


    // =================================================================== image browser (1.4.0)
    // Modal over the page: every image of every collection + the unassigned pool + watched folders, deduplicated by
    // content hash. Filters (collections / unassigned / folders / tags / name), tags, add to collection, import, delete.
    const ILIB_I18N = {
        en: {
            ut_title: "My tags", ut_hint: "Your own groups and tags, saved in user_taxonomy.json (kept across updates).", ut_parent: "Under",
            ut_kind_tag: "Tag", ut_kind_group: "Group", ut_es: "Spanish name", ut_en: "English name", ut_syn_es: "Synonyms ES (comma)", ut_syn_en: "Synonyms EN (comma)",
            ut_excl: "One choice per image (exclusive)", ut_create: "Create", ut_save: "Save", ut_delete: "Delete", ut_undo: "Undo", ut_none: "No custom tags yet.",
            utx_export: "Export taxonomy", utx_full_json: "Full (built-in + mine) · JSON", utx_mine_json: "Only mine · JSON", utx_full_csv: "Full · CSV", utx_mine_csv: "Only mine · CSV", utx_import: "Import…", utx_merge: "Merge", utx_replace: "Replace mine", utx_exported: "Exported {file}", utx_toobig: "File too large (max 2 MB).", utx_badjson: "Not a JSON file.", utx_confirm: "Import taxonomy ({mode}): {added} new, {updated} updated{removed}{rejected}. Continue?", utx_removed: ", {n} of yours removed", utx_rejected: ", {n} rejected", utx_nothing: "Nothing to import{rejected}.", utx_done: "Imported: {added} new, {updated} updated{removed}{rejected}", utx_rej_list: "Rejected:", utx_ok: "Import", ut_created: "Created \"{name}\"", ut_saved: "Saved", ut_deleted: "Deleted \"{name}\"", ut_undone: "Undone",
            ut_newcat: "New category", ut_sub: "Sub", ut_newsub: "New sub-category here", ut_newtag: "New tag here", ut_rename: "Rename / edit",
            ut_move: "Move (or drag it)", ut_one: "one", ut_toplevel: "top level", ut_editing: "Editing", ut_new_category: "New category",
            ut_new_group: "New sub-category", ut_new_tag: "New tag", ut_move_hint: "Click the new place for \"{name}\" (or drag it there)",
            ut_moved: "Moved \"{name}\" to {to}", cancel_btn: "Cancel",
            ut_add_ph: "Add a tag to this image…", ut_added: "Tag added", ut_unknown: "Pick a tag from the list",
            reveal: "Show in folder", reveal_tip: "Opens the folder with this file highlighted", reveal_remote: "Only available when the browser runs on the same PC as WanGP",
            big_preview: "Large preview",
            v_size: "Thumbnail size", v_l: "Very large thumbnails", v_m: "Medium thumbnails", v_s: "Small thumbnails",
            v_details: "Details", v_details_tip: "Show or hide the details panel on the right (selected image)", v_pick: "Select an image to see its details.",
            ctx_details: "Show details", crop: "Crop", crop_tip: "Crop with Cropper; the result is saved to the library", crop_na: "Needs Cropper with file cropping (window.cropper.cropFile, file API 1). Update Cropper to enable it.", crop_audio: "Audio can't be cropped", crop_saved_img: "Crop saved to \u201c{c}\u201d", crop_saved_vid: "Crop saved to the Video Library", crop_fail: "Crop failed: {e}", crop_busy: "A crop is already open", lb_fit: "Fit", lb_fit_tip: "Zoom to fit (0)", lb_1to1: "1:1", lb_1to1_tip: "Actual size, 1:1 (1)",
            lb_prev: "Previous (←)", lb_next: "Next (→)",
            chips_clear: "Clear all", chip_rm: "Remove this filter", chip_or: "or", chip_and: "and", chip_not: "not",
            chip_mode: "Click to switch between include and exclude", chip_find: "Show in the tree", chip_search: "Search: {q}",
            used: "Used as reference", used_tip: "Every image that landed in WanGP's Reference Images (any source), newest use first", used_title: "Images used as reference — newest first",
            used_clear_sel: "Remove selected from this history", used_clear_all: "Clear this history", used_need_sel: "Select images first", used_cleared: "{n} removed from the reference history",
            used_n: "used {n}× · {when}", used_last: "Last used: {when}", used_empty: "No image has been used as reference yet.",
            fs_max: "Full screen", fs_restore: "Restore size", fs_always: "Always open full screen",
            chip_folder: "Folder: {name}", chip_none: "Unassigned", chips_tip: "Same group: any of them (or). Different groups: all of them (and).",
            at_btn: "Auto-tag", at_btn_tip: "Tag the selection automatically with the local model (only new or changed images)",
            at_facets: "Auto tags", at_settings: "Auto-tag settings", at_running: "Auto-tagging {done}/{total}", at_waiting_host: "waiting: WanGP is generating (GPU released)",
            at_paused: "paused", at_pause: "Pause", at_resume: "Resume", at_cancel: "Cancel", at_unload: "Free GPU", at_unload_tip: "Unload the tagging model now",
            at_review: "{n} for review", at_cost: "cost so far ${c}", at_none_facets: "No auto tags yet: select images and click Auto-tag.",
            at_confirm_dl: "First use downloads about {gb} GB of models. Continue?", at_confirm_cloud: "Cloud classifier: {n} image(s), estimated ${usd}{up}. Continue?",
            at_up: ", uploads about {mb} MB", at_go: "Continue", jst_queued: "queued", jst_processing: "processing", jst_done: "done", jst_failed: "failed", jst_local: "local", jst_tip: "Auto-tag status (current or last job)",
            jsf_title: "Tagging status", jsf_queued: "in queue", jsf_processing: "processing", jsf_done: "done", jsf_failed: "failed", jsf_local: "local (fallback / kept local)", jsf_never: "never tagged",
            jsb_queued: "queued", jsb_processing: "processing", jsb_done: "done", jsb_failed: "failed", jst_filter: "Show these images", jst_retry: "Retry failed", locate: "Show folder in tree", locate_tip: "Open the folder tree at this image's folder and show it in the grid (collection images: highlight their collection)", locate_none: "This image is not in a folder or collection.", cl_title: "Paid cloud models (off by default)", cl_enable: "Enable", cl_model_id: "Model id", cl_key: "API key", cl_key_env: "or env {e}",
            cl_price: "USD / 1M tokens: in · out · cache read", cl_batch: "Batch mode for large jobs — off by default (50 % cheaper, results within 24 h; Gemini and GPT)",
            cl_clothed: "Clothed photos only: other photos are tagged locally.", cl_never: "Photos flagged “Review › explicit content” or “appears under 18” are never uploaded; they are always tagged locally. Uploads are downscaled to 1024 px and stripped of EXIF/GPS.",
            cl_warn_price_doubles_2027: "Google doubles this price on 1 Jan 2027.", cl_retention: "Data retention", cl_usage: "Usage / nudity policy",
            cl_pol_google: "Paid tier: prompts and images are not used to train models; kept up to ~55 days for abuse monitoring. Sexual-content filter can be lowered (BLOCK_NONE); sexual content involving minors is always blocked.",
            cl_pol_openai: "API data is not used for training by default; kept up to 30 days for abuse monitoring. Adult sexual content may be refused or reviewed; mass uploads of explicit images can get an account suspended.",
            cl_pol_anthropic: "API data is not used for training; deleted within 30 days (longer if flagged). Usage policy forbids sexual content: only clothed photos are sent.",
            cd_title: "Confirm cloud cost", cd_model: "Model", cd_images: "Images", cd_tokens: "Tokens per image", cd_img_tok: "image ({w}×{h} px)", cd_prompt: "taxonomy prompt",
            cd_out: "output (approx.)", cd_per: "Per image", cd_total: "Total", cd_nocache: "without cache", cd_cache: "with prompt cache", cd_batch: "Batch discount −50 % applied",
            cd_gate: "Photos flagged explicit / under-18 (and, for Claude, any not clothed) stay local and are not billed; the real cost is shown when the job ends.",
            cd_ok: "Start", cd_cancel: "Cancel", cd_nokey: "No API key set for this model.", cd_off: "This cloud model is disabled in settings: the local model ({m}) will be used.",
            rp_title: "Auto-tag report", rp_done: "Processed", rp_sent: "Sent to the cloud", rp_gated: "Kept local by the rules", rp_refused: "Refused → local fallback",
            rp_failed: "Failed", rp_cost: "Real cost (from usage)", rp_tokens: "Tokens: {i} in · {c} cached · {o} out", rp_close: "Close", at_tags: "Auto tags", at_accept: "Accept", at_remove: "Remove", at_restore: "Restore",
            at_conf: "confidence {c}%", at_review_flag: "Marked for review: the person may be under 18. No body or nudity tags are stored.",
            body_title: "Body shape", body_est: "estimated", body_nm: "Not measurable: {r}", body_widths: "Silhouette (width ÷ torso height)",
            body_cm: "Estimated measurements (cm)", body_ratios: "Ratios", body_scores: "Scores", body_prop: "Proportions of height",
            body_height: "Height (cm)", body_height_tip: "Enter the real height to improve the scale; empty = average adult (165 cm)", body_height_col: "for the whole collection",
            body_unc: "± {p}% · scale from {s}, height {h} cm ({src})", body_vlm: "VLM check", body_agree: "agrees", body_disagree: "differs",
            body_ranges: "Body ranges", body_range_tip: "Filter by estimated range",
            set_model: "Model", set_threshold: "Threshold", set_batch: "Batch", set_vram: "VRAM cap (GB)", set_offline: "Offline (only downloaded models)",
            set_body: "Body-shape analysis", set_body_vlm: "VLM cross-check", set_cloud: "Allow cloud (sends images or descriptions)", set_key: "OpenRouter API key",
            set_key_set: "set", set_fallback: "Local fallback", set_jev_url: "Jev server URL (empty = in process)", set_latest: "Jev: use latest instead of pinned 1.13", set_save: "Save",
            browse: "Media browser", browse_tip: "Browse all images, videos and audio (collections, unassigned pool, folders)", close: "Close (Esc)",
            search_ph: "Search by name…", import: "Import", import_tip: "Upload or drop images, videos or audio here: they go to the unassigned pool",
            k_all: "All", k_image: "Photos", k_video: "Videos", k_audio: "Audio", k_tip: "Media type", chip_kind: "Type: {k}",
            k_tree: "{i} photos · {v} videos · {a} audio", dur_none: "duration pending…", play: "Play", pause: "Pause",
            to_vctl: "Use as control video", to_vctl_tip: "Put this video in WanGP's control video input", to_vlib: "Add to Video Library", to_vlib_tip: "Copy the selected videos into the Video Library",
            to_audio: "→ {label}", to_audio_tip: "Put this audio in WanGP's \"{label}\" input (shown by the current model)",
            to_one: "Select a single file for this", only_images_refs: "{n} non-image file(s) skipped (references take images)",
            sent_to: "Sent to {what}", pv_dur: "Duration", pv_codec: "Codec", pv_fps: "Frame rate", pv_rate: "Sample rate",
            rescan: "Re-scan", rescan_tip: "Re-scan the watched folders",
            f_cols: "Collections", f_all: "All", f_none: "Unassigned", f_tags: "Tags", f_folders: "Folders", no_tags: "no tags yet",
            n_images: "{n} files", n_shown: "{shown} of {n}", more: "Show more",
            empty: "Nothing matches these filters.", empty_lib: "The library is empty. Import some files or add a folder.",
            in_n: "In {n} collection(s): {names}", in_none: "Not in any collection", from_folder: "From a watched folder",
            sel_n: "{n} selected", sel_visible: "Select shown", sel_clear: "Clear selection",
            tag_ph: "Add tag…", tag_add: "Add tag", tag_remove: "Remove “{tag}” from the selected images",
            add_to: "Add to collection…", add_go: "Add", add_new: "+ New collection…", add_new_ph: "New collection name",
            add_title: "Add {n} image(s) to", del: "Delete", del_confirm: "Confirm delete", del_tip: "Only unassigned pool images can be deleted",
            undo: "Undo", preview_cols: "Collections", preview_folders: "Files", preview_tags: "Tags", preview_none: "—",
            folders_title: "Watched folders", folder_ph: "Folder on the WanGP machine, e.g. D:\\Fotos\\refs", folder_add: "Add folder",
            recursive: "Include subfolders", folder_remove: "Remove", folder_remove_confirm: "Confirm", folder_missing: "not found",
            folders_note: "Images are read in place (never copied, moved or changed). Adding one to a collection copies it there.",
            drop: "Drop images to import them", pool_badge: "unassigned", folder_badge: "folder", loading: "Loading…",
            add_folder: "Add folder", add_folder_tip: "Watch a folder on the WanGP machine (indexed in place, never copied)", cancel: "Cancel",
            tree_title: "Folders", tree_sub: "Include subfolders", all_images: "All media", up: "Up one level",
            frescan: "Re-scan this folder", fremove: "Remove from the index (files on disk are untouched)", fremove_confirm: "Click again to remove",
            indexing: "Indexing {name}: {done} / {total}", indexing_start: "Indexing {name}…",
            to_refs: "Add to references", to_refs_tip: "Append the selected images to WanGP's Reference Images (duplicates skipped, nothing replaced)",
            recent: "Recent", recent_tip: "Every image, newest first (a view: nothing is copied)", today: "Today", yesterday: "Yesterday",
            this_week: "This week", added_on: "Added {when}", seen_on: "Added / modified {when}", recent_more: "Show older",
            recent_empty: "Nothing added in this period.",
            browse_btn: "Browse…", browse_title: "Choose a folder", pick_this: "Select this folder", drives: "Drives",
            sc_home: "Home", sc_pictures: "Pictures", sc_outputs: "WanGP outputs", pick_images: "{n} images in this folder",
            pick_images_more: "{n}+ images in this folder", pick_nodirs: "No subfolders", pick_roots: "Start", pick_loading: "Reading…",
            del_lib: "Delete from library", del_confirm_n: "Confirm: {n} image(s), {c} collection(s)",
            del_tip_any: "Removes the selected images from every collection and from the unassigned pool (two clicks, Undo)",
            del_tip_disk: "Removes them from every collection and the pool; {k} from watched folders stay on disk",
            del_tip_folder_only: "Only watched-folder images are selected: they are never deleted from disk (remove the folder in the tree to hide them)",
            remove_from: "Remove from {name}", remove_from_tip: "Take the selected images out of \"{name}\" only (Undo)",
            remove_from_none: "None of the selected images is in \"{name}\"",
            pause: "Pause", resume: "Resume", pause_tip: "Pause folder indexing (also in the settings)", resume_tip: "Resume folder indexing",
            idx_paused: "indexing paused", thumbs_gen: "making thumbnails: {n} left",
            close_after: "Close after adding", refs_hidden: "Reference Images isn't available for the current model",
        },
        es: {
            ut_title: "Mis etiquetas", ut_hint: "Tus propios grupos y etiquetas, guardados en user_taxonomy.json (se conservan al actualizar).", ut_parent: "Dentro de",
            ut_kind_tag: "Etiqueta", ut_kind_group: "Grupo", ut_es: "Nombre en español", ut_en: "Nombre en inglés", ut_syn_es: "Sinónimos ES (coma)", ut_syn_en: "Sinónimos EN (coma)",
            ut_excl: "Una sola opción por imagen (exclusivo)", ut_create: "Crear", ut_save: "Guardar", ut_delete: "Borrar", ut_undo: "Deshacer", ut_none: "Aún no hay etiquetas propias.",
            utx_export: "Exportar taxonomía", utx_full_json: "Completa (de serie + mías) · JSON", utx_mine_json: "Solo mías · JSON", utx_full_csv: "Completa · CSV", utx_mine_csv: "Solo mías · CSV", utx_import: "Importar…", utx_merge: "Combinar", utx_replace: "Reemplazar las mías", utx_exported: "Exportado {file}", utx_toobig: "Archivo demasiado grande (máx. 2 MB).", utx_badjson: "No es un archivo JSON.", utx_confirm: "Importar taxonomía ({mode}): {added} nuevas, {updated} actualizadas{removed}{rejected}. ¿Continuar?", utx_removed: ", {n} tuyas eliminadas", utx_rejected: ", {n} rechazadas", utx_nothing: "Nada que importar{rejected}.", utx_done: "Importado: {added} nuevas, {updated} actualizadas{removed}{rejected}", utx_rej_list: "Rechazadas:", utx_ok: "Importar", ut_created: "Creada «{name}»", ut_saved: "Guardado", ut_deleted: "Borrada «{name}»", ut_undone: "Deshecho",
            ut_newcat: "Nueva categoría", ut_sub: "Subcategoría", ut_newsub: "Nueva subcategoría aquí", ut_newtag: "Nueva etiqueta aquí", ut_rename: "Renombrar / editar",
            ut_move: "Mover (o arrástrala)", ut_one: "una", ut_toplevel: "nivel superior", ut_editing: "Editando", ut_new_category: "Nueva categoría",
            ut_new_group: "Nueva subcategoría", ut_new_tag: "Nueva etiqueta", ut_move_hint: "Pulsa el nuevo lugar para «{name}» (o arrástrala allí)",
            ut_moved: "«{name}» movida a {to}", cancel_btn: "Cancelar",
            ut_add_ph: "Añadir etiqueta a esta imagen…", ut_added: "Etiqueta añadida", ut_unknown: "Elige una etiqueta de la lista",
            reveal: "Abrir en el Explorador", reveal_tip: "Abre la carpeta con este archivo resaltado", reveal_remote: "Solo disponible cuando el navegador está en el mismo PC que WanGP",
            big_preview: "Vista grande",
            v_size: "Tamaño de miniaturas", v_l: "Miniaturas muy grandes", v_m: "Miniaturas medianas", v_s: "Miniaturas pequeñas",
            v_details: "Detalles", v_details_tip: "Muestra u oculta el panel de detalles de la derecha (imagen seleccionada)", v_pick: "Selecciona una imagen para ver sus detalles.",
            ctx_details: "Ver detalles", crop: "Recortar", crop_tip: "Recortar con Cropper; el resultado se guarda en la librería", crop_na: "Necesita Cropper con recorte de archivos (window.cropper.cropFile, API de archivos 1). Actualiza Cropper para activarlo.", crop_audio: "Los audios no se pueden recortar", crop_saved_img: "Recorte guardado en «{c}»", crop_saved_vid: "Recorte guardado en la Librería de vídeos", crop_fail: "No se pudo recortar: {e}", crop_busy: "Ya hay un recorte abierto", lb_fit: "Ajustar", lb_fit_tip: "Ajustar a la pantalla (0)", lb_1to1: "1:1", lb_1to1_tip: "Tamaño real, 1:1 (1)",
            lb_prev: "Anterior (←)", lb_next: "Siguiente (→)",
            chips_clear: "Quitar todos", chip_rm: "Quitar este filtro", chip_or: "o", chip_and: "y", chip_not: "no",
            chip_mode: "Clic para alternar entre incluir y excluir", chip_find: "Mostrar en el árbol", chip_search: "Búsqueda: {q}",
            used: "Usadas como referencia", used_tip: "Todas las imágenes que han entrado en Reference Images de WanGP (de cualquier origen), la más reciente primero", used_title: "Imágenes usadas como referencia — más recientes primero",
            used_clear_sel: "Quitar seleccionadas del historial", used_clear_all: "Vaciar historial", used_need_sel: "Selecciona imágenes primero", used_cleared: "{n} quitadas del historial de referencias",
            used_n: "usada {n}× · {when}", used_last: "Último uso: {when}", used_empty: "Aún no se ha usado ninguna imagen como referencia.",
            fs_max: "Pantalla completa", fs_restore: "Restaurar tamaño", fs_always: "Abrir siempre a pantalla completa",
            chip_folder: "Carpeta: {name}", chip_none: "Sin colección", chips_tip: "Mismo grupo: cualquiera (o). Grupos distintos: todos (y).",
            at_btn: "Autoetiquetar", at_btn_tip: "Etiquetar la selección automáticamente con el modelo local (solo imágenes nuevas o cambiadas)",
            at_facets: "Etiquetas automáticas", at_settings: "Ajustes del autoetiquetado", at_running: "Autoetiquetando {done}/{total}", at_waiting_host: "en espera: WanGP está generando (GPU liberada)",
            at_paused: "en pausa", at_pause: "Pausar", at_resume: "Reanudar", at_cancel: "Cancelar", at_unload: "Liberar GPU", at_unload_tip: "Descargar ya el modelo de etiquetado",
            at_review: "{n} para revisar", at_cost: "coste hasta ahora ${c}", at_none_facets: "Aún no hay etiquetas automáticas: selecciona imágenes y pulsa Autoetiquetar.",
            at_confirm_dl: "El primer uso descarga unos {gb} GB de modelos. ¿Continuar?", at_confirm_cloud: "Clasificador en la nube: {n} imagen(es), coste estimado ${usd}{up}. ¿Continuar?",
            at_up: ", sube unos {mb} MB", at_go: "Continuar", jst_queued: "en cola", jst_processing: "procesando", jst_done: "hecha", jst_failed: "falló", jst_local: "local", jst_tip: "Estado del autoetiquetado (trabajo actual o último)",
            jsf_title: "Estado del etiquetado", jsf_queued: "en cola", jsf_processing: "procesando", jsf_done: "hechas", jsf_failed: "fallidas", jsf_local: "local (respaldo / retenida)", jsf_never: "nunca etiquetadas",
            jsb_queued: "en cola", jsb_processing: "procesando", jsb_done: "hechas", jsb_failed: "fallidas", jst_filter: "Mostrar estas imágenes", jst_retry: "Reintentar fallidas", locate: "Localizar carpeta", locate_tip: "Abre el árbol de carpetas en la carpeta de esta imagen y la muestra en la cuadrícula (imágenes de colección: resalta su colección)", locate_none: "Esta imagen no está en ninguna carpeta ni colección.", cl_title: "Modelos de pago en la nube (apagados por defecto)", cl_enable: "Activar", cl_model_id: "Id del modelo", cl_key: "Clave API", cl_key_env: "o variable {e}",
            cl_price: "USD / 1M tokens: entrada · salida · caché", cl_batch: "Modo lote para trabajos grandes — desactivado por defecto (50 % más barato, resultados en 24 h; Gemini y GPT)",
            cl_clothed: "Solo fotos vestidas: las demás se etiquetan en local.", cl_never: "Las fotos marcadas «Revisión › contenido explícito» o «parece menor de edad» nunca se suben; siempre se etiquetan en local. Se envían reducidas a 1024 px y sin EXIF/GPS.",
            cl_warn_price_doubles_2027: "Google duplica este precio el 1 de enero de 2027.", cl_retention: "Retención de datos", cl_usage: "Política de uso / desnudos",
            cl_pol_google: "Plan de pago: no entrena con tus imágenes; se guardan hasta ~55 días para detectar abusos. El filtro sexual se puede bajar (BLOCK_NONE); lo sexual con menores siempre se bloquea.",
            cl_pol_openai: "Por defecto no entrena con datos de la API; se guardan hasta 30 días para detectar abusos. Puede rechazar o revisar contenido sexual adulto; subir desnudos en masa puede suspender la cuenta.",
            cl_pol_anthropic: "No entrena con datos de la API; se borran en 30 días (más si se marcan). Su política prohíbe el contenido sexual: solo se envían fotos vestidas.",
            cd_title: "Confirmar coste en la nube", cd_model: "Modelo", cd_images: "Imágenes", cd_tokens: "Tokens por imagen", cd_img_tok: "imagen ({w}×{h} px)", cd_prompt: "prompt de taxonomía",
            cd_out: "salida (aprox.)", cd_per: "Por imagen", cd_total: "Total", cd_nocache: "sin caché", cd_cache: "con caché del prompt", cd_batch: "Descuento por lote −50 % aplicado",
            cd_gate: "Las fotos explícitas o de posibles menores (y, con Claude, las no vestidas) se quedan en local y no se cobran; el coste real se muestra al terminar.",
            cd_ok: "Empezar", cd_cancel: "Cancelar", cd_nokey: "No hay clave API para este modelo.", cd_off: "Este modelo de nube está desactivado en ajustes: se usará el modelo local ({m}).",
            rp_title: "Informe del autoetiquetado", rp_done: "Procesadas", rp_sent: "Enviadas a la nube", rp_gated: "Retenidas en local por las reglas", rp_refused: "Rechazadas → respaldo local",
            rp_failed: "Fallidas", rp_cost: "Coste real (según uso)", rp_tokens: "Tokens: {i} entrada · {c} en caché · {o} salida", rp_close: "Cerrar", at_tags: "Etiquetas automáticas", at_accept: "Aceptar", at_remove: "Quitar", at_restore: "Restaurar",
            at_conf: "confianza {c}%", at_review_flag: "Marcada para revisión: la persona podría ser menor de 18. No se guardan etiquetas corporales ni de desnudez.",
            body_title: "Forma del cuerpo", body_est: "estimado", body_nm: "No medible: {r}", body_widths: "Silueta (anchura ÷ altura del torso)",
            body_cm: "Medidas estimadas (cm)", body_ratios: "Proporciones", body_scores: "Puntuaciones", body_prop: "Proporciones de la altura",
            body_height: "Altura (cm)", body_height_tip: "Introduce la altura real para mejorar la escala; vacío = adulta media (165 cm)", body_height_col: "para toda la colección",
            body_unc: "± {p}% · escala por {s}, altura {h} cm ({src})", body_vlm: "Comprobación VLM", body_agree: "coincide", body_disagree: "difiere",
            body_ranges: "Rangos corporales", body_range_tip: "Filtrar por rango estimado",
            set_model: "Modelo", set_threshold: "Umbral", set_batch: "Lote", set_vram: "Límite de VRAM (GB)", set_offline: "Sin conexión (solo modelos descargados)",
            set_body: "Análisis de la forma del cuerpo", set_body_vlm: "Comprobación con VLM", set_cloud: "Permitir nube (envía imágenes o descripciones)", set_key: "Clave API de OpenRouter",
            set_key_set: "guardada", set_fallback: "Respaldo local", set_jev_url: "URL del servidor Jev (vacío = en proceso)", set_latest: "Jev: usar la última en vez de la 1.13 fijada", set_save: "Guardar",
            browse: "Explorador de medios", browse_tip: "Examinar imágenes, vídeos y audios (colecciones, sin colección, carpetas)", close: "Cerrar (Esc)",
            search_ph: "Buscar por nombre…", import: "Importar", import_tip: "Sube o suelta aquí imágenes, vídeos o audios: van a la bolsa sin colección",
            k_all: "Todo", k_image: "Fotos", k_video: "Vídeos", k_audio: "Audios", k_tip: "Tipo de medio", chip_kind: "Tipo: {k}",
            k_tree: "{i} fotos · {v} vídeos · {a} audios", dur_none: "duración pendiente…", play: "Reproducir", pause: "Pausa",
            to_vctl: "Usar como vídeo de control", to_vctl_tip: "Pone este vídeo en la entrada de vídeo de control de WanGP", to_vlib: "Añadir a la Librería de vídeos", to_vlib_tip: "Copia los vídeos seleccionados en la Librería de vídeos",
            to_audio: "→ {label}", to_audio_tip: "Pone este audio en la entrada «{label}» de WanGP (la muestra el modelo actual)",
            to_one: "Selecciona un solo archivo para esto", only_images_refs: "{n} archivo(s) que no son imágenes omitidos (las referencias solo admiten imágenes)",
            sent_to: "Enviado a {what}", pv_dur: "Duración", pv_codec: "Códec", pv_fps: "Fotogramas/s", pv_rate: "Frecuencia",
            rescan: "Reescanear", rescan_tip: "Volver a escanear las carpetas vigiladas",
            f_cols: "Colecciones", f_all: "Todas", f_none: "Sin colección", f_tags: "Etiquetas", f_folders: "Carpetas", no_tags: "aún no hay etiquetas",
            n_images: "{n} archivos", n_shown: "{shown} de {n}", more: "Mostrar más",
            empty: "Nada coincide con estos filtros.", empty_lib: "La librería está vacía. Importa archivos o añade una carpeta.",
            in_n: "En {n} colección(es): {names}", in_none: "No está en ninguna colección", from_folder: "De una carpeta vigilada",
            sel_n: "{n} seleccionadas", sel_visible: "Seleccionar las mostradas", sel_clear: "Quitar selección",
            tag_ph: "Añadir etiqueta…", tag_add: "Añadir etiqueta", tag_remove: "Quitar «{tag}» de las imágenes elegidas",
            add_to: "Añadir a colección…", add_go: "Añadir", add_new: "+ Nueva colección…", add_new_ph: "Nombre de la colección nueva",
            add_title: "Añadir {n} imagen(es) a", del: "Borrar", del_confirm: "Confirmar borrado", del_tip: "Solo se pueden borrar imágenes de la bolsa sin colección",
            undo: "Deshacer", preview_cols: "Colecciones", preview_folders: "Archivos", preview_tags: "Etiquetas", preview_none: "—",
            folders_title: "Carpetas vigiladas", folder_ph: "Carpeta del equipo de WanGP, p. ej. D:\\Fotos\\refs", folder_add: "Añadir carpeta",
            recursive: "Incluir subcarpetas", folder_remove: "Quitar", folder_remove_confirm: "Confirmar", folder_missing: "no encontrada",
            folders_note: "Las imágenes se leen en su sitio (nunca se copian, mueven ni cambian). Al añadir una a una colección se copia ahí.",
            drop: "Suelta las imágenes para importarlas", pool_badge: "sin colección", folder_badge: "carpeta", loading: "Cargando…",
            add_folder: "Añadir carpeta", add_folder_tip: "Vigilar una carpeta del equipo de WanGP (se indexa en su sitio, nunca se copia)", cancel: "Cancelar",
            tree_title: "Carpetas", tree_sub: "Incluir subcarpetas", all_images: "Todos los medios", up: "Subir un nivel",
            frescan: "Reescanear esta carpeta", fremove: "Quitar del índice (los archivos del disco no se tocan)", fremove_confirm: "Haz clic otra vez para quitarla",
            indexing: "Indexando {name}: {done} / {total}", indexing_start: "Indexando {name}…",
            to_refs: "Añadir a referencias", to_refs_tip: "Añade las imágenes elegidas a Reference Images de WanGP (sin duplicados, sin sustituir nada)",
            recent: "Recientes", recent_tip: "Todas las imágenes, de la más nueva a la más antigua (es una vista: no copia nada)", today: "Hoy", yesterday: "Ayer",
            this_week: "Esta semana", added_on: "Añadida {when}", seen_on: "Añadida / modificada {when}", recent_more: "Ver más",
            recent_empty: "No se ha añadido nada en este periodo.",
            browse_btn: "Examinar…", browse_title: "Elige una carpeta", pick_this: "Seleccionar esta carpeta", drives: "Unidades",
            sc_home: "Inicio", sc_pictures: "Imágenes", sc_outputs: "Salidas de WanGP", pick_images: "{n} imágenes en esta carpeta",
            pick_images_more: "Más de {n} imágenes en esta carpeta", pick_nodirs: "Sin subcarpetas", pick_roots: "Inicio", pick_loading: "Leyendo…",
            del_lib: "Borrar de la librería", del_confirm_n: "Confirmar: {n} imagen(es), {c} colección(es)",
            del_tip_any: "Quita las imágenes elegidas de todas las colecciones y de la bolsa sin colección (dos clics, Deshacer)",
            del_tip_disk: "Las quita de todas las colecciones y de la bolsa; {k} de carpetas vigiladas se quedan en el disco",
            del_tip_folder_only: "Solo hay imágenes de carpetas vigiladas: nunca se borran del disco (quita la carpeta en el árbol para ocultarlas)",
            remove_from: "Quitar de {name}", remove_from_tip: "Saca las imágenes elegidas solo de «{name}» (Deshacer)",
            remove_from_none: "Ninguna de las imágenes elegidas está en «{name}»",
            pause: "Pausar", resume: "Reanudar", pause_tip: "Pausar la indexación de carpetas (también en los ajustes)", resume_tip: "Reanudar la indexación de carpetas",
            idx_paused: "indexación en pausa", thumbs_gen: "creando miniaturas: faltan {n}",
            close_after: "Cerrar al añadir", refs_hidden: "Reference Images no está disponible para el modelo actual",
        },
    };
    const it = (key, params = {}) => {
        const table = ILIB_I18N[lang()] || ILIB_I18N.en;
        let s = table[key] != null ? table[key] : (ILIB_I18N.en[key] != null ? ILIB_I18N.en[key] : key);
        for (const [k, v] of Object.entries(params)) s = s.split("{" + k + "}").join(String(v));
        return s;
    };
    const esc = (v) => String(v == null ? "" : v).replace(/[&<>"']/g, c => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c]));
    const fold = (v) => String(v || "").normalize("NFKD").replace(/[\u0300-\u036f]/g, "").toLowerCase();
    const GRID_SVG = '<svg viewBox="0 0 24 24" aria-hidden="true"><rect x="3" y="3" width="7.5" height="7.5" rx="1.5" fill="none" stroke="currentColor" stroke-width="2"/><rect x="13.5" y="3" width="7.5" height="7.5" rx="1.5" fill="none" stroke="currentColor" stroke-width="2"/><rect x="3" y="13.5" width="7.5" height="7.5" rx="1.5" fill="none" stroke="currentColor" stroke-width="2"/><path d="M15.5 17.25h4M17.5 15.25v4" stroke="currentColor" stroke-width="2" stroke-linecap="round"/></svg>';
    // ---- 1.4.4: the browser never holds the whole library. The server sends counts + the folder tree (meta) and
    // pages of 120 light items for the current filter; the grid is windowed (only the cards around the viewport
    // exist, recycled while scrolling) and thumbnails are requested for those cards only, a few at a time.
    const PAGE = 120, THUMB_BATCH = 6, THUMB_CACHE_MAX = 1500, CARD_SIZES = { l: 300, m: 160, s: 104 }, GAP = 10, HEAD_H = 34, CARD_EXTRA = 46;
    function makeSel() {
        return {
            all: null,           // {f, sig, total, except: Set}: "all N matching" without loading them
            set: new Set(),
            has(h) { return this.all ? !this.all.except.has(h) : this.set.has(h); },
            get size() { return this.all ? Math.max(0, this.all.total - this.all.except.size) : this.set.size; },
            add(h) { if (this.all) this.all.except.delete(h); else this.set.add(h); },
            delete(h) { if (this.all) this.all.except.add(h); else this.set.delete(h); },
            clear() { this.all = null; this.set.clear(); },
            clone() { const c = makeSel(); c.set = new Set(this.set); c.all = this.all ? Object.assign({}, this.all, { except: new Set(this.all.except) }) : null; return c; },
            payload() { return this.all ? { selection: { all: true, f: this.all.f, except: [...this.all.except] } } : { hashes: [...this.set] }; },
            [Symbol.iterator]() { return (this.all ? [] : [...this.set])[Symbol.iterator](); },
        };
    }
    const ilib = { open: false, data: null, sel: makeSel(), thumbs: new Map(), preview: null, pvItem: null, lang: null,
                   f: { cols: new Set(), none: false, folders: new Set(), tags: new Set(), q: "", node: null, sub: true, recent: false, atags: new Set(), xtags: new Set(), ranges: {}, jst: "", kind: "" },
                   at: { status: null, facets: null, body: null, tax: null, sig: "", img: null, setOpen: false, settings: null, models: null, open: new Set() }, recentPages: 1, recentMore: false, addOpen: false, root: null,
                   expanded: new Set(), faddOpen: false, tree: null, treeFor: null,
                   q: { sig: "", total: 0, items: [], groups: null, pages: new Set(), loading: new Set(), gen: 0, ready: false },
                   lay: null, info: null, infoSig: 0, selSig: 0, anchorIdx: -1, scan: null };

    // 1.4.3: requests share one hidden textbox per channel, so they MUST go one at a time. 1.4.4: everything the
    // browser needs to open and scroll (open, query, range, sel_info, thumbs…) is read-only and goes through the
    // unqueued channel, so it never waits behind WanGP's generation queue.
    const FAST_ACTIONS = new Set(["media_url", "media_dur", "thumbs", "scan_status", "browse", "preview", "open", "query", "range", "sel_info", "pause_index", "at_status", "at_facets", "at_image", "at_suggest", "index_of", "locate", "hist_list", "hist_outputs", "hist_find", "hist_settings", "hist_get"]);
    const chains = { main: Promise.resolve(), fast: Promise.resolve() };
    function sendIlib(req) {
        req = Object.assign({ id: Math.random().toString(16).slice(2), lang: lang(), browser: browserLang() }, req || {});
        const fast = FAST_ACTIONS.has(req.action) && document.getElementById("reflib_ilib_fast_btn");
        const ch = fast ? "fast" : "main";
        const run = () => new Promise((resolve, reject) => {
            setText(fast ? "reflib_ilib_fast_req" : "reflib_ilib_req", JSON.stringify(req));
            const btn = document.getElementById(fast ? "reflib_ilib_fast_btn" : "reflib_ilib_btn");
            if (!btn) { toast(t("error", { e: "bridge missing (reload)" }), "error"); reject(new Error("bridge missing")); return; }
            const timer = setTimeout(() => { pending.delete(req.id); reject(new Error("timeout")); }, req.action === "thumbs" ? 30000 : 120000);
            pending.set(req.id, { resolve, reject, timer });
            setTimeout(() => btn.click(), 0);   // let Gradio take the new textbox value first
        });
        const p = chains[ch].then(run, run);
        chains[ch] = p.catch(() => {});
        return p;
    }
    function filterSnap() {
        const f = ilib.f;
        return { cols: [...f.cols].sort(), none: f.none, tags: [...f.tags].sort(), q: f.q.trim(), node: f.recent || f.used ? null : f.node,
                 sub: f.sub, recent: f.recent && !f.used, used: !!f.used, recent_pages: ilib.recentPages,
                 atags: [...f.atags].sort(), xtags: [...f.xtags].sort(), ranges: Object.entries(f.ranges).map(([k, v]) => [k, v[0], v[1]]).sort(), jst: f.jst || "", kind: f.kind || "" };
    }
    const tz = () => new Date().getTimezoneOffset();
    function setMeta(data) {
        const m = data.meta;
        // replies can arrive out of order (queued vs unqueued channel): never go back to an older index state
        if (ilib.data && m.rev != null && ilib.data.rev != null && m.rev < ilib.data.rev) { if (data.scan) ilib.scan = data.scan; return; }
        ilib.data = Object.assign({}, m, { default_collection: data.default_collection || (ilib.data && ilib.data.default_collection) || "" });
        Object.defineProperty(ilib.data, "images", { get: loadedItems, enumerable: false });   // tests / compat: loaded items only
        ilib.colNames = new Map(m.collections.map(c => [c.id, c.name]));
        const cols = new Set(m.collections.map(c => c.id));
        for (const c of [...ilib.f.cols]) if (!cols.has(c)) ilib.f.cols.delete(c);
        const fids = new Set(m.folders.map(f => f.id));
        for (const f of [...ilib.f.folders]) if (!fids.has(f)) ilib.f.folders.delete(f);
        if (ilib.f.node && !fids.has(ilib.f.node.fid)) ilib.f.node = null;
        if (data.scan) { ilib.scan = data.scan; if (!data.scan.running) ilib.scanSeq = data.scan.seq; }
        if (data.paused != null) ilib.paused = data.paused;
    }
    function applyPage(page, sig, gen) {
        const q = ilib.q;
        if (sig !== q.sig || gen !== q.gen) return false;
        const totalChanged = q.total !== page.total || JSON.stringify(q.groups) !== JSON.stringify(page.groups || null);
        q.total = page.total; q.groups = page.groups || null; q.ready = true;
        if (page.kinds && JSON.stringify(page.kinds) !== JSON.stringify(ilib.kinds)) { ilib.kinds = page.kinds; setTimeout(renderKindBar, 0); }
        ilib.recentMore = !!page.recent_more;
        if (q.items.length > q.total) q.items.length = q.total;
        page.items.forEach((it, k) => {   // keep the same object when nothing changed, so its card isn't rebuilt
            const old = q.items[page.offset + k];
            q.items[page.offset + k] = old && JSON.stringify(old) === JSON.stringify(it) ? old : it;
        });
        const pg = Math.floor(page.offset / PAGE);
        q.pages.add(pg); q.loading.delete(pg);
        if (ilib.sel.all && ilib.sel.all.sig === sig) ilib.sel.all.total = q.total;
        return totalChanged;
    }
    // A new filter: forget the pages; same filter after a change (tag, add, delete…): refetch, keep showing the old ones.
    function newQuery(keepScroll) {
        const sig = JSON.stringify(filterSnap());
        setTimeout(() => loadFacets(), 0);
        const q = ilib.q;
        if (sig !== q.sig) {
            ilib.q = { sig, total: 0, items: [], groups: null, pages: new Set(), loading: new Set(), gen: q.gen + 1, ready: false };
            if (ilib.sel.all && ilib.sel.all.sig !== sig) ilib.sel.clear();   // "all matching" belongs to its filter
            ilib.anchorIdx = -1;
            if (!keepScroll) { const m = ilib.root && ilib.root.querySelector(".reflib-ib-main"); if (m) m.scrollTop = 0; }
        } else {
            q.gen += 1; q.pages = new Set(); q.loading = new Set(); if (!q.total) q.ready = false;   // 1.5.1: an empty result must refetch page 1 too
        }
        render();
    }
    function ensurePages(lo, hi) {
        const q = ilib.q;
        const first = Math.floor(Math.max(0, lo) / PAGE), last = Math.floor(Math.max(0, hi) / PAGE);
        for (let pg = first; pg <= last; pg++) {
            if (q.pages.has(pg) || q.loading.has(pg) || (q.ready && pg * PAGE >= q.total && pg > 0)) continue;
            q.loading.add(pg);
            const sig = q.sig, gen = q.gen;
            sendIlib({ action: "query", f: filterSnap(), offset: pg * PAGE, limit: PAGE, tz: tz() }).then(r => {
                if (!r || r.ok === false || !r.page) { if (ilib.q.gen === gen) ilib.q.loading.delete(pg); return; }
                const relayout = applyPage(r.page, sig, gen);
                if (relayout) renderGrid(); else renderWindow();
                renderFooter();
            }).catch(() => { if (ilib.q.gen === gen) ilib.q.loading.delete(pg); });
        }
    }
    function loadedItems() { return ilib.q.items.filter(Boolean); }
    function ilibApply(data) {
        if (!data || data.ok === false) return;
        if (data.meta) {
            setMeta(data);
            if (data.page) { applyPage(data.page, ilib.q.sig, ilib.q.gen); render(); }
            else newQuery(true);   // something changed: same filter, refetch what's on screen
            return;
        }
        render();
    }
    function mountBrowseButtons() {
        const spots = [];
        for (const tab of TABS) {
            const row = document.querySelector(`#reflib_bar_${tab} .reflib-bar-row .reflib-btns`);
            if (row) spots.push(row);
        }
        const mgr = document.getElementById("reflib_mgr_dd");
        if (mgr && mgr.parentElement) spots.push(mgr.parentElement);
        for (const spot of spots) {
            let b = spot.querySelector(":scope > .reflib-browse-btn");
            if (!b) {
                b = document.createElement("button");
                b.type = "button";
                b.className = "reflib-browse-btn";
                b.innerHTML = GRID_SVG;
                b.addEventListener("click", (e) => { e.preventDefault(); openBrowser(); });
                spot.appendChild(b);
            }
            if (b.title !== it("browse_tip")) { b.title = it("browse_tip"); b.setAttribute("aria-label", it("browse_tip")); }
            let hb = spot.querySelector(":scope > .reflib-hist-btn");
            if (!hb) {
                hb = document.createElement("button"); hb.type = "button"; hb.className = "reflib-hist-btn"; hb.textContent = "🕘";
                hb.addEventListener("click", (e) => { e.preventDefault(); histOpen(); });
                spot.appendChild(hb);
            }
            if (hb.title !== ht("tip")) { hb.title = ht("tip"); hb.setAttribute("aria-label", ht("tip")); }
        }
    }
    setInterval(mountBrowseButtons, 700);

    function whenText(ts) {
        if (!ts) return "";
        return new Date(ts * 1000).toLocaleString(lang() === "es" ? "es-ES" : "en-GB", { dateStyle: "medium", timeStyle: "short" });
    }
    function groupLabel(g) {
        if (g.key === "t") return it("today");
        if (g.key === "y") return it("yesterday");
        if (g.key === "w") return it("this_week");
        const s = new Date((g.ts || 0) * 1000).toLocaleDateString(lang() === "es" ? "es-ES" : "en-GB", { weekday: "long", day: "numeric", month: "long", year: "numeric" });
        return s.charAt(0).toUpperCase() + s.slice(1);
    }
    function chip(label, active, attrs = "", extraCls = "") {
        return `<button type="button" class="reflib-ib-chip ${active ? "on" : ""} ${extraCls}" ${attrs}>${label}</button>`;
    }
    const colName = (id) => (ilib.colNames && ilib.colNames.get(id)) || id;
    function cardHTML(img, idx) {
        const th = ilib.thumbs.get(img.hash);
        const nc = img.cols.length;
        const tip = nc ? it("in_n", { n: nc, names: img.cols.map(colName).join(", ") }) : it("in_none");
        const on = ilib.sel.has(img.hash);
        const when = img.added ? it(img.folders.length && !nc && !img.pool ? "seen_on" : "added_on", { when: whenText(img.added) }) : "";
        const mk = img.kind || "image";   // 1.6.0 media cards: type icon, duration, audio ▶, video hover preview
        const media = mk !== "image" ? `<span class="reflib-ib-kbadge k-${mk}" aria-hidden="true">${mk === "video" ? "🎬" : "🎵"}</span>
                <span class="reflib-ib-dur" title="${esc(img.dur ? it("pv_dur") : it("dur_none"))}">${img.dur ? esc(fmtDur(img.dur)) : "…"}</span>
                ${mk === "audio" ? `<button type="button" class="reflib-ib-aplay ${ilib.audioHash === img.hash ? "on" : ""}" data-act="aplay" data-hash="${img.hash}" title="${esc(it(ilib.audioHash === img.hash ? "pause" : "play"))}" aria-label="${esc(it("play"))}">${ilib.audioHash === img.hash ? "❚❚" : "▶"}</button>` : ""}` : "";
        return `<div title="${esc(when)}" class="reflib-ib-card k-${mk} ${img.virtual ? "virtual" + (img.virtual.broken ? " broken" : "") : ""} ${on ? "sel" : ""} ${ilib.preview === img.hash ? "cur" : ""}" data-hash="${img.hash}" data-idx="${idx}" data-kind="${mk}">
              <div class="reflib-ib-thumb ${th === "" ? "nothumb" : ""}">${th ? `<img src="${th}" alt="" decoding="async">` : ""}${media}
                <label class="reflib-ib-cb" title="${esc(it("sel_visible"))}"><input type="checkbox" ${on ? "checked" : ""}></label>
                ${img.virtual ? `<span class="reflib-ib-vbadge ${img.virtual.broken ? "broken" : ""}" title="${esc(vct(img.virtual.broken ? "broken_tip" : "badge_tip"))}">${img.virtual.broken ? "⚠ " + esc(vct("broken")) : VICO + esc(vct("badge"))}</span>`
                  : `<span class="reflib-ib-badge ${nc ? "" : "zero"}" title="${esc(tip)}">${nc ? "×" + nc : esc(img.pool ? it("pool_badge") : it("folder_badge"))}</span>`}
                ${img.vcopies ? `<span class="reflib-ib-vcount" title="${esc(vct("copies_tip", { n: img.vcopies }))}">${VICO}${img.vcopies}</span>` : ""}
                ${img.folders.length ? `<span class="reflib-ib-fbadge" title="${esc(it("from_folder"))}">📁</span>` : ""}
                ${img.js ? `<span class="reflib-ib-jst jst-${esc(img.js)}" data-js="${esc(img.js)}" title="${esc(it("jst_tip"))}">${esc(it("jst_" + img.js))}</span>` : ""}</div>
              <div class="reflib-ib-name" title="${esc(img.names.join(" · "))}">${esc(img.name)}</div>
              ${img.uses ? `<div class="reflib-ib-uses" title="${esc(it("used_last", { when: whenText(img.used_at) }))}">${esc(it("used_n", { n: img.uses, when: whenText(img.used_at) }))}</div>` : ""}
              <div class="reflib-ib-tags">${img.tags.map(x => `<span>${esc(x)}</span>`).join("")}</div></div>`;
    }
    function render() {
        const root = ilib.root;
        if (!root || !ilib.open) return;
        ilib.lang = lang();
        const d = ilib.data;
        const body = root.querySelector(".reflib-ib-body");
        root.querySelector(".reflib-ib-title").textContent = it("browse");
        root.querySelector(".reflib-ib-x").title = it("close");
        const search = root.querySelector(".reflib-ib-q");
        search.placeholder = it("search_ph");
        const imp = root.querySelector(".reflib-ib-import");
        imp.textContent = it("import"); imp.title = it("import_tip");
        const rs = root.querySelector(".reflib-ib-rescan");
        rs.textContent = it("rescan"); rs.title = it("rescan_tip");
        const fsb = root.querySelector(".reflib-ib-fs"); const fsOn = root.classList.contains("reflib-ib-full");
        fsb.textContent = fsOn ? "🗗" : "⛶"; fsb.title = it(fsOn ? "fs_restore" : "fs_max"); fsb.setAttribute("aria-pressed", fsOn ? "true" : "false");
        renderKindBar();
        const vp = viewPref();   // 1.5.9 view selector
        root.querySelector(".reflib-ib-view").setAttribute("aria-label", it("v_size"));
        root.querySelectorAll(".reflib-ib-vsz").forEach(b => { const on = b.dataset.v === vp.thumb; b.classList.toggle("on", on); b.setAttribute("aria-pressed", on ? "true" : "false"); b.title = it("v_" + b.dataset.v); b.setAttribute("aria-label", it("v_" + b.dataset.v)); });
        const vd = root.querySelector(".reflib-ib-vdet"); vd.textContent = "☰ " + it("v_details"); vd.title = it("v_details_tip"); vd.classList.toggle("on", vp.details); vd.setAttribute("aria-pressed", vp.details ? "true" : "false");
        root.classList.toggle("reflib-ib-nodetails", !vp.details);
        const hb = root.querySelector(".reflib-ib-histbtn"); hb.textContent = "🕘 " + ht("title"); hb.title = ht("tip");
        const af = root.querySelector(".reflib-ib-addfolder");
        af.textContent = it("add_folder"); af.title = it("add_folder_tip");
        const far = root.querySelector(".reflib-ib-faddrow");
        far.hidden = !ilib.faddOpen;
        far.querySelector(".reflib-ib-fpath-in").placeholder = it("folder_ph");
        far.querySelector(".reflib-ib-frec-label").textContent = it("recursive");
        far.querySelector('[data-act="fadd"]').textContent = it("folder_add");
        far.querySelector('[data-act="faddcancel"]').textContent = it("cancel");
        far.querySelector('[data-act="fbrowse"]').textContent = it("browse_btn");
        renderPicker();
        renderProgress();
        root.querySelector(".reflib-ib-drop span").textContent = it("drop");
        if (!d) {   // first open: the shell is up at once, the first page follows
            body.innerHTML = `<div class="reflib-ib-filters"><div class="reflib-ib-frow"><span class="reflib-ib-flabel">${esc(it("f_cols"))}</span><span class="reflib-ib-muted">${esc(it("loading"))}</span></div></div>
                <div class="reflib-ib-split"><aside class="reflib-ib-tree slim"></aside><div class="reflib-ib-main"><div class="reflib-ib-vgrid">${'<div class="reflib-ib-skel"></div>'.repeat(12)}</div></div></div>`;
            return;
        }
        const f = ilib.f;
        const all = !f.cols.size && !f.none;
        let filters = `<div class="reflib-ib-frow"><span class="reflib-ib-flabel">${esc(it("f_cols"))}</span>`
            + chip(esc(it("f_all")), all, 'data-f="all"')
            + chip(`${esc(it("f_none"))} <i>${d.n_unassigned}</i>`, f.none, 'data-f="none"')
            + d.collections.map(c => chip(`${esc(c.name)} <i>${c.count}</i>`, f.cols.has(c.id), `data-f="col" data-id="${esc(c.id)}"`)).join("")
            + `</div>`;
        filters += `<div class="reflib-ib-frow"><span class="reflib-ib-flabel">${esc(it("f_tags"))}</span>`
            + (d.tags.length ? d.tags.map(x => chip(`${esc(x.tag)} <i>${x.count}</i>`, f.tags.has(fold(x.tag)), `data-f="tag" data-tag="${esc(fold(x.tag))}"`)).join("")
                : `<span class="reflib-ib-muted">${esc(it("no_tags"))}</span>`) + `</div>`;
        const oldTree = root.querySelector(".reflib-ib-tree");
        if (oldTree) ilib.treeScroll = oldTree.scrollTop;
        const oldMain = body.querySelector(".reflib-ib-main");
        const scroll = oldMain ? oldMain.scrollTop : 0;
        const keepTag = root.querySelector(".reflib-ib-tagin");
        const tagVal = keepTag ? keepTag.value : "";
        const tagFocused = keepTag && document.activeElement === keepTag;
        body.innerHTML = `<div class="reflib-ib-filters">${filters}</div>
            <div class="reflib-ib-split">${renderTree(d)}<div class="reflib-ib-main">${renderFilterChips(d)}${renderCrumbs(d)}<div class="reflib-ib-vgrid"></div><div class="reflib-ib-gridend"></div></div><div class="reflib-ib-pvhost"></div></div><div class="reflib-ib-foothost"></div>`;
        const treeEl = body.querySelector(".reflib-ib-tree");
        if (treeEl) treeEl.scrollTop = ilib.treeScroll || 0;
        const main = body.querySelector(".reflib-ib-main");
        main.addEventListener("scroll", onGridScroll, { passive: true });
        if (ilib.ro) { ilib.ro.disconnect(); ilib.ro.observe(main); }
        ilib.cards = new Map(); ilib.heads = new Map();
        renderGrid();
        main.scrollTop = scroll;
        renderWindow();
        renderPreview();
        renderFooter();
        const tagin = body.querySelector(".reflib-ib-tagin");
        if (tagin) { tagin.value = tagVal; if (tagFocused) tagin.focus(); }
        if (!ilib.q.ready) ensurePages(0, PAGE - 1);
    }
    // ---- windowed grid ----
    function computeLayout() {
        const main = ilib.root && ilib.root.querySelector(".reflib-ib-main");
        const vg = main && main.querySelector(".reflib-ib-vgrid");
        if (!vg) return null;
        const CARD_MIN = CARD_SIZES[viewPref().thumb] || CARD_SIZES.m;   // 1.5.9 thumbnail size from the header
        const W = Math.max(CARD_MIN, vg.clientWidth || main.clientWidth - 4);
        const cols = Math.max(1, Math.floor((W + GAP) / (CARD_MIN + GAP)));
        const cw = (W - GAP * (cols - 1)) / cols, ch = cw + CARD_EXTRA;
        const q = ilib.q;
        const groups = q.groups && q.groups.length ? q.groups : [{ key: null, start: 0, count: q.total }];
        const rows = [];
        let y = 0;
        for (const g of groups) {
            if (g.key) { rows.push({ head: true, y, g }); y += HEAD_H; }
            const n = Math.ceil(g.count / cols);
            for (let r = 0; r < n; r++) { rows.push({ head: false, y, start: g.start + r * cols, n: Math.min(cols, g.count - r * cols) }); y += ch + GAP; }
        }
        return { W, cols, cw, ch, rows, height: Math.max(0, y - GAP) };
    }
    function renderGrid() {
        const main = ilib.root && ilib.root.querySelector(".reflib-ib-main");
        if (!main) return;
        const vg = main.querySelector(".reflib-ib-vgrid");
        const end = main.querySelector(".reflib-ib-gridend");
        const q = ilib.q, d = ilib.data;
        if (q.ready && !q.total) {
            vg.style.height = "auto";
            vg.innerHTML = `<div class="reflib-ib-empty">${esc(ilib.f.used ? it("used_empty") : ilib.f.recent ? it("recent_empty") : (d && d.total ? it("empty") : it("empty_lib")))}</div>`;
            ilib.cards = new Map(); ilib.heads = new Map();
        } else if (vg.querySelector(".reflib-ib-empty")) { vg.innerHTML = ""; ilib.cards = new Map(); ilib.heads = new Map(); }
        ilib.lay = computeLayout();
        if (q.total) vg.style.height = ilib.lay.height + "px";
        end.innerHTML = ilib.f.recent && ilib.recentMore ? `<div class="reflib-ib-more"><button type="button" class="reflib-ib-btn" data-act="recentmore">${esc(it("recent_more"))}</button></div>` : "";
        // a re-layout (column count, groups) repositions every card: start fresh
        for (const el of ilib.cards.values()) el.remove();
        for (const el of ilib.heads.values()) el.remove();
        ilib.cards = new Map(); ilib.heads = new Map();
        renderWindow();
    }
    let scrollRaf = 0;
    function onGridScroll() {
        if (scrollRaf) return;
        scrollRaf = requestAnimationFrame(() => { scrollRaf = 0; renderWindow(); });
    }
    function visibleRows(extra) {
        const main = ilib.root.querySelector(".reflib-ib-main"), vg = main.querySelector(".reflib-ib-vgrid");
        const lay = ilib.lay;
        const top = main.scrollTop - vg.offsetTop, h = main.clientHeight;
        const lo = top - extra * h, hi = top + h + extra * h;
        return lay.rows.filter(r => r.y + (r.head ? HEAD_H : lay.ch) >= lo && r.y <= hi);
    }
    function renderWindow() {
        if (!ilib.open || !ilib.root || !ilib.lay) return;
        const main = ilib.root.querySelector(".reflib-ib-main");
        const vg = main && main.querySelector(".reflib-ib-vgrid");
        if (!vg) return;
        const lay = ilib.lay, q = ilib.q;
        if (!q.total) { if (!q.ready) ensurePages(0, PAGE - 1); return; }
        const rows = visibleRows(0.75);   // ~2.5 screens of cards exist at most (≈ 60-150 with usual sizes)
        const wantCards = new Map(), wantHeads = new Set();
        let lo = Infinity, hi = -1;
        for (const r of rows) {
            if (r.head) { wantHeads.add(r.g.start); continue; }
            for (let c = 0; c < r.n; c++) { const idx = r.start + c; wantCards.set(idx, [r.y, c]); lo = Math.min(lo, idx); hi = Math.max(hi, idx); }
        }
        if (hi >= 0) ensurePages(lo, hi);
        for (const [idx, el] of ilib.cards) {
            const it2 = q.items[idx];
            if (!wantCards.has(idx) || (el._item || null) !== (it2 || null)) { el.remove(); ilib.cards.delete(idx); }   // gone, or refreshed data
        }
        for (const [k, el] of ilib.heads) if (!wantHeads.has(k)) { el.remove(); ilib.heads.delete(k); }
        const frag = document.createDocumentFragment();
        for (const r of rows) {
            if (!r.head || ilib.heads.has(r.g.start)) continue;
            const el = document.createElement("div");
            el.className = "reflib-ib-group";
            el.textContent = groupLabel(r.g);
            el.style.cssText = `position:absolute;left:0;right:0;top:${r.y}px;height:${HEAD_H}px`;
            ilib.heads.set(r.g.start, el); frag.appendChild(el);
        }
        const tmp = document.createElement("div");
        for (const [idx, [y, c]] of wantCards) {
            if (ilib.cards.has(idx)) continue;
            const img = q.items[idx];
            let el;
            if (img) { tmp.innerHTML = cardHTML(img, idx); el = tmp.firstElementChild; el._item = img; }
            else { el = document.createElement("div"); el.className = "reflib-ib-skel"; }
            el.style.cssText = `position:absolute;left:${c * (lay.cw + GAP)}px;top:${y}px;width:${lay.cw}px;height:${lay.ch}px`;
            ilib.cards.set(idx, el); frag.appendChild(el);
        }
        if (!durTimer) pollDurations();   // 1.6.0
        if (frag.childNodes.length) {
            vg.appendChild(frag);
            // keep DOM order = list order (keyboard/tab order, accessibility); moves ≤ 200 nodes
            const ordered = [...ilib.cards.entries()].sort((x, y) => x[0] - y[0]).map(x => x[1]);
            if (ordered.some((el, k) => k && ordered[k - 1].compareDocumentPosition(el) & Node.DOCUMENT_POSITION_PRECEDING)) ordered.forEach(el => vg.appendChild(el));
        }
        queueThumbs();
    }
    // ---- thumbnails: visible cards (+ a small margin) only, ≤ THUMB_BATCH per request, one request in flight;
    // cards scrolled away before their turn are dropped from the queue (cancelled). Cached thumbs come straight from
    // disk; missing ones are made on demand (server budget per request, the rest in a low-priority worker).
    let thumbFlush = null, thumbBusy = false, thumbFails = 0;
    const thumbRetry = new Map();   // hash -> earliest retry time (server said "pending")
    function wantedThumbs() {
        if (!ilib.open || !ilib.root || !ilib.lay) return [];
        const main = ilib.root.querySelector(".reflib-ib-main");
        if (!main) return [];
        const vg = main.querySelector(".reflib-ib-vgrid");
        const top = main.scrollTop - vg.offsetTop, h = main.clientHeight, margin = 200;
        const now = Date.now(), out = [];
        for (const [idx, el] of ilib.cards) {
            const hsh = el.dataset.hash;
            if (!hsh || ilib.thumbs.has(hsh) || (thumbRetry.get(hsh) || 0) > now) continue;
            const y = parseFloat(el.style.top);
            if (y + ilib.lay.ch < top - margin || y > top + h + margin) continue;
            const vis = y + ilib.lay.ch >= top && y <= top + h;
            out.push([hsh, vis ? 0 : 1, y, idx]);
        }
        out.sort((a, b) => a[1] - b[1] || a[2] - b[2] || a[3] - b[3]);
        return out.map(x => x[0]);
    }
    function queueThumbs() { if (!thumbFlush && !thumbBusy) thumbFlush = setTimeout(flushThumbs, 16); }
    function putThumb(h) {
        const src = ilib.thumbs.get(h);
        for (const el of ilib.cards ? ilib.cards.values() : []) {
            if (el.dataset.hash !== h) continue;
            const box = el.querySelector(".reflib-ib-thumb");
            if (src && !box.querySelector("img")) box.insertAdjacentHTML("afterbegin", `<img src="${src}" alt="" decoding="async">`);
            box.classList.toggle("nothumb", src === "");
        }
    }
    function rememberThumb(h, v) {
        ilib.thumbs.delete(h); ilib.thumbs.set(h, v);
        if (ilib.thumbs.size > THUMB_CACHE_MAX) {   // bounded: the oldest data URIs go (they're re-fetched from the disk cache if needed)
            for (const k of ilib.thumbs.keys()) { if (ilib.thumbs.size <= THUMB_CACHE_MAX) break; ilib.thumbs.delete(k); }
        }
    }
    async function flushThumbs() {
        thumbFlush = null;
        if (thumbBusy || !ilib.open) return;
        const batch = wantedThumbs().slice(0, THUMB_BATCH);
        if (!batch.length) {
            if (thumbRetry.size) { const next = Math.min(...thumbRetry.values()) - Date.now(); thumbFlush = setTimeout(flushThumbs, Math.max(100, next)); }
            return;
        }
        thumbBusy = true;
        try {
            const r = await sendIlib({ action: "thumbs", hashes: batch });
            if (!r || r.ok === false || !r.thumbs) throw new Error((r && r.error) || "no thumbs");
            const pend = new Set(r.pending || []);
            for (const h of batch) {
                if (pend.has(h)) { thumbRetry.set(h, Date.now() + 450); continue; }
                thumbRetry.delete(h);
                rememberThumb(h, r.thumbs[h] ? r.thumbs[h] : "");   // "" = no readable source: placeholder
                putThumb(h);
            }
            thumbFails = 0;
        } catch (e) {
            console.warn("[Reference Library] thumbs failed, retrying", e);
            thumbFails++;
            for (const h of batch) thumbRetry.set(h, Date.now() + Math.min(5000, 400 * thumbFails));
        } finally { thumbBusy = false; }
        thumbFlush = setTimeout(flushThumbs, 0);
    }
    function observeThumbs() { queueThumbs(); }
    function loadThumbs() { queueThumbs(); }
    const FOLDER_SVG = '<svg viewBox="0 0 24 24" aria-hidden="true"><path d="M3 6.5A1.5 1.5 0 0 1 4.5 5h4.6l2 2h8.4A1.5 1.5 0 0 1 21 8.5v9a1.5 1.5 0 0 1-1.5 1.5h-15A1.5 1.5 0 0 1 3 17.5z" fill="currentColor" opacity=".85"/></svg>';
    const CLOCK_SVG = '<svg viewBox="0 0 24 24" aria-hidden="true"><circle cx="12" cy="12" r="8.5" fill="none" stroke="currentColor" stroke-width="2"/><path d="M12 7.5V12l3 2" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round"/></svg>';
    const RESCAN_SVG = '<svg viewBox="0 0 24 24" aria-hidden="true"><path d="M20 11a8 8 0 1 0-2.3 5.7M20 4v7h-7" fill="none" stroke="currentColor" stroke-width="2.2" stroke-linecap="round" stroke-linejoin="round"/></svg>';
    // Folder tree from the server's per-folder counts (1.4.4: no image list needed): nodes "fid|rel" with [direct, subtree].
    function buildTree(d) {
        if (ilib.treeFor === d.tree) return ilib.tree;
        const nodes = new Map();
        const node = (fid, rel) => {
            const key = fid + "|" + rel;
            let n = nodes.get(key);
            if (!n) {
                n = { key, fid, rel, name: rel ? rel.split("/").pop() : "", children: new Map(), direct: 0, all: 0 };
                nodes.set(key, n);
                if (rel) node(fid, rel.split("/").slice(0, -1).join("/")).children.set(n.name, n);
            }
            return n;
        };
        for (const f of d.folders) {
            node(f.id, "");
            for (const [rel, [dc, ac, ki, kv, ka]] of Object.entries((d.tree || {})[f.id] || {})) { const n = node(f.id, rel); n.direct = dc; n.all = ac; n.k = { image: ki || 0, video: kv || 0, audio: ka || 0 }; }
        }
        ilib.tree = { nodes };
        ilib.treeFor = d.tree;
        return ilib.tree;
    }
    function renderTree(d) {
        const { nodes } = buildTree(d);
        const cur = ilib.f.recent ? null : ilib.f.node;
        if (cur) {   // keep the current node's ancestors open
            const parts = cur.rel ? cur.rel.split("/") : [];
            for (let k = 0; k < parts.length; k++) ilib.expanded.add(cur.fid + "|" + parts.slice(0, k).join("/"));
        }
        const row = (n, depth, root) => {
            const kids = [...n.children.values()].sort((a, b) => a.name.localeCompare(b.name, undefined, { numeric: true, sensitivity: "base" }));
            const open = ilib.expanded.has(n.key);
            const active = cur && cur.fid === n.fid && cur.rel === n.rel;
            const kc = n.k || { image: n.all, video: 0, audio: 0 };
            const count = ilib.f.kind ? kc[ilib.f.kind] : (ilib.f.sub ? n.all : n.direct);   // 1.6.0: per media type
            const ktip = it("k_tree", { i: kc.image, v: kc.video, a: kc.audio });
            let html = `<div class="reflib-ib-tnode ${active ? "on" : ""} ${root ? "root" : ""}" style="padding-left:${6 + depth * 14}px" data-act="node" data-key="${esc(n.key)}" title="${esc((root ? (root.virtual ? vct("badge_tip") : root.path) : n.rel) + " — " + ktip)}">
                <span class="reflib-ib-caret ${kids.length ? "" : "none"}" data-act="caret" data-key="${esc(n.key)}">${kids.length ? (open ? "▾" : "▸") : ""}</span>
                <span class="reflib-ib-ticon">${root && root.virtual ? `<span class="reflib-vc-ticon">${VICO}</span>` : FOLDER_SVG}</span><span class="reflib-ib-tname">${esc(root ? folderLabel(root).replace(/^⧉\s*/, "") : n.name)}</span>
                <span class="reflib-ib-tcount">${root && root.missing ? "⚠" : count}</span>
                ${root && !root.virtual ? `<span class="reflib-ib-tacts"><button type="button" data-act="frescan" data-fid="${esc(root.id)}" title="${esc(it("frescan"))}">${RESCAN_SVG}</button><button type="button" class="reflib-ib-trm" data-act="fremove" data-fid="${esc(root.id)}" title="${esc(it("fremove"))}">×</button></span>` : ""}</div>`;
            if (open) for (const k of kids) html += row(k, depth + 1, null);
            return html;
        };
        const roots = d.folders.map(f => row(nodes.get(f.id + "|"), 0, f)).join("");
        const recentOn = !!ilib.f.recent && !ilib.f.used, usedOn = !!ilib.f.used;
        const head = d.folders.length ? `<div class="reflib-ib-thead"><span>${esc(it("tree_title"))}</span>
            <label class="reflib-ib-check" title="${esc(it("tree_sub"))}"><input type="checkbox" class="reflib-ib-subtoggle" ${ilib.f.sub ? "checked" : ""}> ${esc(it("tree_sub"))}</label></div>` : "";
        return `<aside class="reflib-ib-tree ${d.folders.length ? "" : "slim"}">
            <div class="reflib-ib-trecent ${recentOn ? "on" : ""}" data-act="recent" title="${esc(it("recent_tip"))}"><span class="reflib-ib-ticon">${CLOCK_SVG}</span><span class="reflib-ib-tname">${esc(it("recent"))}</span></div>
            <div class="reflib-ib-tused ${usedOn ? "on" : ""}" data-act="used" title="${esc(it("used_tip"))}"><span class="reflib-ib-ticon">↺</span><span class="reflib-ib-tname">${esc(it("used"))}</span></div>
            <div class="reflib-ib-tall ${cur || recentOn || usedOn ? "" : "on"}" data-act="crumb" data-fid="">${esc(it("all_images"))} <i>${ilib.f.kind && d.kinds ? d.kinds[ilib.f.kind] : d.total}</i></div>${head}${roots}${renderFacets()}</aside>`;
    }
    function renderCrumbs(d) {
        if (ilib.f.used) return `<div class="reflib-ib-usedbar"><span>${esc(it("used_title"))}</span>
            <button type="button" class="reflib-ib-btn reflib-ib-danger" data-dact="sel">${esc(it("used_clear_sel"))}</button>${delMenuHTML("used")}</div>`;
        const n = ilib.f.recent ? null : ilib.f.node;
        if (!n) return "";
        const root = d.folders.find(f => f.id === n.fid);
        if (!root) return "";
        const parts = n.rel ? n.rel.split("/") : [];
        let html = `<div class="reflib-ib-crumbs"><button type="button" class="reflib-ib-up" data-act="up" title="${esc(it("up"))}">↑</button>
            <button type="button" data-act="crumb" data-fid="">${esc(it("all_images"))}</button><span>›</span>
            <button type="button" data-act="crumb" data-fid="${esc(root.id)}" data-rel="" title="${esc(root.path)}">${esc(folderLabel(root))}</button>`;
        parts.forEach((p, k) => {
            html += `<span>›</span><button type="button" data-act="crumb" data-fid="${esc(root.id)}" data-rel="${esc(parts.slice(0, k + 1).join("/"))}">${esc(p)}</button>`;
        });
        return html + `</div>`;
    }
    // ---- 1.5.0 auto-tagger: facets, preview panel ("Forma del cuerpo"), job bar, settings ----
    const AT_FAST = new Set(["at_status", "at_facets", "at_image", "at_suggest"]);
    const tlabel = (id) => { const n = ilib.at.tax && ilib.at.tax.byId.get(id); return n ? (lang() === "es" ? n.es : n.en) : id; };
    function loadFacets(force) {
        if (!ilib.open) return;
        const sig = JSON.stringify(filterSnap());
        if (!force && sig === ilib.at.sig && ilib.at.facets) return;
        ilib.at.sig = sig;
        sendIlib({ action: "at_facets", f: filterSnap(), tax: !ilib.at.tax }).then(r => {
            if (!r || !r.ok || sig !== ilib.at.sig) return;
            if (r.tax) setTax(r.tax);
            ilib.at.facets = r.facets; ilib.at.body = r.body; ilib.at.jobs = r.jobs; if (r.jrev !== undefined) ilib.at.jrev = r.jrev;
            const host = ilib.root && ilib.root.querySelector(".reflib-ib-facets");
            if (host) host.outerHTML = renderFacets();
        }).catch(() => {});
    }
    const BODY_RANGE_FIELDS = ["age", "bust", "waist", "hip", "thigh", "waist_hip", "waist_bust", "shoulder_hip", "thigh_hip", "gap_hip", "curvature", "waist_definition"];
    function catOf(id) {
        const tax = ilib.at.tax;
        let n = tax && tax.byId.get(id);
        while (n && n.p) { const up = tax.byId.get(n.p); if (!up) break; if (up.k === "c") return up.id; n = up; }
        return n && n.k === "c" ? n.id : null;
    }
    function groupOf(id) {
        const tax = ilib.at.tax;
        let n = tax && tax.byId.get(id);
        while (n && n.k !== "g") n = tax.byId.get(n.p);
        return n ? n.id : id;
    }
    // ---- 1.5.1 active filter chips (under the search row): every filter at a glance, × removes, click finds it in the tree
    function renderFilterChips(d) {
        const f = ilib.f, chips = [];
        const chip = (kind, key, label, extra = "") => `<span class="reflib-ib-fchip ${extra}" data-act="chipfind" data-kind="${kind}" data-key="${esc(key)}" title="${esc(it(kind === "at" || kind === "xt" ? "chip_find" : "chip_rm"))}">${label}<button type="button" data-act="chiprm" data-kind="${kind}" data-key="${esc(key)}" title="${esc(it("chip_rm"))}">×</button></span>`;
        const join = (arr, word) => arr.join(`<i class="reflib-ib-fjoin">${esc(it(word))}</i>`);
        const groups = [];
        const cols = [...f.cols].map(c => chip("col", c, esc(colName(c)), "col"));
        if (f.none) cols.push(chip("none", "", esc(it("chip_none")), "col"));
        if (cols.length) groups.push(join(cols, "chip_or"));
        if (f.node && !f.recent) {
            const root = d.folders.find(x => x.id === f.node.fid);
            if (root) groups.push(chip("node", "", esc(it("chip_folder", { name: folderLabel(root) + (f.node.rel ? "/" + f.node.rel : "") }))));
        }
        for (const tg of [...f.tags]) groups.push(chip("tag", tg, "#" + esc(tg), "tag"));
        const byGroup = new Map();
        for (const t of f.atags) { const g = groupOf(t); if (!byGroup.has(g)) byGroup.set(g, []); byGroup.get(g).push(t); }
        const modeBtn = (t, not) => `<button type="button" class="reflib-ib-fmode" data-act="chipmode" data-key="${esc(t)}" title="${esc(it("chip_mode"))}">${not ? "≠" : "="}</button>`;
        for (const [g, ts] of byGroup) groups.push(`<span class="reflib-ib-fgrp" title="${esc(tlabel(g))}">` + join(ts.map(t => chip("at", t, modeBtn(t, false) + esc(tlabel(t)), "at")), "chip_or") + `</span>`);
        for (const t of f.xtags) groups.push(chip("xt", t, modeBtn(t, true) + `<s>${esc(tlabel(t))}</s>`, "xt"));
        for (const [k, v] of Object.entries(f.ranges)) {
            const lo = v[0] > -1e8 ? v[0] : "", hi = v[1] < 1e8 ? v[1] : "";
            groups.push(chip("range", k, esc(`${bodyName(k)} ${lo !== "" && hi !== "" ? lo + "–" + hi : lo !== "" ? "≥ " + lo : "≤ " + hi}`), "range"));
        }
        if (f.q.trim()) groups.push(chip("q", "", esc(it("chip_search", { q: f.q.trim() })), "q"));
        if (f.jst) groups.push(chip("jst", f.jst, esc(it("jsf_title") + ": " + it("jsf_" + f.jst)), "jst"));
        if (f.kind) groups.push(chip("kind", f.kind, esc(it("chip_kind", { k: it("k_" + f.kind) })), "kind"));
        if (!groups.length) return "";
        return `<div class="reflib-ib-fchips" title="${esc(it("chips_tip"))}">${join(groups, "chip_and")}<button type="button" class="reflib-ib-fclear" data-act="chipclear">${esc(it("chips_clear"))}</button></div>`;
    }
    function chipClick(act, el) {
        const f = ilib.f, k = el.dataset.key, kind = el.dataset.kind;
        if (act === "chipclear") {
            f.cols.clear(); f.none = false; f.node = null; f.tags.clear(); f.atags.clear(); f.xtags.clear(); f.ranges = {}; f.q = ""; f.jst = ""; f.kind = "";
            const qi = ilib.root.querySelector(".reflib-ib-q"); if (qi) qi.value = "";
            newQuery(); return true;
        }
        if (act === "chipmode") {
            if (f.atags.has(k)) { f.atags.delete(k); f.xtags.add(k); } else { f.xtags.delete(k); f.atags.add(k); }
            newQuery(); return true;
        }
        if (act === "chiprm") {
            if (kind === "col") f.cols.delete(k); else if (kind === "none") f.none = false; else if (kind === "node") f.node = null;
            else if (kind === "tag") f.tags.delete(k); else if (kind === "at") f.atags.delete(k); else if (kind === "xt") f.xtags.delete(k);
            else if (kind === "range") delete f.ranges[k];
            else if (kind === "jst") f.jst = "";
            else if (kind === "kind") f.kind = "";
            else if (kind === "q") { f.q = ""; const qi = ilib.root.querySelector(".reflib-ib-q"); if (qi) qi.value = ""; }
            newQuery(); return true;
        }
        if (act === "chipfind") {
            if (kind === "at" || kind === "xt") {
                const cat = catOf(k); if (cat) ilib.at.open.add(cat);
                const host = ilib.root.querySelector(".reflib-ib-facets"); if (host) host.outerHTML = renderFacets();
                const node = ilib.root.querySelector(`.reflib-ib-fnode[data-tag="${CSS.escape(k)}"]`);
                if (node) { node.scrollIntoView({ block: "center" }); node.classList.add("flash"); setTimeout(() => node.classList.remove("flash"), 1600); }
            } else if (kind === "range") {
                const inp = ilib.root.querySelector(`[data-act="atrange"][data-k="${CSS.escape(k)}"]`);
                if (inp) { inp.scrollIntoView({ block: "center" }); inp.focus(); }
            } else if (kind === "q") ilib.root.querySelector(".reflib-ib-q").focus();
            return true;
        }
        return false;
    }
    // ---- 1.5.1 tag autocomplete in the search box
    const sug = { list: [], idx: -1, timer: null, seq: 0 };
    function sugBox() {
        let b = ilib.root.querySelector(".reflib-ib-sug");
        if (!b) {
            b = document.createElement("div"); b.className = "reflib-ib-sug";
            const qi = ilib.root.querySelector(".reflib-ib-q"); qi.parentElement.style.position = "relative"; qi.parentElement.appendChild(b);
            b.addEventListener("mousedown", (e) => { const r = e.target.closest("[data-i]"); if (r) { e.preventDefault(); pickSug(+r.dataset.i); } });
        }
        return b;
    }
    function closeSug() { sug.list = []; sug.idx = -1; sug.seq++; const b = ilib.root && ilib.root.querySelector(".reflib-ib-sug"); if (b) b.style.display = "none"; }
    function suggestSoon(text) {
        clearTimeout(sug.timer);
        if ((text || "").trim().length < 2) { closeSug(); return; }
        sug.timer = setTimeout(() => {
            const my = ++sug.seq;
            sendIlib({ action: "at_suggest", text, f: filterSnap() }).then(r => {
                if (my !== sug.seq || !r || !r.ok) return;
                sug.list = r.sug || []; sug.idx = -1; drawSug();
            });
        }, 120);
    }
    function drawSug() {
        const b = sugBox();
        if (!sug.list.length) { b.style.display = "none"; return; }
        b.innerHTML = sug.list.map((x, i) => `<div class="reflib-ib-sugrow ${i === sug.idx ? "on" : ""} ${x.n ? "" : "zero"}" data-i="${i}">${x.kind === "folder" ? `<span class="reflib-ib-sugfold" aria-hidden="true">📁</span>` : ""}<span class="p">${esc(x.path)}</span>${x.match ? `<i>${esc(x.match)}</i>` : ""}<b>${x.n}</b></div>`).join("");
        b.style.display = "block";
        const on = b.querySelector(".on"); if (on) on.scrollIntoView({ block: "nearest" });
    }
    function pickSug(i) {
        const x = sug.list[i]; if (!x) return;
        if (x.kind === "folder") {   // 1.5.5: same as clicking the folder in the tree (+ "Carpeta: x" chip)
            ilib.f.node = { fid: x.fid, rel: x.rel || "" }; ilib.f.recent = false; ilib.f.used = false;
            const parts = (x.rel || "").split("/").filter(Boolean);
            for (let k = 0; k <= parts.length; k++) ilib.expanded.add(x.fid + "|" + parts.slice(0, k).join("/"));
            ilib.f.q = ""; const qf = ilib.root.querySelector(".reflib-ib-q"); qf.value = "";
            closeSug(); newQuery(); qf.focus(); return;
        }
        (x.kind === "tag" ? ilib.f.tags : ilib.f.atags).add(x.id);
        if (x.kind === "at") ilib.f.xtags.delete(x.id);
        ilib.f.q = ""; const qi = ilib.root.querySelector(".reflib-ib-q"); qi.value = "";
        closeSug(); newQuery(); qi.focus();
    }
    function sugKey(e) {
        if (!sug.list.length) return false;
        const k = e.key, n = sug.list.length;
        if (k === "ArrowDown") { sug.idx = sug.idx + 1 >= n ? -1 : sug.idx + 1; drawSug(); }
        else if (k === "ArrowUp") { sug.idx = sug.idx - 1 < -1 ? n - 1 : sug.idx - 1; drawSug(); }
        else if ((k === "Enter" && sug.idx >= 0) || k === "Tab") pickSug(Math.max(0, sug.idx));
        else if (k === "Escape") closeSug();
        else return false;
        e.preventDefault(); e.stopPropagation(); return true;
    }
    // 1.5.4 "Estado del etiquetado": per-image job status counts (current filter) — click filters the grid
    const JST_ORDER = ["queued", "processing", "done", "failed", "local", "never"];
    function renderJobFacet() {
        const c = ilib.at.jobs;
        if (!c) return "";
        const rows = JST_ORDER.filter(k => c[k] || ilib.f.jst === k).map(k => `<div class="reflib-ib-fnode reflib-ib-jfacet ${ilib.f.jst === k ? "on" : ""}" style="padding-left:10px" data-act="atjst" data-jst="${k}"><span><i class="reflib-ib-jdot jst-${k}"></i>${esc(it("jsf_" + k))}</span><i>${c[k] || 0}</i></div>`).join("");
        const retry = c.failed ? `<button type="button" class="reflib-ib-btn reflib-ib-retry" data-act="atretry">${esc(it("jst_retry"))}</button>` : "";
        return `<div class="reflib-ib-jobfacet"><div class="reflib-ib-fgroup">${esc(it("jsf_title"))}</div>${rows || `<div class="reflib-ib-muted" style="padding-left:10px">—</div>`}${retry}</div>`;
    }
    function renderFacets() {
        const fc = ilib.at.facets, tax = ilib.at.tax;
        const gear = `<button type="button" class="reflib-ib-atgear" data-act="atset" title="${esc(it("at_settings"))}">⚙</button>`;
        if (!fc || !tax) return `<div class="reflib-ib-facets"><div class="reflib-ib-fhead"><span>${esc(it("at_facets"))}</span>${gear}</div></div>`;
        let html = `<div class="reflib-ib-facets"><div class="reflib-ib-fhead"><span>${esc(it("at_facets"))}</span>${gear}</div>`;
        html += renderJobFacet();
        if (!Object.keys(fc).length && !ilib.f.atags.size) html += `<div class="reflib-ib-muted reflib-ib-fempty">${esc(it("at_none_facets"))}</div>`;
        for (const cat of tax.kids.get(null) || []) {
            const groups = (tax.kids.get(cat) || []).filter(g => (tax.byId.get(g).k === "g"));
            const rows = [];
            for (const g of groups) {
                const tags = [];
                const walk = (id, depth) => { for (const k of tax.kids.get(id) || []) { if (fc[k] || ilib.f.atags.has(k) || ilib.f.xtags.has(k)) tags.push([k, depth]); walk(k, depth + 1); } };
                walk(g, 0);
                if (!tags.length) continue;
                rows.push(`<div class="reflib-ib-fgroup">${esc(tlabel(g))}</div>` + tags.map(([k, dp]) =>
                    `<div class="reflib-ib-fnode ${tax.byId.get(k).k === "g" ? "sub" : ""} ${ilib.f.atags.has(k) ? "on" : ""} ${ilib.f.xtags.has(k) ? "not" : ""}" style="padding-left:${10 + dp * 12}px" data-act="atfacet" data-tag="${esc(k)}"><span>${esc(tlabel(k))}</span><i>${fc[k] || 0}</i></div>`).join(""));
            }
            // 1.5.2: tags placed straight in a category (custom, any level)
            const direct = (tax.kids.get(cat) || []).filter(t => tax.byId.get(t).k === "t" && (fc[t] || ilib.f.atags.has(t) || ilib.f.xtags.has(t)));
            if (direct.length) rows.unshift(direct.map(k => `<div class="reflib-ib-fnode ${ilib.f.atags.has(k) ? "on" : ""} ${ilib.f.xtags.has(k) ? "not" : ""}" style="padding-left:10px" data-act="atfacet" data-tag="${esc(k)}"><span>${esc(tlabel(k))}</span><i>${fc[k] || 0}</i></div>`).join(""));
            if (!rows.length) continue;
            const open = ilib.at.open.has(cat);
            const nAct = [...ilib.f.atags, ...ilib.f.xtags].filter(t => catOf(t) === cat).length;
            html += `<div class="reflib-ib-fcat ${open ? "open" : ""}" data-act="atcat" data-cat="${esc(cat)}">${open ? "▾" : "▸"} ${esc(tlabel(cat))}${nAct ? `<b class="reflib-ib-fbadge">${nAct}</b>` : ""}</div>${open ? rows.join("") : ""}`;
        }
        const bs = ilib.at.body || {};
        const avail = BODY_RANGE_FIELDS.filter(k => bs[k] && bs[k].n);
        if (avail.length) {
            html += `<div class="reflib-ib-fcat open">▾ ${esc(it("body_ranges"))} <span class="reflib-ib-est">${esc(it("body_est"))}</span></div>`;
            for (const k of avail) {
                const st = bs[k], cur = ilib.f.ranges[k] || [], ratio = st.max <= 2;
                const step = ratio ? 0.01 : 1;
                html += `<div class="reflib-ib-frange" title="${esc(it("body_range_tip"))}"><span>${esc(bodyName(k))}</span>
                    <input type="number" step="${step}" data-act="atrange" data-k="${k}" data-i="0" placeholder="${ratio ? st.min.toFixed(2) : Math.floor(st.min)}" value="${cur[0] != null && cur[0] > -1e8 ? cur[0] : ""}">–<input type="number" step="${step}" data-act="atrange" data-k="${k}" data-i="1" placeholder="${ratio ? st.max.toFixed(2) : Math.ceil(st.max)}" value="${cur[1] != null && cur[1] < 1e8 ? cur[1] : ""}"><i>${st.n}</i></div>`;
            }
        }
        return html + `</div>`;
    }
    const BODY_NAMES = { en: { age: "apparent age (estimated)", bust: "bust", underbust: "underbust", waist: "waist", high_hip: "high hip", hip: "hip", thigh: "thigh", knee: "knee", gap: "inner-thigh gap",
            shoulder: "shoulders", shoulder_width: "shoulder width", waist_hip: "waist / hip", waist_bust: "waist / bust", shoulder_hip: "shoulder / hip", bust_hip: "bust / hip",
            thigh_hip: "thigh / hip", thigh_knee: "thigh / knee", gap_hip: "thigh gap / hip", curvature: "curvature", waist_definition: "waist definition", torso: "torso", leg: "legs", arm: "arms" },
        es: { age: "edad aparente (estimada)", bust: "pecho", underbust: "bajo pecho", waist: "cintura", high_hip: "cadera alta", hip: "cadera", thigh: "muslo", knee: "rodilla", gap: "separación de muslos",
            shoulder: "hombros", shoulder_width: "anchura de hombros", waist_hip: "cintura / cadera", waist_bust: "cintura / pecho", shoulder_hip: "hombro / cadera", bust_hip: "pecho / cadera",
            thigh_hip: "muslo / cadera", thigh_knee: "muslo / rodilla", gap_hip: "separación / cadera", curvature: "curvatura", waist_definition: "definición de cintura", torso: "torso", leg: "piernas", arm: "brazos" } };
    const bodyName = (k) => (BODY_NAMES[lang()] || BODY_NAMES.en)[k] || k;
    function loadAutoImage(h) {
        if (!h) return;
        sendIlib({ action: "at_image", hash: h }).then(r => {
            if (!r || !r.ok || ilib.preview !== h) return;
            ilib.at.img = r.img;
            const host = ilib.root && ilib.root.querySelector(".reflib-ib-autohost");
            if (host) host.innerHTML = renderAutoPanel(h);
        }).catch(() => {});
    }
    function renderAutoPanel(h) {
        const a = ilib.at.img;
        if (!a || a.hash !== h) return "";
        let html = "";
        if (ilib.at.tax && !a.review) {
            const opts = ilib.at.tax.list.filter(n => n.k === "t" && n.id !== "appears_minor" && n.id !== "needs_review")
                .map(n => `<option value="${esc(taxPath(n.id))}"></option>`).join("");
            html += `<input class="reflib-ib-atadd" data-act="atadd" list="reflib-ib-atdl" placeholder="${esc(it("ut_add_ph"))}"><datalist id="reflib-ib-atdl">${opts}</datalist>`;
        }
        if (a.review) html += `<div class="reflib-ib-atreview">⚠ ${esc(it("at_review_flag"))}</div>`;
        else if (a.age && a.age.est) html += `<div class="reflib-ib-atage" title="${esc(bodyName("age"))}">${esc(bodyName("age"))}: <b>~${Math.round(a.age.est)} ± ${Math.round(a.age.pm)}</b></div>`;
        if (a.tags.length) {
            html += `<h4>${esc(it("at_tags"))} <span class="reflib-ib-muted">${esc(a.model || "")}</span></h4><div class="reflib-ib-pv-list reflib-ib-atlist">` + a.tags.map(x =>
                `<span class="reflib-ib-chip static reflib-ib-atchip ${x.shown ? "" : "off"} ${x.accepted ? "acc" : ""}" title="${esc(it("at_conf", { c: Math.round(x.conf * 100) }) + " · " + x.src)}">${esc(x.label)}<small>${Math.round(x.conf * 100)}</small>`
                + (x.rejected ? `<button type="button" data-act="atedit" data-op="restore" data-tag="${esc(x.id)}" title="${esc(it("at_restore"))}">↺</button>`
                   : `${x.accepted ? "" : `<button type="button" data-act="atedit" data-op="accept" data-tag="${esc(x.id)}" title="${esc(it("at_accept"))}">✓</button>`}<button type="button" data-act="atedit" data-op="remove" data-tag="${esc(x.id)}" title="${esc(it("at_remove"))}">×</button>`)
                + `</span>`).join("") + `</div>`;
        }
        const b = a.body;
        if (b) {
            html += `<div class="reflib-ib-body-panel"><h4>${esc(it("body_title"))} <span class="reflib-ib-est">${esc(it("body_est"))}</span></h4>`;
            if (!b.measurable) html += `<div class="reflib-ib-muted">${esc(it("body_nm", { r: b.reason || "" }))}</div>`;
            else {
                const row = (k, v, extra) => `<tr><td>${esc(bodyName(k))}</td><td>${v}</td><td class="reflib-ib-muted">${extra || ""}</td></tr>`;
                html += `<table class="reflib-ib-btab"><tr><th colspan="3">${esc(it("body_cm"))}</th></tr>` + Object.entries(b.cm || {}).map(([k, v]) => row(k, `~${Math.round(v[0])}`, `${v[1]}–${v[2]}`)).join("");
                html += `<tr><th colspan="3">${esc(it("body_ratios"))}</th></tr>` + Object.entries(b.ratios || {}).map(([k, v]) => row(k, v.toFixed(2))).join("");
                html += `<tr><th colspan="3">${esc(it("body_scores"))}</th></tr>` + Object.entries(b.scores || {}).map(([k, v]) => row(k, v.toFixed(2))).join("");
                if (b.prop) html += `<tr><th colspan="3">${esc(it("body_prop"))}</th></tr>` + Object.entries(b.prop).map(([k, v]) => row(k, Math.round(v * 100) + "%")).join("");
                html += `<tr><th colspan="3">${esc(it("body_widths"))}</th></tr>` + Object.entries(b.norm || {}).map(([k, v]) => row(k, v.toFixed(2))).join("");
                if (b.vlm) html += `<tr><th colspan="3">${esc(it("body_vlm"))}</th></tr>` + Object.entries(b.vlm.agree || {}).map(([k, v]) => row(k, (b.vlm.values || {})[k] != null ? esc(String(b.vlm.values[k])) : "", esc(it(v ? "body_agree" : "body_disagree")))).join("");
                html += `</table><div class="reflib-ib-muted reflib-ib-bunc">${esc(it("body_unc", { p: Math.round((b.uncertainty || 0) * 100), s: b.scale_from === "stature" ? (lang() === "es" ? "estatura" : "stature") : "torso", h: b.height_cm, src: lang() === "es" ? ({ user: "introducida", assumed: "supuesta" }[b.height_source] || b.height_source) : b.height_source }))}</div>`;
                const oc = oneCol();
                html += `<div class="reflib-ib-bheight"><label title="${esc(it("body_height_tip"))}">${esc(it("body_height"))} <input type="number" min="120" max="220" class="reflib-ib-hin" value="${a.height_cm || ""}" placeholder="165"></label>
                    <button type="button" class="reflib-ib-btn" data-act="atheight">OK</button>${oc ? `<label class="reflib-ib-check"><input type="checkbox" class="reflib-ib-hcol"> ${esc(it("body_height_col"))}</label>` : ""}</div>`;
            }
            html += `</div>`;
        }
        return html;
    }
    function renderAtBar() {
        const bar = ilib.root && ilib.root.querySelector(".reflib-ib-atbar");
        const st = ilib.at.status;
        if (!bar) return;
        const jc0 = (st && st.jcounts) || {};
        if (!st || (!st.running && !st.loaded && !jc0.failed && !ilib.f.jst)) { bar.hidden = true; return; }
        bar.hidden = false;
        let text = st.running ? it("at_running", { done: st.done, total: st.total }) : (st.model || "");
        if (st.waiting === "host_busy") text += " · " + it("at_waiting_host");
        if (st.paused) text += " · " + it("at_paused");
        if (st.review) text += " · " + it("at_review", { n: st.review });
        if (st.cost_usd) text += " · " + it("at_cost", { c: st.cost_usd.toFixed(4) });
        if (st.error) text += " · ⚠ " + st.error;
        bar.querySelector(".reflib-ib-attext").textContent = text;
        let jc = bar.querySelector(".reflib-ib-jcounts");
        if (!jc) { jc = document.createElement("span"); jc.className = "reflib-ib-jcounts"; bar.querySelector(".reflib-ib-attext").after(jc); }
        const c = st.jcounts || {};
        jc.innerHTML = ["queued", "processing", "done", "failed"].map(k => `<button type="button" class="reflib-ib-jcount jst-${k} ${ilib.f.jst === k ? "on" : ""}" data-act="atjst" data-jst="${k}" title="${esc(it("jst_filter"))}">${c[k] || 0} ${esc(it("jsb_" + k))}</button>`).join("")
            + (c.failed && !st.running ? `<button type="button" class="reflib-ib-btn reflib-ib-retry" data-act="atretry">${esc(it("jst_retry"))}</button>` : "");
        bar.querySelector("i").style.width = (st.total ? Math.round(100 * st.done / st.total) : 0) + "%";
        const pb = bar.querySelector('[data-act="atpause"]'); pb.textContent = it(st.paused ? "at_resume" : "at_pause"); pb.hidden = !st.running;
        const cb = bar.querySelector('[data-act="atcancel"]'); cb.textContent = it("at_cancel"); cb.hidden = !st.running;
        const ub = bar.querySelector('[data-act="atunload"]'); ub.textContent = it("at_unload"); ub.title = it("at_unload_tip"); ub.hidden = !st.loaded;
    }
    let atTimer = null, atWasRunning = false;
    function pollAt() {
        clearTimeout(atTimer);
        sendIlib({ action: "at_status" }).then(r => {
            if (!r || !r.ok) return;
            const was = atWasRunning;
            ilib.at.status = r.at; atWasRunning = r.at.running;
            renderAtBar();
            if (r.at.jrev !== undefined && r.at.jrev !== ilib.at.jrevSeen) { ilib.at.jrevSeen = r.at.jrev; if (ilib.open) { newQuery(true); loadFacets(true); } }
            if (r.at.running && ilib.open) {
                if (r.at.done !== (ilib.at.lastDone || 0)) { ilib.at.lastDone = r.at.done; loadFacets(true); }
                atTimer = setTimeout(pollAt, 700);
            } else if (was) { if (r.at.report && ilib.open) reportDialog(r.at.report); loadFacets(true); newQuery(true); if (ilib.preview) loadAutoImage(ilib.preview); }
        }).catch(() => {});
    }
    function setTax(list) {
        const byId = new Map(list.map(n => [n.id, n])), kids = new Map();
        for (const n of list) { if (!kids.has(n.p)) kids.set(n.p, []); kids.get(n.p).push(n.id); }
        ilib.at.tax = { list, byId, kids };
    }
    function taxPath(id) {
        const tax = ilib.at.tax, out = []; let n = tax && tax.byId.get(id);
        while (n) { out.unshift(tlabel(n.id)); n = tax.byId.get(n.p); }
        return out.join(" › ");
    }
    // ---- 1.5.1 taxonomy editor ("Mis etiquetas"): custom groups/tags merged over the shipped taxonomy
    function renderTaxEditor() {
        // 1.5.2 tree editor: new top-level categories, sub-categories at any depth, tags at any level; rename, move
        // (drag & drop or "Mover" then click the destination), delete, undo. Built-in nodes can host children but stay as they are.
        const tax = ilib.at.tax; if (!tax) return "";
        const ut = ilib.at.ut || (ilib.at.ut = { open: new Set(), form: null, move: null });
        const hidden = (n) => n.id === "age_band" || n.id === "review" || n.p === "review" || n.p === "age_band";
        const rows = [];
        const walk = (pid, depth) => {
            for (const id of tax.kids.get(pid) || []) {
                const n = tax.byId.get(id); if (!n || hidden(n)) continue;
                if (n.k === "t" && !n.u) continue;   // built-in tags are not listed (330+); their groups are
                const kids = (tax.kids.get(id) || []).filter(k => { const c = tax.byId.get(k); return c && !hidden(c) && (c.k !== "t" || c.u); });
                const open = ut.open.has(id);
                const canHost = n.k !== "t";
                const isTarget = ut.move && canHost && ut.move !== id;
                rows.push(`<div class="reflib-ib-utnode ${n.u ? "user" : ""} k-${n.k} ${isTarget ? "target" : ""} ${ut.move === id ? "moving" : ""}" data-tid="${esc(id)}" ${n.u ? 'draggable="true"' : ""} style="padding-left:${4 + depth * 14}px">
                    <span class="reflib-ib-utcaret" data-act="atuttoggle" data-tid="${esc(id)}">${kids.length ? (open ? "▾" : "▸") : "·"}</span>
                    <span class="reflib-ib-utlabel" data-act="atutpick" data-tid="${esc(id)}" title="${esc(taxPath(id))}">${n.k === "t" ? "# " : ""}${esc(tlabel(id))}${n.x ? ` <small>(${esc(it("ut_one"))})</small>` : ""}</span>
                    <span class="reflib-ib-utbtns">${canHost ? `<button type="button" data-act="atutnew" data-parent="${esc(id)}" data-kind="group" title="${esc(it("ut_newsub"))}">+ ${esc(it("ut_sub"))}</button><button type="button" data-act="atutnew" data-parent="${esc(id)}" data-kind="tag" title="${esc(it("ut_newtag"))}">+ #</button>` : ""}${n.u ? `<button type="button" data-act="atutedit" data-tid="${esc(id)}" title="${esc(it("ut_rename"))}">✎</button><button type="button" data-act="atutmove" data-tid="${esc(id)}" title="${esc(it("ut_move"))}" ${n.k === "c" ? "disabled" : ""}>⇄</button><button type="button" data-act="atutdel" data-tid="${esc(id)}" title="${esc(it("ut_delete"))}">🗑</button>` : ""}</span></div>`);
                if (open || (ut.move && kids.length && open)) walk(id, depth + 1);
            }
        };
        walk(null, 0);
        let form = "";
        const f = ut.form;
        if (f) {
            const n = f.tid ? tax.byId.get(f.tid) : null;
            const kind = n ? ({ c: "category", g: "group", t: "tag" })[n.k] : f.kind;
            const where = f.tid ? taxPath(n.p) : (f.parent ? taxPath(f.parent) : it("ut_toplevel"));
            const syn = (n && n.s) || { es: [], en: [] };
            form = `<div class="reflib-ib-utform" data-kind="${kind}">
                <div class="reflib-ib-muted">${esc(it(f.tid ? "ut_editing" : "ut_new_" + kind))} · ${esc(it("ut_parent"))}: <b>${esc(where || "—")}</b></div>
                <input data-utn="es" placeholder="${esc(it("ut_es"))}" value="${esc(n ? n.es : "")}"><input data-utn="en" placeholder="${esc(it("ut_en"))}" value="${esc(n ? n.en : "")}">
                <input data-utn="syn_es" placeholder="${esc(it("ut_syn_es"))}" value="${esc((syn.es || []).join(", "))}"><input data-utn="syn_en" placeholder="${esc(it("ut_syn_en"))}" value="${esc((syn.en || []).join(", "))}">
                ${kind === "group" ? `<label><input type="checkbox" data-utn="exclusive" ${n && n.x ? "checked" : ""}> ${esc(it("ut_excl"))}</label>` : ""}
                <button type="button" class="reflib-ib-btn reflib-ib-primary" data-act="${f.tid ? "atutsave" : "atutadd"}">${esc(it(f.tid ? "ut_save" : "ut_create"))}</button>
                <button type="button" class="reflib-ib-btn" data-act="atutcancel">${esc(it("cancel_btn"))}</button></div>`;
        }
        const mv = ut.move ? `<div class="reflib-ib-utmove">${esc(it("ut_move_hint", { name: tlabel(ut.move) }))} <button type="button" data-act="atutmovecancel">${esc(it("cancel_btn"))}</button></div>` : "";
        return `<div class="reflib-ib-utax"><b>${esc(it("ut_title"))}</b> <span class="reflib-ib-muted">${esc(it("ut_hint"))}</span>
            <div class="reflib-ib-uttop"><button type="button" class="reflib-ib-btn" data-act="atutnew" data-parent="" data-kind="category">+ ${esc(it("ut_newcat"))}</button>
              <button type="button" class="reflib-ib-btn" data-act="atutundo">↶ ${esc(it("ut_undo"))}</button>
              <span class="reflib-ib-utio"><select data-utx="what" aria-label="${esc(it("utx_export"))}">${["full_json", "mine_json", "full_csv", "mine_csv"].map(k => `<option value="${k}">${esc(it("utx_" + k))}</option>`).join("")}</select><button type="button" class="reflib-ib-btn" data-act="atutexport">⤓ ${esc(it("utx_export"))}</button></span>
              <span class="reflib-ib-utio"><select data-utx="mode" aria-label="${esc(it("utx_import"))}"><option value="merge">${esc(it("utx_merge"))}</option><option value="replace">${esc(it("utx_replace"))}</option></select><button type="button" class="reflib-ib-btn" data-act="atutimport">⤒ ${esc(it("utx_import"))}</button></span></div>
            ${mv}${form}<div class="reflib-ib-uterr" role="alert"></div>
            <div class="reflib-ib-uttree">${rows.join("")}</div></div>`;
    }
    function utSend(req, okMsg) {
        const err = ilib.root.querySelector(".reflib-ib-uterr");
        return sendIlib(req).then(r => {
            if (!r || !r.ok) { if (err) err.textContent = (r && r.error) || "error"; return false; }
            setTax(r.tax);
            const ut = ilib.at.ut; ut.form = null; ut.move = null;
            if (r.r && r.r.parent) { let p = r.r.parent; while (p) { ut.open.add(p); const pn = ilib.at.tax.byId.get(p); p = pn && pn.p; } }
            renderAtSettings(false); newQuery(); loadFacets(true); toast(okMsg(r), "ok");
            if (ilib.preview) loadAutoImage(ilib.preview);
            return true;
        }).catch(() => false);
    }
    // ---- 1.5.8 export / import of the taxonomy (download through the browser; import validated server-side, undoable)
    function utDownload(name, text, mime) {
        const url = URL.createObjectURL(new Blob([text], { type: mime }));
        const a = document.createElement("a"); a.href = url; a.download = name; a.style.display = "none";
        document.body.appendChild(a); a.click(); setTimeout(() => { a.remove(); URL.revokeObjectURL(url); }, 1500);
    }
    function utExport(what) {
        const [scope, fmt] = String(what || "full_json").split("_");
        sendIlib({ action: "at_tax_export", scope, fmt }).then(r => {
            if (!r || !r.ok) { toast((r && r.error) || "error", "error"); return; }
            const d = new Date(), stamp = `${d.getFullYear()}${String(d.getMonth() + 1).padStart(2, "0")}${String(d.getDate()).padStart(2, "0")}`;
            const file = `reflib-taxonomy-${scope}-${stamp}.${r.fmt}`;
            utDownload(file, r.fmt === "csv" ? r.data : JSON.stringify(r.data, null, 1), r.fmt === "csv" ? "text/csv;charset=utf-8" : "application/json");
            toast(it("utx_exported", { file }), "ok");
        }).catch(() => toast("error", "error"));
    }
    function utSummary(r) {
        return { added: r.added, updated: r.updated, mode: it(r.mode === "replace" ? "utx_replace" : "utx_merge"),
                 removed: r.removed ? it("utx_removed", { n: r.removed }) : "", rejected: r.n_rejected ? it("utx_rejected", { n: r.n_rejected }) : "" };
    }
    function utShowRejects(r) {
        const err = ilib.root.querySelector(".reflib-ib-uterr");
        if (err) err.textContent = r.n_rejected ? it("utx_rej_list") + " " + r.rejected.slice(0, 12).map(x => `${x.label || x.id} (${x.reason})`).join(" · ") + (r.n_rejected > 12 ? " …" : "") : "";
    }
    function utImportPick(mode) {
        const inp = document.createElement("input"); inp.type = "file"; inp.accept = ".json,application/json"; inp.className = "reflib-ib-utfile"; inp.style.display = "none";
        document.body.appendChild(inp);
        inp.addEventListener("change", () => { const f = inp.files && inp.files[0]; inp.remove(); if (f) utImportFile(f, mode); });
        inp.click();
    }
    async function utImportFile(file, mode) {
        if (file.size > 2 * 1024 * 1024) { toast(it("utx_toobig"), "error"); return; }
        let data; try { data = JSON.parse((await file.text()).replace(/^\uFEFF/, "")); } catch (e) { toast(it("utx_badjson"), "error"); return; }
        const pre = await sendIlib({ action: "at_tax_import", data, mode, dry_run: true }).catch(() => null);
        if (!pre || !pre.ok) { toast((pre && pre.error) || "error", "error"); return; }
        const r0 = pre.r; utShowRejects(r0);
        if (!(r0.added || r0.updated || r0.removed)) { toast(it("utx_nothing", { rejected: utSummary(r0).rejected }), "info"); return; }
        if (!(await confirmDlg(it("utx_confirm", utSummary(r0)), it("utx_ok")))) return;
        const ok = await utSend({ action: "at_tax_import", data, mode }, () => "");
        if (ok) {
            utShowRejects(r0);
            toast(it("utx_done", utSummary(r0)), "ok", [{ label: it("ut_undo"), onClick: () => utSend({ action: "at_tax_undo" }, () => it("ut_undone")) }], 12000);
        }
    }
    function utMoveTo(tid, parent) {
        if (!tid || !parent || tid === parent) return;
        utSend({ action: "at_tax_update", tid, parent }, () => it("ut_moved", { name: tlabel(tid), to: taxPath(parent) }));
    }
    function utClick(act, el) {
        const box = ilib.root.querySelector(".reflib-ib-utax"); if (!box) return false;
        const ut = ilib.at.ut, tid = el.dataset.tid;
        if (act === "atuttoggle") { ut.open.has(tid) ? ut.open.delete(tid) : ut.open.add(tid); renderAtSettings(); return true; }
        if (act === "atutpick") {
            if (ut.move) { const n = ilib.at.tax.byId.get(tid); if (n && n.k !== "t") utMoveTo(ut.move, tid); return true; }
            ut.open.has(tid) ? ut.open.delete(tid) : ut.open.add(tid); renderAtSettings(); return true;
        }
        if (act === "atutnew") { ut.form = { parent: el.dataset.parent || "", kind: el.dataset.kind }; ut.move = null; if (el.dataset.parent) ut.open.add(el.dataset.parent); renderAtSettings(false); const i = box.ownerDocument.querySelector('.reflib-ib-utform [data-utn="es"]'); if (i) i.focus(); return true; }
        if (act === "atutedit") { ut.form = { tid }; ut.move = null; renderAtSettings(false); return true; }
        if (act === "atutcancel") { ut.form = null; renderAtSettings(false); return true; }
        if (act === "atutmove") { ut.move = tid; ut.form = null; renderAtSettings(false); return true; }
        if (act === "atutmovecancel") { ut.move = null; renderAtSettings(false); return true; }
        if (act === "atutexport") { utExport(box.querySelector('[data-utx="what"]').value); return true; }
        if (act === "atutimport") { utImportPick(box.querySelector('[data-utx="mode"]').value); return true; }
        if (act === "atutundo") { utSend({ action: "at_tax_undo" }, () => it("ut_undone")); return true; }
        if (act === "atutdel") { const name = tlabel(tid); utSend({ action: "at_tax_delete", tid }, () => it("ut_deleted", { name })); return true; }
        const v = (k) => { const x = box.querySelector(`.reflib-ib-utform [data-utn="${k}"]`); return x ? (x.type === "checkbox" ? x.checked : x.value) : undefined; };
        if (act === "atutadd") {
            const f = ut.form || {};
            utSend({ action: "at_tax_add", kind: f.kind || "tag", parent: f.parent || null, es: v("es"), en: v("en"), syn_es: v("syn_es"), syn_en: v("syn_en"), exclusive: !!v("exclusive") },
                   r => it("ut_created", { name: lang() === "es" ? r.r.es : r.r.en }));
            return true;
        }
        if (act === "atutsave") {
            const req = { action: "at_tax_update", tid: ut.form.tid, es: v("es"), en: v("en"), syn_es: v("syn_es"), syn_en: v("syn_en") };
            if (v("exclusive") !== undefined) req.exclusive = !!v("exclusive");
            utSend(req, () => it("ut_saved"));
            return true;
        }
        return false;
    }
    function utDragWire(box) {   // drag a user node onto a category / sub-category to move it
        box.addEventListener("dragstart", (e) => { const n = e.target.closest(".reflib-ib-utnode.user"); if (!n) return; e.dataTransfer.setData("text/reflib-tid", n.dataset.tid); e.dataTransfer.effectAllowed = "move"; });
        box.addEventListener("dragover", (e) => { const n = e.target.closest(".reflib-ib-utnode:not(.k-t)"); if (n && [...e.dataTransfer.types].includes("text/reflib-tid")) { e.preventDefault(); n.classList.add("drop"); } });
        box.addEventListener("dragleave", (e) => { const n = e.target.closest(".reflib-ib-utnode"); if (n) n.classList.remove("drop"); });
        box.addEventListener("drop", (e) => { const n = e.target.closest(".reflib-ib-utnode:not(.k-t)"); const tid = e.dataTransfer.getData("text/reflib-tid"); if (n && tid) { e.preventDefault(); utMoveTo(tid, n.dataset.tid); } });
    }
    function renderAtSettings(keep = true) {
        const box0 = ilib.root && ilib.root.querySelector(".reflib-ib-atset");
        const kept = new Map();   // a late settings reply must not wipe what the user is typing in the editor
        if (keep && box0) box0.querySelectorAll(".reflib-ib-utax input, .reflib-ib-utax select").forEach(el => {
            const row = el.closest(".reflib-ib-utrow"); kept.set((row ? row.dataset.tid : "") + "|" + (el.dataset.ut || el.dataset.utn), el.type === "checkbox" ? el.checked : el.value);
        });
        renderAtSettingsBase();
        const box = ilib.root && ilib.root.querySelector(".reflib-ib-atset");
        if (box && ilib.at.setOpen && ilib.at.settings) {
            box.insertAdjacentHTML("beforeend", renderTaxEditor());
            const ub = box.querySelector(".reflib-ib-utax"); if (ub) utDragWire(ub);
            box.querySelectorAll(".reflib-ib-utax input, .reflib-ib-utax select").forEach(el => {
                const row = el.closest(".reflib-ib-utrow"), k = (row ? row.dataset.tid : "") + "|" + (el.dataset.ut || el.dataset.utn);
                if (kept.has(k)) { if (el.type === "checkbox") el.checked = kept.get(k); else el.value = kept.get(k); }
            });
        }
    }
    // 1.5.4 Spanish model names / licences in the selector and dialogs
    const MODEL_ES = { "gemini-3.8-flash": "Gemini 3.8 Flash (nube, de pago · recomendado)", "gpt-6.1-sol": "GPT-6.1 Sol (nube, de pago · máxima calidad)",
        "claude-opus-5-5": "Claude Opus 5.5 (nube, de pago · solo fotos vestidas)", "claude-sonnet-5-5": "Claude Sonnet 5.5 (nube, de pago · solo fotos vestidas)",
        openai: "Endpoint compatible con OpenAI (nube)", gemini: "Google Gemini (nube)", grok: "xAI Grok (nube)", fake: "Falso (pruebas)",
        "wd+qwen": "WD-EVA02 + Qwen2.5-VL-7B (recomendado)", "wd-small": "WD-ViT tagger v3 (pequeño)",
        "openrouter-router": "OpenRouter Jev Router (nube, sube la imagen)", "openrouter-jev": "Descripción local + decisiones de OpenRouter Jev 1.13 (nube, solo texto)",
        jev: "Jev (jevimage 0.1.20, SigLIP2 so400m; URL del servidor o venv propio)", "jev+qwen": "Jev + Qwen2.5-VL-7B para los grupos finos (necesita un servidor Jev)" };
    const LIC_ES = { "service terms (paid)": "condiciones del servicio (de pago)", "service terms": "condiciones del servicio", "service terms + local describer": "condiciones del servicio + descriptor local" };
    function mlabel(k) { const m = (ilib.at.models || {})[k] || {}; return (lang() === "es" && MODEL_ES[k]) || m.label || k; }
    function mlic(l) { return (lang() === "es" && LIC_ES[l]) || l || ""; }
    function renderAtSettingsBase() {
        const box = ilib.root && ilib.root.querySelector(".reflib-ib-atset");
        if (!box) return;
        box.hidden = !ilib.at.setOpen;
        const s = ilib.at.settings, models = ilib.at.models;
        if (!ilib.at.setOpen || !s) return;
        const opt = (k) => `<option value="${esc(k)}" ${s.model === k ? "selected" : ""}>${esc(mlabel(k))}${models[k].size_gb ? ` · ${models[k].size_gb} GB` : ""} · ${esc(mlic(models[k].licence))}</option>`;
        const fb = (k) => `<option value="${esc(k)}" ${s.fallback_model === k ? "selected" : ""}>${esc(mlabel(k))}</option>`;
        box.innerHTML = `<b>${esc(it("at_settings"))}</b>
            <label>${esc(it("set_model"))} <select data-k="model">${Object.keys(models).map(opt).join("")}</select></label>
            <label>${esc(it("set_fallback"))} <select data-k="fallback_model">${Object.keys(models).filter(k => !models[k].cloud).map(fb).join("")}</select></label>
            <label>${esc(it("set_threshold"))} <input type="number" step="0.05" min="0" max="1" data-k="threshold" value="${s.threshold}"></label>
            <label>${esc(it("set_batch"))} <input type="number" min="1" max="64" data-k="batch" value="${s.batch}"></label>
            <label>${esc(it("set_vram"))} <input type="number" min="4" max="32" data-k="vram_gb" value="${s.vram_gb}"></label>
            <label class="reflib-ib-check"><input type="checkbox" data-k="offline" ${s.offline ? "checked" : ""}> ${esc(it("set_offline"))}</label>
            <label class="reflib-ib-check"><input type="checkbox" data-k="body_shape" ${s.body_shape ? "checked" : ""}> ${esc(it("set_body"))}</label>
            <label class="reflib-ib-check"><input type="checkbox" data-k="body_vlm_check" ${s.body_vlm_check ? "checked" : ""}> ${esc(it("set_body_vlm"))}</label>
            <label>${esc(it("set_jev_url"))} <input type="text" data-k="jev_url" value="${esc(s.jev_url || "")}" placeholder="http://127.0.0.1:8731"></label>
            <label class="reflib-ib-check"><input type="checkbox" data-k="jev_latest" ${s.jev_latest ? "checked" : ""}> ${esc(it("set_latest"))}</label>
            <label class="reflib-ib-check"><input type="checkbox" data-k="cloud_ok" ${s.cloud_ok ? "checked" : ""}> ${esc(it("set_cloud"))}</label>
            <label>${esc(it("set_key"))} <input type="password" autocomplete="off" data-k="openrouter_api_key" placeholder="${s.openrouter_api_key_set ? "•••• " + esc(it("set_key_set")) : "sk-or-…"}"></label>
            ${renderCloudSettings(s)}
            <button type="button" class="reflib-ib-btn reflib-ib-primary" data-act="atsave">${esc(it("set_save"))}</button>
            <button type="button" class="reflib-ib-btn" data-act="atset">×</button>`;
    }
    // ---- 1.5.3 paid cloud backends: per-backend toggle, model id, key (masked), editable prices, policy notes
    function renderCloudSettings(s) {
        const cl = ilib.at.cloud || {}, pol = ilib.at.policies || {};
        if (!Object.keys(cl).length) return "";
        const en = s.cloud_enabled || {}, ids = s.cloud_models || {}, pr = s.cloud_prices || {};
        const keys = new Set();
        const rows = Object.keys(cl).map(k => {
            const c = cl[k], p = Object.assign({}, c.price, pr[k] || {});
            let key = "";
            if (!keys.has(c.key_field)) {
                keys.add(c.key_field);
                const set = s[c.key_field + "_set"] || c.env_set;
                key = `<label>${esc(it("cl_key"))} <input type="password" autocomplete="off" data-k="${esc(c.key_field)}" placeholder="${set ? "•••• " + esc(it("set_key_set")) : esc(it("cl_key_env", { e: c.key_env }))}"></label>`;
            }
            const pl = pol[c.provider] || {};
            return `<div class="reflib-ib-clrow" data-m="${esc(k)}">
                <label class="reflib-ib-check reflib-ib-clname"><input type="checkbox" data-ck="enable" ${en[k] ? "checked" : ""}> <b>${esc(mlabel(k))}</b></label>
                <label>${esc(it("cl_model_id"))} <input type="text" data-ck="model_id" value="${esc(ids[k] || "")}" placeholder="${esc(c.model_id)}"></label>
                ${key}
                <label title="${esc(it("cl_price"))}">$ <input type="number" step="0.001" min="0" data-ck="in" value="${p.in}" aria-label="in"><input type="number" step="0.001" min="0" data-ck="out" value="${p.out}" aria-label="out"><input type="number" step="0.001" min="0" data-ck="cache" value="${p.cache}" aria-label="cache"></label>
                <div class="reflib-ib-clnote">${c.clothed_only ? `<span class="reflib-ib-clwarn">${esc(it("cl_clothed"))}</span> ` : ""}${c.warning ? `<span class="reflib-ib-clwarn">⚠ ${esc(it("cl_warn_" + c.warning))}</span> ` : ""}${esc(it("cl_pol_" + c.provider))}
                  <a href="${esc(pl.retention || "#")}" target="_blank" rel="noopener">${esc(it("cl_retention"))}</a> · <a href="${esc(pl.usage || "#")}" target="_blank" rel="noopener">${esc(it("cl_usage"))}</a></div></div>`;
        }).join("");
        return `<div class="reflib-ib-cloudset"><b>${esc(it("cl_title"))}</b> <span class="reflib-ib-muted">${esc(it("cl_price"))}</span>
            <div class="reflib-ib-clnever">${esc(it("cl_never"))}</div>${rows}
            <label class="reflib-ib-check"><input type="checkbox" data-k="cloud_batch" ${s.cloud_batch ? "checked" : ""}> ${esc(it("cl_batch"))}</label></div>`;
    }
    function cloudSettingsValues() {
        const out = { cloud_enabled: {}, cloud_models: {}, cloud_prices: {} };
        ilib.root.querySelectorAll(".reflib-ib-clrow").forEach(r => {
            const m = r.dataset.m, q = (k) => r.querySelector(`[data-ck="${k}"]`);
            out.cloud_enabled[m] = q("enable").checked;
            if (q("model_id").value.trim()) out.cloud_models[m] = q("model_id").value.trim();
            out.cloud_prices[m] = { in: Number(q("in").value), out: Number(q("out").value), cache: Number(q("cache").value) };
        });
        return out;
    }
    function closeCostDlg() { const d = ilib.root && ilib.root.querySelector(".reflib-ib-costbg"); if (d) d.remove(); }
    function costDialog(e, onOk) {
        closeCostDlg();
        const f = (x) => "$" + Number(x || 0).toFixed(x < 1 ? 4 : 2), fm = (x) => Number(x).toLocaleString();
        const label = mlabel(e.model);
        const body = e.paid ? `<table class="reflib-ib-costtab">
              <tr><th>${esc(it("cd_model"))}</th><td>${esc(label)} <code>${esc(e.model_id || "")}</code></td></tr>
              <tr><th>${esc(it("cd_images"))}</th><td>${fm(e.images)}</td></tr>
              <tr><th>${esc(it("cd_tokens"))}</th><td>${fm(e.image_tokens)} ${esc(it("cd_img_tok", { w: e.image_px[0], h: e.image_px[1] }))} + ${fm(e.prompt_tokens)} ${esc(it("cd_prompt"))} + ${fm(e.output_tokens)} ${esc(it("cd_out"))}</td></tr>
              <tr><th>$ / 1M</th><td>${e.price.in} · ${e.price.out} · ${e.price.cache}</td></tr>
              <tr><th>${esc(it("cd_per"))}</th><td>${f(e.per_image_usd)} ${esc(it("cd_cache"))} · ${f(e.per_image_nocache_usd)} ${esc(it("cd_nocache"))}</td></tr>
              <tr class="reflib-ib-costtotal"><th>${esc(it("cd_total"))}</th><td><b class="reflib-ib-costusd">${f(e.usd)}</b> ${esc(it("cd_cache"))} · ${f(e.usd_nocache)} ${esc(it("cd_nocache"))}</td></tr></table>
            ${e.batch ? `<div class="reflib-ib-clwarn">${esc(it("cd_batch"))}</div>` : ""}
            ${e.warning ? `<div class="reflib-ib-clwarn">⚠ ${esc(it("cl_warn_" + e.warning))}</div>` : ""}
            ${e.clothed_only ? `<div class="reflib-ib-clwarn">${esc(it("cl_clothed"))}</div>` : ""}
            ${e.key_set === false ? `<div class="reflib-ib-clwarn">⚠ ${esc(it("cd_nokey"))}</div>` : ""}
            <div class="reflib-ib-muted">${esc(it("cd_gate"))}</div>`
            : `<div>${esc(it("cd_off", { m: e.local_instead || "" }))}</div>`;
        const bg = document.createElement("div");
        bg.className = "reflib-ib-costbg";
        bg.innerHTML = `<div class="reflib-ib-costdlg" role="dialog" aria-modal="true"><h3>${esc(it("cd_title"))}</h3>${body}
            <div class="reflib-ib-costbtns"><button type="button" class="reflib-ib-btn" data-cd="no">${esc(it("cd_cancel"))}</button>
            <button type="button" class="reflib-ib-btn reflib-ib-primary" data-cd="ok">${esc(it("cd_ok"))}</button></div></div>`;
        bg.addEventListener("click", (ev) => { const b = ev.target.closest("[data-cd]"); if (!b) return; ev.stopPropagation(); closeCostDlg(); if (b.dataset.cd === "ok") onOk(); });
        (ilib.root.querySelector(".reflib-ib-modal") || ilib.root).appendChild(bg);
    }
    function reportDialog(rp) {
        closeCostDlg();
        const u = rp.usage || {};
        const bg = document.createElement("div");
        bg.className = "reflib-ib-costbg";
        bg.innerHTML = `<div class="reflib-ib-costdlg reflib-ib-report" role="dialog"><h3>${esc(it("rp_title"))}</h3><table class="reflib-ib-costtab">
            <tr><th>${esc(it("cd_model"))}</th><td>${esc(rp.model || "")}</td></tr>
            <tr><th>${esc(it("rp_done"))}</th><td>${rp.done}</td></tr><tr><th>${esc(it("rp_sent"))}</th><td>${rp.cloud_sent}</td></tr>
            <tr><th>${esc(it("rp_gated"))}</th><td>${rp.gated}</td></tr><tr><th>${esc(it("rp_refused"))}</th><td>${rp.refused}</td></tr>
            <tr><th>${esc(it("rp_failed"))}</th><td>${rp.failed}</td></tr>
            <tr class="reflib-ib-costtotal"><th>${esc(it("rp_cost"))}</th><td><b class="reflib-ib-rpcost">$${Number(rp.cost_usd || 0).toFixed(4)}</b></td></tr>
            <tr><th></th><td class="reflib-ib-muted">${esc(it("rp_tokens", { i: u.input || 0, c: u.cached || 0, o: u.output || 0 }))}</td></tr></table>
            <div class="reflib-ib-costbtns"><button type="button" class="reflib-ib-btn reflib-ib-primary" data-cd="no">${esc(it("rp_close"))}</button></div></div>`;
        bg.addEventListener("click", (ev) => { if (ev.target.closest("[data-cd]")) closeCostDlg(); });
        (ilib.root.querySelector(".reflib-ib-modal") || ilib.root).appendChild(bg);
    }
    function atEnqueue(confirm) {
        sendIlib(Object.assign({ action: "at_enqueue", confirm: !!confirm }, ilib.sel.payload())).then(r => {
            if (!r || !r.ok) { if (r && r.error) toast(r.error, "error"); return; }
            if (r.confirm) {
                const e = r.confirm;
                if (e.model && ilib.at.cloud && ilib.at.cloud[e.model]) { costDialog(e, () => atEnqueue(true)); return; }
                const msg = e.cloud ? it("at_confirm_cloud", { n: e.images, usd: (e.usd || 0).toFixed(e.usd < 1 ? 4 : 2), up: e.upload_mb ? it("at_up", { mb: e.upload_mb }) : "" }) : it("at_confirm_dl", { gb: e.download_gb });
                toast(msg, "info", [{ label: it("at_go"), onClick: () => atEnqueue(true) }], 20000);
                return;
            }
            if (r.message) toast(r.message, "ok");
            ilib.at.status = r.at; renderAtBar(); pollAt();
        }).catch(() => {});
    }
    function atClick(act, el) {
        if (act.startsWith("atut")) return utClick(act, el);
        if (act === "atgo") { atEnqueue(false); return true; }
        if (act === "atjst") { const k = el.dataset.jst; ilib.f.jst = ilib.f.jst === k ? "" : k; newQuery(); return true; }
        if (act === "atretry") {
            sendIlib({ action: "at_retry" }).then(r => { if (r && r.ok) { if (r.message) toast(r.message, "ok"); ilib.at.status = r.at; renderAtBar(); pollAt(); } }).catch(() => {});
            return true;
        }
        if (act === "atpause") { sendIlib({ action: "at_pause", paused: !(ilib.at.status && ilib.at.status.paused) }).then(r => { if (r && r.at) { ilib.at.status = r.at; renderAtBar(); } }).catch(() => {}); return true; }
        if (act === "atcancel") { sendIlib({ action: "at_cancel" }).then(r => { if (r && r.at) { ilib.at.status = r.at; renderAtBar(); } }).catch(() => {}); return true; }
        if (act === "atunload") { sendIlib({ action: "at_unload" }).then(r => { if (r && r.at) { ilib.at.status = r.at; renderAtBar(); } }).catch(() => {}); return true; }
        if (act === "atfacet") { const tg = el.dataset.tag; if (ilib.f.xtags.has(tg)) ilib.f.xtags.delete(tg); else if (ilib.f.atags.has(tg)) ilib.f.atags.delete(tg); else ilib.f.atags.add(tg); newQuery(); return true; }
        if (act === "atcat") { const c = el.dataset.cat; ilib.at.open.has(c) ? ilib.at.open.delete(c) : ilib.at.open.add(c); const host = ilib.root.querySelector(".reflib-ib-facets"); if (host) host.outerHTML = renderFacets(); return true; }
        if (act === "atedit") {
            sendIlib({ action: "at_edit", hash: ilib.preview, tag: el.dataset.tag, op: el.dataset.op }).then(r => {
                if (r && r.ok) { ilib.at.img = r.img; const host = ilib.root.querySelector(".reflib-ib-autohost"); if (host) host.innerHTML = renderAutoPanel(ilib.preview); loadFacets(true); }
                else if (r && r.error) toast(r.error, "error");
            }).catch(() => {});
            return true;
        }
        if (act === "atheight") {
            const inp = ilib.root.querySelector(".reflib-ib-hin"), col = ilib.root.querySelector(".reflib-ib-hcol"), oc = oneCol();
            const req = { action: "at_height", hash: ilib.preview, cm: inp && inp.value ? Number(inp.value) : null };
            if (col && col.checked && oc) req.collection_id = oc.id;
            sendIlib(req).then(r => { if (r && r.ok) { if (r.img) { ilib.at.img = r.img; const host = ilib.root.querySelector(".reflib-ib-autohost"); if (host) host.innerHTML = renderAutoPanel(ilib.preview); } loadFacets(true); } else if (r && r.error) toast(r.error, "error"); }).catch(() => {});
            return true;
        }
        if (act === "atset") {
            ilib.at.setOpen = !ilib.at.setOpen;
            if (ilib.at.setOpen) sendIlib({ action: "at_settings" }).then(r => { if (r && r.ok) { ilib.at.settings = r.settings; ilib.at.models = r.models; ilib.at.cloud = r.cloud; ilib.at.policies = r.policies; renderAtSettings(); } }).catch(() => {});
            renderAtSettings();
            if (!ilib.at.setOpen) requestAnimationFrame(() => render());   // 1.5.8: the virtual grid re-measures once the panel is gone (was left blank)
            return true;
        }
        if (act === "atsave") {
            const set = {};
            ilib.root.querySelectorAll(".reflib-ib-atset [data-k]").forEach(x => {
                const k = x.dataset.k;
                if (x.type === "checkbox") set[k] = x.checked;
                else if (x.type === "number") set[k] = Number(x.value);
                else if (x.type === "password") { if (x.value) set[k] = x.value; }
                else set[k] = x.value;
            });
            Object.assign(set, cloudSettingsValues());
            sendIlib({ action: "at_settings", set }).then(r => { if (r && r.ok) { ilib.at.settings = r.settings; ilib.at.setOpen = false; renderAtSettings(); loadFacets(true); toast(it("set_save") + " ✓", "ok"); } }).catch(() => {});
            return true;
        }
        return false;
    }
    function renderPreview() {
        const host = ilib.root && ilib.root.querySelector(".reflib-ib-pvhost");
        if (!host) return;
        const h = ilib.preview;
        if (!viewPref().details) { host.innerHTML = ""; return; }   // 1.5.9: the details panel is opt-in (header "Detalles")
        if (!h) { host.innerHTML = `<aside class="reflib-ib-preview reflib-ib-pvempty"><button type="button" class="reflib-ib-pv-x" data-act="pvclose" title="${esc(it("close"))}">×</button><p class="reflib-ib-muted">${esc(it("v_pick"))}</p></aside>`; return; }
        const full = ilib.pvSrc && ilib.pvSrc.hash === h ? ilib.pvSrc : null;
        const lite = ilib.pvItem && ilib.pvItem.hash === h ? ilib.pvItem : null;
        const name = (full && full.name) || (lite && lite.name) || "";
        const cols = full ? (full.collections || []).map(c => c.name) : (lite ? lite.cols.map(colName) : []);
        const tags = (full && full.tags) || (lite && lite.tags) || [];
        const files = (full && full.files) || [];
        const added = (full && full.added) || (lite && lite.added) || 0;
        const folderOnly = full ? (full.folders || []).length && !(full.collections || []).length && !full.in_pool : lite && lite.folders.length && !lite.cols.length && !lite.pool;
        const src = full && full.src ? full.src : ilib.thumbs.get(h);
        const pmk = (full && full.kind) || (lite && lite.kind) || "image";   // 1.6.0
        const fv = full && full.virtual, lv = fv || (lite && lite.virtual) || null;   // 1.6.6 virtual copy / original's copies
        const rendering = !!(fv && full.render === "rendering");
        const vBox = lv ? `<div class="reflib-vc-box ${lv.broken ? "broken" : ""}"><div class="reflib-vc-head">${VICO}${esc(vct("is_virtual"))}</div>
                ${fv ? `<div class="reflib-vc-orig"><span>${esc(vct("orig"))}</span> <b title="${esc((fv.orig && fv.orig.path) || "")}">${esc((fv.orig && fv.orig.name) || "?")}</b></div>
                <div class="reflib-ib-muted">${esc(vParams(fv.params, pmk))}</div>
                ${fv.broken ? `<div class="reflib-vc-warn">⚠ ${esc(vct("orig_missing", { path: (fv.orig && fv.orig.path) || "?" }))}</div>` : (fv.orig_in_library ? "" : `<div class="reflib-vc-warn">${esc(vct("orig_gone"))}</div>`)}
                ${rendering ? `<div class="reflib-ib-muted reflib-vc-rendering">⏳ ${esc(vct("rendering"))}</div>` : ""}${full.render_error ? `<div class="reflib-vc-warn">${esc(vct("render_fail", { e: full.render_error }))}</div>` : ""}
                <div class="reflib-ib-pvbtns">${vBtn("vorig", (fv.orig && fv.orig.hash) || "", "reflib-ib-btn reflib-vc-showorig", vct("show_orig"), vct("show_orig"), fv.broken || !fv.orig_in_library, true)}</div>` : ""}</div>`
            : (full && full.copies && full.copies.length ? `<h4>${esc(vct("copies", { n: full.copies.length }))}</h4><div class="reflib-vc-list">${full.copies.map(c => `<button type="button" class="reflib-ib-chip" data-act="vshow" data-hash="${esc(c.hash)}" title="${esc(vParams(c.params, c.kind))}">${VICO}${esc(c.name)}</button>`).join("")}</div>` : "");
        if (rendering) vPollRender(h);
        host.innerHTML = `<aside class="reflib-ib-preview k-${pmk}"><button type="button" class="reflib-ib-pv-x" data-act="pvclose" title="${esc(it("close"))}">×</button>
              <div class="reflib-ib-pv-img">${pmk === "video" && full && full.url ? `<video class="reflib-ib-pvmedia" src="${esc(full.url)}" ${src ? `poster="${src}"` : ""} controls preload="metadata" playsinline></video>`
                  : (src ? `<img src="${src}" alt="">` : "") + (pmk === "audio" && full && full.url ? `<audio class="reflib-ib-pvmedia" src="${esc(full.url)}" controls preload="metadata"></audio>` : "")}</div>
              <div class="reflib-ib-pv-name">${esc(name)}</div>
              <div class="reflib-ib-pvbtns">${revealBtn(h, "reflib-ib-btn reflib-ib-pvreveal")}${locateBtn(h, "reflib-ib-btn reflib-ib-pvlocate")}${lv ? vBtn("vedit", h, "reflib-ib-btn reflib-vc-pvedit", "✎ " + vct("edit"), vct("edit_tip"), lv.broken) : cropBtn(h, "reflib-ib-btn reflib-ib-pvcrop", pmk)}${pmk === "video" && !(lv && lv.broken) ? resizeBtn(h, "reflib-ib-btn reflib-ib-pvresize") : ""}${lv && lv.broken ? "" : vBtn("vnew", h, "reflib-ib-btn reflib-vc-pvnew", vct("new"), vct("new_tip"), false, true)}</div>
              ${vBox}
              ${full && full.locations && full.locations.length ? `<div class="reflib-ib-pvcrumbs">${full.locations.map(locCrumbs).join("")}</div>` : ""}
              <div class="reflib-ib-muted">${pmk !== "image" ? esc([full && full.dur ? it("pv_dur") + " " + fmtDur(full.dur) : "", full && full.width ? `${full.width}×${full.height}` : "", full && full.fps ? Math.round(full.fps * 100) / 100 + " fps" : "",
                  full && full.codec ? full.codec : "", full && full.rate ? (full.rate / 1000) + " kHz" : "", full && full.size ? (full.size > 1048576 ? (full.size / 1048576).toFixed(1) + " MB" : Math.round(full.size / 1024) + " KB") : ""].filter(Boolean).join(" · "))
                  : (full && full.width ? `${full.width}×${full.height}${full.size ? ` · ${Math.round(full.size / 1024)} KB` : ""}` : "")}</div>
              ${added ? `<div class="reflib-ib-muted reflib-ib-pv-when">${esc(it(folderOnly ? "seen_on" : "added_on", { when: whenText(added) }))}</div>` : ""}
              <h4>${esc(it("preview_cols"))}</h4><div class="reflib-ib-pv-list">${cols.length ? cols.map(c => `<span class="reflib-ib-chip static">${esc(c)}</span>`).join("") : esc(it("in_none"))}</div>
              ${files.length ? `<h4>${esc(it("preview_folders"))}</h4><div class="reflib-ib-pv-files">${files.map(p => `<div title="${esc(p)}">${esc(p)}</div>`).join("")}</div>` : ""}
              <h4>${esc(it("preview_tags"))}</h4><div class="reflib-ib-pv-list">${tags.length ? tags.map(x => `<span class="reflib-ib-chip static">${esc(x)}</span>`).join("") : esc(it("preview_none"))}</div>
              ${pmk === "image" ? `<div class="reflib-ib-autohost">${renderAutoPanel(h)}</div>` : ""}</aside>`;
        if (pmk === "image" && (!ilib.at.img || ilib.at.img.hash !== h)) loadAutoImage(h);
    }
    // ---- selection footer: the server summarises the selection (it can be "all 11 207 matching") ----
    let infoTimer = null;
    function selChanged() {
        ilib.selSig++;
        ilib.delArmed = false;
        paintSelection();
        renderFooter();
        clearTimeout(infoTimer);
        if (!ilib.sel.size) { ilib.info = null; return; }
        infoTimer = setTimeout(() => {
            const sig = ilib.selSig, oc = oneCol();
            sendIlib(Object.assign({ action: "sel_info", one_col: oc ? oc.id : "" }, ilib.sel.payload())).then(r => {
                if (!r || !r.info || sig !== ilib.selSig) return;
                ilib.info = Object.assign({ sig }, r.info);
                renderFooter();
            }).catch(() => {});
        }, 60);
    }
    function oneCol() {
        const f = ilib.f, d = ilib.data;
        return d && f.cols.size === 1 && !f.none ? d.collections.find(c => f.cols.has(c.id)) : null;
    }
    function countText() {
        const d = ilib.data, q = ilib.q;
        if (!d) return "";
        return q.total === d.total ? it("n_images", { n: d.total }) : it("n_shown", { shown: q.total, n: d.total });
    }
    function mediaActions(inf, n) {   // 1.6.0: only what the selection and the current WanGP model can take
        const k = inf.kinds || { image: n, video: 0, audio: 0 };
        let html = "";
        if (k.image) html += `<button type="button" class="reflib-ib-btn reflib-ib-primary" data-act="torefs" title="${esc(it("to_refs_tip") + (k.video || k.audio ? " — " + it("only_images_refs", { n: k.video + k.audio }) : ""))}">${esc(it("to_refs"))}</button>`;
        if (k.video) {
            if (wanInput("reflib-vt-generate")) html += `<button type="button" class="reflib-ib-btn reflib-ib-primary" data-act="tovctl" ${n === 1 && k.video === 1 ? "" : "disabled"} title="${esc(n === 1 ? it("to_vctl_tip") : it("to_one"))}">🎬 ${esc(it("to_vctl"))}</button>`;
            html += `<button type="button" class="reflib-ib-btn" data-act="tovlib" title="${esc(it("to_vlib_tip"))}">${esc(it("to_vlib"))}</button>`;
        }
        if (k.audio) for (const a of audioTargets()) html += `<button type="button" class="reflib-ib-btn reflib-ib-primary" data-act="toaudio" data-to="${a.to}" ${n === 1 && k.audio === 1 ? "" : "disabled"} title="${esc(n === 1 ? it("to_audio_tip", { label: a.label }) : it("to_one"))}">🎵 ${esc(it("to_audio", { label: a.label }))}</button>`;
        return html;
    }
    function renderFooter() {
        const host = ilib.root && ilib.root.querySelector(".reflib-ib-foothost");
        const d = ilib.data;
        if (!host || !d) return;
        const n = ilib.sel.size;
        const info = ilib.info && ilib.info.sig === ilib.selSig ? ilib.info : null;
        const stale = !info && ilib.info;   // keep the last answer while the new one is on its way
        const inf = info || ilib.info || { deletable: n, cols: 0, folder_only: 0, on_disk: 0, in_one: n, tags: [] };
        const canDelete = inf.deletable > 0;
        const delTip = !canDelete ? it("del_tip_folder_only") : (inf.on_disk ? it("del_tip_disk", { k: inf.on_disk }) : it("del_tip_any"));
        const oc = oneCol();
        const removeBtn = oc ? `<button type="button" class="reflib-ib-btn reflib-ib-danger" data-act="removefrom" data-cid="${esc(oc.id)}" ${inf.in_one ? "" : "disabled"}
              title="${esc(inf.in_one ? it("remove_from_tip", { name: oc.name }) : it("remove_from_none", { name: oc.name }))}">${esc(it("remove_from", { name: oc.name }))}</button>` : "";
        const delLabel = ilib.delArmed ? it("del_confirm_n", { n: inf.deletable, c: inf.cols }) : it("del_lib");
        const def = d.collections.some(c => c.id === ilib.addTarget) ? ilib.addTarget : (d.collections.some(c => c.id === d.default_collection) ? d.default_collection : (d.collections[0] || {}).id || "__new");
        const addPanel = ilib.addOpen && n ? `<div class="reflib-ib-addpanel"><span>${esc(it("add_title", { n }))}</span>
              <select class="reflib-ib-target">${d.collections.map(c => `<option value="${esc(c.id)}" ${c.id === def ? "selected" : ""}>${esc(c.name)} (${c.count})</option>`).join("")}
                <option value="__new" ${def === "__new" ? "selected" : ""}>${esc(it("add_new"))}</option></select>
              <input type="text" class="reflib-ib-newname" placeholder="${esc(it("add_new_ph"))}" style="${def === "__new" ? "" : "display:none"}">
              <button type="button" class="reflib-ib-btn reflib-ib-primary" data-act="addgo">${esc(it("add_go"))}</button></div>` : "";
        const keepTag = host.querySelector(".reflib-ib-tagin");
        const tagVal = keepTag ? keepTag.value : "";
        const tagFocused = keepTag && document.activeElement === keepTag;
        const keepName = host.querySelector(".reflib-ib-newname");
        const nameVal = keepName ? keepName.value : "";
        host.innerHTML = `<div class="reflib-ib-foot ${n ? "" : "nosel"} ${stale ? "stale" : ""}">
              <span class="reflib-ib-count">${esc(n ? it("sel_n", { n }) : countText())}</span>
              <button type="button" class="reflib-ib-btn" data-act="selall">${esc(it("sel_visible"))}</button>
              ${n ? `<button type="button" class="reflib-ib-btn" data-act="selnone">${esc(it("sel_clear"))}</button>` : ""}
              <span class="reflib-ib-spacer"></span>
              ${n ? `<span class="reflib-ib-seltags">${(inf.tags || []).map(tg => `<span class="reflib-ib-chip static">${esc(tg)}<button type="button" data-act="untag" data-tag="${esc(tg)}" title="${esc(it("tag_remove", { tag: tg }))}">×</button></span>`).join("")}</span>
                <input type="text" class="reflib-ib-tagin" list="reflib-ib-taglist" placeholder="${esc(it("tag_ph"))}">
                <datalist id="reflib-ib-taglist">${d.tags.map(x => `<option value="${esc(x.tag)}"></option>`).join("")}</datalist>
                <button type="button" class="reflib-ib-btn" data-act="tag">${esc(it("tag_add"))}</button>
                <label class="reflib-ib-check" title="${esc(it("close_after"))}"><input type="checkbox" class="reflib-ib-closeafter" ${localStorage.getItem("reflib_ib_close_after") === "1" ? "checked" : ""}> ${esc(it("close_after"))}</label>
                ${mediaActions(inf, n)}
                <button type="button" class="reflib-ib-btn reflib-ib-primary" data-act="addopen">${esc(it("add_to"))}</button>
                ${!inf.kinds || inf.kinds.image ? `<button type="button" class="reflib-ib-btn reflib-ib-at" data-act="atgo" title="${esc(it("at_btn_tip"))}">✨ ${esc(it("at_btn"))}</button>` : ""}
                ${removeBtn}<button type="button" class="reflib-ib-btn reflib-ib-danger ${ilib.delArmed ? "armed" : ""}" data-act="del" ${canDelete ? "" : "disabled"} title="${esc(delTip)}">${esc(delLabel)}</button>` : ""}
            </div>${addPanel}`;
        const tagin = host.querySelector(".reflib-ib-tagin");
        if (tagin) { tagin.value = tagVal; if (tagFocused) tagin.focus(); }
        const nn = host.querySelector(".reflib-ib-newname");
        if (nn && nameVal) nn.value = nameVal;
    }
    // ---- background work indicator: folder indexing (pausable) and thumbnails being generated ----
    function renderProgress() {
        const bar = ilib.root && ilib.root.querySelector(".reflib-ib-progress");
        if (!bar) return;
        const st = ilib.scan || {};
        const thumbsLeft = st.thumbs_pending || 0;
        const paused = !!st.pause_set;
        if (!st.running && !thumbsLeft && !paused) { bar.hidden = true; return; }
        bar.hidden = false;
        const name = (st.path || "").split(/[\\/]/).filter(Boolean).pop() || st.path || "";
        let text = "";
        if (st.running) text = st.total ? it("indexing", { name, done: st.done, total: st.total }) : it("indexing_start", { name });
        if (paused) text = (text ? text + " · " : "") + it("idx_paused");
        if (thumbsLeft) text = (text ? text + " · " : "") + it("thumbs_gen", { n: thumbsLeft });
        bar.querySelector(".reflib-ib-progress-text").textContent = text;
        bar.querySelector(".reflib-ib-progress-bar i").style.width = (st.running ? (st.total ? Math.round(100 * st.done / st.total) : 3) : 100) + "%";
        bar.classList.toggle("paused", paused);
        const pb = bar.querySelector(".reflib-ib-pause");
        pb.textContent = paused ? it("resume") : it("pause");
        pb.title = paused ? it("resume_tip") : it("pause_tip");
    }
    let pollTimer = null, pollAnnounce = false, pollLastRefresh = 0, pollLastDone = -1, pollWasRunning = false;
    function pollScan(announce) {
        pollAnnounce = pollAnnounce || !!announce;
        if (pollTimer) return;
        const tick = async () => {
            pollTimer = null;
            let r;
            try { r = await sendIlib({ action: "scan_status" }); } catch (e) { return; }
            const st = (r && r.scan) || {};
            ilib.scan = st;
            renderProgress();
            if (st.running) {
                pollWasRunning = true;
                if (ilib.open && Date.now() - pollLastRefresh > 3000 && st.done !== pollLastDone) {
                    pollLastRefresh = Date.now(); pollLastDone = st.done;
                    refreshData();
                }
                pollTimer = setTimeout(tick, 800);
                return;
            }
            pollLastDone = -1;
            if ((pollWasRunning || (st.seq != null && st.seq !== ilib.scanSeq)) && ilib.open) refreshData();   // also scans too quick to be seen running
            ilib.scanSeq = st.seq;
            pollWasRunning = false;
            if (pollAnnounce && r.scan_message) toast(r.scan_message, st.missing && st.missing.length ? "error" : "ok");
            pollAnnounce = false;
            if (ilib.open && (st.thumbs_pending || st.pause_set)) pollTimer = setTimeout(tick, 1500);
        };
        pollTimer = setTimeout(tick, 300);
    }
    // the index changed (scan progress): counts + the pages on screen, never the whole list
    function refreshData() {
        const q = ilib.q, sig = q.sig;
        const main = ilib.root && ilib.root.querySelector(".reflib-ib-main");
        let first = 0;
        if (main && ilib.lay) { const r = visibleRows(0).find(x => !x.head); if (r) first = r.start; }
        const pg = Math.floor(first / PAGE);
        sendIlib({ action: "query", f: filterSnap(), offset: pg * PAGE, limit: PAGE, tz: tz(), meta: true }).then(r => {
            if (!r || r.ok === false || !r.meta) return;
            setMeta(r);   // counts/tree always; the page only if the filter didn't change meanwhile
            ilib.q.gen += 1; ilib.q.pages = new Set(); ilib.q.loading = new Set();
            if (ilib.q.sig === sig) applyPage(r.page, sig, ilib.q.gen);
            render();
        }).catch(() => {});
    }
    function buildModal() {
        const bg = document.createElement("div");
        bg.className = "reflib-ib-bg";
        bg.innerHTML = `<div class="reflib-ib-modal" role="dialog" aria-modal="true">
            <div class="reflib-ib-head"><span class="reflib-ib-ico">${GRID_SVG}</span><h3 class="reflib-ib-title"></h3>
              <input type="search" class="reflib-ib-q" spellcheck="false">
              <button type="button" class="reflib-ib-btn reflib-ib-import"></button>
              <button type="button" class="reflib-ib-btn reflib-ib-addfolder"></button>
              <button type="button" class="reflib-ib-btn reflib-ib-rescan"></button>
              <button type="button" class="reflib-ib-btn reflib-ib-histbtn" data-act="hist"></button>
              <span class="reflib-ib-kinds" role="group"></span>
              <span class="reflib-ib-view" role="group"><button type="button" class="reflib-ib-vsz" data-act="vsize" data-v="l">▣</button><button type="button" class="reflib-ib-vsz" data-act="vsize" data-v="m">▦</button><button type="button" class="reflib-ib-vsz" data-act="vsize" data-v="s">▩</button><button type="button" class="reflib-ib-vdet" data-act="vdetails"></button></span>
              <button type="button" class="reflib-ib-fs" data-act="fullscreen" aria-label="fullscreen">⛶</button>
              <button type="button" class="reflib-ib-x" aria-label="close">×</button></div>
            <div class="reflib-ib-faddrow" hidden><input type="text" class="reflib-ib-fpath-in" spellcheck="false" autocomplete="off">
              <label class="reflib-ib-check"><input type="checkbox" class="reflib-ib-frec-in" checked> <span class="reflib-ib-frec-label"></span></label>
              <button type="button" class="reflib-ib-btn" data-act="fbrowse"></button>
              <button type="button" class="reflib-ib-btn reflib-ib-primary" data-act="fadd"></button>
              <button type="button" class="reflib-ib-btn" data-act="faddcancel"></button></div>
            <div class="reflib-ib-picker" hidden></div>
            <div class="reflib-ib-progress" hidden><span class="reflib-ib-progress-text"></span><span class="reflib-ib-progress-bar"><i></i></span><button type="button" class="reflib-ib-btn reflib-ib-pause" data-act="pause"></button></div>
            <div class="reflib-ib-atbar" hidden><span class="reflib-ib-attext"></span><span class="reflib-ib-progress-bar"><i></i></span>
              <button type="button" class="reflib-ib-btn" data-act="atpause"></button><button type="button" class="reflib-ib-btn" data-act="atcancel"></button>
              <button type="button" class="reflib-ib-btn" data-act="atunload"></button></div>
            <div class="reflib-ib-atset" hidden></div>
            <div class="reflib-ib-body"></div>
            <div class="reflib-ib-drop"><span></span></div>
            <input type="file" class="reflib-ib-file" accept="image/*,video/*,audio/*" multiple hidden></div>`;
        const host = document.querySelector(".gradio-container") || document.body;
        host.appendChild(bg);
        ilib.root = bg;
        const modal = bg.querySelector(".reflib-ib-modal");
        bg.addEventListener("mousedown", (e) => { if (e.target === bg) closeBrowser(); });
        bg.querySelector(".reflib-ib-x").addEventListener("click", closeBrowser);
        let qTimer = null;   // search is server-side: debounce typing
        bg.querySelector(".reflib-ib-q").addEventListener("input", (e) => { ilib.f.q = e.target.value; clearTimeout(qTimer); qTimer = setTimeout(() => newQuery(), 180); suggestSoon(e.target.value); });
        bg.querySelector(".reflib-ib-q").addEventListener("keydown", (e) => { if (sugKey(e)) clearTimeout(qTimer); }, true);
        bg.querySelector(".reflib-ib-q").addEventListener("blur", () => setTimeout(() => closeSug(), 150));
        bg.querySelector(".reflib-ib-rescan").addEventListener("click", () => sendIlib({ action: "rescan" }).then(r => { ilibApply(r); pollScan(true); }).catch(() => {}));
        bg.querySelector(".reflib-ib-addfolder").addEventListener("click", () => {
            ilib.faddOpen = !ilib.faddOpen; render();
            if (ilib.faddOpen) setTimeout(() => bg.querySelector(".reflib-ib-fpath-in").focus(), 30);
        });
        const file = bg.querySelector(".reflib-ib-file");
        bg.querySelector(".reflib-ib-import").addEventListener("click", () => file.click());
        file.addEventListener("change", () => { if (file.files.length) uploadFiles([...file.files]); file.value = ""; });
        modal.addEventListener("dragover", (e) => { if ([...(e.dataTransfer.types || [])].includes("Files")) { e.preventDefault(); modal.classList.add("dropping"); } });
        modal.addEventListener("dragleave", (e) => { if (e.target === modal || !modal.contains(e.relatedTarget)) modal.classList.remove("dropping"); });
        modal.addEventListener("drop", (e) => {
            e.preventDefault(); modal.classList.remove("dropping");
            const files = [...(e.dataTransfer.files || [])].filter(f => /^(image|video|audio)\//.test(f.type) || /\.(png|jpe?g|webp|bmp|gif|tiff?|mp4|mov|m4v|webm|mkv|avi|wav|mp3|flac|ogg|m4a|aac|opus)$/i.test(f.name));
            if (files.length) uploadFiles(files);
        });
        bg.addEventListener("click", onClick);
        bg.addEventListener("contextmenu", (e) => {   // 1.5.2 right-click menu on a card
            const card = e.target.closest(".reflib-ib-card");
            if (!card || !card.dataset.hash) return;
            e.preventDefault();
            openCtx(e, card);
        });
        bg.addEventListener("mousedown", (e) => { if (!e.target.closest(".reflib-ib-ctx")) closeCtx(); }, true);
        bg.addEventListener("dblclick", (e) => {   // 1.5.2: double-click opens the large preview
            const card = e.target.closest(".reflib-ib-card");
            if (!card || e.target.closest(".reflib-ib-cb") || !card.dataset.hash) return;
            e.preventDefault();
            openLightbox(+card.dataset.idx);
        });
        bg.addEventListener("mousedown", startDrag);
        hoverWire(bg);
        // Shift on a checkbox = range (the change event doesn't carry the modifier)
        bg.addEventListener("click", (e) => { if (e.target.matches(".reflib-ib-cb input")) ilib.cbShift = e.shiftKey; }, true);
        bg.addEventListener("change", onChange);
        bg.addEventListener("keydown", (e) => {
            if (e.key === "Enter" && e.target.classList.contains("reflib-ib-tagin")) { e.preventDefault(); doTag(); }
            else if (e.key === "Enter" && e.target.classList.contains("reflib-ib-fpath-in")) { e.preventDefault(); addFolder(); }
            else if (e.key === "Enter" && e.target.classList.contains("reflib-ib-newname")) { e.preventDefault(); doAdd(); }
        });
        let rsTimer = null;   // the grid width changes with the window and when the preview panel opens/closes
        ilib.ro = new ResizeObserver(() => { clearTimeout(rsTimer); rsTimer = setTimeout(() => { if (ilib.open && ilib.lay) { const l = computeLayout(); if (l && (l.cols !== ilib.lay.cols || Math.abs(l.cw - ilib.lay.cw) > 1)) renderGrid(); } }, 30); });
    }
    function uploadFiles(files) {
        const root = document.getElementById("reflib_ilib_upload");
        const input = root && root.querySelector('input[type="file"]');
        if (!input) { toast(t("error", { e: "upload missing (reload)" }), "error"); return; }
        const id = Math.random().toString(16).slice(2);
        setText("reflib_ilib_upload_meta", JSON.stringify({ id, lang: lang(), browser: browserLang() }));
        const dt = new DataTransfer();
        for (const f of files) dt.items.add(f);
        new Promise((resolve, reject) => {
            const timer = setTimeout(() => { pending.delete(id); reject(new Error("timeout")); }, 180000);
            pending.set(id, { resolve, reject, timer });
            setTimeout(() => { input.files = dt.files; input.dispatchEvent(new Event("change", { bubbles: true })); }, 150);
        }).then(ilibApply).catch(e => toast(t("error", { e: e.message || e }), "error"));
    }
    function undoToast(r, sel) {
        if (!r || !r.undo_remove) return;
        if (sel.all) ilib.sel.clear(); else for (const h of sel.hashes || []) ilib.sel.delete(h);
        selChanged();
        const box = ensureToasts();
        const last = box.lastElementChild;
        if (last) last.remove();   // replaced by the same message with an Undo button
        toast(r.toast, "ok", [{ label: it("undo"), onClick: () => sendIlib({ action: "undo_remove", token: r.undo_remove }).then(ilibApply).catch(() => {}) }], 15000);
    }
    function selectedHashes() { return [...ilib.sel]; }
    function doTag() {
        const inp = ilib.root.querySelector(".reflib-ib-tagin");
        const v = inp ? inp.value.trim() : "";
        if (!v) { toast(lang() === "es" ? "Escribe una etiqueta" : "Type a tag", "error"); return; }
        const add = v.split(/[,;]/).map(x => x.trim()).filter(Boolean);
        inp.value = "";
        sendIlib(Object.assign({ action: "tag", add }, ilib.sel.payload())).then(r => { ilibApply(r); selChanged(); }).catch(() => {});
    }
    function doAdd() {
        const sel = ilib.root.querySelector(".reflib-ib-target");
        if (!sel) return;
        const req = Object.assign({ action: "add" }, ilib.sel.payload());
        if (sel.value === "__new") req.new_name = (ilib.root.querySelector(".reflib-ib-newname") || {}).value || "";
        else req.collection_id = sel.value;
        ilib.addTarget = sel.value;
        sendIlib(req).then(r => { if (r && r.ok !== false) { ilib.addOpen = false; if (r.collection_id) ilib.addTarget = r.collection_id; } ilibApply(r); selChanged(); }).catch(() => {});
    }
    // Reference Images is "available" when the generator bar under it isn't hidden by WanGP (Gradio's "hidden" class /
    // display:none on an ancestor). Inactive tabs don't count as hidden, so this also works from the manager tab.
    function refsAvailable() {
        const bar = document.getElementById("reflib_bar_generate");
        if (!bar) return false;
        for (let el = bar; el && el !== document.body; el = el.parentElement) {
            if (el.classList.contains("tabitem") || el.getAttribute("role") === "tabpanel") break;
            if (el.classList.contains("hidden") || el.hidden || getComputedStyle(el).display === "none") return false;
        }
        return true;
    }
    function sendToRefs() {
        if (!ilib.sel.size) return;
        if (!refsAvailable()) { toast(it("refs_hidden"), "error"); return; }
        sendBridge(Object.assign({ action: "apply_images", mode: "append", target: "generate:image_refs" }, ilib.sel.payload())).then(r => {
            if (r && r.ok !== false && localStorage.getItem("reflib_ib_close_after") === "1") closeBrowser();
        }).catch(e => toast(t("error", { e: (e && e.message) || e }), "error"));
    }
    // Folder picker ("Browse…"): served by the WanGP server, read-only, one folder level at a time.
    function pickerGo(path) {
        ilib.picker = Object.assign(ilib.picker || {}, { loading: true, want: path });
        renderPicker();
        sendIlib({ action: "browse", path }).then(r => {
            if (!ilib.picker) return;
            if (r && r.ok !== false && r.browse) ilib.picker = { data: r.browse, loading: false };
            else ilib.picker.loading = false;   // error toast comes from handleToast; keep the previous listing
            renderPicker();
        }).catch(() => { if (ilib.picker) { ilib.picker.loading = false; renderPicker(); } });
    }
    function renderPicker() {
        const box = ilib.root && ilib.root.querySelector(".reflib-ib-picker");
        if (!box) return;
        const pk = ilib.picker;
        box.hidden = !(pk && ilib.faddOpen);
        if (box.hidden) { box.innerHTML = ""; return; }
        const d = pk.data;
        const scName = s => ({ home: it("sc_home"), pictures: it("sc_pictures"), outputs: it("sc_outputs") }[s.kind] || s.name);
        let body;
        if (!d) body = `<div class="reflib-ib-muted">${esc(it("pick_loading"))}</div>`;
        else if (!d.path) {
            body = `<div class="reflib-ib-pk-sec">${esc(it("drives"))}</div><div class="reflib-ib-pk-list">${d.drives.map(x => `<div class="reflib-ib-pk-row" data-act="pgo" data-path="${esc(x.path)}"><span class="reflib-ib-ticon">${FOLDER_SVG}</span>${esc(x.name)}</div>`).join("")}</div>`
                + (d.shortcuts.length ? `<div class="reflib-ib-pk-sec">★</div><div class="reflib-ib-pk-list">${d.shortcuts.map(x => `<div class="reflib-ib-pk-row" data-act="pgo" data-path="${esc(x.path)}" title="${esc(x.path)}"><span class="reflib-ib-ticon">${FOLDER_SVG}</span><b>${esc(scName(x))}</b><span class="reflib-ib-muted">${esc(x.path)}</span></div>`).join("")}</div>` : "");
        } else {
            const crumbs = `<button type="button" data-act="pgo" data-path="">${esc(it("pick_roots"))}</button>` + d.crumbs.map(c => `<span>›</span><button type="button" data-act="pgo" data-path="${esc(c.path)}">${esc(c.name)}</button>`).join("");
            body = `<div class="reflib-ib-crumbs reflib-ib-pk-crumbs"><button type="button" class="reflib-ib-up" data-act="pgo" data-path="${esc(d.parent || "")}" title="${esc(it("up"))}">↑</button>${crumbs}</div>
                <div class="reflib-ib-pk-list">${d.dirs.length ? d.dirs.map(x => `<div class="reflib-ib-pk-row" data-act="pgo" data-path="${esc(x.path)}"><span class="reflib-ib-ticon">${FOLDER_SVG}</span>${esc(x.name)}</div>`).join("") : `<div class="reflib-ib-muted">${esc(it("pick_nodirs"))}</div>`}</div>
                <div class="reflib-ib-pk-foot"><span class="reflib-ib-muted reflib-ib-pk-count">${esc(it(d.images_more ? "pick_images_more" : "pick_images", { n: d.images }))}</span><span class="reflib-ib-spacer"></span>
                <button type="button" class="reflib-ib-btn reflib-ib-primary" data-act="ppick">${esc(it("pick_this"))}</button></div>`;
        }
        box.innerHTML = `<div class="reflib-ib-pk-head"><b>${esc(it("browse_title"))}</b>${pk.loading && d ? `<span class="reflib-ib-muted">${esc(it("pick_loading"))}</span>` : ""}<span class="reflib-ib-spacer"></span><button type="button" class="reflib-ib-x" data-act="pclose" title="${esc(it("close"))}">×</button></div>${body}`;
    }
    function addFolder() {
        const p = ilib.root.querySelector(".reflib-ib-fpath-in");
        const rec = ilib.root.querySelector(".reflib-ib-frec-in");
        if (!p || !p.value.trim()) return;
        const path = p.value.trim();
        sendIlib({ action: "folder_add", path, recursive: !!(rec && rec.checked) }).then(r => {
            if (r && r.ok !== false) {
                p.value = ""; ilib.faddOpen = false;
                if (r.folder_id) { ilib.f.node = { fid: r.folder_id, rel: "" }; ilib.f.recent = false; ilib.f.used = false; ilib.expanded.add(r.folder_id + "|"); }
                pollScan(true);
            }
            ilibApply(r);
        }).catch(() => {});
    }
    function onChange(e) {
        const el = e.target;
        if (el.matches('[data-act="atadd"]')) {
            const want = el.value.trim(); if (!want) return;
            const n = ilib.at.tax.list.find(x => x.k === "t" && (taxPath(x.id) === want || tlabel(x.id) === want || x.es === want || x.en === want));
            if (!n) { toast(it("ut_unknown"), "warn"); return; }
            const h = ilib.preview;
            sendIlib({ action: "at_edit", hash: h, tag: n.id, op: "accept" }).then(r => { if (r && r.ok) { ilib.at.img = r.img; const host = ilib.root.querySelector(".reflib-ib-autohost"); if (host) host.innerHTML = renderAutoPanel(h); loadFacets(true); toast(it("ut_added"), "ok"); } }).catch(() => {});
            return;
        }
        if (el.matches('[data-act="atrange"]')) {
            const k = el.dataset.k, i = +el.dataset.i;
            const cur = ilib.f.ranges[k] || [-1e9, 1e9];
            cur[i] = el.value === "" ? (i ? 1e9 : -1e9) : Number(el.value);
            if (cur[0] <= -1e9 && cur[1] >= 1e9) delete ilib.f.ranges[k]; else ilib.f.ranges[k] = cur;
            newQuery();
            return;
        }
        if (el.matches(".reflib-ib-cb input")) {
            const card = el.closest(".reflib-ib-card");
            const h = card.dataset.hash, idx = +card.dataset.idx;
            if (ilib.cbShift && ilib.anchorIdx >= 0 && ilib.anchorIdx !== idx) { selectRange(ilib.anchorIdx, idx, true); }
            else { if (el.checked) ilib.sel.add(h); else ilib.sel.delete(h); selChanged(); }
            ilib.cbShift = false;
            ilib.anchorIdx = idx;
        } else if (el.matches(".reflib-ib-target")) {
            ilib.addTarget = el.value;
            const nn = ilib.root.querySelector(".reflib-ib-newname");
            if (nn) { nn.style.display = el.value === "__new" ? "" : "none"; if (el.value === "__new") nn.focus(); }
        } else if (el.matches(".reflib-ib-closeafter")) {
            localStorage.setItem("reflib_ib_close_after", el.checked ? "1" : "0");
        } else if (el.matches(".reflib-ib-subtoggle")) {
            ilib.f.sub = el.checked; newQuery();
        }
    }
    // 1.5.2 "Show in folder": only when the browser is on the WanGP PC (the server checks it too)
    const IS_LOCAL = ["localhost", "127.0.0.1", "[::1]", "::1"].includes(location.hostname) || /^127\./.test(location.hostname);
    function revealBtn(h, cls) {
        return `<button type="button" class="${cls}" data-act="reveal" data-hash="${esc(h)}" ${IS_LOCAL ? "" : "disabled"} title="${esc(it(IS_LOCAL ? "reveal_tip" : "reveal_remote"))}">📂 ${esc(it("reveal"))}</button>`;
    }
    function doReveal(h) {
        if (!IS_LOCAL || !h) return;
        sendIlib({ action: "reveal", hash: h }).then(r => { if (r && !r.ok) toast(r.error || "error", "warn"); }).catch(() => {});
    }
    // 1.5.3 "Localizar carpeta": open the folder tree down to the image's subfolder, filter to it (no subfolders),
    // scroll to the image and keep it selected; collection / pool images highlight their collection chip(s)
    function locateBtn(h, cls) {
        return `<button type="button" class="${cls}" data-act="locate" data-hash="${esc(h)}" title="${esc(it("locate_tip"))}">🧭 ${esc(it("locate"))}</button>`;
    }
    // 1.6.1 "Recortar": opens the Cropper plugin for a library image/video through its file API (contract:
    // window.cropper.fileApi >= 1 and window.cropper.cropFile({path, url, kind, name, source}) -> Promise of
    // {ok, path, width, height} | {ok:false, cancelled} | {ok:false, error}). Without it the button is disabled.
    function cropApi() { const c = window.cropper; return c && typeof c.cropFile === "function" && (+c.fileApi || 0) >= 1 ? c : null; }
    function cropBtn(h, cls, kind) {
        if (kind === "audio") return "";
        const ok = !!cropApi();
        return `<button type="button" class="${cls} reflib-ib-cropbtn" data-act="crop" data-hash="${esc(h)}" ${ok ? "" : "aria-disabled=\"true\" disabled"} title="${esc(it(ok ? "crop_tip" : "crop_na"))}">✂ ${esc(it("crop"))}</button>`;
    }
    async function doCrop(h) {
        const api = cropApi(); if (!api || !h) return;
        const src = await sendIlib({ action: "media_src", hash: h }).catch(() => null);
        if (!src || !src.ok) { toast(it("crop_fail", { e: (src && src.error) || "?" }), "error"); return; }
        if (src.kind === "audio") { toast(it("crop_audio"), "warn"); return; }
        if (ilib.lightbox) closeLightbox();
        let res;
        try { res = await api.cropFile({ path: src.path, url: src.url, kind: src.kind, name: src.name, source: "reference-library" }); }
        catch (e) { res = { ok: false, error: String(e && e.message || e) }; }
        if (!res || res.cancelled) return;
        if (res.busy) { toast(it("crop_busy"), "info"); return; }   // Cropper 1.5.0: an editor is already open
        if (!res.ok || !res.path) { toast(it("crop_fail", { e: res.error || "?" }), "error"); return; }
        const r = await sendIlib({ action: "crop_save", path: res.path, kind: src.kind, src: h }).catch(() => null);
        if (!r || !r.ok) { toast(it("crop_fail", { e: (r && r.error) || "?" }), "error"); return; }
        if (r.kind === "image") {
            toast(it("crop_saved_img", { c: r.collection_name || "" }), "ok");
            ilib.f.node = null; ilib.f.recent = false; ilib.f.used = false; ilib.f.none = false; ilib.f.kind = "";
            ilib.f.cols = new Set([r.collection_id]);
            if (ilib.f.q) { ilib.f.q = ""; const qi = ilib.root && ilib.root.querySelector(".reflib-ib-q"); if (qi) qi.value = ""; }
            newQuery(); if (r.hash) focusImage(r.hash);
        } else toast(it("crop_saved_vid"), "ok");
    }
    function locCrumbs(l) {
        const parts = l.rel ? l.rel.split("/") : [];
        let html = `<div class="reflib-ib-loc" title="${esc(l.root)}"><button type="button" data-act="loccrumb" data-fid="${esc(l.fid)}" data-rel="">${l.managed === "virtual" ? VICO : ""}${esc(l.managed ? folderLabel(l) : l.root_name)}</button>`;
        parts.forEach((p, k) => { html += `<span>›</span><button type="button" data-act="loccrumb" data-fid="${esc(l.fid)}" data-rel="${esc(parts.slice(0, k + 1).join("/"))}">${esc(p)}</button>`; });
        return html + `</div>`;
    }
    function locateTo(fid, rel, h) {
        const parts = rel ? rel.split("/") : [];
        for (let k = 0; k <= parts.length; k++) ilib.expanded.add(fid + "|" + parts.slice(0, k).join("/"));
        ilib.f.node = { fid, rel }; ilib.f.recent = false; ilib.f.used = false; ilib.f.sub = false;
        ilib.f.cols = new Set(); ilib.f.none = false;
        if (h && ilib.f.q) { ilib.f.q = ""; const qi = ilib.root.querySelector(".reflib-ib-q"); if (qi) qi.value = ""; }   // show it in its folder's context
        newQuery();
        if (h) focusImage(h);
    }
    function focusImage(h) {
        sendIlib({ action: "index_of", f: filterSnap(), hash: h }).then(r => {
            if (!r || !r.ok || r.index < 0) return;
            const idx = r.index;
            ilib.sel.clear(); ilib.sel.add(h); ilib.anchorIdx = idx; selChanged();
            const go = (tries) => {
                const lay = ilib.lay, main = ilib.root && ilib.root.querySelector(".reflib-ib-main");
                const row = lay && lay.rows.find(x => !x.head && idx >= x.start && idx < x.start + x.n);
                if (!row || !main) { if (tries > 0) setTimeout(() => go(tries - 1), 150); return; }
                const vg = main.querySelector(".reflib-ib-vgrid");
                main.scrollTop = Math.max(0, vg.offsetTop + row.y - main.clientHeight / 2 + lay.ch / 2);
                renderWindow();
                const mark = (t2) => {
                    const card = ilib.cards.get(idx);
                    if (!card) { if (t2 > 0) setTimeout(() => mark(t2 - 1), 150); return; }
                    card.classList.add("located"); setTimeout(() => card.classList.remove("located"), 2500);
                    showPreview(h, idx);
                };
                mark(30);
            };
            go(40);
        }).catch(() => {});
    }
    function doLocate(h) {
        if (!h) return;
        sendIlib({ action: "locate", hash: h }).then(r => {
            if (!r || !r.ok) return;
            if (r.folders && r.folders.length) { const l = r.folders[0]; locateTo(l.fid, l.rel, h); return; }
            const ids = (r.collections || []).map(c => c.id);
            ilib.root.querySelectorAll(".reflib-ib-chip.located").forEach(c => c.classList.remove("located"));
            const chips = [...ilib.root.querySelectorAll('.reflib-ib-chip[data-f="col"]')].filter(c => ids.includes(c.dataset.id));
            if (r.in_pool && !ids.length) { const n = ilib.root.querySelector('.reflib-ib-chip[data-f="none"]'); if (n) chips.push(n); }
            chips.forEach(c => { c.classList.add("located"); setTimeout(() => c.classList.remove("located"), 4000); });
            if (chips[0]) chips[0].scrollIntoView({ block: "nearest", inline: "nearest" });
            if (!chips.length) toast(it("locate_none"), "info");
        }).catch(() => {});
    }
    function closeCtx() { const m = ilib.root && ilib.root.querySelector(".reflib-ib-ctx"); if (m) m.remove(); }
    function openCtx(e, card) {
        closeCtx();
        const idx = +card.dataset.idx, h = card.dataset.hash;
        if (!ilib.sel.has(h)) { ilib.sel.clear(); ilib.sel.add(h); ilib.anchorIdx = idx; selChanged(); }
        showPreview(h, idx);
        const m = document.createElement("div");
        m.className = "reflib-ib-ctx";
        const cv = (ilib.q.items[idx] || {}).virtual;   // 1.6.6
        m.innerHTML = revealBtn(h, "reflib-ib-ctxitem") + locateBtn(h, "reflib-ib-ctxitem") + (cv ? vBtn("vedit", h, "reflib-ib-ctxitem", "✎ " + vct("edit"), vct("edit_tip"), cv.broken) + vBtn("vorig", cv.orig, "reflib-ib-ctxitem", vct("show_orig"), vct("show_orig"), cv.broken, true) : cropBtn(h, "reflib-ib-ctxitem", (ilib.q.items[idx] || {}).kind || "image"))
            + (cv && cv.broken ? "" : vBtn("vnew", h, "reflib-ib-ctxitem", vct("new"), vct("new_tip"), false, true)) + (((ilib.q.items[idx] || {}).kind) === "video" ? resizeBtn(h, "reflib-ib-ctxitem") : "") + `<button type="button" class="reflib-ib-ctxitem" data-act="ctxbig" data-idx="${idx}">🔍 ${esc(it("big_preview"))}</button>` + (viewPref().details ? "" : `<button type="button" class="reflib-ib-ctxitem" data-act="ctxdetails">☰ ${esc(it("ctx_details"))}</button>`);
        const modal = ilib.root.querySelector(".reflib-ib-modal"), r = modal.getBoundingClientRect();
        m.style.left = Math.min(e.clientX - r.left, r.width - 230) + "px"; m.style.top = Math.min(e.clientY - r.top, r.height - 90) + "px";
        modal.appendChild(m);
    }
    function showPreview(hh, idx) {
        ilib.preview = hh; ilib.pvItem = ilib.q.items[idx] || null;
        for (const c of ilib.cards.values()) c.classList.toggle("cur", c.dataset.hash === hh);
        renderPreview();
        if (!viewPref().details) return Promise.resolve();   // 1.5.9: a click only selects; details load when the panel is on
        return sendIlib({ action: "preview", hash: hh }).then(r => { if (r && r.image && ilib.preview === hh) { ilib.pvSrc = Object.assign({}, r.image, { hash: hh }); renderPreview(); } }).catch(() => {});
    }
    // 1.5.2 large preview (double-click): the full image over the browser; ←/→ step through the results, Esc / click closes
    // 1.5.9 full-screen viewer: fixed over the whole window; ←/→ previous/next in the filtered results, Esc closes,
    // "Ajustar" (fit) / "1:1" (actual size, scrollable), click on the image toggles them. Works without the details panel.
    function openLightbox(idx) {
        const it2 = ilib.q.items[idx]; if (!it2) return;
        let box = ilib.lightbox;
        if (!box) {
            box = document.createElement("div");
            box.className = "reflib-ib-lightbox fit"; box.setAttribute("role", "dialog"); box.setAttribute("aria-modal", "true");
            box.innerHTML = `<div class="reflib-ib-lbstage"><img alt=""></div>
                <div class="reflib-ib-lbbar"><button type="button" data-lb="prev">‹</button><span class="reflib-ib-lbpos"></span><button type="button" data-lb="next">›</button>
                  <span class="reflib-ib-lbsep"></span><button type="button" data-lb="fit"></button><button type="button" data-lb="one"></button><span class="reflib-ib-lbsep"></span><button type="button" data-lb="crop" class="reflib-ib-cropbtn"></button><button type="button" data-lb="resize" class="reflib-rs-btn"></button><button type="button" data-lb="vnew" class="reflib-vc-lbbtn"></button><button type="button" data-lb="vedit" class="reflib-vc-lbbtn"></button></div>
                <div class="reflib-ib-lbname"></div><button type="button" class="reflib-ib-lbclose">×</button>`;
            box.addEventListener("click", (e) => {
                const b = e.target.closest("[data-lb]");
                if (b) { e.stopPropagation(); const k = b.dataset.lb; if (k === "crop") { if (!b.disabled) doCrop((ilib.q.items[+box.dataset.idx] || {}).hash); return; }
                if (k === "vnew" || k === "vedit") { const hh = (ilib.q.items[+box.dataset.idx] || {}).hash; if (!b.disabled) { closeLightbox(); vOpen(hh, k === "vedit" ? "edit" : "new"); } return; }
                if (k === "resize") { const hh = (ilib.q.items[+box.dataset.idx] || {}).hash; const r0 = b.getBoundingClientRect(); closeLightbox(); openResizeMenu({ getBoundingClientRect: () => r0 }, { hash: hh }); return; } if (k === "prev" || k === "next") lightboxStep(k === "next" ? 1 : -1); else lightboxZoom(k === "one"); return; }
                if (e.target.classList.contains("reflib-ib-lbclose") || e.target === box || e.target.classList.contains("reflib-ib-lbstage")) { closeLightbox(); return; }
                if (e.target.tagName === "IMG") lightboxZoom(box.classList.contains("fit"));
            });
            box.addEventListener("dblclick", (e) => e.stopPropagation());
            document.body.appendChild(box);
            ilib.lightbox = box;
        }
        box.dataset.idx = idx;
        const img = box.querySelector("img");
        box.querySelector(".reflib-ib-lbname").textContent = it2.name || "";
        box.querySelector(".reflib-ib-lbpos").textContent = `${idx + 1} / ${ilib.q.total}`;
        box.querySelector('[data-lb="prev"]').title = it("lb_prev"); box.querySelector('[data-lb="next"]').title = it("lb_next");
        box.querySelector('[data-lb="prev"]').disabled = idx <= 0; box.querySelector('[data-lb="next"]').disabled = idx >= ilib.q.total - 1;
        const fb = box.querySelector('[data-lb="fit"]'), ob = box.querySelector('[data-lb="one"]');
        const cb = box.querySelector('[data-lb="crop"]'), cok = !!cropApi(), isAud = it2.kind === "audio";
        const rb = box.querySelector('[data-lb="resize"]'); rb.textContent = "⤡ " + rt("btn"); rb.title = rt("tip"); rb.hidden = it2.kind !== "video";
        cb.textContent = "✂ " + it("crop"); cb.hidden = isAud || !!it2.virtual; cb.disabled = !cok; cb.title = it(cok ? "crop_tip" : "crop_na");
        const vn = box.querySelector('[data-lb="vnew"]'), ve = box.querySelector('[data-lb="vedit"]'), vbr = !!(it2.virtual && it2.virtual.broken);   // 1.6.6
        vn.innerHTML = VICO + esc(vct("new")); vn.title = vct("new_tip"); vn.disabled = vbr;
        ve.textContent = "✎ " + vct("edit"); ve.title = vct("edit_tip"); ve.hidden = !it2.virtual; ve.disabled = vbr;
        fb.textContent = it("lb_fit"); fb.title = it("lb_fit_tip"); ob.textContent = it("lb_1to1"); ob.title = it("lb_1to1_tip");
        fb.classList.toggle("on", box.classList.contains("fit")); ob.classList.toggle("on", !box.classList.contains("fit"));
        const th = ilib.thumbs.get(it2.hash); img.src = th || ""; img.dataset.hash = it2.hash;
        // 1.6.0: videos and audio play in the viewer (audio over its waveform)
        const stage = box.querySelector(".reflib-ib-lbstage");
        stage.querySelectorAll(".reflib-ib-lbmedia").forEach(m => { try { m.pause(); } catch (e) {} m.remove(); });
        const mk = it2.kind || "image";
        box.dataset.kind = mk;
        img.hidden = mk === "video";
        if (mk !== "image") {
            stopAudio();
            mediaUrl(it2.hash).then(u => {
                if (!u || ilib.lightbox !== box || img.dataset.hash !== it2.hash) return;
                const m = document.createElement(mk === "video" ? "video" : "audio");
                m.className = "reflib-ib-lbmedia"; m.controls = true; m.autoplay = true; m.preload = "auto"; m.src = u;
                if (mk === "video") { m.playsInline = true; if (th) m.poster = th; }
                stage.appendChild(m); m.play().catch(() => {});
            });
        }
        showPreview(it2.hash, idx);
        sendIlib({ action: "preview", hash: it2.hash }).then(r => { if (ilib.lightbox === box && img.dataset.hash === it2.hash && r && r.image && r.image.src) img.src = r.image.src; }).catch(() => {});
    }
    function lightboxZoom(one) {
        const box = ilib.lightbox; if (!box) return;
        box.classList.toggle("fit", !one);
        box.querySelector('[data-lb="fit"]').classList.toggle("on", !one); box.querySelector('[data-lb="one"]').classList.toggle("on", !!one);
    }
    function lightboxStep(d) {
        const box = ilib.lightbox; if (!box) return;
        const i = +box.dataset.idx + d;
        if (i < 0 || i >= ilib.q.total) return;
        ensurePages(i, i);
        const go = () => { const it2 = ilib.q.items[i]; if (!it2) return false; ilib.sel.clear(); ilib.sel.add(it2.hash); selChanged(); ilib.anchorIdx = i; openLightbox(i); return true; };
        if (!go()) { let n = 0; const t = setInterval(() => { if (go() || ++n > 40 || ilib.lightbox !== box) clearInterval(t); }, 100); }
    }
    function closeLightbox(silent) {
        if (ilib.lightbox) { ilib.lightbox.querySelectorAll(".reflib-ib-lbmedia").forEach(m => { try { m.pause(); } catch (e) {} }); ilib.lightbox.remove(); ilib.lightbox = null; }
    }

    // ---- 1.6.0 media browser: type filter, durations, audio playback, video hover preview, WanGP audio/video targets
    const KINDS = ["image", "video", "audio"];
    const closeAfter = () => localStorage.getItem("reflib_ib_close_after") === "1";
    function fmtDur(sec) {
        const t = Math.max(0, +sec || 0);
        if (t < 60) return "0:" + String(Math.round(t)).padStart(2, "0");
        const r = Math.round(t), h = Math.floor(r / 3600), m = Math.floor((r % 3600) / 60), x = r % 60;
        return h ? `${h}:${String(m).padStart(2, "0")}:${String(x).padStart(2, "0")}` : `${m}:${String(x).padStart(2, "0")}`;
    }
    function renderKindBar() {
        const host = ilib.root && ilib.root.querySelector(".reflib-ib-kinds"); if (!host) return;
        const k = ilib.kinds || (ilib.data && ilib.data.kinds) || {}, cur = ilib.f.kind || "";
        const tot = KINDS.reduce((a, x) => a + (k[x] || 0), 0);
        host.setAttribute("aria-label", it("k_tip"));
        host.innerHTML = [["", it("k_all"), tot]].concat(KINDS.map(x => [x, it("k_" + x), k[x] || 0])).map(([v, l, n]) =>
            `<button type="button" class="reflib-ib-kbtn ${cur === v ? "on" : ""}" data-act="kind" data-v="${v}" aria-pressed="${cur === v}" title="${esc(l)} (${n})">${esc(l)} <i>${n}</i></button>`).join("");
    }
    const murl = new Map();
    function mediaUrl(h, tries = 0) {
        if (murl.has(h)) return Promise.resolve(murl.get(h));
        return sendIlib({ action: "media_url", hash: h }).then(r => {
            const u = r && r.ok ? r.url : null; if (u) murl.set(h, u);
            if (!u && r && r.rendering && tries < 90) return new Promise(res => setTimeout(res, 1500)).then(() => mediaUrl(h, tries + 1));   // 1.6.6 virtual copy
            return u;
        }).catch(() => null);
    }
    function stopAudio() {
        if (ilib.audio) { try { ilib.audio.pause(); } catch (e) {} ilib.audio = null; }
        const was = ilib.audioHash; ilib.audioHash = null;
        if (was) { const b = ilib.root && ilib.root.querySelector(`.reflib-ib-aplay[data-hash="${was}"]`); if (b) { b.classList.remove("on"); b.textContent = "▶"; b.title = it("play"); } }
    }
    function toggleAudio(h) {
        if (ilib.audioHash === h) { stopAudio(); return; }
        stopAudio();
        mediaUrl(h).then(u => {
            if (!u) return;
            const a = new Audio(u); a.preload = "auto"; ilib.audio = a; ilib.audioHash = h;
            a.addEventListener("ended", () => { if (ilib.audio === a) stopAudio(); });
            a.play().catch(() => {});
            const b = ilib.root && ilib.root.querySelector(`.reflib-ib-aplay[data-hash="${h}"]`); if (b) { b.classList.add("on"); b.textContent = "❚❚"; b.title = it("pause"); }
        });
    }
    function hoverWire(bg) {
        let timer = null, cur = null;
        const clear = () => { clearTimeout(timer); timer = null; if (cur) { const v = cur.querySelector(".reflib-ib-hvid"); if (v) { try { v.pause(); } catch (e) {} v.remove(); } cur = null; } };
        bg.addEventListener("mouseover", (e) => {
            const card = e.target.closest(".reflib-ib-card[data-kind='video']");
            if (card === cur) return;
            clear();
            if (!card || ilib.drag) return;
            cur = card;
            timer = setTimeout(() => {   // a short delay so sweeping across the grid starts nothing
                const h = card.dataset.hash;
                mediaUrl(h).then(u => {
                    if (!u || cur !== card) return;
                    const th = card.querySelector(".reflib-ib-thumb"); if (!th) return;
                    const v = document.createElement("video");
                    v.className = "reflib-ib-hvid"; v.muted = true; v.loop = true; v.playsInline = true; v.preload = "metadata"; v.src = u;
                    v.addEventListener("loadeddata", () => v.classList.add("on"));
                    th.appendChild(v); v.play().catch(() => {});
                });
            }, 450);
        });
        bg.addEventListener("mouseleave", clear);
        bg.addEventListener("mousedown", clear, true);
    }
    let durTimer = null, durTries = 0;
    function pollDurations() {   // durations are probed in the background (throttled); refresh the visible cards that wait
        clearTimeout(durTimer);
        if (!ilib.open) return;
        const want = [...(ilib.cards || new Map()).values()].map(c => c.dataset.hash).filter(h => { const x = ilib.q.items.find(i => i && i.hash === h); return x && x.kind && !x.dur; }).slice(0, 200);
        if (!want.length) { durTries = 0; durTimer = null; return; }
        if (++durTries > 60) { durTimer = null; return; }
        durTimer = setTimeout(() => (durTimer = null, sendIlib({ action: "media_dur", hashes: want }).then(r => {
            if (!r || !r.ok) return;
            let changed = false;
            for (const x of ilib.q.items) if (x && r.dur[x.hash]) { x.dur = r.dur[x.hash]; changed = true; const c = ilib.cards.get(x.hash) || [...ilib.cards.values()].find(cc => cc.dataset.hash === x.hash); const sp = c && c.querySelector(".reflib-ib-dur"); if (sp) { sp.textContent = fmtDur(x.dur); sp.title = it("pv_dur"); } }
            pollDurations();
        }).catch(() => pollDurations())), 1500);
    }
    function wanInput(cls) {   // a WanGP input the CURRENT model shows (hidden ones have no layout box)
        const el = document.querySelector("." + cls);
        if (!el || !el.offsetParent || getComputedStyle(el).display === "none") return null;
        const lab = el.querySelector('[data-testid="block-label"], label span, .label-wrap span');
        return { el, label: ((lab && lab.textContent) || "").trim() };
    }
    function audioTargets() {
        return ["audio_guide", "audio_guide2", "audio_guide3"].map(n => { const w = wanInput(`reflib-at-${n}-generate`); return w ? { to: n, label: w.label || n } : null; }).filter(Boolean);
    }
    function sendMediaTo(to) {
        const h = [...ilib.sel][0]; if (!h) return;
        sendBridge({ hash: h, to, target: "generate:history" }).then(r => {
            if (r && r.ok && (r.restored || []).length) { toast(it("sent_to", { what: to === "video_guide" ? it("to_vctl") : (audioTargets().find(a => a.to === to) || { label: to }).label }), "ok"); if (closeAfter()) closeBrowser(); }
            else toast((r && r.error) || "error", "error");
        }).catch(() => {});
    }
    // 1.5.9 view preferences (thumbnail size, details panel): plugin settings + localStorage fallback
    function viewPref() {
        const t = cfg.browser_thumb || "m";
        return { thumb: CARD_SIZES[t] ? t : "m", details: !!cfg.browser_details };
    }
    function setView(ch) {
        const prev = viewPref();
        if ("thumb" in ch && CARD_SIZES[ch.thumb]) cfg.browser_thumb = ch.thumb;
        if ("details" in ch) cfg.browser_details = !!ch.details;
        const now = viewPref();
        sendIlib(Object.assign({ action: "ui_pref" }, "thumb" in ch ? { browser_thumb: now.thumb } : {}, "details" in ch ? { browser_details: now.details } : {})).catch(() => {});
        if (now.details && !prev.details && ilib.preview) { const i = ilib.q.items.findIndex(x => x && x.hash === ilib.preview); showPreview(ilib.preview, i); }
        else renderPreview();
        render();
        if (now.thumb !== prev.thumb) requestAnimationFrame(() => renderGrid());
    }
    function selectAllMatching() {
        const q = ilib.q;
        ilib.sel.clear();
        ilib.sel.all = { f: filterSnap(), sig: q.sig, total: q.total, except: new Set() };
        selChanged();
    }
    function onClick(e) {
        if (e.target.closest(".reflib-ib-usedbar")) {   // 1.5.6 "Usadas como referencia" delete (selection / ranges)
            delMenuClick(e, "used", () => (ilib.sel.size || ilib.sel.all) ? ilib.sel.payload() : null, (r) => { if (r && r.ok && r.batch) { ilib.sel.clear(); selChanged(); } newQuery(); });
            return;
        }
        const el = e.target.closest("[data-f], [data-act], .reflib-ib-card");
        if (!el && ilib.data && !e.shiftKey && !e.ctrlKey && !e.metaKey && e.target.closest(".reflib-ib-main")
            && !e.target.closest(".reflib-ib-crumbs, .reflib-ib-fchips, .reflib-ib-dayhead, .reflib-ib-more")) {
            if (ilib.justDragged || Date.now() - (ilib.dragEndAt || 0) < 400) { ilib.justDragged = false; return; }   // the click that ends a marquee
            if (ilib.sel.size) { ilib.sel.clear(); ilib.addOpen = false; selChanged(); }   // 1.5.2: click on empty grid space
            return;
        }
        if (!el || !ilib.data) return;
        if (el.matches(".reflib-ib-cb, .reflib-ib-cb *") || e.target.closest(".reflib-ib-cb")) return;
        if (ilib.justDragged && el.classList.contains("reflib-ib-card")) { ilib.justDragged = false; return; }
        const f = ilib.f;
        if (el.dataset.f) {
            const kind = el.dataset.f;
            if (kind === "all") { f.cols.clear(); f.none = false; f.folders.clear(); }
            else if (kind === "none") f.none = !f.none;
            else if (kind === "col") f.cols.has(el.dataset.id) ? f.cols.delete(el.dataset.id) : f.cols.add(el.dataset.id);
            else if (kind === "folder") f.folders.has(el.dataset.id) ? f.folders.delete(el.dataset.id) : f.folders.add(el.dataset.id);
            else if (kind === "tag") f.tags.has(el.dataset.tag) ? f.tags.delete(el.dataset.tag) : f.tags.add(el.dataset.tag);
            newQuery();
            if (ilib.sel.size) selChanged();   // "Remove from <collection>" depends on the filter
            return;
        }
        const act = el.dataset.act;
        if (el.classList.contains("reflib-ib-card") && !act) {
            if (ilib.justDragged) { ilib.justDragged = false; return; }
            const hh = el.dataset.hash, idx = +el.dataset.idx;
            if (!hh) return;
            if (e.shiftKey && ilib.anchorIdx >= 0) { selectRange(ilib.anchorIdx, idx, e.ctrlKey || e.metaKey); return; }
            if (e.ctrlKey || e.metaKey) { ilib.sel.has(hh) ? ilib.sel.delete(hh) : ilib.sel.add(hh); ilib.anchorIdx = idx; selChanged(); return; }
            ilib.anchorIdx = idx;
            if (!ilib.sel.has(hh)) { ilib.sel.clear(); ilib.sel.add(hh); selChanged(); }   // 1.5.3: a click on an already-selected card keeps the selection (preview + anchor only)
            showPreview(hh, idx);
            return;
        }
        if (act === "reveal") { closeCtx(); doReveal(el.dataset.hash); return; }
        if (act === "locate") { closeCtx(); doLocate(el.dataset.hash); return; }
        if (act === "crop") { closeCtx(); if (!el.disabled) doCrop(el.dataset.hash); return; }
        if (act === "resize") { const r0 = el.getBoundingClientRect(); closeCtx(); openResizeMenu({ getBoundingClientRect: () => r0 }, { hash: el.dataset.hash }); return; }
        if (act === "vnew" || act === "vedit") { closeCtx(); if (!el.disabled) vOpen(el.dataset.hash, act === "vedit" ? "edit" : "new"); return; }
        if (act === "vorig") { closeCtx(); if (!el.disabled) vShowOriginal(el.dataset.hash); return; }
        if (act === "vshow") { vShowCopy(el.dataset.hash); return; }
        if (act === "loccrumb") { locateTo(el.dataset.fid, el.dataset.rel || "", ilib.preview); return; }
        if (act === "ctxbig") { closeCtx(); openLightbox(+el.dataset.idx); return; }
        if (act === "pvclose") { setView({ details: false }); }   // 1.5.9: × hides the details panel (same as the header toggle)
        if (act === "vsize") { setView({ thumb: el.dataset.v }); return; }
        if (act === "kind") { ilib.f.kind = el.dataset.v || ""; newQuery(); renderKindBar(); render(); return; }
        if (act === "aplay") { e.stopPropagation(); toggleAudio(el.dataset.hash); return; }
        if (act === "tovctl") { sendMediaTo("video_guide"); return; }
        if (act === "toaudio") { sendMediaTo(el.dataset.to); return; }
        if (act === "tovlib") { sendIlib(Object.assign({ action: "to_vlib" }, ilib.sel.payload())).then(r => { toast((r && r.message) || "error", r && r.ok ? "ok" : "error"); }).catch(() => {}); return; }
        if (act === "vdetails") { setView({ details: !viewPref().details }); return; }
        if (act === "ctxdetails") { closeCtx(); setView({ details: true }); return; }
        else if (act === "selall") selectAllMatching();
        else if (act === "selnone") { ilib.sel.clear(); ilib.addOpen = false; selChanged(); }
        else if (act === "tag") doTag();
        else if (act === "untag") sendIlib(Object.assign({ action: "tag", remove: [el.dataset.tag] }, ilib.sel.payload())).then(r => { ilibApply(r); selChanged(); }).catch(() => {});
        else if (act === "addopen") { ilib.addOpen = !ilib.addOpen; renderFooter(); }
        else if (act === "addgo") doAdd();
        else if (act === "torefs") sendToRefs();
        else if (act === "pause") {
            const paused = !(ilib.scan && ilib.scan.pause_set);
            sendIlib({ action: "pause_index", paused }).then(r => { if (r && r.scan) { ilib.scan = r.scan; renderProgress(); pollScan(false); } }).catch(() => {});
        }
        else if (act === "del") {
            if (!ilib.delArmed) {
                ilib.delArmed = true; renderFooter();
                clearTimeout(ilib.delTimer);
                ilib.delTimer = setTimeout(() => { ilib.delArmed = false; renderFooter(); }, 5000);
                return;
            }
            ilib.delArmed = false; clearTimeout(ilib.delTimer);
            const pl = ilib.sel.payload(), sel = { all: !!ilib.sel.all, hashes: pl.hashes };
            sendIlib(Object.assign({ action: "delete_all" }, pl)).then(r => { undoToast(r, sel); ilibApply(r); }).catch(() => {});
        }
        else if (act === "removefrom") {
            const pl = ilib.sel.payload(), sel = { all: !!ilib.sel.all, hashes: pl.hashes };
            sendIlib(Object.assign({ action: "remove_from", collection_id: el.dataset.cid }, pl)).then(r => { undoToast(r, sel); ilibApply(r); }).catch(() => {});
        }
        else if (act === "fadd") addFolder();
        else if (act === "faddcancel") { ilib.faddOpen = false; ilib.picker = null; render(); }
        else if (act === "fbrowse") { if (ilib.picker) { ilib.picker = null; renderPicker(); } else pickerGo(""); }
        else if (act === "pgo") pickerGo(el.dataset.path || "");
        else if (act === "pclose") { ilib.picker = null; renderPicker(); }
        else if (act === "ppick") {
            const p = ilib.picker && ilib.picker.data && ilib.picker.data.path;
            if (!p) return;
            const inp = ilib.root.querySelector(".reflib-ib-fpath-in");
            inp.value = p;
            ilib.picker = null; renderPicker();
            addFolder();
        }
        else if (act === "hist") histOpen();
        else if (act === "fullscreen") setFull(!ilib.root.classList.contains("reflib-ib-full"));
        else if (act === "node") {
            const key = el.dataset.key, [fid, ...relParts] = key.split("|"), rel = relParts.join("|");
            ilib.f.node = { fid, rel }; ilib.f.recent = false; ilib.f.used = false; ilib.expanded.add(key);
            newQuery();
        }
        else if (act && act.startsWith("at") && atClick(act, el)) { /* auto-tag */ }
        else if (act && act.startsWith("chip") && chipClick(act, el)) { /* filter chips */ }
        else if (act === "used") { ilib.f.used = true; ilib.f.recent = false; ilib.f.node = null; newQuery(); }
        else if (act === "usedclear") {
            const all = el.dataset.all === "1";
            if (!all && !ilib.sel.set.size && !ilib.sel.all) { toast(it("used_need_sel"), "info"); }
            else sendIlib(Object.assign({ action: "used_clear", all }, all ? {} : ilib.sel.payload())).then(r => { if (r && r.ok) { toast(it("used_cleared", { n: r.n })); if (!all) { ilib.sel.clear(); selChanged(); } newQuery(); } });
        }
        else if (act === "recent") { ilib.f.used = false; ilib.f.recent = true; ilib.f.node = null; ilib.recentPages = 1; newQuery(); }
        else if (act === "recentmore") { ilib.recentPages += 1; newQuery(true); }
        else if (act === "caret") {
            const key = el.dataset.key;
            ilib.expanded.has(key) ? ilib.expanded.delete(key) : ilib.expanded.add(key);
            const tree = ilib.root.querySelector(".reflib-ib-tree");
            if (tree) { const sc = tree.scrollTop; tree.outerHTML = renderTree(ilib.data); ilib.root.querySelector(".reflib-ib-tree").scrollTop = sc; }
        }
        else if (act === "crumb") {
            const fid = el.dataset.fid;
            ilib.f.node = fid ? { fid, rel: el.dataset.rel || "" } : null; ilib.f.recent = false; ilib.f.used = false; newQuery();
        }
        else if (act === "up") {
            const n = ilib.f.node;
            if (n) ilib.f.node = n.rel ? { fid: n.fid, rel: n.rel.split("/").slice(0, -1).join("/") } : null;
            newQuery();
        }
        else if (act === "frescan") sendIlib({ action: "folder_rescan", folder_id: el.dataset.fid }).then(r => { ilibApply(r); pollScan(true); }).catch(() => {});
        else if (act === "fremove") {
            if (!el.classList.contains("armed")) {
                el.classList.add("armed"); el.title = it("fremove_confirm");
                setTimeout(() => { if (el.isConnected) { el.classList.remove("armed"); el.title = it("fremove"); } }, 5000);
                return;
            }
            sendIlib({ action: "folder_remove", folder_id: el.dataset.fid }).then(ilibApply).catch(() => {});
        }
    }
    function inField(el) {
        return el && (el.tagName === "INPUT" && !/^(checkbox|radio|button)$/i.test(el.type) || el.tagName === "TEXTAREA" || el.tagName === "SELECT" || el.isContentEditable);
    }
    function onKey(e) {
        if (!ilib.open) return;
        if ((e.ctrlKey || e.metaKey) && (e.key === "a" || e.key === "A") && !inField(document.activeElement)) {
            e.preventDefault(); e.stopPropagation();
            selectAllMatching();   // 1.4.4: every matching image, not only the loaded ones
            return;
        }
        if (ilib.lightbox && (e.key === "ArrowRight" || e.key === "ArrowLeft")) {
            e.preventDefault(); e.stopPropagation();
            lightboxStep(e.key === "ArrowRight" ? 1 : -1);
            return;
        }
        if (ilib.lightbox && (e.key === "1" || e.key === "0")) { e.preventDefault(); e.stopPropagation(); lightboxZoom(e.key === "1"); return; }
        if (e.key !== "Escape") return;
        e.preventDefault(); e.stopPropagation();
        if (ilib.root.querySelector(".reflib-ib-ctx")) { closeCtx(); return; }
        if (ilib.lightbox) { closeLightbox(); return; }
        if (sug.list.length) { closeSug(); return; }
        if (ilib.drag) { cancelDrag(); return; }
        if (ilib.addOpen) { ilib.addOpen = false; renderFooter(); return; }
        if (ilib.picker) { ilib.picker = null; renderPicker(); return; }
        if (ilib.faddOpen) { ilib.faddOpen = false; render(); return; }
        if (ilib.sel.size) { ilib.sel.clear(); selChanged(); return; }   // 1st Esc clears, 2nd closes
        closeBrowser();
    }
    // ---- multi-select: Shift ranges (by position in the filtered list, fetched from the server when not loaded)
    // and rubber-band selection (by grid geometry, so it also covers cards scrolled out of the DOM) ----
    function shownList() { return loadedItems(); }
    function addIndices(idxs, done) {
        const q = ilib.q, missing = [];
        for (const k of idxs) { const it2 = q.items[k]; if (it2) ilib.sel.add(it2.hash); else missing.push(k); }
        if (!missing.length) { if (done) done(); return; }
        const want = new Set(missing), a = Math.min(...missing), b = Math.max(...missing), sig = q.sig;
        sendIlib({ action: "range", f: filterSnap(), start: a, end: b }).then(r => {
            if (!r || !r.hashes || ilib.q.sig !== sig) return;
            r.hashes.forEach((h, k) => { if (want.has(a + k)) ilib.sel.add(h); });
            if (done) done();
        }).catch(() => {});
    }
    function selectRange(fromIdx, toIdx, additive) {
        if (!additive) ilib.sel.clear();
        const a = Math.min(fromIdx, toIdx), b = Math.max(fromIdx, toIdx), idxs = [];
        for (let k = a; k <= b; k++) idxs.push(k);
        addIndices(idxs, selChanged);
        selChanged();
    }
    function paintSelection() {
        if (!ilib.root || !ilib.cards) return;
        for (const c of ilib.cards.values()) {
            if (!c.dataset.hash) continue;
            const on = ilib.sel.has(c.dataset.hash);
            c.classList.toggle("sel", on);
            const cb = c.querySelector(".reflib-ib-cb input");
            if (cb) cb.checked = on;
        }
        const cnt = ilib.root.querySelector(".reflib-ib-count");
        if (cnt) cnt.textContent = ilib.sel.size ? it("sel_n", { n: ilib.sel.size }) : countText();
    }
    function startDrag(e) {
        const main = ilib.root && ilib.root.querySelector(".reflib-ib-main");
        if (!main || e.button !== 0 || !main.contains(e.target)) return;
        if (e.target.closest(".reflib-ib-cb, button, input, select, textarea, a, .reflib-ib-crumbs")) return;
        const r = main.getBoundingClientRect();
        if (e.clientX > r.left + main.clientWidth) return;   // the scrollbar
        e.preventDefault();   // no text selection, no native image drag
        if (inField(document.activeElement)) document.activeElement.blur();   // so Ctrl+A then means "the grid", not the search text
        ilib.drag = { main, x0: e.clientX - r.left + main.scrollLeft, y0: e.clientY - r.top + main.scrollTop, cx: e.clientX, cy: e.clientY,
                      base: (e.ctrlKey || e.metaKey) ? ilib.sel.clone() : null, before: ilib.sel.clone(), moved: false, box: null, raf: 0, idxs: [] };
        document.addEventListener("mousemove", moveDrag, true);
        document.addEventListener("mouseup", endDrag, true);
    }
    function marqueeIndices(L, T, W, H) {
        const lay = ilib.lay, vg = ilib.root.querySelector(".reflib-ib-vgrid");
        if (!lay) return [];
        const off = vg.offsetTop, out = [];
        for (const r of lay.rows) {
            if (r.head) continue;
            const top = r.y + off;
            if (top > T + H || top + lay.ch < T) continue;
            for (let c = 0; c < r.n; c++) {
                const left = c * (lay.cw + GAP) + vg.offsetLeft;
                if (left < L + W && left + lay.cw > L) out.push(r.start + c);
            }
        }
        return out;
    }
    function updateMarquee() {
        const d = ilib.drag;
        if (!d) return;
        const main = d.main, r = main.getBoundingClientRect();
        const x1 = d.cx - r.left + main.scrollLeft, y1 = Math.max(0, Math.min(main.scrollHeight, d.cy - r.top + main.scrollTop));
        const L = Math.min(d.x0, x1), T = Math.min(d.y0, y1), W = Math.abs(x1 - d.x0), H = Math.abs(y1 - d.y0);
        if (!d.box) { d.box = document.createElement("div"); d.box.className = "reflib-ib-marquee"; main.appendChild(d.box); }
        Object.assign(d.box.style, { left: L + "px", top: T + "px", width: W + "px", height: H + "px" });
        d.idxs = marqueeIndices(L, T, W, H);
        const sel = d.base ? d.base.clone() : makeSel();
        for (const k of d.idxs) { const it2 = ilib.q.items[k]; if (it2) sel.add(it2.hash); }
        ilib.sel = sel;
        paintSelection();
    }
    function autoScroll() {
        const d = ilib.drag;
        if (!d) return;
        const r = d.main.getBoundingClientRect(), edge = 48;
        let dy = 0;
        if (d.cy < r.top + edge) dy = -Math.ceil((r.top + edge - d.cy) / 3);
        else if (d.cy > r.bottom - edge) dy = Math.ceil((d.cy - (r.bottom - edge)) / 3);
        if (dy) { d.main.scrollTop += Math.max(-40, Math.min(40, dy)); renderWindow(); updateMarquee(); }
        d.raf = requestAnimationFrame(autoScroll);
    }
    function moveDrag(e) {
        const d = ilib.drag;
        if (!d) return;
        d.cx = e.clientX; d.cy = e.clientY;
        if (!d.moved) {
            const r = d.main.getBoundingClientRect();
            if (Math.hypot(e.clientX - r.left + d.main.scrollLeft - d.x0, e.clientY - r.top + d.main.scrollTop - d.y0) < 6) return;
            d.moved = true;
            d.main.classList.add("marquee-on");
            d.raf = requestAnimationFrame(autoScroll);
        }
        e.preventDefault();
        updateMarquee();
    }
    function finishDrag(keep) {
        const d = ilib.drag;
        if (!d) return;
        document.removeEventListener("mousemove", moveDrag, true);
        document.removeEventListener("mouseup", endDrag, true);
        cancelAnimationFrame(d.raf);
        if (d.box) d.box.remove();
        d.main.classList.remove("marquee-on");
        ilib.drag = null;
        if (!d.moved) return false;
        if (!keep) ilib.sel = d.before;
        ilib.justDragged = true; ilib.dragEndAt = Date.now();
        setTimeout(() => { ilib.justDragged = false; }, 0);
        if (keep) addIndices(d.idxs, selChanged);   // cards the rectangle crossed before their page was loaded
        selChanged();
        return true;
    }
    function endDrag() { finishDrag(true); }
    function cancelDrag() { finishDrag(false); }
    document.addEventListener("keydown", onKey, true);
    function fullPref() {   // "Abrir siempre a pantalla completa": plugin settings only (1.5.7)
        return !!cfg.browser_fullscreen;
    }
    function setFull(on) {
        if (!ilib.root) return;
        ilib.root.classList.toggle("reflib-ib-full", !!on);
        render();
        setTimeout(() => window.dispatchEvent(new Event("resize")), 30);   // grid re-measures: more columns
    }
    function openBrowser(opts = {}) {
        if (!ilib.root) buildModal();
        ilib.root.classList.toggle("reflib-ib-full", fullPref());
        ilib.open = true;
        setTimeout(() => { pollAt(); loadFacets(true); }, 400);   // after the first page: never delays the shell
        ilib.preview = null; ilib.addOpen = false; ilib.delArmed = false; if (ilib.at) { ilib.at.setOpen = false; renderAtSettings(false); }   // 1.5.2: settings start closed, the gear always opens them
        if (opts.collection_id) { ilib.f.cols = new Set([opts.collection_id]); ilib.f.none = false; ilib.f.folders.clear(); }
        ilib.root.classList.add("open");
        document.documentElement.classList.add("reflib-ib-lock");
        // the shell shows at once (last known counts, if any); counts + tree + page 1 arrive in one small request
        const sig = JSON.stringify(filterSnap());
        if (sig !== ilib.q.sig) ilib.q = { sig, total: 0, items: [], groups: null, pages: new Set(), loading: new Set(), gen: ilib.q.gen + 1, ready: false };
        else { ilib.q.gen += 1; ilib.q.pages = new Set(); ilib.q.loading = new Set(); ilib.q.loading.add(0); }
        if (!ilib.q.ready) ilib.q.loading.add(0);
        render();
        setTimeout(() => ilib.root.querySelector(".reflib-ib-q").focus(), 50);
        const gen = ilib.q.gen;
        return sendIlib({ action: "open", f: filterSnap(), limit: PAGE, tz: tz() }).then(r => {
            if (!r || r.ok === false) return r;
            setMeta(r);
            if (r.page && ilib.q.sig === sig && ilib.q.gen === gen) applyPage(r.page, sig, gen);
            render();
            if (r.scan && (r.scan.running || r.scan.thumbs_pending || r.scan.pause_set)) pollScan(false);
            return r;
        }).catch(e => { toast(t("error", { e: e.message || e }), "error"); });
    }
    function closeBrowser() {
        if (!ilib.root) return;
        closeLightbox(); stopAudio();
        ilib.open = false;
        ilib.root.classList.remove("open");
        document.documentElement.classList.remove("reflib-ib-lock");
        const vg = ilib.root.querySelector(".reflib-ib-vgrid");
        if (vg) vg.innerHTML = "";   // free the cards (and their data URIs) while closed
        ilib.cards = new Map(); ilib.heads = new Map();
        reloadLists();
    }
    setInterval(() => { if (ilib.open && ilib.lang !== lang()) render(); }, 700);

    // ---- 1.5.6 delete menu + confirm + undo (Historial and Usadas como referencia) ----
    const DT = {
        en: { del_menu: "Delete…", del_sel: "Delete selected ({n})", r1h: "Last hour", r24h: "Last 24 h", r7d: "Last 7 days", rall: "Everything", rcustom: "Custom range…",
              from: "From", to: "To", apply: "Delete range", cancel: "Cancel", del: "Delete", none: "Nothing to delete in that range",
              c_hist: "Delete {n} history entries? Outputs and original files are never touched; only copies made by the history and no longer used are removed.",
              c_used: "Remove {n} images from \"Used as reference\"? The images themselves stay in the library.", undo: "Undo", need_sel: "Select entries first" },
        es: { del_menu: "Borrar…", del_sel: "Borrar seleccionadas ({n})", r1h: "Última hora", r24h: "Últimas 24 h", r7d: "Últimos 7 días", rall: "Todo", rcustom: "Rango de fechas…",
              from: "Desde", to: "Hasta", apply: "Borrar rango", cancel: "Cancelar", del: "Borrar", none: "No hay nada que borrar en ese rango",
              c_hist: "¿Borrar {n} entradas del historial? Nunca se tocan los vídeos generados ni los originales; solo se eliminan las copias hechas por el historial que ya nadie usa.",
              c_used: "¿Quitar {n} imágenes de \"Usadas como referencia\"? Las imágenes siguen en la librería.", undo: "Deshacer", need_sel: "Selecciona entradas primero" },
    };
    const dt = (k, p = {}) => String((DT[lang()] || DT.en)[k] || DT.en[k] || k).replace(/\{(\w+)\}/g, (_, n) => p[n] ?? "");
    function delMenuHTML(kind) {
        return `<span class="reflib-del-wrap" data-kind="${kind}"><button type="button" class="reflib-ib-btn reflib-ib-danger" data-dact="menu">${esc(dt("del_menu"))} ▾</button>
          <div class="reflib-del-menu" hidden>${["1h", "24h", "7d", "all"].map(r => `<button type="button" data-dact="range" data-range="${r}">${esc(dt("r" + r))}</button>`).join("")}
            <button type="button" data-dact="custom">${esc(dt("rcustom"))}</button>
            <div class="reflib-del-custom" hidden><label>${esc(dt("from"))} <input type="datetime-local" class="reflib-del-from"></label><label>${esc(dt("to"))} <input type="datetime-local" class="reflib-del-to"></label>
              <button type="button" class="reflib-ib-btn reflib-ib-danger" data-dact="crange">${esc(dt("apply"))}</button></div></div></span>`;
    }
    function confirmDlg(text, okLabel) {
        return new Promise(res => {
            const bg = document.createElement("div"); bg.className = "reflib-confirm-bg";
            bg.innerHTML = `<div class="reflib-confirm" role="alertdialog" aria-modal="true"><p></p><div><button type="button" class="reflib-ib-btn" data-c="0"></button><button type="button" class="reflib-ib-btn reflib-ib-danger" data-c="1"></button></div></div>`;
            bg.querySelector("p").textContent = text; bg.querySelector('[data-c="0"]').textContent = dt("cancel"); bg.querySelector('[data-c="1"]').textContent = okLabel || dt("del");
            const done = v => { bg.remove(); window.removeEventListener("keydown", key, true); res(v); };
            const key = e => { if (e.key === "Escape") { e.stopImmediatePropagation(); e.preventDefault(); done(false); } else if (e.key === "Enter") { e.preventDefault(); done(true); } };
            bg.addEventListener("click", e => { const b = e.target.closest("[data-c]"); if (b) done(b.dataset.c === "1"); else if (e.target === bg) done(false); });
            window.addEventListener("keydown", key, true);   // window capture runs before the modals' Esc handlers
            document.body.appendChild(bg); bg.querySelector('[data-c="1"]').focus();
        });
    }
    // kind: "hist" | "used"; scope: {ids} | {hashes|selection} | {range, from, to}
    async function doDelete(kind, scope, after) {
        const act = kind === "hist" ? "hist_del" : "used_del";
        const c = await sendIlib(Object.assign({ action: act, dry: true }, scope));
        const n = (c && c.n) || 0;
        if (!n) { toast(scope.range ? dt("none") : dt("need_sel"), "info"); return; }
        if (!(await confirmDlg(dt(kind === "hist" ? "c_hist" : "c_used", { n })))) return;
        const r = await sendIlib(Object.assign({ action: act }, scope));
        if (after) after(r);
        if (r && r.ok && r.batch) toast(r.message, "ok", [{ label: dt("undo"), onClick: () => sendIlib({ action: kind === "hist" ? "hist_undo_batch" : "used_undo", batch: r.batch }).then(u => { if (after) after(u); }) }], 10000);
    }
    function delMenuClick(ev, kind, selScope, after) {
        const el = ev.target.closest("[data-dact]"); if (!el) return false;
        if (el.dataset.dact === "sel") { const sc = selScope(); if (!sc) toast(dt("need_sel"), "info"); else doDelete(kind, sc, after); return true; }
        const wrap = el.closest(".reflib-del-wrap"), menu = wrap.querySelector(".reflib-del-menu");
        const a = el.dataset.dact;
        if (a === "menu") { menu.hidden = !menu.hidden; }
        else if (a === "custom") { wrap.querySelector(".reflib-del-custom").hidden = false; }
        else if (a === "range") { menu.hidden = true; doDelete(kind, { range: el.dataset.range }, after); }
        else if (a === "crange") {
            const f = wrap.querySelector(".reflib-del-from").value, t = wrap.querySelector(".reflib-del-to").value;
            menu.hidden = true;
            doDelete(kind, { range: "custom", from: f ? new Date(f).getTime() / 1000 : 0, to: t ? new Date(t).getTime() / 1000 : "" }, after);
        }
        else if (a === "sel") { const sc = selScope(); if (!sc) toast(dt("need_sel"), "info"); else doDelete(kind, sc, after); }
        return true;
    }
    // ---- 1.5.5 generation history ("Historial") ----
    const HT = {
        en: { title: "History", tip: "Generation history", search: "Search prompt, model or file…", empty: "No generations recorded yet. Generate a video in WanGP and it shows up here.",
              reuse_all: "Reuse all settings", seed_note: "seed stays random (-1)", reuse_all_tip: "Model, prompt, resolution, steps… (the seed stays random, -1) through WanGP's own settings loader, plus refs, control video and masks",
              reuse_refs: "Reuse references only", replace: "Replace current refs (default: append)", savecol: "Save refs as collection", del: "Delete", undo: "Undo",
              outputs: "Generated videos without history", outputs_tip: "From WanGP's output folder: settings come from the metadata embedded in the file",
              more: "Load more", missing: "output file missing", size: "{mb} MB stored", cap: "Size cap (MB, 0 = no cap)", enabled: "Record generations",
              no_loader: "WanGP's settings loader was not found on the page", loading: "Loading settings in WanGP…", restored: "Restored: {what}",
              refs: "Refs", start: "Start", end: "End", control: "Control", vmask: "Video mask", imask: "Image mask", guide: "Guide", source: "Source", aud1: "Audio 1", aud2: "Audio 2", aud3: "Audio 3", find: "History", nohist: "no history entry", noembed: "no embedded settings" },
        es: { title: "Historial", tip: "Historial de generaciones", search: "Buscar prompt, modelo o archivo…", empty: "Aún no hay generaciones. Genera un vídeo en WanGP y aparecerá aquí.",
              reuse_all: "Reutilizar todos los ajustes", seed_note: "semilla aleatoria (-1)", reuse_all_tip: "Modelo, prompt, resolución, pasos… (la semilla queda aleatoria, -1) con el cargador de ajustes de WanGP, más refs, vídeo de control y máscaras",
              reuse_refs: "Reutilizar solo referencias", replace: "Reemplazar las refs actuales (por defecto: añadir)", savecol: "Guardar refs como colección", del: "Borrar", undo: "Deshacer",
              outputs: "Vídeos generados sin historial", outputs_tip: "De la carpeta de salida de WanGP: los ajustes salen de los metadatos incrustados en el archivo",
              more: "Cargar más", missing: "falta el archivo de salida", size: "{mb} MB guardados", cap: "Tamaño máximo (MB, 0 = sin límite)", enabled: "Registrar generaciones",
              no_loader: "No se encontró el cargador de ajustes de WanGP en la página", loading: "Cargando ajustes en WanGP…", restored: "Restaurado: {what}",
              refs: "Refs", start: "Inicio", end: "Final", control: "Control", vmask: "Máscara vídeo", imask: "Máscara imagen", guide: "Guía", source: "Origen", aud1: "Audio 1", aud2: "Audio 2", aud3: "Audio 3", find: "Historial", nohist: "sin entrada en el historial", noembed: "sin ajustes incrustados" },
    };
    const ht = (k, p = {}) => String((HT[lang()] || HT.en)[k] || HT.en[k] || k).replace(/\{(\w+)\}/g, (_, n) => p[n] ?? "");
    const HFIELD = { image_refs: "refs", image_start: "start", image_end: "end", video_guide: "control", video_mask: "vmask", image_mask: "imask", image_guide: "guide", video_source: "source", audio_guide: "aud1", audio_guide2: "aud2", audio_guide3: "aud3" };
    const hist = { root: null, items: [], total: 0, q: "", timer: 0, outputs: [], replace: false, sel: new Set(), anchor: -1 };
    function histBuild() {
        const bg = document.createElement("div");
        bg.className = "reflib-hist-bg";
        bg.innerHTML = `<div class="reflib-hist-modal" role="dialog" aria-modal="true"><div class="reflib-hist-head"><h3></h3>
            <input type="search" class="reflib-hist-q" spellcheck="false"><label class="reflib-ib-check"><input type="checkbox" class="reflib-hist-rep"> <span class="reflib-hist-repl"></span></label>
            <button type="button" class="reflib-ib-x" data-hact="close">×</button></div>
            <div class="reflib-hist-cfg"></div><div class="reflib-hist-tools"></div><div class="reflib-hist-list"></div><div class="reflib-hist-outs"></div></div>`;
        document.body.appendChild(bg);
        bg.addEventListener("click", histClick);
        bg.addEventListener("mousedown", e => { if (e.target === bg) histClose(); });
        bg.querySelector(".reflib-hist-q").addEventListener("input", e => { hist.q = e.target.value; clearTimeout(hist.timer); hist.timer = setTimeout(() => histLoad(), 200); });
        bg.querySelector(".reflib-hist-rep").addEventListener("change", e => { hist.replace = e.target.checked; });
        bg.addEventListener("change", e => {
            const el = e.target;
            if (el.classList.contains("reflib-hist-cap") || el.classList.contains("reflib-hist-en"))
                sendIlib({ action: "hist_config", set: { cap_mb: +bg.querySelector(".reflib-hist-cap").value, enabled: bg.querySelector(".reflib-hist-en").checked } }).then(r => { if (r && r.ok) { hist.config = r.config; hist.size = r.size_mb; histRender(); } });
        });
        document.addEventListener("keydown", e => { if (e.key === "Escape" && hist.root && hist.root.classList.contains("open")) { e.stopPropagation(); histClose(); } }, true);
        hist.root = bg;
    }
    function histOpen() {
        if (!hist.root) histBuild();
        hist.root.classList.add("open");
        hist.items = []; histRender(); histLoad();
        sendIlib({ action: "hist_outputs" }).then(r => { hist.outputs = (r && r.outputs) || []; histRender(); }).catch(() => {});
        setTimeout(() => hist.root.querySelector(".reflib-hist-q").focus(), 50);
    }
    function histClose() { if (hist.root) hist.root.classList.remove("open"); }
    function histLoad(more) {
        return sendIlib({ action: "hist_list", q: hist.q, offset: more ? hist.items.length : 0, limit: 30 }).then(r => {
            if (!r || !r.ok) return;
            hist.items = more ? hist.items.concat(r.hist.items) : r.hist.items;
            const live = new Set(hist.items.map(x => x.id)); for (const id of [...hist.sel]) if (!live.has(id)) hist.sel.delete(id);
            hist.total = r.hist.total; hist.size = r.hist.size_mb; hist.config = r.config; hist.trash = r.hist.trash;
            histRender();
        });
    }
    function histRow(e) {
        const date = new Date(e.ts * 1000).toLocaleString(lang() === "es" ? "es-ES" : "en-GB");
        const k = e.key || {};
        const meta = [e.model_type, k.resolution, k.video_length ? k.video_length + "f" : "", k.num_inference_steps ? k.num_inference_steps + " steps" : "", k.seed !== undefined ? "seed " + k.seed : ""].filter(Boolean).join(" · ");
        const groups = Object.entries(e.media || {}).map(([f, xs]) => `<div class="reflib-hist-grp"><span>${esc(ht(HFIELD[f] || f))}</span>${xs.map(x => e.thumbs[x.h] ? `<img src="${e.thumbs[x.h]}" alt="" class="${x.kind === "video" ? "vid" : ""}">` : `<i class="reflib-hist-noimg">${x.kind === "video" ? "🎞" : x.kind === "audio" ? "♪" : "▣"}</i>`).join("")}</div>`).join("");
        const hasRefs = !!(e.media && e.media.image_refs);
        return `<div class="reflib-hist-row ${hist.sel.has(e.id) ? "sel" : ""}" data-eid="${esc(e.id)}" aria-selected="${hist.sel.has(e.id)}">
            <div class="reflib-hist-out">${e.poster_src ? `<img src="${e.poster_src}" alt="">` : `<i class="reflib-hist-noimg">🎞</i>`}</div>
            <div class="reflib-hist-main"><div class="reflib-hist-top"><b>${esc(date)}</b><span class="reflib-hist-meta">${esc(meta)}</span>${e.output_exists ? "" : `<span class="reflib-hist-miss">${esc(ht("missing"))}</span>`}</div>
              <div class="reflib-hist-prompt" title="${esc(e.prompt)}">${esc(e.prompt)}</div>
              <div class="reflib-hist-media">${groups}</div>
              <div class="reflib-hist-file" title="${esc(e.output.join("\n"))}">${esc(e.output.map(o => o.split(/[\\/]/).pop()).join(", "))}</div>
              <div class="reflib-hist-btns"><button type="button" class="reflib-ib-btn reflib-ib-primary" data-hact="all" title="${esc(ht("reuse_all_tip"))}">${esc(ht("reuse_all"))}</button>
                <button type="button" class="reflib-ib-btn" data-hact="refs" ${hasRefs ? "" : "disabled"}>${esc(ht("reuse_refs"))}</button>
                <button type="button" class="reflib-ib-btn" data-hact="savecol" ${hasRefs ? "" : "disabled"}>${esc(ht("savecol"))}</button>
                <button type="button" class="reflib-ib-btn reflib-ib-danger" data-hact="del">${esc(ht("del"))}</button></div></div></div>`;
    }
    function histRender() {
        const r = hist.root; if (!r) return;
        r.querySelector("h3").textContent = ht("title");
        r.querySelector(".reflib-hist-q").placeholder = ht("search");
        r.querySelector(".reflib-hist-repl").textContent = ht("replace");
        const c = hist.config || {};
        r.querySelector(".reflib-hist-cfg").innerHTML = `<label class="reflib-ib-check"><input type="checkbox" class="reflib-hist-en" ${c.enabled === false ? "" : "checked"}> ${esc(ht("enabled"))}</label>
            <label>${esc(ht("cap"))} <input type="number" min="0" step="256" class="reflib-hist-cap" value="${esc(c.cap_mb ?? 2048)}"></label><span>${esc(ht("size", { mb: hist.size ?? 0 }))}</span>`;
        r.querySelector(".reflib-hist-tools").innerHTML = `<button type="button" class="reflib-ib-btn reflib-ib-danger reflib-hist-delsel" data-dact="sel" ${hist.sel.size ? "" : "disabled"}>${esc(dt("del_sel", { n: hist.sel.size }))}</button>${delMenuHTML("hist")}`;
        r.querySelector(".reflib-hist-list").innerHTML = hist.items.length ? hist.items.map(histRow).join("") + (hist.items.length < hist.total ? `<button type="button" class="reflib-ib-btn" data-hact="more">${esc(ht("more"))}</button>` : "")
            : `<div class="reflib-hist-empty">${esc(ht("empty"))}</div>`;
        const outs = hist.outputs.filter(o => !o.eid);
        r.querySelector(".reflib-hist-outs").innerHTML = outs.length ? `<h4 title="${esc(ht("outputs_tip"))}">${esc(ht("outputs"))}</h4>` + outs.map(o => `<div class="reflib-hist-orow" data-path="${esc(o.path)}" data-url="${esc(o.url)}"><span title="${esc(o.path)}">${esc(o.name)}</span>
            <button type="button" class="reflib-ib-btn" data-hact="oall" title="${esc(ht("outputs_tip"))}">${esc(ht("reuse_all"))}</button></div>`).join("") : "";
    }
    // 1.6.3: WanGP 18.18 also gives the model's custom_guide gr.File the class "wangp-settings-upload" (and it comes
    // first in the page), so pick the real "Load Settings From Media File / Json / Zip" loader: it sits next to WanGP's
    // settings buttons (export / default / reset), is labelled "Load Settings", and accepts any file (no `accept`).
    function settingsInput() {
        const best = settingsLoaderCandidates()[0];
        return best && best.score > 0 ? best.input : null;
    }
    function settingsLoaderCandidates() {
        const out = [];
        document.querySelectorAll(".wangp-settings-upload").forEach((blk, i) => {
            const input = blk.querySelector("input[type=file]"); if (!input) return;
            const label = ((blk.querySelector('[data-testid="block-label"], label, .label-wrap') || {}).textContent || "").trim();
            let score = 0, near = false, el = blk;
            for (let k = 0; k < 4 && el && el.parentElement; k++) {   // WanGP's own settings buttons in the same column
                el = el.parentElement;
                // 1.6.4: only the block's own neighbourhood counts, never the page itself or a container of several uploads
                if (el === document.body || el === document.documentElement || el.tagName === "GRADIO-APP" || el.classList.contains("gradio-container")) break;
                if (el.querySelectorAll(".wangp-settings-upload").length > 1) break;
                if (el.querySelector(".wangp-settings-export, .wangp-settings-default, .wangp-reset-settings, .wangp-settings-include-media")) { near = true; break; }
            }
            if (near) score += 4;
            if (/load settings/i.test(label)) score += 3;
            if (/custom guide/i.test(label)) score -= 6;
            if (input.getAttribute("accept")) score -= 2;   // custom_guide restricts the file types, the loader does not
            // 1.6.5 hotfix: WanGP 18.18 builds a second, complete form in its hidden "Edit" tab (queue task editor,
            // #edit-tab-content) with its own identical loader. Loading there refreshes the invisible Edit form (Gradio
            // then warns about the output count) and the Generate form never changes. Never use it; prefer the loader
            // that is on screen and shares the tab panel with the output player (#gallery).
            const edit = !!blk.closest('#edit-tab-content, [id^="edit-tab"]') || inHiddenEditTab(blk);
            if (edit) score -= 20;
            if (score > 0) {   // only a block that already qualifies as a settings loader gets the location bonuses
                if (blk.getClientRects().length) score += 2;
                const tp = blk.closest('.tabitem, [role="tabpanel"]'), gal = document.getElementById("gallery");
                if (tp && gal && tp.contains(gal) && !gal.closest('#edit-tab-content')) score += 3;
            }
            out.push({ input, block: blk, label, score, i, edit });
        });
        return out.sort((a, b) => b.score - a.score || a.i - b.i);   // tie: the first one (the Generate form comes before the Edit form)
    }
    function inHiddenEditTab(blk) {   // fallback when WanGP renames #edit-tab-content: the Edit tab's panel is labelled "Edit"
        const tp = blk.closest('.tabitem, [role="tabpanel"]'); if (!tp) return false;
        const lab = tp.getAttribute("aria-labelledby"); const btn = lab && document.getElementById(lab);
        return !!(btn && /^\s*edit\s*$/i.test(btn.textContent || ""));
    }
    async function nativeLoad(file) {
        const input = settingsInput();
        if (!input) { toast(ht("no_loader"), "error"); return false; }
        const dt = new DataTransfer(); dt.items.add(file);
        input.files = dt.files;
        input.dispatchEvent(new Event("change", { bubbles: true }));
        toast(ht("loading") + " · " + ht("seed_note"), "info");
        forceRandomSeed();
        return true;
    }
    // 1.6.5: reusing settings NEVER copies the seed. The JSON we hand over already says seed -1; a generated video
    // handed over as a file still carries its seed in its metadata, and WanGP may re-render the form a few seconds
    // later (model switch), so the Generate form's Seed field is kept at -1 for a while after the load. It stops as
    // soon as you touch the Seed field yourself.
    // WanGP 18.18 has several "Seed (-1 for random)" sliders in the Generate form (generation seed in Advanced Mode >
    // "General", audio post-processing, Deepy) plus copies in the hidden Edit tab: take the generation one.
    function seedInput() {
        const li = settingsInput(); const panel = li && li.closest('.tabitem, [role="tabpanel"]'); if (!panel) return null;
        const found = [];
        for (const blk of panel.querySelectorAll(".block")) {
            if (blk.closest("#edit-tab-content")) continue;
            const lab = blk.querySelector('[data-testid="block-info"], label span, .label-wrap span, label');
            if (!lab || !/^\s*seed\b/i.test(lab.textContent || "")) continue;
            const num = blk.querySelector('input[type="number"]'); if (num) found.push(num);
        }
        const general = found.find(n => { const tab = n.closest(".tabitem"); const btn = tab && tab.id && document.querySelector(`button[role="tab"][aria-controls="${CSS.escape(tab.id)}"]`);
            return btn && /^\s*general\s*$/i.test(btn.textContent || ""); });
        return general || found[0] || null;
    }
    let seedGuard = 0;
    function forceRandomSeed(ms = 20000) {
        const run = ++seedGuard, t0 = Date.now(); let touched = false, hooked = null;
        const setter = Object.getOwnPropertyDescriptor(HTMLInputElement.prototype, "value").set;
        const tick = () => {
            if (run !== seedGuard || touched) return;
            const inp = seedInput();
            if (inp && inp !== hooked) { hooked = inp; inp.addEventListener("focus", () => { if (run === seedGuard) touched = true; }, { once: true }); }
            if (inp && document.activeElement !== inp && String(inp.value).trim() !== "-1") {
                setter.call(inp, "-1");
                inp.dispatchEvent(new Event("input", { bubbles: true }));
                inp.dispatchEvent(new Event("change", { bubbles: true }));
                const rng = inp.closest(".block").querySelector('input[type="range"]');
                if (rng) { setter.call(rng, "-1"); rng.dispatchEvent(new Event("input", { bubbles: true })); rng.dispatchEvent(new Event("change", { bubbles: true })); }
            }
            if (Date.now() - t0 < ms) setTimeout(tick, 300);
        };
        setTimeout(tick, 300);
    }
    async function reuseAll(eid, path, url) {
        let file = null;
        if (!eid && url) {   // a generated video without history: hand the file itself to WanGP (it also extracts embedded source images)
            try { const b = await (await fetch(url)).blob(); file = new File([b], path.split(/[\\/]/).pop(), { type: b.type || "video/mp4" }); } catch (_) { file = null; }
        }
        if (!file) {
            const r = await sendIlib(eid ? { action: "hist_settings", eid } : { action: "hist_settings", path });
            if (!r || !r.ok) { toast((r && r.error) || ht("noembed"), "error"); return; }
            file = new File([r.json], r.name || "settings.json", { type: "application/json" });
        }
        if (!(await nativeLoad(file))) return;
        histClose(); if (ilib.open) closeBrowser();
        if (!eid) return;
        let e = hist.items.find(x => x.id === eid);
        if (!e) { const g = await sendIlib({ action: "hist_get", eid }).catch(() => null); e = g && g.entry; }   // 1.5.7: from the player
        await new Promise(res => setTimeout(res, 3500));   // after WanGP's own form refresh / model switch
        const done = [];
        if (e && e.media && e.media.image_refs) {
            const r = await sendBridge({ action: "apply_history", eid, mode: "replace", target: "generate:image_refs" }).catch(() => null);
            if (r && r.ok) done.push(ht("refs"));
        }
        if (e && Object.keys(e.media || {}).some(f => f !== "image_refs")) {
            const r = await sendBridge({ eid, target: "generate:history" }).catch(() => null);
            for (const f of (r && r.restored) || []) done.push(ht(HFIELD[f] || f));
        }
        if (done.length) toast(ht("restored", { what: done.join(", ") }));
    }
    function histClick(ev) {
        if (delMenuClick(ev, "hist", () => hist.sel.size ? { ids: [...hist.sel] } : null, () => histLoad())) return;
        const el = ev.target.closest("[data-hact]");
        if (!el) {   // 1.5.6 row selection: click / Ctrl+click / Shift+click, like the browser
            const row = ev.target.closest(".reflib-hist-row"); if (!row || ev.target.closest("button,input,a")) return;
            const id = row.dataset.eid, idx = hist.items.findIndex(x => x.id === id);
            if (ev.shiftKey && hist.anchor >= 0) {
                if (!(ev.ctrlKey || ev.metaKey)) hist.sel.clear();
                const [a, b] = [Math.min(hist.anchor, idx), Math.max(hist.anchor, idx)];
                for (let k = a; k <= b; k++) hist.sel.add(hist.items[k].id);
            } else if (ev.ctrlKey || ev.metaKey) { hist.sel.has(id) ? hist.sel.delete(id) : hist.sel.add(id); hist.anchor = idx; }
            else { if (!(hist.sel.has(id) && hist.sel.size > 1)) { hist.sel.clear(); hist.sel.add(id); } hist.anchor = idx; }
            histRender(); return;
        }
        const act = el.dataset.hact, row = el.closest("[data-eid]"), eid = row && row.dataset.eid;
        if (act === "close") histClose();
        else if (act === "more") histLoad(true);
        else if (act === "all") reuseAll(eid);
        else if (act === "oall") { const o = el.closest("[data-path]"); reuseAll(null, o.dataset.path, o.dataset.url); }
        else if (act === "refs") sendBridge({ action: "apply_history", eid, mode: hist.replace ? "replace" : "append", target: "generate:image_refs" }).catch(() => {});
        else if (act === "savecol") sendIlib({ action: "hist_savecol", eid }).then(r => { if (r) { handleToast(r); reloadLists(); } });
        else if (act === "del") doDelete("hist", { ids: [eid] }, () => histLoad());
    }
    function histFindVideo(path) {   // bonus: any generated video -> its history entry, else WanGP's embedded settings
        return sendIlib({ action: "hist_find", path });
    }

    // ---- 1.5.7 reuse from WanGP's output player (#gallery): a small bar BELOW the player, never over the video
    // (Vidosser draws on the picture itself and owns the keyboard; this bar has no shortcuts and no overlay) ----
    const PVT = {
        en: { all: "Reuse settings", all_tip: "Reuse ALL settings of the video shown in the player (history entry, else the metadata embedded in the file, through WanGP's own loader). The seed is never copied: it stays random (-1)",
              refs: "References only", refs_tip: "Add the reference images of the video shown in the player to Reference Images", none: "No generated video selected in the player", label: "Reference Library" },
        es: { all: "Reutilizar ajustes", all_tip: "Reutiliza TODOS los ajustes del vídeo mostrado en el reproductor (entrada del historial o, si no hay, los metadatos incrustados en el archivo, con el cargador de WanGP). La semilla nunca se copia: queda aleatoria (-1)",
              refs: "Solo referencias", refs_tip: "Añade a Reference Images las imágenes de referencia del vídeo mostrado en el reproductor", none: "No hay ningún vídeo generado seleccionado en el reproductor", label: "Reference Library" },
    };
    const pvt = (k) => (PVT[lang()] || PVT.en)[k] || PVT.en[k];
    function playerSrc() {
        const g = document.getElementById("gallery"); if (!g) return "";
        const pv = g.querySelector(".preview video, .preview img, [class*='preview'] video, [class*='preview'] img");
        const sel = g.querySelector("button.selected video, button.selected img, .thumbnail-item.selected video, .thumbnail-item.selected img");
        const any = g.querySelector("video, img");
        for (const el of [pv, sel, any]) { const s = el && (el.currentSrc || el.src); if (s && /file=|\/file\//.test(s)) return s; }
        return "";
    }
    async function pvReuse(kind) {
        const url = playerSrc();
        if (!url) { toast(pvt("none"), "info"); return; }
        const r = await sendIlib({ action: "hist_find", url }).catch(() => null);
        if (!r || !r.ok || !r.path) { toast((r && r.error) || pvt("none"), "error"); return; }
        if (kind === "all") return reuseAll(r.eid || null, r.path, url);
        if (r.eid) return sendBridge({ action: "apply_history", eid: r.eid, mode: hist.replace ? "replace" : "append", target: "generate:image_refs" }).catch(() => {});
        return sendBridge({ action: "apply_video_refs", path: r.path, mode: "append", target: "generate:image_refs" }).catch(() => {});
    }
    function mountPlayerBar() {
        const g = document.getElementById("gallery");
        if (!g || !g.parentElement) return;
        let bar = g.parentElement.querySelector(":scope > .reflib-pvbar");
        if (!bar) {
            bar = document.createElement("div"); bar.className = "reflib-pvbar";
            bar.innerHTML = `<span class="reflib-pvbar-l"></span><button type="button" class="reflib-pvbtn" data-pv="all"></button><button type="button" class="reflib-pvbtn" data-pv="refs"></button>`;
            bar.addEventListener("click", e => { const b = e.target.closest("[data-pv]"); if (b) { e.preventDefault(); e.stopPropagation(); b.blur(); pvReuse(b.dataset.pv); } });
            bar.addEventListener("keydown", e => e.stopPropagation());   // never feed the player's shortcuts from our buttons
            g.insertAdjacentElement("afterend", bar);
        }
        const L = lang();
        if (bar.dataset.lang !== L) {
            bar.dataset.lang = L;
            bar.querySelector(".reflib-pvbar-l").textContent = pvt("label");
            const a = bar.querySelector('[data-pv="all"]'), b = bar.querySelector('[data-pv="refs"]');
            a.textContent = "↺ " + pvt("all"); a.title = pvt("all_tip"); b.textContent = pvt("refs"); b.title = pvt("refs_tip");
        }
        bar.classList.toggle("off", !playerSrc());
    }
    setInterval(mountPlayerBar, 800);


    // ================================================================ 1.6.2 video resize (ours; cropping is Cropper's)
    // Short-side presets; the server keeps the aspect ratio, makes the long side a multiple of 16, never upscales
    // without confirmation, encodes with NVENC when it works (else libx264 CRF 18), keeps the audio and never touches
    // the source. Result: "<name> (720p)" in the Video Library; from the Control Video bar it also replaces the input.
    const RT = {
        en: { btn: "Resize", tip: "Resize this video (480p / 720p / 1080p); the result goes to the Video Library", title: "Resize video",
              hint: "Short side · aspect ratio kept · sizes in multiples of 16 · the original is never changed",
              hint_ctl: "Replaces the Control Video with the resized copy and saves it to the Video Library",
              up_q: "This would upscale the video from {src} to {dst}. Upscaling adds no detail. Continue?", up_ok: "Upscale",
              prog: "Resizing “{name}” to {preset}", cancel: "Cancel", cancelled: "Resize cancelled",
              saved: "“{name}” ({w}×{h}) saved to the Video Library", replaced: "Control Video replaced with “{name}” ({w}×{h}), also saved to the Video Library",
              fail: "Resize failed: {e}", busy: "A resize is already running" },
        es: { btn: "Redimensionar", tip: "Redimensionar este vídeo (480p / 720p / 1080p); el resultado va a la Librería de vídeos", title: "Redimensionar vídeo",
              hint: "Lado corto · se mantiene la proporción · medidas múltiplo de 16 · el original no se modifica",
              hint_ctl: "Sustituye el vídeo de control por la copia redimensionada y la guarda en la Librería de vídeos",
              up_q: "Esto ampliaría el vídeo de {src} a {dst}. Ampliar no añade detalle. ¿Continuar?", up_ok: "Ampliar",
              prog: "Redimensionando «{name}» a {preset}", cancel: "Cancelar", cancelled: "Redimensionado cancelado",
              saved: "«{name}» ({w}×{h}) guardado en la Librería de vídeos", replaced: "Vídeo de control sustituido por «{name}» ({w}×{h}), también guardado en la Librería de vídeos",
              fail: "No se pudo redimensionar: {e}", busy: "Ya hay un redimensionado en marcha" },
    };
    const rt = (k, p = {}) => String((RT[lang()] || RT.en)[k] || RT.en[k] || k).replace(/\{(\w+)\}/g, (_, n) => p[n] ?? "");
    const RS_PRESETS = ["480p", "720p", "1080p"];
    let rsRunning = null;
    function resizeBtn(h, cls) {
        return `<button type="button" class="${cls} reflib-rs-btn" data-act="resize" data-hash="${esc(h)}" title="${esc(rt("tip"))}">⤡ ${esc(rt("btn"))}</button>`;
    }
    function closeResizeMenu() { const m = document.querySelector(".reflib-rs-menu"); if (m) { m.remove(); window.removeEventListener("keydown", rsKey, true); document.removeEventListener("mousedown", rsOut, true); } }
    function rsKey(e) { if (e.key === "Escape") { e.stopImmediatePropagation(); e.preventDefault(); closeResizeMenu(); } }
    function rsOut(e) { if (!e.target.closest(".reflib-rs-menu")) closeResizeMenu(); }
    // opts: {hash} (library video) or {tab} (current Control Video of that form)
    function openResizeMenu(anchor, opts) {
        closeResizeMenu();
        const m = document.createElement("div");
        m.className = "reflib-rs-menu"; m.setAttribute("role", "menu");
        m.innerHTML = `<div class="reflib-rs-title"></div><div class="reflib-rs-presets">${RS_PRESETS.map(p => `<button type="button" role="menuitem" data-rs="${p}">${p}</button>`).join("")}</div><div class="reflib-rs-hint"></div>`;
        m.querySelector(".reflib-rs-title").textContent = rt("title");
        m.querySelector(".reflib-rs-hint").textContent = opts.tab ? rt("hint") + ". " + rt("hint_ctl") + "." : rt("hint") + ".";
        m.addEventListener("click", e => { const b = e.target.closest("[data-rs]"); if (b) { closeResizeMenu(); runResize(opts, b.dataset.rs, false); } });
        document.body.appendChild(m);
        const r = (anchor && anchor.getBoundingClientRect) ? anchor.getBoundingClientRect() : { left: innerWidth / 2 - 130, bottom: innerHeight / 2, top: innerHeight / 2 };
        const mw = m.offsetWidth, mh = m.offsetHeight;
        m.style.left = Math.max(8, Math.min(innerWidth - mw - 8, r.left)) + "px";
        m.style.top = (r.bottom + mh + 8 < innerHeight ? r.bottom + 6 : Math.max(8, r.top - mh - 6)) + "px";
        window.addEventListener("keydown", rsKey, true); setTimeout(() => document.addEventListener("mousedown", rsOut, true), 0);
        const f = m.querySelector('[data-rs="720p"]'); if (f) f.focus();
    }
    const rsStart = (opts, preset, upscale) => opts.tab
        ? sendBridge({ target: `${opts.tab}:video_guide`, action: "resize_start", preset, upscale })
        : sendIlib({ action: "resize_start", hash: opts.hash, preset, upscale });
    async function runResize(opts, preset, upscale) {
        if (rsRunning) { toast(rt("busy"), "info"); return; }
        let r;
        try { r = await rsStart(opts, preset, upscale); } catch (e) { toast(rt("fail", { e: String(e && e.message || e) }), "error"); return; }
        if (!r) return;
        if (r.ok === false) { if (!opts.tab) toast(r.error || rt("fail", { e: "?" }), "error"); return; }   // bridge errors are toasted by bridgeResponse
        if (r.same) { if (!opts.tab) toast(r.toast, "info"); return; }
        if (r.need_confirm) {
            const go = await confirmDlg(rt("up_q", { src: r.src.join("×"), dst: r.dst.join("×") }), rt("up_ok"));
            if (go) runResize(opts, preset, true);
            return;
        }
        if (r.job) trackResize(opts, r, preset);
    }
    function trackResize(opts, r, preset) {
        const box = document.createElement("div");
        box.className = "reflib-rs-prog"; box.setAttribute("role", "status");
        box.innerHTML = `<div class="reflib-rs-ptext"></div><div class="reflib-rs-bar"><i></i></div><div class="reflib-rs-prow"><span class="reflib-rs-pct">0%</span><span class="reflib-rs-enc"></span><button type="button" class="reflib-rs-cancel"></button></div>`;
        box.querySelector(".reflib-rs-ptext").textContent = rt("prog", { name: r.name, preset }) + ` · ${r.dst.join("×")}`;
        const cb = box.querySelector(".reflib-rs-cancel"); cb.textContent = rt("cancel");
        cb.addEventListener("click", () => { cb.disabled = true; sendIlib({ action: "resize_cancel", job: r.job }).catch(() => {}); });
        document.body.appendChild(box);
        rsRunning = r.job;
        const end = () => { rsRunning = null; box.remove(); };
        const tick = async () => {
            let st = null;
            try { const s2 = await sendIlib({ action: "resize_status", job: r.job }); st = s2 && s2.job; } catch (e) {}
            if (!st) { setTimeout(tick, 800); return; }
            const pc = Math.round((st.progress || 0) * 100);
            box.querySelector(".reflib-rs-bar i").style.width = pc + "%"; box.querySelector(".reflib-rs-pct").textContent = pc + "%";
            if (st.encoder) box.querySelector(".reflib-rs-enc").textContent = st.encoder === "h264_nvenc" ? "NVENC" : "x264";
            if (st.state === "queued" || st.state === "running") { setTimeout(tick, 400); return; }
            end();
            if (st.state === "cancelled") { toast(rt("cancelled"), "info"); return; }
            if (st.state !== "done") { toast(rt("fail", { e: st.error || "?" }), "error"); return; }
            const res = st.result || {}, w = (st.dst_size || r.dst)[0], h = (st.dst_size || r.dst)[1];
            reloadVideos();
            if (opts.tab) {
                const a = await sendBridge({ target: `${opts.tab}:video_guide`, action: "resize_apply", job: r.job }).catch(() => null);
                if (a && a.ok) toast(rt("replaced", { name: res.name || r.name, w, h }), "ok");
                else toast(rt("saved", { name: res.name || r.name, w, h }), "ok");
            } else toast(rt("saved", { name: res.name || r.name, w, h }), "ok");
            emit("reflib:changed", { reason: "video-added", id: res.video_id || null, kind: "video" });
        };
        setTimeout(tick, 300);
    }
    // Control Video bar: a "Resize" button next to Load / Save / Manage
    function mountResizeButtons() {
        for (const tab of TABS) {
            const bar = document.getElementById("reflib_vbar_" + tab);
            if (!bar) continue;
            let b = bar.querySelector(".reflib-rs-vbtn");
            if (!b) {
                const host = bar.querySelector(".reflib-bar-row .reflib-btns") || bar.querySelector(".reflib-btns");
                if (!host) continue;
                const sib = document.getElementById("reflib_vbar_manage_" + tab) || host.querySelector("button");
                b = document.createElement("button"); b.type = "button";
                b.className = ((sib && sib.className) || "lg secondary").replace(/\breflib-ico-\S+/g, "") + " reflib-rs-vbtn";
                b.addEventListener("click", (e) => { e.preventDefault(); e.stopPropagation(); openResizeMenu(b, { tab }); });
                host.appendChild(b);
            }
            const lbl = "⤡ " + rt("btn"); if (b.textContent !== lbl) { b.textContent = lbl; b.title = rt("hint_ctl"); }
        }
    }
    setInterval(mountResizeButtons, 700);

    // ================================================================ 1.6.4 "📚 Guardar en librería" on WanGP inputs
    // Every WanGP video / audio input (tagged .reflib-savein by the plugin) gets a small button in its top toolbar,
    // after Media Editor's Crop / Resize and before Gradio's own buttons; shown only while the input has a value.
    // Gradio 5's trim renders the selection in the browser and uploads it as a NEW file ("video.mp4" / "audio.wav")
    // that becomes the value, so saving the current value saves the trimmed version. We remember the name the input
    // had before the trim so the copy is "<name> (recorte)", not "video".
    const SVT = {
        en: { btn: "Save to library", short: "Save", tip: "Save this input's current file (trimmed if you trimmed it) to the Reference Library",
              tip_a: "Save this audio (trimmed if you trimmed it) to “Saved audio” in the media browser",
              tip_v: "Save this video (trimmed if you trimmed it) to the Video Library",
              saved_a: "“{name}” ({d}) saved to “Saved audio”", saved_v: "“{name}” ({d}) saved to the Video Library",
              dup_a: "Already in “Saved audio”: “{name}”", dup_v: "Already in the Video Library: “{name}”",
              undone: "Removed “{name}” from the library", fail: "Could not save: {e}", busy: "Saving…", folder: "Saved audio",
              not_trimmed: "Gradio didn't actually trim this video (its FFmpeg was still loading), so the full video was saved. Wait a few seconds and trim again if you wanted a trimmed copy." },
        es: { btn: "Guardar en librería", short: "Guardar", tip: "Guardar el archivo actual de esta entrada (recortado si lo has recortado) en la Reference Library",
              tip_a: "Guardar este audio (recortado si lo has recortado) en «Audios guardados» del explorador de medios",
              tip_v: "Guardar este vídeo (recortado si lo has recortado) en la Librería de vídeos",
              saved_a: "«{name}» ({d}) guardado en «Audios guardados»", saved_v: "«{name}» ({d}) guardado en la Librería de vídeos",
              dup_a: "Ya está en «Audios guardados»: «{name}»", dup_v: "Ya está en la Librería de vídeos: «{name}»",
              undone: "«{name}» quitado de la librería", fail: "No se pudo guardar: {e}", busy: "Guardando…", folder: "Audios guardados",
              not_trimmed: "Gradio no llegó a recortar este vídeo (su FFmpeg aún se estaba cargando), así que se ha guardado completo. Espera unos segundos y vuelve a recortar si querías una copia recortada." },
    };
    const svt = (k, p = {}) => String((SVT[lang()] || SVT.en)[k] || SVT.en[k] || k).replace(/\{(\w+)\}/g, (_, n) => p[n] ?? "");
    const SV_AUDIO = /^(audio_guide\d?|audio_source|replace_voice_sample\d?)$/;
    const svField = (block) => { const m = /\breflib-si-(\w+?)-(generate|edit)\b/.exec(block.className || ""); return m ? { field: m[1], tab: m[2] } : null; };
    function svValueUrl(block, field) {
        if (SV_AUDIO.test(field)) {
            if (!block.querySelector(".waveform-container, .component-wrapper")) return "";
            const a = block.querySelector("a.download-link[href]"); const au = block.querySelector("audio");
            return (a && a.getAttribute("href")) || (au && (au.currentSrc || au.getAttribute("src"))) || "wave";
        }
        const v = block.querySelector("video");
        return (v && (v.currentSrc || v.getAttribute("src"))) || "";
    }
    function svNameOf(url) {
        let b = String(url || "").split(/[?#]/)[0].split("/").pop() || "";
        try { b = decodeURIComponent(b); } catch (e) {}
        return b.replace(/\.[A-Za-z0-9]{1,5}$/, "");
    }
    const svState = new WeakMap();   // block -> {url, orig, trimmed, pending}
    function svTrack(block, field) {
        const st = svState.get(block) || { url: "", orig: "", trimmed: false, pending: null };
        const url = svValueUrl(block, field);
        if (url !== st.url) {
            const base = svNameOf(url).toLowerCase();
            const isTrimUpload = base === "video" || base === "audio";
            if (st.pending && Date.now() - st.pending.ts < 180000 && url) {
                const pr = st.pending.range, was = st.trimmed && st.range;   // 1.6.6: in/out as fractions of the ORIGINAL
                st.range = pr ? (was ? { fs: was.fs + pr.fs * (was.fe - was.fs), fe: was.fs + pr.fe * (was.fe - was.fs) } : pr) : null;
                if (!st.trimmed) st.origUrl = st.pending.url;
                st.trimmed = true; st.orig = st.pending.name; st.dur0 = st.pending.dur || 0;
            }
            else if (isTrimUpload && st.trimmed && url) { /* a second trim of a trimmed value: keep the original name */ }
            else { st.trimmed = false; st.orig = svNameOf(url); st.origUrl = url; st.range = null; }
            st.pending = null; st.url = url;
            svState.set(block, st);
        }
        return st;
    }
    // Gradio's "Trim" apply button (text "Trim", not translated by Gradio) inside a tagged input
    document.addEventListener("click", (e) => {
        const b = e.target && e.target.closest && e.target.closest("button");
        if (!b || !/^\s*Trim\s*$/.test(b.textContent || "")) return;
        const block = b.closest(".reflib-savein"); const f = block && svField(block);
        if (!f) return;
        const st = svTrack(block, f.field);
        const vid = block.querySelector("video");   // duration before the trim: Gradio's video trim can silently return the original
        st.pending = { ts: Date.now(), name: st.trimmed ? st.orig : (st.orig || svNameOf(st.url)), dur: (vid && isFinite(vid.duration)) ? vid.duration : 0,
                       url: st.url, range: svTrimRange(block, SV_AUDIO.test(f.field)) };
    }, true);
    const svDur = (s) => { s = Math.max(0, Number(s) || 0); const m = Math.floor(s / 60), r = s - m * 60; return m ? `${m}:${r.toFixed(1).padStart(4, "0")}` : `${r.toFixed(1)} s`; };
    async function saveInput(block, btn) {
        const f = svField(block); if (!f || btn.dataset.busy) return null;
        const st = svTrack(block, f.field);
        const isAudio = SV_AUDIO.test(f.field);
        const vid = isAudio ? null : block.querySelector("video");
        const fake = !!(st.trimmed && vid && st.dur0 > 0 && isFinite(vid.duration) && Math.abs(vid.duration - st.dur0) < 0.05);
        btn.dataset.busy = "1"; btn.classList.add("busy");
        try {
            if (st.trimmed && !fake && st.range && st.origUrl && (st.range.fs > 0.0005 || st.range.fe < 0.9995)) {   // 1.6.6
                const pr = await sendBridge({ action: "save_input_probe", target: `${f.tab}:save_${f.field}`, orig: st.origUrl }).catch(() => null);
                if (pr && pr.ok && pr.orig) {
                    delete btn.dataset.busy; btn.classList.remove("busy");
                    const ch = await svChoice(btn, pr.orig.name);
                    if (!ch) return null;
                    btn.dataset.busy = "1"; btn.classList.add("busy");
                    if (ch === "virtual") return await svSaveVirtual(f, st, btn);
                }
            }
            const r = await sendBridge({ action: "save_input", target: `${f.tab}:save_${f.field}`, name: st.orig || "", trimmed: !!st.trimmed && !fake });
            if (!r || !r.ok) return r;
            const k = isAudio ? "a" : "v";
            const text = r.created ? svt("saved_" + k, { name: r.name, d: svDur(r.duration) }) : svt("dup_" + k, { name: r.name });
            const buttons = r.created ? [{ label: t("undo"), onClick: () => sendBridge({ action: "save_input_undo", target: `${f.tab}:save_${f.field}`, kind: r.kind, ref: r.kind === "video" ? r.video_id : r.path })
                .then(u => { if (u && u.ok) toast(svt("undone", { name: r.name }), "info"); }) }] : [];
            toast(text, r.created ? "ok" : "info", buttons, r.created ? 9000 : 4000);
            if (fake) toast(svt("not_trimmed"), "info", [], 12000);
            return Object.assign(r, { not_trimmed: fake });
        } catch (e) {
            toast(svt("fail", { e: (e && e.message) || e }), "error"); return null;
        } finally { delete btn.dataset.busy; btn.classList.remove("busy"); }
    }
    function mountSaveButtons() {
        for (const block of document.querySelectorAll(".reflib-savein")) {
            const f = svField(block); if (!f) continue;
            const st = svTrack(block, f.field);
            const bar = block.querySelector(".icon-button-wrapper");
            let b = block.querySelector(".reflib-sv-btn");
            if (!bar) { if (b) b.hidden = true; continue; }
            if (!b || b.parentElement !== bar) {
                if (b) b.remove();
                b = document.createElement("button"); b.type = "button"; b.className = "reflib-sv-btn";
                b.innerHTML = '<span class="reflib-sv-ico" aria-hidden="true">📚</span><span class="reflib-sv-lbl"></span>';
                b.addEventListener("click", (e) => { e.preventDefault(); e.stopPropagation(); saveInput(block, b); });
                const crp = [...bar.querySelectorAll(".crp-tool")].pop();   // after Media Editor's Crop / Resize
                if (crp) crp.after(b); else bar.prepend(b);
            }
            b.hidden = !st.url;
            const lbl = svt("btn"), tip = svt(SV_AUDIO.test(f.field) ? "tip_a" : "tip_v");
            const l = b.querySelector(".reflib-sv-lbl"); if (l.textContent !== lbl) l.textContent = lbl;
            if (b.title !== tip) { b.title = tip; b.setAttribute("aria-label", tip); }
            b.classList.toggle("narrow", block.getBoundingClientRect().width < 440);
        }
    }
    setInterval(mountSaveButtons, 700);
    // ================================================================ 1.6.6 virtual copies (Lightroom-like)
    // A virtual copy stores only params over ONE library original: image {rect}, video {rect?, start?, end?}, audio
    // {start, end}. The server renders it on demand (cache) whenever a real file is needed; the original is never touched.
    // Images use Cropper's rect mode when window.cropper.fileApi >= 2 (cropFile({mode:"rect", initialRect}) ->
    // {ok, rect:{x,y,w,h}, width, height}); otherwise (and for video frames) the built-in rect tool below.
    const VFOLDER = "__virtual";
    // two joined squares, drawn (the "⧉" character is missing from many fonts)
    var VICO = '<svg class="reflib-vc-ico" viewBox="0 0 16 16" width="1em" height="1em" aria-hidden="true" focusable="false"><rect x="1.25" y="4.75" width="9" height="9" rx="1.6" fill="none" stroke="currentColor" stroke-width="1.6"/><rect x="5.75" y="1.25" width="9" height="9" rx="1.6" fill="none" stroke="currentColor" stroke-width="1.6"/></svg>';
    const VCT = {
        en: { badge: "virtual", badge_tip: "Virtual copy: only the crop / in-out is stored, the original file is untouched", broken: "broken", broken_tip: "The original file of this virtual copy is missing",
              copies_tip: "{n} virtual cop(ies) of this file", folder: "Virtual copies", new: "New virtual copy", new_tip: "Stores only a crop (or in/out) pointing at this file: nothing is duplicated",
              edit: "Edit crop", edit_tip: "Change this virtual copy's crop / in-out (the original stays untouched)", show_orig: "Show original", orig: "Original:", copies: "Virtual copies ({n})", is_virtual: "Virtual copy",
              p_rect: "Crop {w}×{h} at {x}, {y}", p_inout: "In {a} · Out {b} ({d})", p_none: "No changes yet (same as the original)", rendering: "Preparing the preview…", render_fail: "Couldn't render: {e}",
              orig_missing: "Original file missing: {path}", orig_gone: "The original is no longer in the library", t_new: "New virtual copy of “{name}”", t_edit: "Edit “{name}”", save_new: "Create copy", save: "Save",
              cancel: "Cancel", reset: "Reset", aspect: "Aspect", free: "Free", original: "Original", rect_on: "Crop the frame", set_in: "Set in", set_out: "Set out", play: "Play selection", stop: "Stop",
              in_l: "In (s)", out_l: "Out (s)", len: "Length {d}", hint_img: "Drag to draw the crop, drag the edges or corners to adjust it. Enter saves, Esc cancels.",
              hint_av: "Drag the handles, or press I / O at the current time. Space plays the selection. Enter saves, Esc cancels.", show: "Show", cropper2: "Crop in Media Editor", cropper2_tip: "Draw the frame crop in Media Editor (rect only: nothing is rendered or written)",
              me_fail: "Media Editor could not open it ({e}): using the built-in crop tool",
              sv_file: "Save the trimmed file", sv_file_tip: "A new file with only the trimmed part", sv_virtual: "Virtual copy of “{name}”",
              sv_virtual_tip: "Duplicates nothing: remembers the in/out over the library original", sv_saved: "Virtual copy “{name}” ({d}) of “{orig}” created", sv_undone: "Virtual copy removed" },
        es: { badge: "virtual", badge_tip: "Copia virtual: solo se guarda el recorte / entrada-salida, el archivo original no se toca", broken: "rota", broken_tip: "Falta el archivo original de esta copia virtual",
              copies_tip: "{n} copia(s) virtual(es) de este archivo", folder: "Copias virtuales", new: "Nueva copia virtual", new_tip: "Guarda solo un recorte (o entrada/salida) que apunta a este archivo: no se duplica nada",
              edit: "Editar recorte", edit_tip: "Cambiar el recorte / entrada-salida de esta copia virtual (el original no se toca)", show_orig: "Mostrar original", orig: "Original:", copies: "Copias virtuales ({n})", is_virtual: "Copia virtual",
              p_rect: "Recorte {w}×{h} en {x}, {y}", p_inout: "Entrada {a} · Salida {b} ({d})", p_none: "Aún sin cambios (igual que el original)", rendering: "Preparando la vista previa…", render_fail: "No se pudo generar: {e}",
              orig_missing: "Falta el archivo original: {path}", orig_gone: "El original ya no está en la librería", t_new: "Nueva copia virtual de «{name}»", t_edit: "Editar «{name}»", save_new: "Crear copia", save: "Guardar",
              cancel: "Cancelar", reset: "Restablecer", aspect: "Proporción", free: "Libre", original: "Original", rect_on: "Recortar el encuadre", set_in: "Marcar entrada", set_out: "Marcar salida", play: "Reproducir selección", stop: "Parar",
              in_l: "Entrada (s)", out_l: "Salida (s)", len: "Duración {d}", hint_img: "Arrastra para dibujar el recorte y ajusta bordes o esquinas. Intro guarda, Esc cancela.",
              hint_av: "Arrastra los tiradores o pulsa I / O en el instante actual. Espacio reproduce la selección. Intro guarda, Esc cancela.", show: "Mostrar", cropper2: "Recortar en Media Editor", cropper2_tip: "Dibuja el recorte del encuadre en Media Editor (solo el rectángulo: no se genera ni se escribe nada)",
              me_fail: "Media Editor no pudo abrirlo ({e}): se usa la herramienta de recorte propia",
              sv_file: "Guardar el archivo recortado", sv_file_tip: "Un archivo nuevo con solo la parte recortada", sv_virtual: "Copia virtual de «{name}»",
              sv_virtual_tip: "No duplica nada: recuerda la entrada y salida sobre el original de la librería", sv_saved: "Copia virtual «{name}» ({d}) de «{orig}» creada", sv_undone: "Copia virtual quitada" },
    };
    const vct = (k, p = {}) => String((VCT[lang()] || VCT.en)[k] || VCT.en[k] || k).replace(/\{(\w+)\}/g, (_, n) => p[n] ?? "");
    const vTime = (s) => { s = Math.max(0, +s || 0); const m = Math.floor(s / 60), r = s - m * 60; return `${m}:${r.toFixed(2).padStart(5, "0")}`; };
    function vParams(p, kind) {   // one-line summary of a copy's params
        p = p || {}; const out = [];
        if (p.rect) out.push(vct("p_rect", { x: p.rect[0], y: p.rect[1], w: p.rect[2], h: p.rect[3] }));
        if (p.end != null) out.push(vct("p_inout", { a: vTime(p.start || 0), b: vTime(p.end), d: svDur(p.end - (p.start || 0)) }));
        return out.length ? out.join(" · ") : vct("p_none");
    }
    function cropApi2() { const c = window.cropper; return c && typeof c.cropFile === "function" && (+c.fileApi || 0) >= 2 ? c : null; }
    // Media Editor 1.7.0 rect mode (fileApi 2): renders nothing, returns { ok, mode:"rect", kind, rect:{x,y,w,h}, width, height,
    // sourceWidth, sourceHeight, preset }. Integers in SOURCE pixels, origin top-left; for images in the upright (EXIF-transposed)
    // frame, which is the frame our renderer crops (it applies exif_transpose first); video rects come snapped to even values.
    // Returns { rect:[x,y,w,h] } | { cancelled } | { busy } | { error }.
    async function vMeRect(api, src, kind, rect) {
        const W = +src.width || 0, H = +src.height || 0;
        const opts = { path: src.path, url: src.url, kind, name: src.name, source: "reference-library", mode: "rect" };
        if (rect && rect.length === 4) opts.initialRect = { x: rect[0], y: rect[1], w: rect[2], h: rect[3] };
        let res;
        try { res = await api.cropFile(opts); } catch (e) { res = { ok: false, error: String((e && e.message) || e) }; }
        if (!res || res.cancelled) return { cancelled: true };
        if (res.busy) return { busy: true };
        const r = res.ok && res.rect;
        if (!r || ![r.x, r.y, r.w, r.h].every(Number.isFinite) || r.w <= 0 || r.h <= 0) return { error: (res && (res.error || res.code)) || "no rect" };
        let x = r.x, y = r.y, w = r.w, h = r.h;
        const sw = +(res.sourceWidth || res.width) || W, sh = +(res.sourceHeight || res.height) || H;
        if (W && H && sw && sh && (Math.abs(sw - W) > 1 || Math.abs(sh - H) > 1)) {   // its frame differs from ours: scale
            const kx = W / sw, ky = H / sh; x *= kx; w *= kx; y *= ky; h *= ky;
        }
        x = Math.max(0, Math.round(x)); y = Math.max(0, Math.round(y));
        w = Math.round(Math.min(w, (W || x + w) - x)); h = Math.round(Math.min(h, (H || y + h) - y));
        if (kind === "video") { x -= x % 2; y -= y % 2; w -= w % 2; h -= h % 2; }
        return { rect: [x, y, w, h], preset: res.preset || "" };
    }
    function vBtn(act, h, cls, label, tip, dis, icon) {
        return `<button type="button" class="${cls}" data-act="${act}" data-hash="${esc(h)}" ${dis ? "disabled" : ""} title="${esc(tip || label)}">${icon ? VICO : ""}${esc(label)}</button>`;
    }
    function vShowOriginal(h) {   // "Mostrar original": its folder when it has one, else everything; selected + scrolled to
        if (!h) return;
        sendIlib({ action: "locate", hash: h }).then(r => {
            if (r && r.ok && r.folders && r.folders.length && r.folders[0].fid !== VFOLDER) { const l = r.folders[0]; locateTo(l.fid, l.rel, h); return; }
            const f = ilib.f;
            f.node = null; f.recent = false; f.used = false; f.cols = new Set(); f.none = false; f.kind = ""; f.tags.clear && f.tags.clear();
            if (f.q) { f.q = ""; const qi = ilib.root && ilib.root.querySelector(".reflib-ib-q"); if (qi) qi.value = ""; }
            newQuery(); renderKindBar(); focusImage(h);
        }).catch(() => {});
    }
    function vShowCopy(h) { if (h) locateTo(VFOLDER, "", h); }
    let vPollT = null;
    function vPollRender(h) {   // a virtual video / audio preview is rendered in the background: wait for it, then reload
        clearTimeout(vPollT);
        vPollT = setTimeout(() => {
            if (ilib.preview !== h) return;
            sendIlib({ action: "virt_status", hash: h }).then(r => {
                if (!r || ilib.preview !== h) return;
                if (r.state === "rendering") { vPollRender(h); return; }
                murl.delete(h);
                const i = ilib.q.items.findIndex(x => x && x.hash === h); showPreview(h, i);
            }).catch(() => {});
        }, 1200);
    }
    function vRefresh(h) { ilib.thumbs.delete(h); murl.delete(h); }
    async function vOpen(h, mode) {
        if (!h) return null;
        const src = await sendIlib({ action: "virt_src", hash: h }).catch(() => null);
        if (!src || !src.ok) return null;   // the error toast comes from handleToast
        const edit = mode === "edit" && src.virtual;
        let params = null;
        const api = src.kind === "image" ? cropApi2() : null;
        if (api) {   // images: Media Editor's rect mode (fileApi 2); video / audio use our editor (in/out + its "Recortar en Media Editor")
            if (ilib.lightbox) closeLightbox();
            const m = await vMeRect(api, src, "image", (src.params || {}).rect);
            if (m.cancelled) return null;
            if (m.busy) { toast(it("crop_busy"), "info"); return null; }
            if (m.rect) params = { rect: m.rect };
            else { toast(vct("me_fail", { e: m.error }), "info", [], 6000); params = await vEditor(src, edit, true); if (!params) return null; }   // fallback: built-in tool
        } else {
            params = await vEditor(src, edit);
            if (!params) return null;
        }
        const r = await sendIlib({ action: edit ? "virt_update" : "virt_create", hash: h, params }).catch(() => null);
        if (!r || !r.ok) return null;
        vRefresh(r.hash);
        if (edit) {
            toast(r.message, "ok", [], 4000);
            refreshData();
            if (ilib.preview === r.hash) { const i = ilib.q.items.findIndex(x => x && x.hash === r.hash); showPreview(r.hash, i); }
            const card = ilib.root && ilib.root.querySelector(`.reflib-ib-card[data-hash="${r.hash}"] .reflib-ib-thumb img`); if (card) card.remove();
            queueThumbs && queueThumbs([r.hash]);
        } else {
            toast(r.message, "ok", [{ label: vct("show"), onClick: () => vShowCopy(r.hash) },
                { label: it("undo"), onClick: () => sendIlib({ action: "delete_all", hashes: [r.hash] }).then(u => { ilibApply(u); }).catch(() => {}) }], 10000);
            vShowCopy(r.hash);
            refreshData();   // folder list / counts: the "⧉ Copias virtuales" pseudo folder may be new
        }
        return r;
    }
    // ---- the built-in editor: rect tool (images, video frames) + in/out timeline (video, audio) ----
    function vEditor(src, edit, noMe) {
        return new Promise((resolve) => {
            const kind = src.kind, P = src.params || {};
            const W = +src.width || 0, H = +src.height || 0;
            let D = +src.duration || 0;
            const st = { rect: P.rect ? { x: P.rect[0], y: P.rect[1], w: P.rect[2], h: P.rect[3] } : null, aspect: "free",
                         rectOn: kind === "image" || !!P.rect, tin: P.start != null ? +P.start : 0, tout: P.end != null ? +P.end : D, playSel: false };
            const bg = document.createElement("div"); bg.className = "reflib-vc-bg";
            const hasRect = kind !== "audio", hasTl = kind !== "image";
            const ASP = [["free", vct("free")], ["orig", vct("original")], ["1:1", "1:1"], ["4:3", "4:3"], ["3:4", "3:4"], ["16:9", "16:9"], ["9:16", "9:16"]];
            bg.innerHTML = `<div class="reflib-vc-dlg k-${kind}" role="dialog" aria-modal="true" aria-label="${esc(vct(edit ? "t_edit" : "t_new", { name: src.name }))}">
                <div class="reflib-vc-title">${VICO}${esc(vct(edit ? "t_edit" : "t_new", { name: src.name }))}</div>
                ${kind !== "audio" ? `<div class="reflib-vc-stage"><div class="reflib-vc-media">${kind === "image" ? `<img alt="" draggable="false">` : `<video playsinline preload="auto"></video>`}
                    <div class="reflib-vc-ov"><div class="reflib-vc-rect" hidden>${["n", "s", "e", "w", "nw", "ne", "sw", "se"].map(d => `<i data-h="${d}" class="h-${d}"></i>`).join("")}</div></div></div></div>` : `<audio preload="auto"></audio>`}
                <div class="reflib-vc-tools">${hasRect ? `${kind === "video" ? `<label class="reflib-vc-chk"><input type="checkbox" class="reflib-vc-recton" ${st.rectOn ? "checked" : ""}> ${esc(vct("rect_on"))}</label>` : ""}
                    <label class="reflib-vc-asp">${esc(vct("aspect"))} <select class="reflib-vc-aspect">${ASP.map(([v, l]) => `<option value="${v}">${esc(l)}</option>`).join("")}</select></label>
                    <span class="reflib-vc-read"></span>${kind === "video" && !noMe && cropApi2() ? `<button type="button" class="reflib-ib-btn reflib-vc-me" data-v="me" title="${esc(vct("cropper2_tip"))}">✂ ${esc(vct("cropper2"))}</button>` : ""}` : ""}</div>
                ${hasTl ? `<div class="reflib-vc-tl"><div class="reflib-vc-track ${kind === "audio" ? "wave" : ""}"><div class="reflib-vc-dim l"></div><div class="reflib-vc-dim r"></div><div class="reflib-vc-sel"></div><div class="reflib-vc-ph"></div>
                    <button type="button" class="reflib-vc-hd in" aria-label="${esc(vct("in_l"))}"></button><button type="button" class="reflib-vc-hd out" aria-label="${esc(vct("out_l"))}"></button></div>
                    <div class="reflib-vc-tlrow"><button type="button" class="reflib-ib-btn" data-v="in">⟦ ${esc(vct("set_in"))}</button>
                      <label>${esc(vct("in_l"))} <input type="number" class="reflib-vc-in" min="0" step="0.01"></label>
                      <button type="button" class="reflib-ib-btn reflib-vc-play" data-v="play">▶ ${esc(vct("play"))}</button>
                      <label>${esc(vct("out_l"))} <input type="number" class="reflib-vc-out" min="0" step="0.01"></label>
                      <button type="button" class="reflib-ib-btn" data-v="out">${esc(vct("set_out"))} ⟧</button><span class="reflib-vc-len"></span></div></div>` : ""}
                <div class="reflib-vc-hint">${esc(vct(kind === "image" ? "hint_img" : "hint_av"))}</div>
                <div class="reflib-vc-btns"><button type="button" class="reflib-ib-btn" data-v="reset">${esc(vct("reset"))}</button><span class="reflib-ib-spacer"></span>
                  <button type="button" class="reflib-ib-btn" data-v="cancel">${esc(vct("cancel"))}</button><button type="button" class="reflib-ib-btn reflib-ib-primary" data-v="save">${esc(vct(edit ? "save" : "save_new"))}</button></div></div>`;
            const q = (s) => bg.querySelector(s);
            const media = q(kind === "image" ? "img" : kind === "video" ? "video" : "audio");
            const ov = q(".reflib-vc-ov"), rectEl = q(".reflib-vc-rect"), read = q(".reflib-vc-read");
            // ---------- rect (source pixels) ----------
            const ratio = () => { const a = st.aspect; if (a === "free") return 0; if (a === "orig") return W / H; const [x, y] = a.split(":").map(Number); return x / y; };
            const box = () => media.getBoundingClientRect();
            const scale = () => { const b = box(); return b.width ? W / b.width : 1; };
            function clampRect(r) {
                let { x, y, w, h } = r;
                w = Math.max(8, Math.min(w, W)); h = Math.max(8, Math.min(h, H));
                x = Math.max(0, Math.min(x, W - w)); y = Math.max(0, Math.min(y, H - h));
                return { x: Math.round(x), y: Math.round(y), w: Math.round(w), h: Math.round(h) };
            }
            function fitAspect(r) {   // keep the centre, shrink to the ratio
                const k = ratio(); if (!k || !r) return r;
                let w = r.w, h = r.h;
                if (w / h > k) w = h * k; else h = w / k;
                return clampRect({ x: r.x + (r.w - w) / 2, y: r.y + (r.h - h) / 2, w, h });
            }
            function drawRect() {
                if (!rectEl) return;
                const on = hasRect && st.rectOn && W && H;
                ov.classList.toggle("off", !on);
                if (!on || !st.rect) { rectEl.hidden = true; if (read) read.textContent = on ? "" : `${W}×${H}`; return; }
                const s = scale(), r = st.rect;
                rectEl.hidden = false;
                Object.assign(rectEl.style, { left: r.x / s + "px", top: r.y / s + "px", width: r.w / s + "px", height: r.h / s + "px" });
                if (read) read.textContent = `${r.w}×${r.h} px · x ${r.x}, y ${r.y}`;
            }
            let drag = null;
            if (ov) {
                ov.addEventListener("pointerdown", (e) => {
                    if (!st.rectOn || e.button !== 0) return;
                    e.preventDefault(); ov.setPointerCapture(e.pointerId);
                    const b = box(), s = scale(), px = (e.clientX - b.left) * s, py = (e.clientY - b.top) * s;
                    const hd = e.target.dataset && e.target.dataset.h;
                    if (hd && st.rect) drag = { mode: hd, sx: px, sy: py, r0: Object.assign({}, st.rect) };
                    else if (st.rect && e.target === rectEl) drag = { mode: "move", sx: px, sy: py, r0: Object.assign({}, st.rect) };
                    else { drag = { mode: "se", sx: px, sy: py, r0: { x: px, y: py, w: 0, h: 0 }, fresh: true }; }
                });
                ov.addEventListener("pointermove", (e) => {
                    if (!drag) return;
                    const b = box(), s = scale();
                    const px = Math.max(0, Math.min(W, (e.clientX - b.left) * s)), py = Math.max(0, Math.min(H, (e.clientY - b.top) * s));
                    const dx = px - drag.sx, dy = py - drag.sy, r0 = drag.r0;
                    if (drag.mode === "move") { st.rect = clampRect({ x: r0.x + dx, y: r0.y + dy, w: r0.w, h: r0.h }); drawRect(); return; }
                    let x1 = r0.x, y1 = r0.y, x2 = r0.x + r0.w, y2 = r0.y + r0.h;
                    if (drag.fresh) { x1 = Math.min(drag.sx, px); x2 = Math.max(drag.sx, px); y1 = Math.min(drag.sy, py); y2 = Math.max(drag.sy, py); }
                    else {
                        if (drag.mode.includes("w")) x1 = Math.min(r0.x + dx, x2 - 8); if (drag.mode.includes("e")) x2 = Math.max(x2 + dx, x1 + 8);
                        if (drag.mode.includes("n")) y1 = Math.min(r0.y + dy, y2 - 8); if (drag.mode.includes("s")) y2 = Math.max(y2 + dy, y1 + 8);
                    }
                    let w = x2 - x1, h = y2 - y1;
                    const k = ratio();
                    if (k && w > 0 && h > 0) {   // aspect: the dragged edge leads
                        if (drag.mode === "n" || drag.mode === "s") w = h * k; else h = w / k;
                        if (drag.fresh) { if (px < drag.sx) x1 = drag.sx - w; if (py < drag.sy) y1 = drag.sy - h; }
                        else { if (drag.mode.includes("w")) x1 = x2 - w; if (drag.mode.includes("n")) y1 = y2 - h; }
                    }
                    if (w >= 2 && h >= 2) { st.rect = clampRect({ x: x1, y: y1, w, h }); if (k) st.rect = fitAspect(st.rect); drawRect(); }
                });
                const end = () => { if (drag && drag.fresh && st.rect && (st.rect.w < 8 || st.rect.h < 8)) st.rect = null; drag = null; drawRect(); };
                ov.addEventListener("pointerup", end); ov.addEventListener("pointercancel", end);
            }
            const aspSel = q(".reflib-vc-aspect");
            if (aspSel) aspSel.addEventListener("change", () => { st.aspect = aspSel.value; if (st.rect) st.rect = fitAspect(st.rect); else if (st.aspect !== "free") st.rect = fitAspect({ x: 0, y: 0, w: W, h: H }); drawRect(); });
            const rOn = q(".reflib-vc-recton");
            if (rOn) rOn.addEventListener("change", () => { st.rectOn = rOn.checked; if (st.rectOn && !st.rect) st.rect = clampRect({ x: W * 0.1, y: H * 0.1, w: W * 0.8, h: H * 0.8 }); drawRect(); });
            // ---------- in / out ----------
            const track = q(".reflib-vc-track"), selEl = q(".reflib-vc-sel"), ph = q(".reflib-vc-ph"), hin = q(".reflib-vc-hd.in"), hout = q(".reflib-vc-hd.out");
            const iin = q(".reflib-vc-in"), iout = q(".reflib-vc-out"), lenEl = q(".reflib-vc-len"), playB = q(".reflib-vc-play");
            const dl = q(".reflib-vc-dim.l"), dr = q(".reflib-vc-dim.r");
            function drawTl() {
                if (!track || !D) return;
                st.tin = Math.max(0, Math.min(st.tin, D)); st.tout = Math.max(st.tin + 0.1, Math.min(st.tout, D));
                const a = st.tin / D * 100, b = st.tout / D * 100;
                hin.style.left = a + "%"; hout.style.left = b + "%"; selEl.style.left = a + "%"; selEl.style.width = (b - a) + "%";
                dl.style.width = a + "%"; dr.style.left = b + "%";
                if (document.activeElement !== iin) iin.value = st.tin.toFixed(2);
                if (document.activeElement !== iout) iout.value = st.tout.toFixed(2);
                iin.max = iout.max = D.toFixed(2);
                lenEl.textContent = vct("len", { d: svDur(st.tout - st.tin) });
            }
            function drawPh() { if (ph && D) ph.style.left = (Math.min(media.currentTime || 0, D) / D * 100) + "%"; }
            let tdrag = null;
            const tAt = (e) => { const b = track.getBoundingClientRect(); return Math.max(0, Math.min(1, (e.clientX - b.left) / b.width)) * D; };
            if (track) {
                track.addEventListener("pointerdown", (e) => {
                    if (e.button !== 0 || !D) return;
                    e.preventDefault(); track.setPointerCapture(e.pointerId);
                    tdrag = e.target === hin ? "in" : e.target === hout ? "out" : "seek";
                    if (tdrag === "seek") { media.currentTime = tAt(e); drawPh(); }
                });
                track.addEventListener("pointermove", (e) => {
                    if (!tdrag || tdrag === "seek") { if (tdrag === "seek") { media.currentTime = tAt(e); drawPh(); } return; }
                    const tt = tAt(e);
                    if (tdrag === "in") st.tin = Math.min(tt, st.tout - 0.1); else st.tout = Math.max(tt, st.tin + 0.1);
                    media.currentTime = tdrag === "in" ? st.tin : st.tout; drawTl(); drawPh();
                });
                const tend = () => { tdrag = null; };
                track.addEventListener("pointerup", tend); track.addEventListener("pointercancel", tend);
                for (const [hd, which] of [[hin, "in"], [hout, "out"]]) hd.addEventListener("keydown", (e) => {   // keyboard nudge: ←/→ 0.1 s (Shift 1 s)
                    if (e.key !== "ArrowLeft" && e.key !== "ArrowRight") return;
                    e.preventDefault(); e.stopPropagation();
                    const d = (e.key === "ArrowLeft" ? -1 : 1) * (e.shiftKey ? 1 : 0.1);
                    if (which === "in") st.tin = Math.min(st.tin + d, st.tout - 0.1); else st.tout = Math.max(st.tout + d, st.tin + 0.1);
                    drawTl();
                });
                iin.addEventListener("change", () => { st.tin = Math.min(+iin.value || 0, st.tout - 0.1); drawTl(); });
                iout.addEventListener("change", () => { st.tout = Math.max(+iout.value || 0, st.tin + 0.1); drawTl(); });
            }
            function togglePlay() {
                if (!media || kind === "image") return;
                if (!media.paused && st.playSel) { media.pause(); return; }
                st.playSel = true; media.currentTime = st.tin; media.play().catch(() => {});
            }
            if (media && kind !== "image") {
                media.addEventListener("timeupdate", () => { drawPh(); if (st.playSel && media.currentTime >= st.tout) { media.pause(); media.currentTime = st.tout; } });
                media.addEventListener("play", () => { if (playB) playB.textContent = "❚❚ " + vct("stop"); const loop = () => { drawPh(); if (!media.paused) requestAnimationFrame(loop); }; loop(); });
                media.addEventListener("pause", () => { st.playSel = false; if (playB) playB.textContent = "▶ " + vct("play"); });
                media.addEventListener("loadedmetadata", () => {
                    if (!D && isFinite(media.duration)) { D = media.duration; if (P.end == null) st.tout = D; }
                    drawTl(); drawRect();
                    if (P.start) media.currentTime = +P.start;
                });
            }
            // ---------- dialog ----------
            const done = (v) => { try { media && media.pause && media.pause(); } catch (e) {} window.removeEventListener("keydown", key, true); window.removeEventListener("resize", onRs); bg.remove(); resolve(v); };
            const result = () => {
                const out = {};
                if (hasRect && st.rectOn && st.rect) out.rect = [st.rect.x, st.rect.y, st.rect.w, st.rect.h];
                if (hasTl && D) { out.start = +st.tin.toFixed(3); out.end = +st.tout.toFixed(3); }
                return out;
            };
            const key = (e) => {
                if (e.key === "Escape") { e.stopImmediatePropagation(); e.preventDefault(); done(null); return; }
                const typing = e.target && e.target.tagName === "INPUT" && e.target.type === "number";
                if (e.key === "Enter" && !typing) { e.preventDefault(); e.stopImmediatePropagation(); done(result()); return; }
                if (typing || e.target.tagName === "SELECT") return;
                if (hasTl && (e.key === "i" || e.key === "I")) { e.preventDefault(); e.stopImmediatePropagation(); st.tin = Math.min(media.currentTime || 0, st.tout - 0.1); drawTl(); }
                else if (hasTl && (e.key === "o" || e.key === "O")) { e.preventDefault(); e.stopImmediatePropagation(); st.tout = Math.max(media.currentTime || 0, st.tin + 0.1); drawTl(); }
                else if (hasTl && e.key === " ") { e.preventDefault(); e.stopImmediatePropagation(); togglePlay(); }
            };
            const onRs = () => drawRect();
            bg.addEventListener("click", (e) => {
                const b = e.target.closest("[data-v]");
                if (!b) { if (e.target === bg) done(null); return; }
                const v = b.dataset.v;
                if (v === "cancel") done(null);
                else if (v === "save") done(result());
                else if (v === "reset") { st.rect = kind === "image" ? null : null; st.tin = 0; st.tout = D; if (rOn) { rOn.checked = false; st.rectOn = false; } drawRect(); drawTl(); }
                else if (v === "in") { st.tin = Math.min(media.currentTime || 0, st.tout - 0.1); drawTl(); }
                else if (v === "out") { st.tout = Math.max(media.currentTime || 0, st.tin + 0.1); drawTl(); }
                else if (v === "play") togglePlay();
                else if (v === "me") meCrop();
            });
            async function meCrop() {   // video frame crop in Media Editor's rect mode; our dialog steps aside meanwhile
                const api = cropApi2(); if (!api || bg.__meBusy) return;
                bg.__meBusy = true; try { media && media.pause && media.pause(); } catch (e) {}
                window.removeEventListener("keydown", key, true); bg.style.display = "none";
                const m = await vMeRect(api, src, "video", st.rectOn && st.rect ? [st.rect.x, st.rect.y, st.rect.w, st.rect.h] : null);
                bg.style.display = ""; window.addEventListener("keydown", key, true); bg.__meBusy = false;
                if (m.busy) toast(it("crop_busy"), "info");
                else if (m.error) toast(vct("me_fail", { e: m.error }), "info", [], 6000);
                if (!m.rect) return;
                const full = m.rect[0] === 0 && m.rect[1] === 0 && Math.abs(m.rect[2] - W) <= 1 && Math.abs(m.rect[3] - H) <= 1;
                st.rect = full ? null : { x: m.rect[0], y: m.rect[1], w: m.rect[2], h: m.rect[3] }; st.rectOn = !full;
                if (rOn) rOn.checked = st.rectOn;
                st.aspect = "free"; if (aspSel) aspSel.value = "free";
                drawRect();
            }
            bg.addEventListener("dblclick", (e) => e.stopPropagation());
            window.addEventListener("keydown", key, true); window.addEventListener("resize", onRs);
            document.body.appendChild(bg);
            if (kind === "image") { media.addEventListener("load", drawRect); media.src = src.url; }
            else media.src = src.url;
            if (kind === "audio" && src.orig_hash) {   // the waveform under the timeline: the original's card thumbnail
                const put = (u) => { if (u && track) track.style.backgroundImage = `url("${u}")`; };
                const th = ilib.thumbs.get(src.orig_hash);
                if (th) put(th); else sendIlib({ action: "thumbs", hashes: [src.orig_hash] }).then(r => put(r && r.thumbs && r.thumbs[src.orig_hash])).catch(() => {});
            }
            drawTl(); drawRect();
            setTimeout(() => { const sb = q('[data-v="save"]'); if (sb) sb.focus(); }, 0);
            bg.__vc = { st, result, done, get D() { return D; } };   // tests
        });
    }
    // ---- "Guardar en librería": offer a virtual copy when the pre-trim file is a library item ----
    function svTrimRange(block, isAudio) {   // fractions of Gradio's trim timeline at the moment "Trim" is pressed
        try {
            if (isAudio) {
                let reg = null;
                const walk = (root) => { for (const el of root.querySelectorAll("*")) { if (reg) return; if (el.shadowRoot) walk(el.shadowRoot); const pt = el.getAttribute && el.getAttribute("part"); if (pt && /(^|\s)region(\s|$)/.test(pt) && !/handle/.test(pt)) reg = el; } };
                walk(block);
                if (!reg) return null;
                const fs = parseFloat(reg.style.left) / 100, fe = 1 - parseFloat(reg.style.right) / 100;
                return isFinite(fs) && isFinite(fe) && fe > fs ? { fs, fe } : null;
            }
            const l = block.querySelector(".handle.left"), r = block.querySelector(".handle.right");
            if (!l || !r) return null;
            const fs = parseFloat(l.style.left) / 100, fe = parseFloat(r.style.left) / 100;
            return isFinite(fs) && isFinite(fe) && fe > fs ? { fs, fe } : null;
        } catch (e) { return null; }
    }
    function svChoice(btn, origName) {
        return new Promise((resolve) => {
            document.querySelectorAll(".reflib-sv-menu").forEach(m => m.remove());
            const m = document.createElement("div"); m.className = "reflib-sv-menu"; m.setAttribute("role", "menu");
            m.innerHTML = `<button type="button" role="menuitem" data-c="file" title="${esc(vct("sv_file_tip"))}"><span>📚 ${esc(vct("sv_file"))}</span><small>${esc(vct("sv_file_tip"))}</small></button>
                <button type="button" role="menuitem" data-c="virtual" title="${esc(vct("sv_virtual_tip"))}"><span>${VICO}${esc(vct("sv_virtual", { name: origName }))}</span><small>${esc(vct("sv_virtual_tip"))}</small></button>`;
            const r = btn.getBoundingClientRect();
            m.style.left = Math.max(8, Math.min(r.left, window.innerWidth - 330)) + "px"; m.style.top = (r.bottom + 4) + "px";
            const done = (v) => { m.remove(); document.removeEventListener("pointerdown", out, true); window.removeEventListener("keydown", key, true); resolve(v); };
            const out = (e) => { if (!m.contains(e.target)) done(null); };
            const key = (e) => { if (e.key === "Escape") { e.preventDefault(); e.stopImmediatePropagation(); done(null); } };
            m.addEventListener("click", (e) => { const b = e.target.closest("[data-c]"); if (b) { e.stopPropagation(); done(b.dataset.c); } });
            document.addEventListener("pointerdown", out, true); window.addEventListener("keydown", key, true);
            document.body.appendChild(m); m.querySelector("button").focus();
        });
    }
    async function svSaveVirtual(f, st, btn) {
        const tgt = `${f.tab}:save_${f.field}`;
        const r = await sendBridge({ action: "save_input_virtual", target: tgt, orig: st.origUrl, fs: st.range.fs, fe: st.range.fe });
        if (!r || !r.ok) return r;
        toast(vct("sv_saved", { name: r.name, d: svDur(r.duration), orig: r.orig_name }), "ok",
            [{ label: t("undo"), onClick: () => sendBridge({ action: "save_input_undo", target: tgt, kind: "virtual", ref: r.virtual_id }).then(u => { if (u && u.ok) toast(vct("sv_undone"), "info"); }) }], 9000);
        return r;
    }
    const folderLabel = (f) => (f && f.managed === "saved_audio") ? svt("folder") : (f && f.managed === "virtual") ? vct("folder") : (f ? f.name : "");
    window.referenceLibrary = {
        version: VERSION,
        get settings() { return cfg; },
        get tabRequest() { return tabRequest; },
        openBrowser, closeBrowser, sendIlib, openResizeMenu, runResize, saveInput, mountSaveButtons, svState: (b) => svState.get(b), vOpen, vEditor, vShowOriginal, vShowCopy, cropApi2, settingsInput, settingsLoaderCandidates, seedInput, forceRandomSeed, histOpen, histClose, histFindVideo, pvReuse, playerSrc, histState: () => hist, refsAvailable, ilibShown: () => shownList(), ilibState: () => ilib, ilibFiltered: loadedItems,
        ilibQuery: () => ({ total: ilib.q.total, loaded: loadedItems().length, cards: ilib.cards ? ilib.cards.size : 0, selAll: !!ilib.sel.all }),
        applySettings, handleToast, sendBridge, bridgeResponse, openTab, toast, lang, t, localizeTab,
        openNameRow, closeNameRow, toggleNameRow, afterSave, applyTooltips,
        loadVideoRequest, reloadVideos, controlVisible, syncVideoBars, reloadLists, renameResponse, mountPencils, nameFromLabel,
        promptsRefreshed, refreshPrompts,
        appliedIds: () => Object.fromEntries(Object.entries(applied).map(([k, v]) => [k, v.id])),
        get appliedState() { return JSON.parse(JSON.stringify(applied)); },
    };
    log(`v${VERSION} loaded`);
})();
