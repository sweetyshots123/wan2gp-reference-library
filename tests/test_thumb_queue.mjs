// node tests/test_thumb_queue.mjs — 1.12.17: shared visible-first thumbnail ranking + pull-based queue
// (ReflibNet.rankThumbs / createThumbQueue, request_priority.js). Synthetic only.
import assert from "node:assert/strict";
import path from "node:path";
import { fileURLToPath } from "node:url";
const root = path.join(path.dirname(fileURLToPath(import.meta.url)), "..");
await import(path.join(root, "request_priority.js"));
const N = globalThis.ReflibNet;
const sleep = (ms) => new Promise((r) => setTimeout(r, ms));

// rankThumbs: visible top→bottom, then near by distance, far dropped; no position = visible
const view = { top: 1000, bottom: 1600 };
const E = (hash, top, order = 0) => ({ hash, top, bottom: top + 100, order });
assert.deepEqual(N.rankThumbs([E("below", 1700), E("v2", 1300), E("far", 5000), E("above", 850), E("v1", 1000), { hash: "nopos" }, E("v2", 1300)], view, 300),
  ["nopos", "v1", "v2", "above", "below"]);
assert.deepEqual(N.rankThumbs([], view, 0), []);

// queue: tiles scrolled past and released are never sent; each batch is ranked when a slot frees
const pos = new Map();   // el -> top
const sent = [];
let gate = null;
const Q = N.createThumbQueue({
  batch: 3, inflight: 1, delay: 0, retryMs: 30,
  pos: (el) => (pos.has(el) ? { top: pos.get(el), bottom: pos.get(el) + 100 } : null),
  view: () => view, margin: () => 300,
  send: async (hs) => { sent.push(hs.slice()); if (gate) await gate; return { thumbs: Object.fromEntries(hs.filter((h) => h !== "pend").map((h) => [h, "u:" + h])), pending: hs.includes("pend") ? ["pend"] : [] }; },
});
let release; gate = new Promise((r) => { release = r; });
const got = {};
const want = (h, top) => { const el = { h }; pos.set(el, top); return Q.want(h, el, (u) => { got[h] = u; }); };
want("first", 1000);           // goes out alone (slot free)
await sleep(5);
const rels = [];
for (let i = 0; i < 30; i++) rels.push(want("old" + i, 100 + i));   // scrolled past (far above): never requested while far
const relPast = want("past", 1100); relPast();                     // mounted then unmounted before its turn
want("vis_b", 1400); want("vis_a", 1050); want("near", 1650);
release(); gate = null;
await sleep(30);
assert.deepEqual(sent[0], ["first"]);
assert.deepEqual(sent[1], ["vis_a", "vis_b", "near"], "visible first, then near: " + JSON.stringify(sent));
assert.ok(!sent.flat().includes("past"), "released tile never sent");
assert.ok(!sent.flat().some((h) => h.startsWith("old")), "far tiles not requested");
assert.equal(got.vis_a, "u:vis_a"); assert.equal(got.first, "u:first");
rels.forEach((r) => r());
assert.equal(Q.size, 0, "released far tiles dropped");
assert.ok(Q.stats.dropped >= 31);

// pending: retried while still wanted, dropped once released
const relP = want("pend", 1000);
await sleep(10); const n1 = sent.flat().filter((h) => h === "pend").length;
await sleep(80); const n2 = sent.flat().filter((h) => h === "pend").length;
assert.ok(n2 > n1, "pending retried while wanted");
relP(); await sleep(80);
assert.equal(Q.size, 0);
const n3 = sent.flat().filter((h) => h === "pend").length; await sleep(80);
assert.equal(sent.flat().filter((h) => h === "pend").length, n3, "not retried after release");

// two consumers of one hash: one release keeps it wanted
const elA = { a: 1 }, elB = { b: 1 }; pos.set(elA, 1000); pos.set(elB, 1000);
gate = new Promise((r) => { release = r; });
const blocker = Q.want("blk", elA, () => {}); await sleep(5);
const rA = Q.want("dup", elA, (u) => { got.dupA = u; }); Q.want("dup", elB, (u) => { got.dupB = u; }); rA();
release(); gate = null; await sleep(30);
assert.equal(got.dupB, "u:dup"); assert.equal(got.dupA, undefined); blocker();

// thumbnail lane runs 2 at a time, separate from the query lane
const L = N.createLanes(); let par = 0, maxPar = 0;
const job = () => L.enqueue("thumbs", async () => { par++; maxPar = Math.max(maxPar, par); await sleep(20); par--; }, 0);
await Promise.all([job(), job(), job(), job()]);
assert.equal(maxPar, 2);
// 1.12.18 (retest bug 4): a failed batch drops the tiles released meanwhile; they are never re-sent ahead of visible ones
{
  const sentF = []; let fail = true, rel;
  const gateF = new Promise((r) => { rel = r; });
  const posF = new Map();
  const QF = N.createThumbQueue({ batch: 4, inflight: 1, delay: 0, failMs: 20,
    pos: (el) => (posF.has(el) ? { top: posF.get(el), bottom: posF.get(el) + 100 } : null), view: () => view, margin: () => 300,
    send: async (hs) => { sentF.push(hs.slice()); if (fail) { await gateF; fail = false; throw new Error("network"); } return { thumbs: Object.fromEntries(hs.map((h) => [h, "u"])), pending: [] }; } });
  const w = (h, top) => { const el = { h }; posF.set(el, top); return QF.want(h, el, () => {}); };
  const rs = ["a", "b", "c", "d"].map((h, i) => w(h, 1000 + i * 10));
  await sleep(5);
  rs.forEach((r) => r());                         // scrolled away while the batch is in flight
  ["v1", "v2", "v3"].forEach((h, i) => w(h, 1100 + i * 10));
  rel(); await sleep(60);
  assert.deepEqual(sentF[0], ["a", "b", "c", "d"]);
  assert.deepEqual(sentF[1], ["v1", "v2", "v3"], "only the visible tiles after the failure: " + JSON.stringify(sentF));
  assert.ok(!sentF.slice(1).flat().some((h) => "abcd".includes(h)), "released tiles not re-sent");
  assert.equal(QF.size, 0);
}
// 1.12.18 (retest C): supersede — a newer keystroke cancels queued older requests of the same group
{
  assert.equal(N.supersedes({ group: "suggest", sig: "est" }, { group: "suggest", sig: "es" }), true);
  assert.equal(N.supersedes({ group: "query", sig: "A" }, { group: "query", sig: "A" }), false, "pages of the same filter stay");
  assert.equal(N.supersedes({ group: "query", sig: "A" }, { group: "facets", sig: "B" }), false);
  assert.equal(N.supersedes({ group: "query", sig: "A" }, null), false);
  const S = N.createScheduler(); const ran = []; const res = [];
  let open; const block = new Promise((r) => { open = r; });
  const first = S.enqueue(() => block.then(() => ran.push("running")), 5, { group: "suggest", sig: "e" });
  const p1 = S.enqueue(async () => ran.push("es"), 5, { group: "suggest", sig: "es" }).then(() => res.push("es ok"), (e) => res.push("es " + e.message));
  const pq = S.enqueue(async () => ran.push("q-p0"), 5, { group: "query", sig: "F" }).then(() => res.push("q0 ok"));
  const pq1 = S.enqueue(async () => ran.push("q-p1"), 5, { group: "query", sig: "F" }).then(() => res.push("q1 ok"));
  const p2 = S.enqueue(async () => ran.push("est"), 5, { group: "suggest", sig: "est" }).then(() => res.push("est ok"));
  open(); await Promise.all([first, p1, pq, pq1, p2]);
  assert.deepEqual(ran, ["running", "q-p0", "q-p1", "est"], "the running one finishes, the queued older suggestion is dropped: " + JSON.stringify(ran));
  assert.ok(res.includes("es superseded"));
  assert.equal(S.stats.superseded, 1);
}
console.log("test_thumb_queue: ok");
