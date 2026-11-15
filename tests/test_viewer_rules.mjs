// node tests/test_viewer_rules.mjs — 1.12.17 (ml-wheel): Media Library lightbox geometry + wheel intent (viewer_rules.js).
// Pure / synthetic numbers only, plus static checks that reference_library.js and plugin.py use the shared rules.
import assert from "node:assert/strict";
import fs from "node:fs";
import path from "node:path";
import { fileURLToPath } from "node:url";
const root = path.join(path.dirname(fileURLToPath(import.meta.url)), "..");
await import(path.join(root, "wheel_rules.js"));
await import(path.join(root, "viewer_rules.js"));
const V = globalThis.ReflibViewer;
const box = { boxW: 1256, boxH: 820 };
// fit from the ORIGINAL size whatever stage is loaded: thumb 220×147, preview 1024×683, full 3000×2000 → same size
for (const [nw, nh] of [[220, 147], [1024, 683], [3000, 2000]]) {
  const s = V.fitSize({ natW: nw, natH: nh, origW: 3000, origH: 2000, ...box });
  assert.ok(Math.abs(s.h - 820) <= 1 && Math.abs(s.w - 1230) <= 4, `${nw}: ${JSON.stringify(s)}`);
}
// 1:1 = original pixels, even while only the preview is loaded
{ const o = V.fitSize({ natW: 1024, natH: 683, origW: 3000, origH: 2000, ...box, one: true }); assert.ok(o.w === 3000 && Math.abs(o.h - 2000) <= 2, JSON.stringify(o)); }
// EXIF: PIL size is pre-rotation (3000×2000) but the loaded pixels are portrait → portrait, long side 3000
const p = V.fitSize({ natW: 147, natH: 220, origW: 3000, origH: 2000, ...box, one: true });
assert.ok(p.h === 3000 && Math.abs(p.w - 2005) <= 2, JSON.stringify(p));
// a small original is never upscaled beyond 1:1 (Galería: max-width/height 100%)
assert.deepEqual(V.fitSize({ natW: 220, natH: 110, origW: 400, origH: 200, ...box }), { w: 400, h: 200 });
// unknown original: fill the box with the loaded aspect (no 220 px thumbnail on screen)
const u = V.fitSize({ natW: 220, natH: 147, ...box });
assert.ok(Math.abs(u.h - 820) <= 1, JSON.stringify(u));
assert.equal(V.fitSize({ natW: 0, natH: 0, ...box }), null);
// zoom to cursor: point at 30 % / 70 % of a fitted image stays under the cursor after the 1:1 layout
{
  const imgRect = { left: 13, top: 12, width: 1230, height: 820 }, stageRect = { left: 0, top: 0 };
  const cx = 13 + 0.3 * 1230, cy = 12 + 0.7 * 820;
  const z = V.zoomScroll({ cx, cy, imgRect, stageRect, newOffLeft: 0, newOffTop: 0, newW: 3000, newH: 2000 });
  assert.ok(Math.abs(z.fx - 0.3) < 1e-9 && Math.abs(z.fy - 0.7) < 1e-9);
  // after scrolling by (left, top) the image point under the cursor is fx·newW
  assert.ok(Math.abs((cx - stageRect.left + z.left) - 0.3 * 3000) < 1e-6);
  assert.ok(Math.abs((cy - stageRect.top + z.top) - 0.7 * 2000) < 1e-6);
  // a click outside the image clamps to its edge
  const e = V.zoomScroll({ cx: 0, cy: 0, imgRect, stageRect, newOffLeft: 0, newOffTop: 0, newW: 3000, newH: 2000 });
  assert.equal(e.fx, 0); assert.equal(e.fy, 0);
}
// zoomAt (Galería transform, origin = stage centre): the stage point under the cursor maps to the same image point
{
  const o = { s: 1, x: 0, y: 0 }, px = -200, py = 150;   // cursor relative to the stage centre
  const imgPt = (z, X, Y) => [(X - z.x) / z.s, (Y - z.y) / z.s];   // screen (centre-relative) → unscaled image coords
  const z1 = V.zoomAt(o, 2.5, px, py);
  assert.deepEqual(imgPt(z1, px, py).map((v) => +v.toFixed(9)), imgPt(o, px, py).map((v) => +v.toFixed(9)));
  const z2 = V.zoomAt(z1, 1.7, 90, -40);
  assert.deepEqual(imgPt(z2, 90, -40).map((v) => +v.toFixed(9)), imgPt(z1, 90, -40).map((v) => +v.toFixed(9)));
  assert.deepEqual(V.zoomAt(z2, 0.01, 0, 0), { s: 1, x: 0, y: 0 }, "zooming out to 1 = Fit");
  assert.equal(V.zoomAt(o, 100, 0, 0).s, 12, "max 12");
}
// both UIs land in Fit after navigation
assert.deepEqual(V.navZoom(), { s: 1, x: 0, y: 0 });
// wheel intent = the Galería's (Viewer.tsx): Ctrl zoom, zoomed+pannable pan, otherwise step; prevented = leave it
assert.equal(V.wheelIntent({ ctrl: true, zoomed: false }), "zoom");
assert.equal(V.wheelIntent({ ctrl: false, zoomed: true, canPan: true }), "pan");
assert.equal(V.wheelIntent({ ctrl: false, zoomed: true, canPan: false }), "step");
assert.equal(V.wheelIntent({ ctrl: false, zoomed: false, canPan: true }), "step");
assert.equal(V.wheelIntent({ prevented: true, ctrl: true }), "none");
// the ML uses the SAME stepper as the Galería (1 notch = 1 item)
const w = globalThis.ReflibWheel.create();
assert.equal(w.push(100, 0, 0), 1); assert.equal(w.push(100, 0, 10), 1); assert.equal(w.push(-100, 0, 20), -1);

const js = fs.readFileSync(path.join(root, "reference_library.js"), "utf8");
const pl = fs.readFileSync(path.join(root, "plugin.py"), "utf8");
const tuple = /for _shared in \(([^)]*)\)/.exec(pl)[1];
assert.match(tuple, /"wheel_rules\.js"/); assert.match(tuple, /"viewer_rules\.js"/);
assert.match(js, /box\._wheel = window\.ReflibWheel \? ReflibWheel\.create\(\) : null/);
assert.match(js, /ReflibViewer\.fitSize\(/); assert.match(js, /ReflibViewer\.zoomScroll\(/); assert.match(js, /ReflibViewer\.wheelIntent\(/);
assert.match(js, /lightboxZoom\(box\.classList\.contains\("fit"\), e\)/, "click zooms at the pointer");
assert.match(js, /ReflibViewer\.navZoom\(\)/);
// Galería uses the SAME rules (no local copies of the math)
const nav = fs.readFileSync(path.join(root, "gallery/src/viewerNav.ts"), "utf8");
const vw = fs.readFileSync(path.join(root, "gallery/src/Viewer.tsx"), "utf8");
assert.match(nav, /import "\.\.\/\.\.\/viewer_rules\.js"/); assert.match(nav, /import "\.\.\/\.\.\/wheel_rules\.js"/);
assert.match(vw, /VR\.zoomAt\(live\.current, factor/); assert.match(vw, /VR\.wheelIntent\(/); assert.match(vw, /setZ\(VR\.navZoom\(\)\)/); assert.match(vw, /VR\.fitSize\(/);
assert.doesNotMatch(vw, /x: px - \(px - o\.x\) \* k/, "local zoom math left in Viewer.tsx");
console.log("test_viewer_rules: ok");
