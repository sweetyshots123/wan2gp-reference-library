// node tests/test_fullscreen_rules.mjs — synthetic DOM stubs only
import assert from "node:assert/strict";
import path from "node:path";
import { fileURLToPath } from "node:url";
const root = path.join(path.dirname(fileURLToPath(import.meta.url)), "..");
await import(path.join(root, "fullscreen_rules.js"));
const F = globalThis.ReflibFullscreen;
assert.equal(F.version, 1);

function mkDoc() {
  const listeners = {};
  const doc = {
    fullscreenElement: null,
    addEventListener(t, h) { (listeners[t] ||= []).push(h); },
    removeEventListener(t, h) { listeners[t] = (listeners[t] || []).filter((x) => x !== h); },
    fire(t) { (listeners[t] || []).forEach((h) => h()); },
    exitFullscreen() { doc.fullscreenElement = null; doc.fire("fullscreenchange"); return Promise.resolve(); },
    listeners,
  };
  return doc;
}
function mkEl(doc, name, kids = [], opts = {}) {
  const el = {
    name, kids,
    contains(x) { return x === el || kids.some((k) => k === x || (k.contains && k.contains(x))); },
    requestFullscreen() {
      if (opts.deny) return Promise.reject(new Error("no gesture"));
      doc.fullscreenElement = el; doc.fire("fullscreenchange"); return Promise.resolve();
    },
  };
  return el;
}

// 1) nothing fullscreen
{
  const doc = mkDoc(); const video = mkEl(doc, "video"); const stage = mkEl(doc, "stage", [video]);
  assert.equal(F.isActive(doc), false);
  assert.equal(F.escAction(doc), "close");
  assert.equal(F.needsPromote(stage, doc), false);
  assert.equal(await F.beforeNavigate(stage, doc), false);
}
// 2) native video fullscreen → promoted to stable container before navigating
{
  const doc = mkDoc(); const video = mkEl(doc, "video"); const stage = mkEl(doc, "stage", [video]);
  doc.fullscreenElement = video;
  assert.equal(F.owns(stage, doc), true);
  assert.equal(F.needsPromote(stage, doc), true);
  assert.equal(F.escAction(doc), "exit-fullscreen");
  assert.equal(await F.beforeNavigate(stage, doc), true);
  assert.equal(doc.fullscreenElement, stage);
  // now navigation may replace the <video>: container still fullscreen
  stage.kids.length = 0; stage.kids.push(mkEl(doc, "video2"));
  assert.equal(F.owns(stage, doc), true);
  assert.equal(F.needsPromote(stage, doc), false);
}
// 3) container already fullscreen: no-op
{
  const doc = mkDoc(); const stage = mkEl(doc, "stage", []);
  doc.fullscreenElement = stage;
  assert.equal(await F.promote(stage, doc), false);
  assert.equal(doc.fullscreenElement, stage);
}
// 4) unrelated element fullscreen: never stolen
{
  const doc = mkDoc(); const other = mkEl(doc, "other"); const stage = mkEl(doc, "stage", []);
  doc.fullscreenElement = other;
  assert.equal(F.owns(stage, doc), false);
  assert.equal(await F.beforeNavigate(stage, doc), false);
  assert.equal(doc.fullscreenElement, other);
}
// 5) request denied (no user gesture, e.g. wheel) → resolves false, never throws
{
  const doc = mkDoc(); const video = mkEl(doc, "video"); const stage = mkEl(doc, "stage", [video], { deny: true });
  doc.fullscreenElement = video;
  assert.equal(await F.promote(stage, doc), false);
  assert.equal(doc.fullscreenElement, video);
}
// 6) keep(): native fullscreenchange on the video → moved to container; unsubscribe works
{
  const doc = mkDoc(); const video = mkEl(doc, "video"); const stage = mkEl(doc, "stage", [video]);
  const off = F.keep(stage, doc);
  doc.fullscreenElement = video; doc.fire("fullscreenchange");
  await new Promise((r) => setTimeout(r, 0));
  assert.equal(doc.fullscreenElement, stage);
  off();
  assert.equal((doc.listeners.fullscreenchange || []).length, 0);
}
// 7) toggle on/off
{
  const doc = mkDoc(); const stage = mkEl(doc, "stage", []);
  assert.equal(await F.toggle(stage, doc), true);
  assert.equal(doc.fullscreenElement, stage);
  assert.equal(await F.toggle(stage, doc), false);
  assert.equal(doc.fullscreenElement, null);
}
// 8) webkit prefix
{
  const doc = mkDoc(); const stage = mkEl(doc, "stage", []);
  doc.fullscreenElement = undefined; doc.webkitFullscreenElement = stage;
  assert.equal(F.fsEl(doc), stage);
}
// 9) navigate(): fn runs only AFTER fullscreen moved to the container (removing the fs <video> first drops it)
{
  const doc = mkDoc(); const video = mkEl(doc, "video"); const stage = mkEl(doc, "stage", [video]);
  doc.fullscreenElement = video;
  let fsAtFn = "unset";
  await F.navigate(stage, () => { fsAtFn = doc.fullscreenElement; }, doc);
  assert.equal(fsAtFn, stage);
  // no fullscreen: synchronous
  const doc2 = mkDoc(); const st2 = mkEl(doc2, "stage", []);
  let ran = false; const r = F.navigate(st2, () => { ran = true; return 7; }, doc2);
  assert.equal(ran, true); assert.equal(r, 7);
  // denied promotion still navigates
  const doc3 = mkDoc(); const v3 = mkEl(doc3, "video"); const st3 = mkEl(doc3, "stage", [v3], { deny: true });
  doc3.fullscreenElement = v3; let ran3 = false;
  await F.navigate(st3, () => { ran3 = true; }, doc3);
  assert.equal(ran3, true);
}
// Source contracts: both UIs use the shared rule
import fs from "node:fs";
const viewer = fs.readFileSync(path.join(root, "gallery/src/Viewer.tsx"), "utf8");
const rl = fs.readFileSync(path.join(root, "reference_library.js"), "utf8");
const plugin = fs.readFileSync(path.join(root, "plugin.py"), "utf8");
assert.match(viewer, /fullscreen_rules\.js/);
assert.match(viewer, /FS\.navigate\(/);
assert.ok(!/className="vidhost"[^>]*key=\{src\}/.test(viewer), "vidhost must not remount on src change (key={src})");
assert.match(rl, /ReflibFullscreen/);
assert.match(rl, /ReflibFullscreen\.navigate\(/);
assert.match(plugin, /fullscreen_rules\.js/);
console.log("test_fullscreen_rules: ok");
