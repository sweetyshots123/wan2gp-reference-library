// node tests/test_scan_refresh_rules.mjs — 1.12.16 shared rules in request_priority.js (ReflibNet): refresh while
// indexing (scanRefresh) and the preview lane (createLanes). Synthetic only.
import assert from "node:assert/strict";
import path from "node:path";
import { fileURLToPath } from "node:url";
const root = path.join(path.dirname(fileURLToPath(import.meta.url)), "..");
await import(path.join(root, "request_priority.js"));
const N = globalThis.ReflibNet;
assert.equal(N.version, 4);
// indexRefresh (1.12.17): indexing -> idle is always a full refresh, even with the same rev
assert.equal(N.indexRefresh({ was: true, running: false, revChanged: false }), "full");
assert.equal(N.indexRefresh({ was: true, running: false, revChanged: true }), "full");
assert.equal(N.indexRefresh({ was: false, running: false, revChanged: true }), "full");
assert.equal(N.indexRefresh({ was: false, running: false, revChanged: false }), "none");
assert.equal(N.indexRefresh({ was: true, running: true, revChanged: true }), "scan");
assert.equal(N.indexRefresh({ was: false, running: true, revChanged: true }), "scan");
assert.equal(N.indexRefresh({ was: true, running: true, revChanged: false }), "none");
assert.equal(N.indexRefresh(), "none");
// scanRefresh
let d = N.scanRefresh({ ids: ["a", "b", "c"], total: 10, groups: null }, { ids: ["a", "b", "c"], total: 10, groups: null });
assert.deepEqual(d, { countsOnly: true, applyPage: false, relayout: false, resize: false, refetchOthers: false });
d = N.scanRefresh({ ids: ["a", "b", "c"], total: 10 }, { ids: ["a", "b", "c"], total: 11 });
assert.equal(d.countsOnly, false); assert.equal(d.resize, true); assert.equal(d.applyPage, false); assert.equal(d.refetchOthers, true);
d = N.scanRefresh({ ids: ["a", "b", "c"], total: 10 }, { ids: ["n", "a", "b"], total: 11 });
assert.equal(d.applyPage, true); assert.equal(d.refetchOthers, true);
d = N.scanRefresh({ ids: ["a"], total: 1, groups: [["2026-11", 1]] }, { ids: ["a"], total: 1, groups: [["2026-11", 2]] });
assert.equal(d.relayout, true); assert.equal(d.countsOnly, false);
d = N.scanRefresh({ ids: [undefined, "b"], total: 2 }, { ids: ["a", "b"], total: 2 });
assert.equal(d.applyPage, true, "a page not loaded yet counts as changed");
assert.equal(N.sameIds([], []), true); assert.equal(N.scanRefresh(null, null).countsOnly, true);
// lanes: preview never waits behind a slow query; same-lane order still by priority
assert.equal(N.lane("preview"), "pv"); assert.equal(N.lane("media_url"), "pv"); assert.equal(N.lane("query"), "q"); assert.equal(N.lane("thumbs"), "th");   // 1.12.17: own lane
const L = N.createLanes(), order = [];
const slow = (name, ms) => () => new Promise((r) => setTimeout(() => { order.push(name); r(name); }, ms));
const pq = L.enqueue("query", slow("query", 300), 10);
const pp = L.enqueue("preview", slow("preview", 20), 10);
await Promise.all([pq, pp]);
assert.deepEqual(order, ["preview", "query"], "preview finished first");
order.length = 0;
const S = N.createScheduler();
const a = S.enqueue(slow("first", 50), 5), b = S.enqueue(slow("bg", 5), N.bgPrio), c2 = S.enqueue(slow("user", 5), 10);
await Promise.all([a, b, c2]);
assert.deepEqual(order, ["first", "user", "bg"], "background refresh queued behind what the user asked for");
console.log("test_scan_refresh_rules: ok");
