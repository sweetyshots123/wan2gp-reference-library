// node tests/test_wheel_rules.mjs — wheel_rules.js: 1 notch = exactly 1 photo
import assert from "node:assert/strict";
import path from "node:path";
import { fileURLToPath } from "node:url";
const root = path.join(path.dirname(fileURLToPath(import.meta.url)), "..");
await import(path.join(root, "wheel_rules.js"));
const W = globalThis.ReflibWheel;
// events: [deltaY, deltaMode, dtMs]
function run(evs, w = W.create()) { let t = 1000, out = []; for (const [d, m, dt] of evs) { t += dt ?? 16; out.push(w.push(d, m, t)); } return out; }
const sum = a => a.reduce((s, x) => s + x, 0);
// Windows 120 px notches, slow and fast: every notch = 1 (old 100 px step drifted: 5 notches -> 6 photos)
assert.deepEqual(run(Array(10).fill([120, 0, 200])), Array(10).fill(1));
assert.deepEqual(run(Array(10).fill([120, 0, 30])), Array(10).fill(1));
// 100 px notches
assert.deepEqual(run(Array(7).fill([100, 0, 40])), Array(7).fill(1));
assert.deepEqual(run(Array(4).fill([-100, 0, 40])), Array(4).fill(-1));
// display scaling 150 px notches, no drift
assert.equal(sum(run(Array(9).fill([150, 0, 40]))), 9);
// fractional notch (Chrome zoom: 119.99999 / 133.33333)
assert.equal(sum(run(Array(30).fill([133.33333, 0, 30]))), 30);
// Firefox LINE mode: 3 lines per notch
assert.deepEqual(run(Array(5).fill([3, 1, 40])), Array(5).fill(1));
// PAGE mode
assert.deepEqual(run([[1, 2, 40], [1, 2, 40]]), [1, 1]);
// fast spin: one coalesced event worth N notches -> N steps, then calibrated notches keep working
assert.deepEqual(run([[360, 0, 10], [120, 0, 10], [240, 0, 10]]), [3, 1, 2]);
assert.deepEqual(run([[300, 0, 10], [100, 0, 10]]), [3, 1]);
// fast spin of 40 notches at 8 ms: no throttling, all 40 applied
assert.equal(sum(run(Array(40).fill([120, 0, 8]))), 40);
// direction change: remainder dropped, the new direction steps on its own first notch
{ const w = W.create(); run([[120, 0]], w);
  assert.deepEqual(run([[40, 0, 20], [-120, 0, 20], [-120, 0, 20], [120, 0, 20]], w), [0, -1, -1, 1]); }
// trackpad (small pixel deltas) with a calibrated 120 notch: 1 step per 120 px of travel, remainder kept
{ const w = W.create(); run([[120, 0]], w);
  const r = run(Array(30).fill([8, 0, 16]), w);   // 240 px
  assert.equal(sum(r), 2); assert.ok(r.every(x => x <= 1)); }
// trackpad, uncalibrated: default 100 px notch
assert.equal(sum(run(Array(25).fill([4, 0, 16]))), 1);
// idle > 150 ms resets the remainder (40 + idle + 40 = 40 kept, then +40 +40 = one notch)
{ const w = W.create(); run([[120, 0]], w);
  assert.deepEqual(run([[40, 0, 20], [40, 0, 400]], w), [0, 0]);
  assert.deepEqual(run([[40, 0, 20], [40, 0, 20], [40, 0, 20]], w), [0, 1, 0]); }
// a small event never lowers the pixel notch below NOTCH_MIN
{ const w = W.create(); run([[120, 0], [3, 0], [120, 0, 200]], w); assert.equal(w.notch(0), 120); }
console.log("wheel_rules: all tests passed");
