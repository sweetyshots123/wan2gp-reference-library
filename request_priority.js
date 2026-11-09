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

    root.ReflibNet = {
        version: 1,
        VIEW, THUMB, channel, createScheduler, createThumbGate,
        isView: (a) => channel(a) === "view",
        isThumb: (a) => channel(a) === "thumb",
        viewPrio: 10,
        thumbPrio: 0,
        normalPrio: 5,
    };
})(typeof globalThis !== "undefined" ? globalThis : window);
