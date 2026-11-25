// node tests/test_browser_standalone_notice.mjs — standalone Media Library page banner
// ("Media Library independiente…") shows once and never overlaps the search/reset row.
// Synthetic fixtures only. Skips cleanly if google-chrome/ffmpeg missing.
import assert from "node:assert/strict";
import fs from "node:fs";
import os from "node:os";
import path from "node:path";
import { spawn, spawnSync } from "node:child_process";
import { fileURLToPath } from "node:url";

const root = path.join(path.dirname(fileURLToPath(import.meta.url)), "..");
const has = (cmd) => spawnSync("sh", ["-c", "command -v " + cmd]).status === 0;
if (!has("google-chrome") || !has("ffmpeg")) {
  console.log("test_browser_standalone_notice: SKIP (needs google-chrome, ffmpeg)");
  process.exit(0);
}

const DIST = path.join(root, "gallery/dist");
const VERSION = JSON.parse(fs.readFileSync(path.join(root, "plugin_info.json"), "utf8")).version;
const SHOTS = process.env.SHOTS || "";
const tmp = fs.mkdtempSync(path.join(os.tmpdir(), "reflib-stand-notice-"));
const MEDIA = path.join(tmp, "media");
fs.mkdirSync(MEDIA);
spawnSync("ffmpeg", ["-v", "error", "-f", "lavfi", "-i", "testsrc=size=160x120:rate=1", "-frames:v", "1", path.join(MEDIA, "img.png")]);
spawnSync("ffmpeg", ["-v", "error", "-f", "lavfi", "-i", "testsrc=duration=2:size=160x90:rate=10", "-c:v", "libvpx", path.join(MEDIA, "clip.webm")]);

const { freePort } = await import(path.join(root, "tests/browser/ports.mjs"));
const PORT = await freePort();
let CDP = await freePort();
while (CDP === PORT) CDP = await freePort();
const BASE = `http://127.0.0.1:${PORT}`;

const srv = spawn(process.execPath, [path.join(root, "tests/browser/server.mjs")], {
  env: { ...process.env, DIST, PLUGIN: root, VERSION, PORT: String(PORT), MEDIA, MOCK_CHIPS: "8", MOCK_COLS: "3", QDELAY: "20" },
  stdio: ["ignore", "pipe", "inherit"],
});
const sleep = (ms) => new Promise((r) => setTimeout(r, ms));
process.on("exit", () => { try { srv.kill(); } catch {} });
await new Promise((r) => srv.stdout.once("data", r));

process.env.CHROME_PROFILE = path.join(tmp, "chrome");
const { launch } = await import(path.join(root, "tests/browser/cdp.mjs"));
const c = await launch(CDP);
const ev = c.ev;
const done = (code) => { try { c.close(); } catch {} try { srv.kill(); } catch {} try { fs.rmSync(tmp, { recursive: true, force: true }); } catch {} process.exit(code); };
async function waitFor(expr, ms = 12000) {
  const t0 = Date.now();
  while (Date.now() - t0 < ms) {
    try { if (await ev(expr)) return true; } catch {}
    await sleep(50);
  }
  return false;
}
async function shot(name) {
  if (!SHOTS) return;
  fs.mkdirSync(SHOTS, { recursive: true });
  const r = await c.send("Page.captureScreenshot", { format: "png" });
  fs.writeFileSync(path.join(SHOTS, `${name}.png`), Buffer.from(r.result.data, "base64"));
}

const rectsExpr = `(() => {
  const box = (el) => {
    if (!el) return null;
    const r = el.getBoundingClientRect();
    const st = getComputedStyle(el);
    return {
      x: r.x, y: r.y, w: r.width, h: r.height,
      top: r.top, right: r.right, bottom: r.bottom, left: r.left,
      display: st.display, visibility: st.visibility, hidden: !!(el.hidden || st.display === "none" || r.width <= 0 || r.height <= 0),
    };
  };
  const overlap = (a, b) => !!(a && b && !a.hidden && !b.hidden && !(a.right <= b.left || a.left >= b.right || a.bottom <= b.top || a.top >= b.bottom));
  const tip = document.querySelector(".reflib-standalone-tip");
  const q = document.querySelector(".reflib-ib-q");
  const reset = document.querySelector(".reflib-ib-reset");
  const head = document.querySelector(".reflib-ib-head");
  const tb = box(tip), qb = box(q), rb = box(reset), hb = box(head);
  return {
    tipText: tip ? String(tip.textContent || "") : "",
    tip: tb, q: qb, reset: rb, head: hb,
    overlapSearch: overlap(tb, qb),
    overlapReset: overlap(tb, rb),
    overlapHead: overlap(tb, hb),
    flag: (() => { try { return localStorage.getItem("reflib_standalone_notice_seen"); } catch (e) { return null; } })(),
  };
})()`;

try {
  await c.send("Emulation.setDeviceMetricsOverride", { width: 1280, height: 800, deviceScaleFactor: 1, mobile: false });
  await c.send("Page.navigate", { url: BASE + "/reflib/media-library/" });
  assert.ok(await waitFor(`!!document.querySelector('.reflib-ib-q')`, 12000), "standalone ML did not boot");
  await ev(`localStorage.clear(); true`);
  await c.send("Page.reload", { ignoreCache: true });
  assert.ok(await waitFor(`!!document.querySelector('.reflib-standalone-tip') && !!document.querySelector('.reflib-ib-q')`, 12000), "first load did not show the standalone notice");

  // Make Restablecer filtros visible so we can assert it is not covered
  await ev(`(() => {
    const q = document.querySelector('.reflib-ib-q');
    if (!q) return false;
    q.value = 'img_';
    q.dispatchEvent(new Event('input', { bubbles: true }));
    return true;
  })()`);
  assert.ok(await waitFor(`!!document.querySelector('.reflib-ib-reset') && !document.querySelector('.reflib-ib-reset').hidden`, 6000), "reset button did not appear after search");
  await sleep(80);

  const first = await ev(rectsExpr);
  assert.ok(first.tip && !first.tip.hidden, "notice missing or not visible on first load");
  assert.match(first.tipText, /Media Library independiente|Standalone Media Library/);
  assert.ok(first.q && !first.q.hidden, "search field missing");
  assert.ok(first.reset && !first.reset.hidden, "reset button missing or hidden");
  assert.equal(first.overlapSearch, false, "notice overlaps the search field: " + JSON.stringify({ tip: first.tip, q: first.q }));
  assert.equal(first.overlapReset, false, "notice overlaps Restablecer filtros: " + JSON.stringify({ tip: first.tip, reset: first.reset }));
  assert.equal(first.overlapHead, false, "notice overlaps the header/search row: " + JSON.stringify({ tip: first.tip, head: first.head }));
  assert.equal(first.flag, "1", "localStorage flag not set after first show");
  await shot("standalone-notice-first-load");
  console.log("  ok  first load shows the notice without overlapping search/reset");

  await c.send("Page.reload", { ignoreCache: true });
  assert.ok(await waitFor(`!!document.querySelector('.reflib-ib-q') && document.readyState === 'complete'`, 12000), "reload did not boot");
  await sleep(200);
  const again = await ev(rectsExpr);
  assert.ok(!again.tip || again.tip.hidden, "notice should not show after reload, got " + JSON.stringify(again.tip));
  const tipLeft = await ev(`!!document.querySelector('.reflib-standalone-tip')`);
  assert.equal(tipLeft, false, "notice element still in the DOM after reload");
  assert.equal(again.flag, "1");
  await shot("standalone-notice-reload");
  console.log("  ok  reload does not show the notice");
  console.log("test_browser_standalone_notice: ok");
  done(0);
} catch (e) {
  console.error("test_browser_standalone_notice FAIL:", e && e.message);
  done(1);
}
