// node tests/test_capture_stay_gallery.mjs — 1.12.13: Galería frame capture must stay on the open video.
// Synthetic data only. Simulates App.tsx's store/viewer/pin cycle on a refresh where the captured frame is
// inserted before the open video (date_desc), using the SHARED rules (frame_capture_rules.js → ReflibFrameCapture).
import assert from "node:assert/strict";
import fs from "node:fs";
import path from "node:path";
import { fileURLToPath } from "node:url";
const root = path.join(path.dirname(fileURLToPath(import.meta.url)), "..");
await import(path.join(root, "frame_capture_rules.js"));
const FC = globalThis.ReflibFrameCapture;

const vid = (h) => ({ hash: h, kind: "video" }), img = (h) => ({ hash: h, kind: "image" });
const before = [vid("v0"), vid("v1"), img("p2"), vid("v3")];

// 1.12.12 behaviour (model of App.tsx at 30741fc): the pin effect [viewer, ver] re-pins to whatever sits at the
// viewer index after a refresh, so the relocate effect sees "cur.hash === pin" and never moves back.
function legacy(openIdx) {
  let store = before.slice(), viewer = openIdx, pin = store[viewer].hash;
  store = [img("frame"), ...before];                       // refresh after capture: new frame first
  const it = store[viewer]; if (it) pin = it.hash;          // effect 1 (pin follows ver)
  if (store[viewer].hash !== pin) viewer = store.findIndex((x) => x.hash === pin);   // effect 2 (relocate)
  return store[viewer];
}
assert.equal(legacy(0).hash, "frame", "1.12.12 reproduction: open newest video → shows the captured photo");
assert.equal(legacy(1).hash, "v0", "1.12.12 reproduction: shows the neighbour instead of the open video");

// 1.12.13 shared rules
assert.equal(typeof FC.pinFollow, "function", "ReflibFrameCapture.pinFollow");
assert.equal(typeof FC.pinLocate, "function", "ReflibFrameCapture.pinLocate");
function fixed(openIdx, refreshed, { pageHasPin = true } = {}) {
  let store = before.slice(), viewer = openIdx;
  let pin = FC.pinFollow(null, viewer, store[viewer].hash);
  store = refreshed;
  const entries = store.map((x, i) => [i, x.hash]).filter(([, h]) => pageHasPin || h !== pin.hash);
  const loc = FC.pinLocate(pin, viewer, entries);   // atomically with the store write (same React batch)
  if (loc.index !== viewer) { viewer = loc.index; pin = { ...pin, idx: viewer }; }
  const shown = loc.override ? { hash: pin.hash } : store[viewer];
  pin = FC.pinFollow(pin, viewer, store[viewer] && store[viewer].hash);   // pin effect after the render
  return { shown, viewer, pin, loc };
}
for (const i of [0, 1, 3]) {
  const r = fixed(i, [img("frame"), ...before]);
  assert.equal(r.shown.hash, before[i].hash, "stay on " + before[i].hash);
  assert.equal(r.viewer, i + 1);
  assert.equal(r.pin.hash, before[i].hash, "refresh must not re-pin");
}
// open video moved to a page that is not loaded yet: keep showing it (override) until index_of answers
{
  const r = fixed(3, [img("frame"), ...before], { pageHasPin: false });
  assert.equal(r.loc.override, true); assert.equal(r.loc.lookup, true); assert.equal(r.shown.hash, "v3");
}
// user navigation re-pins (pin.idx !== viewer)
{
  let pin = FC.pinFollow(null, 1, "v1");
  pin = FC.pinFollow(pin, 2, "p2"); assert.deepEqual(pin, { hash: "p2", idx: 2 });
  pin = FC.pinFollow(pin, 3, undefined); assert.equal(pin.idx, 2, "not loaded yet: keep old pin (no override, idx differs)");
  assert.equal(FC.pinLocate(pin, 3, [[3, "zz"]]).override, false, "never override a navigation target");
  assert.equal(FC.pinFollow(pin, null, "x"), null, "viewer closed → unpinned");
}
// no shift (capture filtered out): nothing moves
assert.deepEqual(FC.pinLocate({ hash: "v1", idx: 1 }, 1, [[0, "v0"], [1, "v1"]]), { index: 1, override: false, lookup: false });

// App.tsx wiring (source contract)
const app = fs.readFileSync(path.join(root, "gallery/src/App.tsx"), "utf8");
assert.doesNotMatch(app, /if \(it\) viewerHash\.current = it\.hash;/, "App must not re-pin on every refresh (1.12.12 bug)");
assert.match(app, /FrameCap\.pinLocate\(/, "fetchPage relocates the pinned viewer in the same batch as the store write");
assert.match(app, /FrameCap\.pinFollow\(/);
assert.match(app, /viewerItems/, "Viewer gets the pinned item while it is being relocated");
assert.match(app, /<Viewer items=\{viewerItems\}/);
console.log("test_capture_stay_gallery: ok");
