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
    function createScheduler() {
        const q = []; // {prio, run, resolve, reject}
        let busy = false;
        function pump() {
            if (busy) return;
            const item = q.shift();
            if (!item) return;
            busy = true;
            Promise.resolve()
                .then(item.run)
                .then(item.resolve, item.reject)
                .finally(() => { busy = false; pump(); });
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
            get busy() { return busy; },
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
    function lane(action) { return PV.has(String(action || "")) ? "pv" : "q"; }
    function createLanes() {
        const lanes = { pv: createScheduler(), q: createScheduler() };
        return {
            enqueue(action, run, prio) { return lanes[lane(action)].enqueue(run, prio); },
            lane: (l) => lanes[l],
            get size() { return lanes.pv.size + lanes.q.size; },
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

    root.ReflibNet = {
        version: 2,
        VIEW, THUMB, channel, createScheduler, createThumbGate,
        PV, lane, createLanes, scanRefresh, sameIds, bgPrio: 1,
        isView: (a) => channel(a) === "view",
        isThumb: (a) => channel(a) === "thumb",
        viewPrio: 10,
        thumbPrio: 0,
        normalPrio: 5,
    };
})(typeof globalThis !== "undefined" ? globalThis : window);
