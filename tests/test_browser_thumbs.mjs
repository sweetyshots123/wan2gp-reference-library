// node tests/test_browser_thumbs.mjs — 1.12.17: after a long / fast scroll the thumbnails on screen load first.
// Galería (built dist) + standalone Media Library in headless Chrome against tests/browser/server.mjs with 20 000
// synthetic items and simulated slow thumbnails (THUMB_MS per hash, 2 server workers). Measures time-to-visible-thumbs
// after a big scroll and how many thumbnails were requested. Synthetic only. Skips without google-chrome / ffmpeg / dist.
// THUMB_DIST=<other gallery/dist> measures another build (used for the before/after numbers; no assertions then).
import assert from "node:assert/strict";
import fs from "node:fs";
import os from "node:os";
import path from "node:path";
import { spawn, spawnSync } from "node:child_process";
import { fileURLToPath } from "node:url";
const root = path.join(path.dirname(fileURLToPath(import.meta.url)), "..");
const has = (cmd) => spawnSync("sh", ["-c", "command -v " + cmd]).status === 0;
const DIST = process.env.THUMB_DIST || path.join(root, "gallery/dist"), MEASURE_ONLY = !!process.env.THUMB_DIST;
const PLUGIN = process.env.THUMB_PLUGIN || root;
if (!has("google-chrome") || !has("ffmpeg") || !fs.existsSync(path.join(DIST, "index.html"))) { console.log("test_browser_thumbs: SKIP"); process.exit(0); }
const sleep = (ms) => new Promise((r) => setTimeout(r, ms));
const tmp = fs.mkdtempSync(path.join(os.tmpdir(), "reflib-th-"));
const MEDIA = path.join(tmp, "media"); fs.mkdirSync(MEDIA);
spawnSync("ffmpeg", ["-v", "error", "-f", "lavfi", "-i", "testsrc=duration=2:size=160x90:rate=10", "-c:v", "libvpx", "-b:v", "100k", path.join(MEDIA, "clip.webm")]);
spawnSync("ffmpeg", ["-v", "error", "-f", "lavfi", "-i", "color=c=red:s=64x64", "-frames:v", "1", path.join(MEDIA, "img.png")]);
const VERSION = JSON.parse(fs.readFileSync(path.join(root, "plugin_info.json"), "utf8")).version;
const { freePort } = await import(path.join(root, "tests/browser/ports.mjs"));
const PORT = await freePort(); let CDP = await freePort(); while (CDP === PORT) CDP = await freePort();
const BASE = `http://127.0.0.1:${PORT}`;
const srv = spawn(process.execPath, [path.join(root, "tests/browser/server.mjs")], { env: { ...process.env, DIST, PLUGIN, VERSION, PORT: String(PORT), MEDIA, QDELAY: "40", N_ITEMS: "20000", THUMB_MS: "12", THUMB_CONC: "2" }, stdio: ["ignore", "pipe", "inherit"] });
process.on("exit", () => { try { srv.kill(); } catch {} });   // 1.12.18: never leave the mock running (it holds the runner's stderr)
await new Promise((r) => srv.stdout.once("data", r));
process.env.CHROME_PROFILE = path.join(tmp, "chrome");
const { launch } = await import(path.join(root, "tests/browser/cdp.mjs"));
const c = await launch(CDP); const ev = c.ev;
const done = (code) => { try { c.close(); } catch {} srv.kill(); try { fs.rmSync(tmp, { recursive: true, force: true }); } catch {} process.exit(code); };
const post = async (p, b = {}) => (await fetch(BASE + p, { method: "POST", body: JSON.stringify(b) })).json();
async function waitFor(expr, ms = 8000) { const t0 = Date.now(); while (Date.now() - t0 < ms) { try { if (await ev(expr)) return true; } catch {} await sleep(50); } return false; }
const fails = [], report = {};
async function check(name, fn) { try { await fn(); console.log("  ok  " + name); } catch (e) { fails.push(name); console.log("  FAIL " + name + ": " + (e && e.message)); } }

// a long fast scroll: ~1.2 viewports every 40 ms for 2.5 s (tiles mount and unmount), then stop
const FLING = (scroller) => `(async () => { const s = ${scroller}; const t0 = performance.now();
  while (performance.now() - t0 < 2500) { s.scrollBy(0, innerHeight * 1.2); await new Promise((r) => setTimeout(r, 40)); } return true; })()`;
async function timeToVisible(expr, ms) { const t0 = Date.now(); while (Date.now() - t0 < ms) { const r = await ev(expr); if (r && r.n > 0 && r.ok === r.n) return { ms: Date.now() - t0, n: r.n }; await sleep(50); }
  const r = await ev(expr); return { ms: null, n: r && r.n, ok: r && r.ok }; }

console.log("Galería, 20 000 items, slow thumbnails");
await check("long fast scroll: visible tiles get their thumbnails quickly; tiles scrolled past are not all requested", async () => {
  await post("/test/reset");
  await c.send("Page.navigate", { url: BASE + "/reflib/gallery/#/" }); await sleep(300);
  await ev(`localStorage.setItem('gal.sort','date_desc'); localStorage.setItem('gal.kinds','[]'); localStorage.setItem('gal.size','160'); true`);
  await c.send("Page.reload", { ignoreCache: true });
  if (!await waitFor(`document.querySelectorAll('figure.tile').length > 5`, 15000)) throw new Error("no tiles");
  await waitFor(`[...document.querySelectorAll('figure.tile')].filter(f => f.getBoundingClientRect().top < innerHeight).every(f => f.querySelector('img'))`, 20000);
  await post("/test/thumblog", { clear: true });
  await ev(FLING("window"));
  const vis = `(() => { const t = [...document.querySelectorAll('.vcell')].filter(e => { const r = e.getBoundingClientRect(); return r.bottom > 0 && r.top < innerHeight; });
    return { n: t.length, ok: t.filter(e => { const i = e.querySelector('figure.tile img'); return i && i.complete; }).length }; })()`;
  const r = await timeToVisible(vis, 60000);
  const sent = (await post("/test/thumblog")).hashes.length;
  report.gal = { ttvMs: r.ms, visible: r.n, thumbsRequested: sent };
  console.log("    Galería: time to visible thumbs " + r.ms + " ms (" + r.n + " tiles), thumbnails requested during/after the scroll: " + sent);
  if (MEASURE_ONLY) return;
  assert.ok(r.ms != null && r.ms < 5000, "visible thumbs within 5 s: " + JSON.stringify(r));
  assert.ok(sent < 900, "tiles scrolled past are dropped, not all requested: " + sent);
});

{
  console.log("Media Library, 20 000 items, slow thumbnails");
  await check("ML long fast scroll: visible cards get their thumbnails quickly", async () => {
    await post("/test/reset");
    await c.send("Page.navigate", { url: BASE + "/reflib/media-library/" });
    if (!await waitFor(`document.querySelectorAll('.reflib-ib-card').length > 5`, 15000)) throw new Error("no cards");
    await sleep(1500); await post("/test/thumblog", { clear: true });
    await ev(FLING(`document.querySelector('.reflib-ib-main')`));
    const vis = `(() => { const m = document.querySelector('.reflib-ib-main').getBoundingClientRect(); const t = [...document.querySelectorAll('.reflib-ib-card')].filter(e => { const r = e.getBoundingClientRect(); return r.bottom > m.top && r.top < m.bottom; });
      return { n: t.length, ok: t.filter(e => { const i = e.querySelector('.reflib-ib-thumb img'); return i && i.complete; }).length }; })()`;
    const r = await timeToVisible(vis, 60000);
    const sent = (await post("/test/thumblog")).hashes.length;
    report.ml = { ttvMs: r.ms, visible: r.n, thumbsRequested: sent };
    console.log("    Media Library: time to visible thumbs " + r.ms + " ms (" + r.n + " cards), thumbnails requested: " + sent);
    if (MEASURE_ONLY) return;
    assert.ok(r.ms != null && r.ms < 5000, "visible thumbs within 5 s: " + JSON.stringify(r));
  });
}
const ex = c.logs.filter((l) => l.startsWith("EXC ")); if (ex.length) { console.log(ex.slice(0, 5)); fails.push("exceptions"); }
console.log("THUMBS_REPORT " + JSON.stringify(report));
console.log(fails.length ? `test_browser_thumbs: ${fails.length} FAILED` : "test_browser_thumbs: all OK");
done(fails.length ? 1 : 0);
