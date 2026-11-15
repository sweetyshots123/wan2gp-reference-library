// node tests/test_browser_mlwheel.mjs — 1.12.17 (ml-wheel): REAL standalone Media Library AND built Galería in headless Chrome against the
// synthetic mock (tests/browser/server.mjs). Lightbox: wheel = previous/next, "Ajustar" keeps the full-screen size on every
// progressive stage (220 px thumb → 1024 px preview, original 3000×2000), click / Ctrl+wheel zoom keeps the clicked
// image point under the cursor (devicePixelRatio 2), 1:1 wheel pans. Galería (shared viewer_rules.js): wheel steps,
// click / Ctrl+wheel zoom keeps the point, the next item opens in Fit.
// All media generated here with ffmpeg (testsrc); no real data. Skips (exit 0) without google-chrome / ffmpeg.
import assert from "node:assert/strict";
import fs from "node:fs";
import os from "node:os";
import path from "node:path";
import { spawn, spawnSync } from "node:child_process";
import { fileURLToPath } from "node:url";
const root = path.join(path.dirname(fileURLToPath(import.meta.url)), "..");
const has = (cmd) => spawnSync("sh", ["-c", "command -v " + cmd]).status === 0;
if (!has("google-chrome") || !has("ffmpeg") || !fs.existsSync(path.join(root, "gallery/dist/index.html"))) { console.log("test_browser_mlwheel: SKIP (needs google-chrome, ffmpeg)"); process.exit(0); }
const sleep = (ms) => new Promise((r) => setTimeout(r, ms));
const tmp = fs.mkdtempSync(path.join(os.tmpdir(), "reflib-mlwheel-"));
const MEDIA = path.join(tmp, "media"); fs.mkdirSync(MEDIA);
const ff = (size, out) => spawnSync("ffmpeg", ["-v", "error", "-f", "lavfi", "-i", `testsrc=size=${size}:rate=1`, "-frames:v", "1", path.join(MEDIA, out)]);
ff("220x147", "thumb.png"); ff("1024x683", "preview.png");
spawnSync("ffmpeg", ["-v", "error", "-f", "lavfi", "-i", "testsrc=duration=10:size=320x180:rate=25", "-c:v", "libvpx", "-b:v", "300k", path.join(MEDIA, "clip.webm")]);
fs.copyFileSync(path.join(MEDIA, "thumb.png"), path.join(MEDIA, "img.png"));
const VERSION = JSON.parse(fs.readFileSync(path.join(root, "plugin_info.json"), "utf8")).version;
const PORT = 18800 + Math.floor(Math.random() * 90), CDP = 9300 + Math.floor(Math.random() * 90), BASE = `http://127.0.0.1:${PORT}`;
// the "full" file is the 1024 px preview: simulates the original (3000×2000, as the preview reply says) not decoded yet
const srv = spawn(process.execPath, [path.join(root, "tests/browser/server.mjs")], { env: { ...process.env, DIST: path.join(root, "gallery/dist"), PLUGIN: root, VERSION, PORT: String(PORT), MEDIA,
  THUMB: "thumb.png", PREVIEW: "preview.png", FULL: "preview.png", ORIG_W: "3000", ORIG_H: "2000", PREVIEW_DELAY: "1500", QDELAY: "40" }, stdio: ["ignore", "pipe", "inherit"] });
await new Promise((r) => srv.stdout.once("data", r));
process.env.CHROME_PROFILE = path.join(tmp, "chrome");
const { launch } = await import(path.join(root, "tests/browser/cdp.mjs"));
const c = await launch(CDP); const ev = c.ev;
const done = (code) => { try { c.close(); } catch {} srv.kill(); try { fs.rmSync(tmp, { recursive: true, force: true }); } catch {} process.exit(code); };
const post = async (p, b = {}) => (await fetch(BASE + p, { method: "POST", body: JSON.stringify(b) })).json();
async function waitFor(expr, ms = 8000) { const t0 = Date.now(); while (Date.now() - t0 < ms) { try { if (await ev(expr)) return true; } catch {} await sleep(40); } return false; }
const fails = [];
async function check(name, fn) { try { await fn(); console.log("  ok  " + name); } catch (e) { fails.push(name); console.log("  FAIL " + name + ": " + (e && e.message)); } }
await c.send("Emulation.setDeviceMetricsOverride", { width: 1280, height: 900, deviceScaleFactor: 2, mobile: false });
const mouse = (type, x, y, extra = {}) => c.send("Input.dispatchMouseEvent", { type, x, y, button: "none", ...extra });
const wheel = (x, y, dy, mods = 0) => mouse("mouseWheel", x, y, { deltaX: 0, deltaY: dy, modifiers: mods });
const click = async (x, y) => { await mouse("mousePressed", x, y, { button: "left", clickCount: 1 }); await mouse("mouseReleased", x, y, { button: "left", clickCount: 1 }); };
const LB = `document.querySelector('.reflib-ib-lightbox')`;
const st = () => ev(`(() => { const b = ${LB}; if (!b) return null; const i = b.querySelector('.reflib-ib-lbstage img'), s = b.querySelector('.reflib-ib-lbstage'), r = i.getBoundingClientRect(), sr = s.getBoundingClientRect();
  return { idx: +b.dataset.idx, hash: i.dataset.hash, kind: b.dataset.kind, fit: b.classList.contains('fit'), w: r.width, h: r.height, l: r.left, t: r.top, nat: i.naturalWidth, src: i.getAttribute('src') || '',
    sw: s.clientWidth, sh: s.clientHeight, sl: s.scrollLeft, stp: s.scrollTop, dpr: devicePixelRatio, pos: b.querySelector('.reflib-ib-lbpos').textContent }; })()`);
const FIT_H = (s) => Math.min(s.sh - 24, (s.sw - 24) / 1.5);   // 3000×2000 in the stage box minus the old 24 px margins
async function boot() {
  await post("/test/reset");
  await c.send("Page.navigate", { url: BASE + "/reflib/media-library/" });
  if (!await waitFor(`document.querySelectorAll('.reflib-ib-card').length > 5`, 10000)) throw new Error("no cards");
}
// every painted frame of the lightbox <img> (once it has pixels): "never small" is checked on ALL of them, not on a sample
const SAMPLER = `(() => { window.__lbs = []; const f = () => { const b = document.querySelector('.reflib-ib-lightbox'), i = b && b.querySelector('.reflib-ib-lbstage img');
  if (i && !i.hidden && i.complete && i.naturalWidth && b.dataset.kind === 'image' && getComputedStyle(i).visibility !== 'hidden') { const r = i.getBoundingClientRect(), s = b.querySelector('.reflib-ib-lbstage');
    window.__lbs.push({ idx: +b.dataset.idx, nat: i.naturalWidth, fit: b.classList.contains('fit'), w: r.width, h: r.height, sw: s.clientWidth, sh: s.clientHeight }); }
  requestAnimationFrame(f); }; requestAnimationFrame(f); return true; })()`;
async function framesOk(label, minStages = 1) {
  const L = await ev(`window.__lbs.splice(0)`);
  const bad = L.filter((x) => x.fit && Math.abs(x.h - FIT_H(x)) > 3);
  assert.ok(L.length > 0, label + ": no frames");
  assert.equal(bad.length, 0, `${label}: ${bad.length}/${L.length} frames not full-screen, e.g. ${JSON.stringify(bad[0])}`);
  assert.ok(new Set(L.map((x) => x.nat)).size >= minStages, `${label}: stages seen ${[...new Set(L.map((x) => x.nat))]}`);
}
async function openAt(i) {
  await ev(`(() => { document.querySelector('.reflib-ib-card[data-idx="${i}"]').dispatchEvent(new MouseEvent('dblclick', { bubbles: true })); return true; })()`);
  if (!await waitFor(`${LB} && ${LB}.dataset.idx === '${i}'`, 4000)) throw new Error("lightbox not open");
}

console.log("Media Library lightbox (DPR 2)");
await check("open: every painted frame full-screen in Ajustar, thumb 220 px and preview 1024 px stages (old CSS: intrinsic size)", async () => {
  await boot(); await ev(SAMPLER); await openAt(1);
  assert.ok(await waitFor(`${LB}.querySelector('img').naturalWidth === 1024`, 6000), "preview stage");
  await sleep(100);
  const s = await st();
  assert.equal(s.dpr, 2); assert.equal(s.fit, true);
  await framesOk("open (thumb 220 px → preview 1024 px)");   // every painted frame full-screen (the thumb stage may be skipped when its thumbnail is not cached yet)
  assert.ok(Math.abs(s.h - FIT_H(s)) <= 2 && Math.abs(s.w - FIT_H(s) * 1.5) <= 3, `preview stage ${s.w}×${s.h}`);
});
await check("wheel: 1 notch = 1 item, back, fast spin ×3; every landing photo keeps the fit size", async () => {
  const s0 = await st(), cx = 640, cy = 400;
  await wheel(cx, cy, 120); assert.ok(await waitFor(`${LB}.dataset.idx === '2'`, 3000), "next");
  let s = await st(); assert.equal(s.pos.startsWith("3 /"), true);
  await wheel(cx, cy, -120); assert.ok(await waitFor(`${LB}.dataset.idx === '1'`, 3000), "prev");
  for (let k = 0; k < 3; k++) { await wheel(cx, cy, 120); await sleep(15); }
  assert.ok(await waitFor(`${LB}.dataset.idx === '4'`, 3000), "spin ×3 → idx 4, got " + (await st()).idx);
  await sleep(300); assert.equal((await st()).idx, 4, "no extra steps");
  await waitFor(`${LB}.querySelector('img').naturalWidth === 1024`, 6000); await sleep(100);
  await framesOk("wheel steps");
  assert.equal(s0.fit, true);
});
await check("wheel also steps over a video (idx 5 = vid_5) and on to the next photo", async () => {
  await wheel(640, 400, 120); assert.ok(await waitFor(`${LB}.dataset.idx === '5' && ${LB}.dataset.kind === 'video'`, 3000));
  await waitFor(`!!${LB}.querySelector('video.reflib-ib-lbmedia')`, 3000);
  await wheel(640, 300, 120); assert.ok(await waitFor(`${LB}.dataset.idx === '6'`, 3000), "stepped off the video");
  await waitFor(`${LB}.querySelector('img').naturalWidth === 1024`, 6000); await sleep(100);
  assert.equal((await st()).kind, "image"); await framesOk("video → photo");
});
async function pointCheck(s0, s1, cx, cy, label) {
  const fx0 = (cx - s0.l) / s0.w, fy0 = (cy - s0.t) / s0.h, fx1 = (cx - s1.l) / s1.w, fy1 = (cy - s1.t) / s1.h;
  // the same image pixel (in original px) under the cursor, within 1.5 px of the 1:1 image
  assert.ok(Math.abs(fx1 - fx0) * s1.w <= 1.5 && Math.abs(fy1 - fy0) * s1.h <= 1.5, `${label}: ${fx0.toFixed(4)},${fy0.toFixed(4)} → ${fx1.toFixed(4)},${fy1.toFixed(4)}`);
}
await check("click → 1:1 (3000×2000) with the clicked point still under the cursor", async () => {
  await waitFor(`${LB}.querySelector('img').naturalWidth === 1024`, 4000);
  const s0 = await st(); const cx = s0.l + 0.27 * s0.w, cy = s0.t + 0.71 * s0.h;
  await click(cx, cy); await sleep(150);
  const s1 = await st();
  assert.equal(s1.fit, false); assert.ok(Math.abs(s1.w - 3000) <= 1 && Math.abs(s1.h - 2000) <= 2, `1:1 size ${s1.w}×${s1.h}`);
  await pointCheck(s0, s1, cx, cy, "click");
});
await check("1:1: wheel pans (scrolls), does not step; click again → Ajustar", async () => {
  const a = await st(); await wheel(640, 400, 120); await sleep(250);
  const b = await st(); assert.equal(b.idx, a.idx); assert.ok(b.stp > a.stp, `scrollTop ${a.stp} → ${b.stp}`);
  await click(640, 400); await sleep(150); const s = await st(); assert.equal(s.fit, true); assert.ok(Math.abs(s.h - FIT_H(s)) <= 3);
});
await check("Ctrl+wheel up → 1:1 at the cursor (corner point), Ctrl+wheel down → Ajustar", async () => {
  const s0 = await st(); const cx = s0.l + 0.9 * s0.w, cy = s0.t + 0.12 * s0.h;
  await wheel(cx, cy, -120, 2 /* Ctrl */); await sleep(150);
  const s1 = await st(); assert.equal(s1.fit, false); await pointCheck(s0, s1, cx, cy, "ctrl+wheel");
  await wheel(cx, cy, 120, 2); await sleep(150); assert.equal((await st()).fit, true);
});
await check("stepping from 1:1 lands in Ajustar (like the Galería), full-screen sized", async () => {
  await click(640, 400); await sleep(100); assert.equal((await st()).fit, false);
  await ev(`(() => { ${LB}.querySelector('[data-lb="next"]').click(); return true; })()`);
  assert.ok(await waitFor(`${LB}.dataset.idx === '7'`, 3000));
  await waitFor(`${LB}.querySelector('img').naturalWidth === 1024`, 6000); await sleep(100);
  await ev(`window.__lbs.splice(0, window.__lbs.findIndex((x) => x.idx === 7)); true`);   // frames of item 7 only (item 6 was 1:1)
  const s = await st(); assert.equal(s.fit, true); await framesOk("1:1 → step");
  await ev(`document.dispatchEvent(new KeyboardEvent('keydown', { key: 'Escape', bubbles: true })); true`); await sleep(100);
  if (await ev(`!!${LB}`)) await ev(`(() => { ${LB}.querySelector('.reflib-ib-lbclose').click(); return true; })()`);
});

console.log("Galería viewer (DPR 2, shared viewer_rules.js)");
const GI = `document.querySelector('.viewer .stage img:not(.phimg)')`;
const gst = () => ev(`(() => { const i = ${GI}, s = document.querySelector('.viewer .stage'); const r = i ? i.getBoundingClientRect() : null, sr = s.getBoundingClientRect();
  return { count: document.querySelector('.vtop .count')?.textContent || '', zl: document.querySelector('.vbtns .zl')?.textContent || '', l: r && r.left, t: r && r.top, w: r && r.width, h: r && r.height,
    sl: sr.left, st: sr.top, sw: sr.width, sh: sr.height, tf: i ? i.style.transform : '' }; })()`);
async function gBoot() {
  await post("/test/reset");
  await c.send("Page.navigate", { url: BASE + "/reflib/gallery/#/" }); await sleep(300);
  await ev(`localStorage.setItem('gal.sort','date_desc'); localStorage.setItem('gal.kinds','[]'); true`);
  await c.send("Page.reload", { ignoreCache: true }); await sleep(300);
  if (!await waitFor(`document.querySelectorAll('figure.tile').length > 0`, 10000)) throw new Error("no tiles");
  await ev(`document.querySelectorAll('figure.tile')[1].click(); true`, true);   // idx 1 = img_1 (idx 0 is a video)
  if (!await waitFor(`document.querySelector('.vtop .count')?.textContent.startsWith('2 /') && !!${GI}`, 20000)) throw new Error("viewer / full image not shown: " + JSON.stringify(await ev(`({ c: document.querySelector('.vtop .count')?.textContent, st: document.querySelector('.viewer .stage')?.innerHTML.slice(0, 300), href: location.href })`)) + " log " + JSON.stringify((await post("/test/log")).log.slice(-15)));
  await sleep(250);
}
await check("Galería: wheel 1 notch = 1 item, back", async () => {
  await gBoot();
  await wheel(640, 450, 120); assert.ok(await waitFor(`document.querySelector('.vtop .count').textContent.startsWith('3 /')`, 3000), "next");
  await wheel(640, 450, -120); assert.ok(await waitFor(`document.querySelector('.vtop .count').textContent.startsWith('2 /')`, 3000), "prev");
  await waitFor(`!!${GI}`, 20000); await sleep(250);
});
async function gPoint(s0, s1, cx, cy, label) {
  const fx0 = (cx - s0.l) / s0.w, fy0 = (cy - s0.t) / s0.h, fx1 = (cx - s1.l) / s1.w, fy1 = (cy - s1.t) / s1.h;
  assert.ok(s1.w > s0.w * 1.2, `${label}: not zoomed (${s0.w} → ${s1.w})`);
  assert.ok(Math.abs(fx1 - fx0) * s1.w <= 1.5 && Math.abs(fy1 - fy0) * s1.h <= 1.5, `${label}: ${fx0.toFixed(4)},${fy0.toFixed(4)} → ${fx1.toFixed(4)},${fy1.toFixed(4)}`);
}
await check("Galería: click zooms with the clicked point under the cursor", async () => {
  const s0 = await gst(); const cx = s0.l + 0.23 * s0.w, cy = s0.t + 0.68 * s0.h;
  await click(cx, cy); await sleep(350);
  await gPoint(s0, await gst(), cx, cy, "click");
  await click(cx, cy); await sleep(350); assert.equal((await gst()).zl, "100%", "second click = Fit");
});
await check("Galería: Ctrl+wheel zoom keeps the point; the next item opens in Fit", async () => {
  const s0 = await gst(); const cx = s0.l + 0.8 * s0.w, cy = s0.t + 0.2 * s0.h;
  for (let k = 0; k < 3; k++) { await wheel(cx, cy, -120, 2); await sleep(30); }
  await sleep(350);
  await gPoint(s0, await gst(), cx, cy, "ctrl+wheel");
  await ev(`document.body.dispatchEvent(new KeyboardEvent('keydown', { key: 'ArrowRight', bubbles: true })); true`);
  assert.ok(await waitFor(`document.querySelector('.vtop .count').textContent.startsWith('3 /')`, 3000));
  assert.ok(await waitFor(`!!${GI}`, 20000), 'full image'); await sleep(300);
  const s = await gst(); assert.equal(s.zl, "100%"); assert.match(s.tf || "scale(1)", /scale\(1\)/);
});
const errs = c.logs.filter((l) => l.startsWith("EXC"));
if (errs.length) { console.log("page exceptions:", errs.slice(0, 5)); fails.push("page exceptions"); }
console.log(fails.length ? `test_browser_mlwheel: ${fails.length} FAILED` : "test_browser_mlwheel: ok");
done(fails.length ? 1 : 0);
