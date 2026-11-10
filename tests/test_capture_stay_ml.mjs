// node tests/test_capture_stay_ml.mjs — 1.12.13: Media Library parity for "stay on the video after a frame capture".
// Synthetic / static only. Fails on 1.12.12 (re-anchor re-opened the lightbox = new <video>; renderPreview rebuilt it).
import assert from "node:assert/strict";
import fs from "node:fs";
import path from "node:path";
import { fileURLToPath } from "node:url";
const root = path.join(path.dirname(fileURLToPath(import.meta.url)), "..");
await import(path.join(root, "frame_capture_rules.js"));
const FC = globalThis.ReflibFrameCapture;
assert.equal(typeof FC.sameOpen, "function");
assert.equal(FC.sameOpen("abc", "abc"), true);
assert.equal(FC.sameOpen("abc", "frame"), false);
assert.equal(FC.sameOpen(null, "abc"), false);
assert.equal(FC.shouldNavigate({ hash: "frame", stay: true }), false);

const js = fs.readFileSync(path.join(root, "reference_library.js"), "utf8");
const stay = js.slice(js.indexOf("(function frameCaptureStay()"), js.indexOf("function restoreMedia(p)"));
assert.ok(stay.length > 100);
// same item → re-index only, never openLightbox()/showPreview() for it
assert.match(stay, /if \(lbSame\) \{ reindexLightbox\(box, idx\); restoreMedia\(pin\); return; \}/);
assert.match(stay, /FC\.sameOpen\(ilib\.preview, keep\)\) \{[^\n]*restoreMedia\(pin\); return; \}/);
assert.ok(stay.indexOf("lbSame") < stay.indexOf("openLightbox(idx)"), "re-index check before any re-open");
// server index after insert
assert.match(stay, /sendIlib\(\{ action: "index_of", f: filterSnap\(\), hash: keep \}\)/);
// preview-pane video survives a re-render of the same item
const rp = js.slice(js.indexOf("function renderPreview()"), js.indexOf("// ---- selection footer"));
assert.match(rp, /const keepVid = /);
assert.match(rp, /if \(n !== oldImg\) n\.remove\(\)/, "old <video> container never detached");
assert.match(rp, /class="reflib-ib-pvmedia" data-hash=/);
// play intent for the preview video
assert.match(js, /contains\("reflib-ib-pvmedia"\) && window\.ReflibFrameCapture\) ReflibFrameCapture\.notePlay\(m\)/);
// 1.12.14: body rebuild keeps the details host in place (behaviour covered for real in test_browser_capture.mjs)
assert.match(js, /replaceKeeping\(body, /);
console.log("test_capture_stay_ml: ok");
