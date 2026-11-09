// node tests/test_nav_paths.mjs — 1.12.12: every viewer navigation path goes through the fullscreen-keeping
// choke point, and resume offers are scoped/cleared on navigation. Static contracts + synthetic behaviour only.
import assert from "node:assert/strict";
import fs from "node:fs";
import path from "node:path";
import { fileURLToPath } from "node:url";
const root = path.join(path.dirname(fileURLToPath(import.meta.url)), "..");
const read = (f) => fs.readFileSync(path.join(root, f), "utf8");
const strip = (s) => s;   // raw source (comment stripping is unsafe on this codebase: regex/glob literals)

// ---- Galería Viewer: the ONLY place that changes the index is navTo(), which wraps FS.navigate
{
  const v = strip(read("gallery/src/Viewer.tsx"));
  const navLine = v.split("\n").filter((l) => /setIndexRef\.current\(/.test(l));
  assert.ok(navLine.length >= 1, "navTo must call setIndexRef.current");
  for (const l of navLine) assert.match(l, /FS\.navigate\(|else setIndexRef\.current\(j\)/, "setIndexRef.current only inside navTo: " + l.trim());
  const navToDef = v.match(/const navTo = useCallback\(\(j: number\) => \{([\s\S]*?)\}, \[\]\);/);
  assert.ok(navToDef, "navTo helper must exist");
  assert.match(navToDef[1], /FS\.navigate\(stage\.current/);
  // no direct setIndex(...) calls anywhere (only the prop and the ref assignment may mention it)
  const direct = [...v.matchAll(/\bsetIndex\s*\(/g)];
  assert.equal(direct.length, 0, "direct setIndex( calls bypass fullscreen keeping");
  // each known path uses navTo
  assert.match(v, /const go = useCallback\([^\n]*navTo\(j\)/, "keys / ‹ › (go) → navTo");
  assert.match(v, /navToRef\.current\(j\)/, "wheel → navTo");
  const stripBtns = [...v.matchAll(/<button key=\{[^}]+\}[^>]*onClick=\{\(\) => ([a-zA-Z]+)\(j\)\}/g)].map((m) => m[1]);
  assert.ok(stripBtns.length >= 2 && stripBtns.every((f) => f === "navTo"), "filmstrip buttons → navTo: " + stripBtns);
  assert.match(v, /onClick=\{\(\) => go\(-1\)\}/); assert.match(v, /onClick=\{\(\) => go\(1\)\}/);
  // keeper re-attached when the .stage node changes
  assert.match(v, /FS\.keep\(st\)[\s\S]*?\}, \[hasIt\]\);/);
}
// ---- Media Library: openLightboxNow() is called only from the openLightbox() wrapper (which keeps fullscreen)
{
  const js = strip(read("reference_library.js"));
  const calls = [...js.matchAll(/\bopenLightboxNow\(/g)].length;
  // definition + call inside the wrapper (navigate callback) + direct fallback in the wrapper
  assert.equal(calls, 3, "openLightboxNow must only be called by openLightbox (got " + calls + ")");
  const wrap = js.match(/function openLightbox\(idx\) \{([\s\S]*?)\n    \}/);
  assert.ok(wrap, "openLightbox wrapper");
  assert.match(wrap[1], /ReflibFullscreen\.navigate\(box/);
  // the step path uses the wrapper, not a private open
  const step = js.match(/function lightboxStep\(d\) \{([\s\S]*?)\n    \}/);
  assert.ok(step && /openLightbox\(i\)/.test(step[1]));
  // stale offers removed with the old media; late replies ignored
  const now = js.match(/function openLightboxNow\(idx\) \{([\s\S]*?)\n    \}\n/);
  assert.ok(now && /querySelectorAll\("\.reflib-ib-resume"\)\.forEach\(o => o\.remove\(\)\)/.test(now[1]), "openLightboxNow clears .reflib-ib-resume");
  const wr = js.match(/function wireResume\(m, hash, box\) \{([\s\S]*?)\n    \}\n/);
  assert.ok(wr && /m\.isConnected/.test(wr[1]) && /offerFor/.test(wr[1]), "wireResume scoped to current media");
  // frame-capture re-anchor waits for an async open before restoring media
  assert.match(js, /p\.then\(\(\) => restoreMedia\(pin\)\)/);
}
// ---- Shared rule behaviour: offerFor
{
  await import(path.join(root, "playback_rules.js"));
  const P = globalThis.ReflibPlayback;
  assert.equal(P.offerFor({ hash: "aaa", t: 400 }, "aaa"), 400);
  assert.equal(P.offerFor({ hash: "aaa", t: 400 }, "bbb"), null, "offer of the previous video must not apply");
  assert.equal(P.offerFor(null, "aaa"), null);
  assert.equal(P.offerFor({ hash: "aaa", t: "x" }, "aaa"), null);
  assert.equal(P.offerFor({ hash: "aaa", t: 1 }, ""), null);
  const v = read("gallery/src/Viewer.tsx");
  assert.match(v, /Playback\.offerFor\(offerSt, it\?\.hash\)/);
}
// ---- Synthetic behaviour: Galería-style navTo keeps fullscreen across a video→image step
{
  await import(path.join(root, "fullscreen_rules.js"));
  const F = globalThis.ReflibFullscreen;
  const L = {}; const doc = { fullscreenElement: null, addEventListener(t, h) { (L[t] ||= []).push(h); }, removeEventListener() {} };
  const video = { contains: (x) => x === video };
  const stage = { kids: [video], contains(x) { return x === stage || this.kids.some((k) => k === x); },
    requestFullscreen() { doc.fullscreenElement = stage; return Promise.resolve(); } };
  let index = 0;
  const setIndex = (j) => { index = j; stage.kids = []; if (doc.fullscreenElement === video) doc.fullscreenElement = null; };
  const navTo = (j) => F.navigate(stage, () => setIndex(j), doc);
  doc.fullscreenElement = video;                 // native <video> fullscreen
  for (const path of ["wheel", "strip", "key"]) { await navTo(index + 1); assert.equal(doc.fullscreenElement, stage, path + " kept fullscreen"); }
  assert.equal(index, 3);
}
console.log("test_nav_paths: ok");
