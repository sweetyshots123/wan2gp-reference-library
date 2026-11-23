// node tests/test_browser_chips.mjs — compact chip rows in the REAL standalone Media Library and the built Galería
// (headless Chrome, synthetic mock tests/browser/server.mjs with 80 synthetic tags + 24 synthetic collections).
// Measures the height of the chip area at 1280 / 1920 px; checks +N, filter field, active chip visible while
// collapsed, most-used order, ~3-line cap with inner scroll, open state remembered after reload.
// MEASURE_ONLY=1 just prints the heights (used on the old code for the "before" numbers); SHOTS=dir saves screenshots.
// Skips (exit 0) without google-chrome / ffmpeg / gallery/dist. No real data anywhere.
import assert from "node:assert/strict";
import fs from "node:fs";
import os from "node:os";
import path from "node:path";
import { spawn, spawnSync } from "node:child_process";
import { fileURLToPath } from "node:url";
const root = path.join(path.dirname(fileURLToPath(import.meta.url)), "..");
const has = (cmd) => spawnSync("sh", ["-c", "command -v " + cmd]).status === 0;
const DIST = path.join(root, "gallery/dist");
if (!has("google-chrome") || !has("ffmpeg") || !fs.existsSync(path.join(DIST, "index.html"))) { console.log("test_browser_chips: SKIP (needs google-chrome, ffmpeg, gallery/dist)"); process.exit(0); }
const MEASURE_ONLY = !!process.env.MEASURE_ONLY, SHOTS = process.env.SHOTS || "", TAG = process.env.SHOT_TAG || "after";
const sleep = (ms) => new Promise((r) => setTimeout(r, ms));
const tmp = fs.mkdtempSync(path.join(os.tmpdir(), "reflib-chips-"));
const MEDIA = path.join(tmp, "media"); fs.mkdirSync(MEDIA);
spawnSync("ffmpeg", ["-v", "error", "-f", "lavfi", "-i", "testsrc=size=160x120:rate=1", "-frames:v", "1", path.join(MEDIA, "img.png")]);
spawnSync("ffmpeg", ["-v", "error", "-f", "lavfi", "-i", "testsrc=duration=2:size=160x90:rate=10", "-c:v", "libvpx", path.join(MEDIA, "clip.webm")]);
const VERSION = JSON.parse(fs.readFileSync(path.join(root, "plugin_info.json"), "utf8")).version;
const PORT = 18700 + Math.floor(Math.random() * 90), CDP = 9200 + Math.floor(Math.random() * 90), BASE = `http://127.0.0.1:${PORT}`;
const srv = spawn(process.execPath, [path.join(root, "tests/browser/server.mjs")], { env: { ...process.env, DIST, PLUGIN: root, VERSION, PORT: String(PORT), MEDIA, MOCK_CHIPS: "80", MOCK_COLS: "24", QDELAY: "30" }, stdio: ["ignore", "pipe", "inherit"] });
await new Promise((r) => srv.stdout.once("data", r));
process.env.CHROME_PROFILE = path.join(tmp, "chrome");
const { launch } = await import(path.join(root, "tests/browser/cdp.mjs"));
const c = await launch(CDP); const ev = c.ev;
const done = (code) => { try { c.close(); } catch {} srv.kill(); try { fs.rmSync(tmp, { recursive: true, force: true }); } catch {} process.exit(code); };
const post = async (p, b = {}) => (await fetch(BASE + p, { method: "POST", body: JSON.stringify(b) })).json();
async function waitFor(expr, ms = 8000) { const t0 = Date.now(); while (Date.now() - t0 < ms) { try { if (await ev(expr)) return true; } catch {} await sleep(50); } return false; }
const fails = [];
async function check(name, fn) { try { await fn(); console.log("  ok  " + name); } catch (e) { fails.push(name); console.log("  FAIL " + name + ": " + (e && e.message)); } }
const size = (w) => c.send("Emulation.setDeviceMetricsOverride", { width: w, height: 1000, deviceScaleFactor: 1, mobile: false });
async function shot(name) { if (!SHOTS) return; fs.mkdirSync(SHOTS, { recursive: true }); const r = await c.send("Page.captureScreenshot", { format: "png" }); fs.writeFileSync(path.join(SHOTS, `${name}-${TAG}.png`), Buffer.from(r.result.data, "base64")); }
const H = (sel) => ev(`(() => { const e = document.querySelector(${JSON.stringify(sel)}); return e ? Math.round(e.getBoundingClientRect().height) : null; })()`);
async function mlBoot(clearLs = true) {
  await post("/test/reset");
  await c.send("Page.navigate", { url: BASE + "/reflib/media-library/" });
  if (clearLs) { await waitFor(`document.readyState === 'complete'`); await ev(`localStorage.clear(); true`); await c.send("Page.reload", { ignoreCache: true }); }
  if (!await waitFor(`document.querySelectorAll('.reflib-ib-card').length > 3 && document.querySelectorAll('.reflib-ib-filters .reflib-ib-chip').length > 50`, 10000)) throw new Error("no cards / chips");
  await sleep(300);
}
const heights = {};
console.log("Media Library");
for (const w of [1280, 1920]) {
  await check(`chip area height at ${w} px`, async () => {
    await size(w); await mlBoot();
    // Wait for cards after the resize; at 1920 px a layout pass can precede the grid (peer flake).
    assert.ok(await waitFor(`document.querySelectorAll('.reflib-ib-card').length > 3`, 8000), "no cards before measure at " + w);
    const h = await H(".reflib-ib-filters"); heights["ml_" + w] = h; console.log(`    ML .reflib-ib-filters height @${w}: ${h}px`);
    await shot(`ml-${w}`);
    if (!MEASURE_ONLY) assert.ok(h <= 70, `collapsed rows should be ~2 lines, got ${h}px`);
  });
}
if (!MEASURE_ONLY) {
  await check("+N toggle, filter field, most used first, people grouped without prefix", async () => {
    await size(1280); await mlBoot();
    const s = await ev(`(() => { const r = document.querySelector('.reflib-ib-chiprow[data-row="tags"]'), b = r.querySelector('.reflib-ib-chipmore');
      const ch = [...r.querySelectorAll('.reflib-ib-chip')]; const plain = ch.filter((x) => !x.classList.contains('people')).map((x) => +x.querySelector('i').textContent);
      return { more: b.hidden ? null : b.textContent, n: ch.length, plain, people: ch.filter((x) => x.classList.contains('people')).map((x) => x.textContent), grp: !!r.querySelector('.reflib-ib-chipgrp') }; })()`);
    assert.equal(s.n, 80); assert.match(s.more || "", /^\+\d+$/); assert.ok(+s.more.slice(1) > 40, s.more);
    for (let i = 1; i < s.plain.length; i++) assert.ok(s.plain[i] <= s.plain[i - 1], "plain tags not by count");
    assert.ok(s.people.length >= 20 && s.people.every((t) => !/persona:|modelo:/i.test(t)), "people prefix shown"); assert.ok(s.grp);
    await ev(`(() => { const i = document.querySelector('.reflib-ib-chipq[data-row="tags"]'); i.focus(); i.value = 'Persona 4'; i.dispatchEvent(new Event('input', { bubbles: true })); return true; })()`);
    const vis = await ev(`[...document.querySelectorAll('.reflib-ib-chiprow[data-row="tags"] .reflib-ib-chip:not([hidden])')].map((x) => x.title)`);
    assert.ok(vis.length >= 1 && vis.every((t) => /persona 4/i.test(t)), JSON.stringify(vis));
  });
  await check("active chip (a rare one) stays visible on the first line while collapsed", async () => {
    await ev(`(() => { [...document.querySelectorAll('.reflib-ib-chiprow[data-row="tags"] .reflib-ib-chip:not([hidden])')].pop().click(); return true; })()`);
    assert.ok(await waitFor(`!!document.querySelector('.reflib-ib-chiprow[data-row="tags"] .reflib-ib-chip.on')`, 4000));
    await ev(`(() => { const i = document.querySelector('.reflib-ib-chipq[data-row="tags"]'); i.value = ''; i.dispatchEvent(new Event('input', { bubbles: true })); return true; })()`); await sleep(300);
    const s = await ev(`(() => { const box = document.querySelector('.reflib-ib-chiprow[data-row="tags"] .reflib-ib-chipbox'), on = box.querySelector('.reflib-ib-chip.on'), b = box.getBoundingClientRect(), r = on.getBoundingClientRect();
      return { first: box.querySelector('.reflib-ib-chip') === on, inside: r.top >= b.top - 1 && r.bottom <= b.bottom + 1 }; })()`);
    assert.ok(s.first && s.inside, JSON.stringify(s));
  });
  await check("expand: ~3 lines with inner scroll; remembered after reload; collapse", async () => {
    await ev(`(() => { document.querySelector('.reflib-ib-chiprow[data-row="tags"] .reflib-ib-chipmore').click(); return true; })()`); await sleep(200);
    const s = await ev(`(() => { const box = document.querySelector('.reflib-ib-chiprow[data-row="tags"] .reflib-ib-chipbox'); return { h: box.clientHeight, sh: box.scrollHeight, t: document.querySelector('.reflib-ib-chiprow[data-row="tags"] .reflib-ib-chipmore').textContent }; })()`);
    assert.ok(s.h <= 84 && s.h >= 70 && s.sh > s.h, JSON.stringify(s)); assert.equal(s.t, "−");
    heights.ml_open_1280 = await H(".reflib-ib-filters"); console.log(`    ML expanded tags row: filters height ${heights.ml_open_1280}px (box ${s.h}px, content ${s.sh}px)`);
    await shot("ml-1280-expanded");
    await mlBoot(false);
    assert.equal(await ev(`document.querySelector('.reflib-ib-chiprow[data-row="tags"]').classList.contains('open')`), true, "open state not remembered");
    await ev(`(() => { document.querySelector('.reflib-ib-chiprow[data-row="tags"] .reflib-ib-chipmore').click(); return true; })()`); await sleep(150);
    assert.equal(await ev(`localStorage.getItem('reflib_chips_open_tags')`), "0");
  });
}
console.log("Galería");
async function gBoot() {
  await post("/test/reset");
  await c.send("Page.navigate", { url: BASE + "/reflib/gallery/#/" }); await waitFor(`document.readyState === 'complete'`);
  await ev(`localStorage.clear(); localStorage.setItem('gal.kinds','[]'); true`); await c.send("Page.reload", { ignoreCache: true });
  if (!await waitFor(`document.querySelectorAll('figure.tile').length > 3 && document.querySelectorAll('.facets .chip').length > 10`, 10000)) throw new Error("no tiles / facet chips");
  await sleep(400);
}
for (const w of [1280, 1920]) {
  await check(`Galería tag facets row height at ${w} px`, async () => {
    await size(w); await gBoot();
    assert.ok(await waitFor(`document.querySelectorAll('figure.tile').length > 3`, 8000), "no cards before measure at " + w);
    const h = await ev(`Math.round([...document.querySelectorAll('.facets')].reduce((a, e) => a + e.getBoundingClientRect().height, 0))`), n = await ev(`document.querySelectorAll('.facets .chip').length`);
    heights["gal_" + w] = h; console.log(`    Galería .facets height @${w}: ${h}px (${n} chips)`);
    await shot(`gal-${w}`);
    if (!MEASURE_ONLY) { assert.ok(h <= 34, `${h}px`); assert.ok(n > 14, "all tags of the loaded items, not 14"); }
  });
}
if (!MEASURE_ONLY) await check("Galería: +N, active chip first, expand ≤ 3 lines, remembered", async () => {
  await size(1280); await gBoot();
  assert.match(await ev(`document.querySelector('.chiprow .chipmore')?.textContent || ''`), /^\+\d+$/);
  await ev(`(() => { document.querySelector('.chiprow .chipmore').click(); return true; })()`); await sleep(200);
  const s = await ev(`(() => { const b = document.querySelector('.chiprow .chipbox'); return { h: b.clientHeight, sh: b.scrollHeight }; })()`);
  assert.ok(s.h <= 92 && s.h >= 70 && s.sh > s.h, JSON.stringify(s));
  assert.equal(await ev(`localStorage.getItem('reflib_chips_open_gtags')`), "1");
  await shot("gal-1280-expanded");
  await ev(`(() => { document.querySelector('.chiprow .chipmore').click(); return true; })()`); await sleep(150);   // collapsed again
  await ev(`(() => { [...document.querySelectorAll('.chiprow .chipbox .chip')][30].click(); return true; })()`);
  assert.ok(await waitFor(`document.querySelector('.chiprow .chipbox .chip')?.classList.contains('on')`, 5000), "active chip not first");
  const r = await ev(`(() => { const b = document.querySelector('.chiprow .chipbox').getBoundingClientRect(), o = document.querySelector('.chiprow .chipbox .chip.on').getBoundingClientRect(); return o.top >= b.top - 1 && o.bottom <= b.bottom + 1; })()`);
  assert.ok(r, "active chip not visible while collapsed");
});
console.log("HEIGHTS " + JSON.stringify(heights));
const errs = c.logs.filter((l) => l.startsWith("EXC"));
if (errs.length) { console.log("page exceptions:", errs.slice(0, 5)); fails.push("page exceptions"); }
console.log(fails.length ? `test_browser_chips: ${fails.length} FAILED` : "test_browser_chips: ok");
done(fails.length ? 1 : 0);
