// Geometry of the 'Caras' overlay (reflib_faces.js): % of the container, object-fit aware, waits for load.
import fs from "fs"; import vm from "vm"; import assert from "assert";
const RL = { extend() {} };
const style = { position: "relative" };
const ctx = { window: { referenceLibrary: RL }, setInterval() {}, getComputedStyle: el => el._cs || style,
  document: { createElement: () => ({ style: {} }), head: { appendChild() {} }, querySelector: () => null, addEventListener() {} } };
ctx.window.ResizeObserver = undefined;
vm.runInNewContext(fs.readFileSync(new URL("../reflib_faces.js", import.meta.url), "utf8"), ctx);
const rect = (l, t, w, h) => ({ left: l, top: t, width: w, height: h });
const box = { clientWidth: 1000, clientHeight: 500, clientLeft: 0, clientTop: 0, getBoundingClientRect: () => rect(100, 50, 1000, 500) };
// img fills the box, object-fit contain, 4:3 picture -> pillarboxed 666.67 x 500 centred
const img = { clientWidth: 1000, clientHeight: 500, naturalWidth: 800, naturalHeight: 600, complete: true, _cs: { objectFit: "contain" },
  getBoundingClientRect: () => rect(100, 50, 1000, 500) };
const near = (a, b) => assert.ok(Math.abs(a - b) < 1e-6, a + " != " + b);
let r = RL.facesRect(img, box);
near(r.width, 66.66666666666667); near(r.height, 100); near(r.left, 16.666666666666664); near(r.top, 0);
// resize: values stay relative, recomputed for the new size (landscape box -> letterbox)
Object.assign(box, { clientWidth: 400, clientHeight: 600, getBoundingClientRect: () => rect(0, 0, 400, 600) });
Object.assign(img, { clientWidth: 400, clientHeight: 600, getBoundingClientRect: () => rect(0, 0, 400, 600) });
r = RL.facesRect(img, box); near(r.width, 100); near(r.height, 50); near(r.top, 25); near(r.left, 0);
// placement + not loaded yet -> hidden until load
const ov = { style: {} };
RL.facesPlace(ov, img, box); assert.equal(ov.style.visibility, ""); assert.equal(ov.style.top, "25%");
RL.facesPlace(ov, { ...img, complete: false }, box); assert.equal(ov.style.visibility, "hidden");
// zero-size box (hidden / fullscreen transition) -> no NaN
assert.equal(RL.facesRect(img, { ...box, clientWidth: 0 }), null);
console.log("test_faces_overlay passed");
