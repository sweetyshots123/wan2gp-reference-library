// Reference Library 1.12.9 — prioritize viewer I/O over thumbnail backlog (shared by Media Library + Galería).
// After a big folder scan, hundreds of thumb requests can saturate the Gradio fast-chain / browser connections
// and make zoom wait. Viewer actions (preview, media_url, …) jump ahead; thumbs pause while a lightbox/viewer is open.
(function (root) {
    "use strict";
    const VIEW = new Set([
        "preview", "media_url", "media_dur", "media_src", "open", "query", "range", "sel_info",
        "playback_get", "playback_set", "playback_settings", "index_of", "virt_src", "virt_status",
    ]);
    const THUMB = new Set(["thumbs"]);

    function channel(action) {
        const a = String(action || "");
        if (THUMB.has(a)) return "thumb";
        if (VIEW.has(a)) return "view";
        return "normal";
    }

    /** Promise chain with priority: high items run before normal ones already queued. */
    function createScheduler(conc) {
        const q = []; // {prio, run, resolve, reject}
        const max = Math.max(1, Number(conc) || 1);   // 1.12.17: optional concurrency (thumb lane: 2)
        let running = 0;
        function pump() {
            while (running < max) {
                const item = q.shift();
                if (!item) return;
                running++;
                Promise.resolve()
                    .then(item.run)
                    .then(item.resolve, item.reject)
                    .finally(() => { running--; pump(); });
            }
        }
        function enqueue(run, prio) {
            const p = Number(prio) || 0;
            return new Promise((resolve, reject) => {
                const item = { prio: p, run, resolve, reject };
                // higher prio first; stable among equals
                let i = 0;
                while (i < q.length && q[i].prio >= p) i++;
                q.splice(i, 0, item);
                pump();
            });
        }
        return {
            enqueue,
            clear(pred) {
                for (let i = q.length - 1; i >= 0; i--) {
                    if (pred(q[i])) {
                        q[i].reject(new Error("cancelled"));
                        q.splice(i, 1);
                    }
                }
            },
            get size() { return q.length; },
            get busy() { return running > 0; },
        };
    }

    /** Thumb gate: while viewerOpen, new thumb work is deferred. */
    function createThumbGate() {
        let viewer = 0;
        const waiters = [];
        return {
            enterViewer() { viewer++; },
            leaveViewer() { viewer = Math.max(0, viewer - 1); if (!viewer) { const w = waiters.splice(0); w.forEach((r) => r()); } },
            get blocked() { return viewer > 0; },
            whenFree() {
                if (!viewer) return Promise.resolve();
                return new Promise((r) => waiters.push(r));
            },
        };
    }

    // 1.12.16: the open item's preview / media must not wait behind a slow list query (a catalog rebuild while a folder
    // is being indexed). Where requests can run in parallel (fetch: Galería, standalone Media Library) they go in two
    // lanes, each its own priority queue: "pv" (the open item) and "q" (lists, thumbs, everything else). The Gradio
    // bridge (one textbox per channel) stays one at a time.
    const PV = new Set([
        "preview", "media_url", "media_dur", "media_src", "sel_info",
        "playback_get", "playback_set", "playback_settings", "virt_src", "virt_status", "index_of",
    ]);
    // 1.12.17: thumbnails get a third lane ("th", 2 at a time): they no longer wait behind a list query, and a query
    // (the page the user scrolled to) no longer waits behind a thumbnail batch.
    function lane(action) { const a = String(action || ""); return PV.has(a) ? "pv" : THUMB.has(a) ? "th" : "q"; }
    function createLanes() {
        const lanes = { pv: createScheduler(), q: createScheduler(), th: createScheduler(2) };
        return {
            enqueue(action, run, prio) { return lanes[lane(action)].enqueue(run, prio); },
            lane: (l) => lanes[l],
            get size() { return lanes.pv.size + lanes.q.size + lanes.th.size; },
        };
    }

    // 1.12.17: thumbnails, visible first. entries [{hash, top, bottom, order}] in the same coordinates as view
    // {top, bottom}; entries without a position (search box, filmstrip…) count as visible. Visible tiles first (top to
    // bottom), then the ones within `margin` by distance to the viewport; farther ones are not requested now.
    function rankThumbs(entries, view, margin) {
        const out = [], m = Number(margin) || 0;
        for (const e of entries || []) {
            if (!e || !e.hash) continue;
            if (e.top == null) { out.push([e.hash, 0, -1, e.order || 0]); continue; }
            if (e.bottom < view.top - m || e.top > view.bottom + m) continue;
            const vis = e.bottom >= view.top && e.top <= view.bottom;
            out.push([e.hash, vis ? 0 : 1, vis ? e.top : (e.top > view.bottom ? e.top - view.bottom : view.top - e.bottom), e.order || 0]);
        }
        out.sort((a, b) => a[1] - b[1] || a[2] - b[2] || a[3] - b[3]);
        const seen = new Set(), res = [];
        for (const x of out) if (!seen.has(x[0])) { seen.add(x[0]); res.push(x[0]); }
        return res;
    }

    // 1.12.17: pull-based thumbnail queue (Galería). A tile asks with want(hash, el, cb) and gets a release() for when
    // it unmounts; a tile scrolled past and unmounted is dropped before it is ever sent. Each batch is picked when a
    // slot frees (not when the tile mounted), with rankThumbs on the positions *now*, so after a long / fast scroll the
    // tiles on screen go first instead of a FIFO backlog of everything scrolled past.
    // o: {send(hashes) -> Promise<{thumbs, pending}>, batch=24, inflight=2, pos(el) -> {top,bottom}|null,
    //     view() -> {top,bottom}, margin() -> px, blocked() -> bool, retryMs=450, failMs=2000, delay=16}
    function createThumbQueue(o) {
        o = o || {};
        const want = new Map();   // hash -> {cbs:Set, els:Set, order, retryAt, busy}
        let inflight = 0, order = 0, timer = null;
        const stats = { sent: 0, batches: 0, dropped: 0, done: 0 };
        const delay = o.delay == null ? 16 : o.delay;
        function schedule(ms) {
            if (timer != null) return;
            timer = setTimeout(() => { timer = null; pump(); }, ms == null ? delay : ms);
        }
        function pick(n) {
            const now = Date.now(), entries = [];
            let soonest = Infinity;
            for (const [h, w] of want) {
                if (w.busy) continue;
                if (w.retryAt > now) { soonest = Math.min(soonest, w.retryAt); continue; }
                let best = null;
                for (const el of w.els) { const r = o.pos ? o.pos(el) : null; if (r && (!best || r.top < best.top)) best = r; }
                entries.push(best ? { hash: h, top: best.top, bottom: best.bottom, order: -w.order } : { hash: h, order: -w.order });
            }
            const view = o.view ? o.view() : { top: -Infinity, bottom: Infinity };
            return { hashes: rankThumbs(entries, view, o.margin ? o.margin() : 0).slice(0, n), soonest };
        }
        function finish(h, url) {
            const w = want.get(h); if (!w) return;
            want.delete(h); stats.done++;
            for (const cb of w.cbs) { try { cb(url); } catch (e) { /* tile gone */ } }
        }
        function pump() {
            if (o.blocked && o.blocked()) { schedule(250); return; }
            while (inflight < (o.inflight || 2)) {
                const { hashes, soonest } = pick(o.batch || 24);
                if (!hashes.length) { if (soonest < Infinity) schedule(Math.max(20, soonest - Date.now())); return; }
                inflight++; stats.batches++; stats.sent += hashes.length;
                hashes.forEach((h) => { want.get(h).busy = true; });
                Promise.resolve().then(() => o.send(hashes)).then((r) => {
                    const pend = new Set((r && r.pending) || []);
                    for (const h of hashes) {
                        const w = want.get(h); if (!w) continue;
                        w.busy = false;
                        const u = r && r.thumbs && r.thumbs[h];
                        if (u && !pend.has(h)) finish(h, u);
                        else if (!w.cbs.size) { want.delete(h); stats.dropped++; }
                        else w.retryAt = Date.now() + (o.retryMs || 450);
                    }
                }, () => {
                    for (const h of hashes) { const w = want.get(h); if (w) { w.busy = false; w.retryAt = Date.now() + (o.failMs || 2000); } }
                }).finally(() => { inflight--; pump(); });
            }
        }
        return {
            want(hash, el, cb) {
                let w = want.get(hash);
                if (!w) { w = { cbs: new Set(), els: new Set(), order: 0, retryAt: 0, busy: false }; want.set(hash, w); }
                w.order = ++order; w.cbs.add(cb); if (el) w.els.add(el);
                schedule();
                return () => {
                    w.cbs.delete(cb); if (el) w.els.delete(el);
                    if (!w.cbs.size && !w.busy && want.get(hash) === w) { want.delete(hash); stats.dropped++; }
                };
            },
            poke() { schedule(); },
            get size() { return want.size; },
            get inflight() { return inflight; },
            stats,
        };
    }

    // 1.12.16: refresh while a folder is being indexed. Compare the page on screen before / after; when nothing on
    // screen changed only the counts are updated (loaded pages and cards stay), otherwise the new page is applied in
    // place and the other loaded pages are re-fetched lazily while still shown (never a "Loading…" wipe).
    function sameIds(a, b) {
        a = a || []; b = b || [];
        if (a.length !== b.length) return false;
        for (let i = 0; i < a.length; i++) if (a[i] !== b[i]) return false;
        return true;
    }
    function scanRefresh(prev, next) {
        prev = prev || {}; next = next || {};
        const pageChanged = !sameIds(prev.ids, next.ids);
        const relayout = JSON.stringify(prev.groups == null ? null : prev.groups) !== JSON.stringify(next.groups == null ? null : next.groups);
        const resize = (Number(prev.total) || 0) !== (Number(next.total) || 0);
        return {
            countsOnly: !pageChanged && !relayout && !resize,
            applyPage: pageChanged, relayout, resize,
            refetchOthers: pageChanged || relayout || resize,
        };
    }

    // 1.12.17: what a library poll should do. Indexing just ended -> "full" (every loaded page re-fetched: a change
    // deep in the list, total and first page unchanged, is not missed); while indexing a revision change -> "scan"
    // (scanRefresh); otherwise a revision change -> "full"; nothing -> "none". Same rule in both UIs.
    function indexRefresh(o) {
        o = o || {};
        if (o.was && !o.running) return "full";
        if (!o.revChanged) return "none";
        return o.running ? "scan" : "full";
    }

    root.ReflibNet = {
        version: 4, indexRefresh, rankThumbs, createThumbQueue,
        VIEW, THUMB, channel, createScheduler, createThumbGate,
        PV, lane, createLanes, scanRefresh, sameIds, bgPrio: 1,
        isView: (a) => channel(a) === "view",
        isThumb: (a) => channel(a) === "thumb",
        viewPrio: 10,
        thumbPrio: 0,
        normalPrio: 5,
    };
})(typeof globalThis !== "undefined" ? globalThis : window);
