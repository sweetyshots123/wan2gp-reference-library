// node tests/test_frame_capture_rules.mjs — stay on video after frame capture
import assert from "node:assert/strict";
import path from "node:path";
import { fileURLToPath } from "node:url";
const root = path.join(path.dirname(fileURLToPath(import.meta.url)), "..");
await import(path.join(root, "frame_capture_rules.js"));
const FC = globalThis.ReflibFrameCapture;
assert.equal(FC.version, 3);   // 1.12.13: + pinFollow / pinLocate / sameOpen; 1.12.14: + play intent
assert.equal(FC.EVENT, "vidosser:frame-saved");
assert.equal(FC.shouldNavigate({ hash: "abc", name: "x.png" }), false);
assert.equal(FC.stayHash("videoHash", { hash: "frameHash" }), "videoHash");
assert.equal(FC.stayHash(null, { hash: "frameHash" }), null);
assert.equal(FC.resumePlayback(true), true);
assert.equal(FC.resumePlayback(false), false);
assert.match(FC.toastText({ name: "a.png" }, "es"), /Fotograma/);
assert.match(FC.toastText({ name: "a.png" }, "en"), /Frame saved/);
assert.deepEqual(FC.keepOpen("vh", { hash: "fh" }), { navigate: false, hash: "vh", toast: true });
console.log("test_frame_capture_rules: ok");
