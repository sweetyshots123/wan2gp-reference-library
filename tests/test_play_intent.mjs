// node tests/test_play_intent.mjs — 1.12.14: play intent around Vidosser's pause-for-capture (shared rule, real code:
// frame_capture_rules.js + the Galería wrapper gallery/src/frameCapture.ts). Synthetic fake <video> only.
import assert from "node:assert/strict";
import path from "node:path";
import { fileURLToPath } from "node:url";
const root = path.join(path.dirname(fileURLToPath(import.meta.url)), "..");
let NOW = 1000;
globalThis.performance = { now: () => NOW };
const { FrameCap, trackWantPlay, wasWantPlay } = await import(path.join(root, "gallery/src/frameCapture.ts"));
const FC = globalThis.ReflibFrameCapture;
assert.equal(FrameCap, FC);
assert.equal(FC.version, 3);

class FakeVideo extends EventTarget {
  constructor() { super(); this.paused = true; this.ended = false; }
  play() { this.paused = false; this.dispatchEvent(new Event("play")); }
  pause() { if (!this.paused) { this.paused = true; this.dispatchEvent(new Event("pause")); } }
}
for (const [label, track, want] of [["Galería wrapper", trackWantPlay, wasWantPlay], ["shared rule", (v) => FC.trackIntent(v), (v) => FC.wantPlay(v)]]) {
  // BUG-1 (1.12.13): autoplay → user pauses → >2 s later Vidosser captures → must stay paused
  const v = new FakeVideo(); const off = track(v);
  v.play(); NOW += 5000; v.pause(); NOW += 2600;
  assert.equal(want(v), false, label + ": user pause older than 2 s → do not resume");
  // playing → Vidosser pauses for the frame → resume
  v.play(); NOW += 3000; v.pause(); NOW += 300;
  assert.equal(want(v), true, label + ": Vidosser's own pause (<2 s) → resume");
  // still playing (no pause at all)
  v.play(); NOW += 10000;
  assert.equal(want(v), true, label + ": playing");
  off();
  // never played (autoplay blocked)
  const w = new FakeVideo(); track(w); NOW += 9000;
  assert.equal(want(w), false, label + ": never played");
  // attached while already playing (effect re-attaches every render)
  const x = new FakeVideo(); x.paused = false; track(x);
  assert.equal(want(x), true, label + ": attached while playing");
}
// 1.12.13 regression shape: the flag must be cleared by a pause
{ const v = new FakeVideo(); FC.trackIntent(v); v.play(); v.pause(); assert.equal(v._reflibWantPlay, false); }
console.log("test_play_intent: ok");
