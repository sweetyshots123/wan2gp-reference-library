// node tests/test_browser_keepstate.mjs — real headless Chrome tests for 1.12.27 keep-state
// ("Recordar búsqueda y filtros al reabrir" + "Restablecer filtros") in BOTH UIs:
//   - Media Library (closeBrowser -> openBrowser AND full reload / reopen)
//   - Galería (close/reopen from #/ AND full reload, route + search + chips + facets + sort + scroll)
//   - Stale collection/tag pruning
//   - Reset filters action
//   - Setting OFF disables persistence and clears saved state
// Synthetic fixtures only (server.mjs). Skips cleanly if google-chrome/ffmpeg/dist missing.
import assert from "node:assert/strict";
import fs from "node:fs";
import os from "node:os";
import path from "node:path";
import { spawn, spawnSync } from "node:child_process";
import { fileURLToPath } from "node:url";

const root = path.join(path.dirname(fileURLToPath(import.meta.url)), "..");
const has = (cmd) => spawnSync("sh", ["-c", "command -v " + cmd]).status === 0;
const DIST = path.join(root, "gallery/dist");
if (!has("google-chrome") || !has("ffmpeg") || !fs.existsSync(path.join(DIST, "index.html"))) {
  console.log("test_browser_keepstate: SKIP (needs google-chrome, ffmpeg, gallery/dist)");
  process.exit(0);
}

const SHOTS = process.env.SHOTS || "";
const sleep = (ms) => new Promise((r) => setTimeout(r, ms));
const tmp = fs.mkdtempSync(path.join(os.tmpdir(), "reflib-keepstate-"));
const MEDIA = path.join(tmp, "media");
fs.mkdirSync(MEDIA);
spawnSync("ffmpeg", ["-v", "error", "-f", "lavfi", "-i", "testsrc=size=160x120:rate=1", "-frames:v", "1", path.join(MEDIA, "img.png")]);
spawnSync("ffmpeg", ["-v", "error", "-f", "lavfi", "-i", "testsrc=duration=2:size=160x90:rate=10", "-c:v", "libvpx", path.join(MEDIA, "clip.webm")]);

const VERSION = JSON.parse(fs.readFileSync(path.join(root, "plugin_info.json"), "utf8")).version;
const { freePort } = await import(path.join(root, "tests/browser/ports.mjs"));
const PORT = await freePort();
let CDP = await freePort();
while (CDP === PORT) CDP = await freePort();
const BASE = `http://127.0.0.1:${PORT}`;

const srv = spawn(process.execPath, [path.join(root, "tests/browser/server.mjs")], {
  env: {
    ...process.env,
    DIST,
    PLUGIN: root,
    VERSION,
    PORT: String(PORT),
    MEDIA,
    N_ITEMS: "300",
    MOCK_CHIPS: "20",
    MOCK_COLS: "6",
    MOCK_FAV: "p001,p002,v000,v005",
    MOCK_FOLDERS: "1",
    MOCK_QFILTER: "1",
    QDELAY: "20",
  },
  stdio: ["ignore", "pipe", "inherit"],
});
process.on("exit", () => { try { srv.kill(); } catch {} });
await new Promise((r) => srv.stdout.once("data", r));

process.env.CHROME_PROFILE = path.join(tmp, "chrome");
const { launch } = await import(path.join(root, "tests/browser/cdp.mjs"));
const c = await launch(CDP);
const ev = c.ev;
const done = (code) => { try { c.close(); } catch {} srv.kill(); try { fs.rmSync(tmp, { recursive: true, force: true }); } catch {} process.exit(code); };
const post = async (p, b = {}) => (await fetch(BASE + p, { method: "POST", body: JSON.stringify(b) })).json();
async function waitFor(expr, ms = 10000) {
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
const fails = [];
async function check(name, fn) {
  try { await fn(); console.log("  ok  " + name); }
  catch (e) { fails.push(name); console.log("  FAIL " + name + ": " + (e && e.message)); }
}

await c.send("Emulation.setDeviceMetricsOverride", { width: 1280, height: 900, deviceScaleFactor: 1, mobile: false });

async function mlBoot(clearLs = true) {
  await c.send("Page.navigate", { url: BASE + "/reflib/media-library/" });
  if (clearLs) {
    await waitFor(`document.readyState === 'complete'`);
    await ev(`localStorage.clear(); true`);
    await c.send("Page.reload", { ignoreCache: true });
  }
  assert.ok(await waitFor(`document.querySelectorAll('.reflib-ib-card').length > 3 && !!document.querySelector('.reflib-ib-q')`, 12000), "ML failed to boot");
  await sleep(250);
}

async function galBoot(hash = "#/", clearLs = true) {
  await c.send("Page.navigate", { url: BASE + "/reflib/gallery/" + hash });
  if (clearLs) {
    await waitFor(`document.readyState === 'complete'`);
    await ev(`localStorage.clear(); true`);
    await c.send("Page.navigate", { url: BASE + "/reflib/gallery/" + hash });
    await c.send("Page.reload", { ignoreCache: true });
  }
  assert.ok(await waitFor(`!!document.querySelector('header.top') && !!document.querySelector('main')`, 12000), "Galería failed to boot");
  await sleep(250);
}

console.log("Media Library");
await check("keeps search, collection, tag, kind, sort, chipQ, and scroll across modal close/reopen AND reload", async () => {
  await post("/test/reset");
  await mlBoot(true);
  await shot("ml-clean-initial");

  // Apply search query, collection col0, tag chip, kind image, sort name_asc, chipQ tags filter, scroll down
  await ev(`(() => {
    const q = document.querySelector('.reflib-ib-q');
    q.value = 'img_';
    q.dispatchEvent(new Event('input', { bubbles: true }));
    return true;
  })()`);
  await sleep(250);
  await ev(`(() => {
    document.querySelector('.reflib-ib-chiprow[data-row="cols"] .reflib-ib-chip[data-f="col"][data-id="col0"]').click();
    return true;
  })()`);
  await sleep(150);
  await ev(`(() => {
    document.querySelector('.reflib-ib-kbtn[data-v="image"]').click();
    const so = document.querySelector('.reflib-ib-sort');
    so.value = 'name_asc';
    so.dispatchEvent(new Event('change', { bubbles: true }));
    const cq = document.querySelector('.reflib-ib-chipq[data-row="tags"]');
    cq.value = 'Persona';
    cq.dispatchEvent(new Event('input', { bubbles: true }));
    return true;
  })()`);
  await sleep(250);
  assert.ok(await waitFor(`document.querySelectorAll('.reflib-ib-card').length > 0`, 6000), "filtered cards");
  await ev(`(() => { const m = document.querySelector('.reflib-ib-main'); m.scrollTop = 180; m.dispatchEvent(new Event('scroll')); return m.scrollTop; })()`);
  await sleep(250);

  // Reset button should be visible
  const resetVis = await ev(`!document.querySelector('.reflib-ib-reset').hidden`);
  assert.equal(resetVis, true, "reset filters button should be visible");
  await shot("ml-filtered-before-close");

  // 1) Close & reopen modal in-page
  await ev(`(() => { window.referenceLibrary.closeBrowser(); return true; })()`);
  await sleep(150);
  await ev(`(() => { window.referenceLibrary.openBrowser(); return true; })()`);
  assert.ok(await waitFor(`document.querySelectorAll('.reflib-ib-card').length > 0 && document.querySelector('.reflib-ib-q').value === 'img_'`, 8000), "reopen modal");
  await sleep(300);

  const afterReopen = await ev(`(() => ({
    q: document.querySelector('.reflib-ib-q').value,
    sort: document.querySelector('.reflib-ib-sort').value,
    kindOn: document.querySelector('.reflib-ib-kbtn[data-v="image"]').classList.contains('on'),
    colOn: [...document.querySelectorAll('.reflib-ib-chiprow[data-row="cols"] .reflib-ib-chip[data-f="col"].on')].length,
    chipQ: document.querySelector('.reflib-ib-chipq[data-row="tags"]').value,
    scroll: Math.round(document.querySelector('.reflib-ib-main').scrollTop),
  }))()`);
  assert.equal(afterReopen.q, "img_");
  assert.equal(afterReopen.sort, "name_asc");
  assert.equal(afterReopen.kindOn, true);
  assert.equal(afterReopen.colOn, 1);
  assert.equal(afterReopen.chipQ, "Persona");
  assert.ok(afterReopen.scroll >= 100, "scroll after reopen: " + afterReopen.scroll);

  // 2) Close tab / full reload
  await mlBoot(false);
  await sleep(350);
  const afterReload = await ev(`(() => ({
    q: document.querySelector('.reflib-ib-q').value,
    sort: document.querySelector('.reflib-ib-sort').value,
    kindOn: document.querySelector('.reflib-ib-kbtn[data-v="image"]').classList.contains('on'),
    colOn: [...document.querySelectorAll('.reflib-ib-chiprow[data-row="cols"] .reflib-ib-chip[data-f="col"].on')].length,
    chipQ: document.querySelector('.reflib-ib-chipq[data-row="tags"]').value,
    scroll: Math.round(document.querySelector('.reflib-ib-main').scrollTop),
  }))()`);
  assert.equal(afterReload.q, "img_");
  assert.equal(afterReload.sort, "name_asc");
  assert.equal(afterReload.kindOn, true);
  assert.equal(afterReload.colOn, 1);
  assert.equal(afterReload.chipQ, "Persona");
  assert.ok(afterReload.scroll >= 100, "scroll after reload: " + afterReload.scroll);
  const contrast = await ev(`(() => {
    const rgb = (cs) => { const m = String(cs).match(/rgba?\\((\\d+),\\s*(\\d+),\\s*(\\d+)(?:,\\s*([0-9.]+))?\\)/); return m ? {r:+m[1],g:+m[2],b:+m[3],a:m[4]===undefined?1:+m[4]} : null; };
    const lum = ({r,g,b}) => { const f=(v)=>{v/=255;return v<=0.04045?v/12.92:Math.pow((v+0.055)/1.055,2.4);}; return 0.2126*f(r)+0.7152*f(g)+0.0722*f(b); };
    const ratio = (fg,bg) => { if(!fg||!bg) return 0; const hi=Math.max(lum(fg),lum(bg)), lo=Math.min(lum(fg),lum(bg)); return (hi+0.05)/(lo+0.05); };
    const solidBg = (el) => { for (let n=el;n;n=n.parentElement) { const bg=rgb(getComputedStyle(n).backgroundColor); if(bg&&bg.a>0) return bg; } return rgb(getComputedStyle(document.body).backgroundColor); };
    const info = (sel) => { const el=document.querySelector(sel); if(!el||el.hidden) return {sel, missing:true, contrast:0}; const fg=rgb(getComputedStyle(el).color), bg=solidBg(el); return {sel, contrast:Math.round(ratio(fg,bg)*100)/100, color:getComputedStyle(el).color}; };
    return [info('.reflib-ib-reset'), info('.reflib-ib-head h3'), info('.reflib-ib-chip:not(.on)'), info('.reflib-ib-btn.reflib-ib-addfolder')];
  })()`);
  for (const s of contrast) {
    assert.ok(!s.missing, "missing " + s.sel);
    assert.ok(s.contrast >= 4.5, `${s.sel} contrast ${s.contrast} < 4.5 (${s.color})`);
  }
  await shot("ml-restored-after-reload");
});

await check("Media Library prunes stale deleted collection gracefully on reload", async () => {
  await post("/test/drop_meta", { col: "col0" });
  await mlBoot(false);
  await sleep(350);
  const st = await ev(`(() => ({
    q: document.querySelector('.reflib-ib-q').value,
    colOn: [...document.querySelectorAll('.reflib-ib-chiprow[data-row="cols"] .reflib-ib-chip[data-f="col"].on')].length,
  }))()`);
  assert.equal(st.q, "img_");
  assert.equal(st.colOn, 0, "deleted collection should be pruned");
});

await check("Media Library Reset filters clears all filters and saved state", async () => {
  await ev(`document.querySelector('.reflib-ib-reset').click(), true`);
  await sleep(300);
  const st = await ev(`(() => ({
    q: document.querySelector('.reflib-ib-q').value,
    sort: document.querySelector('.reflib-ib-sort').value,
    kindOn: document.querySelector('.reflib-ib-kbtn[data-v="image"]').classList.contains('on'),
    chipQ: document.querySelector('.reflib-ib-chipq[data-row="tags"]').value,
    resetHidden: document.querySelector('.reflib-ib-reset').hidden,
    saved: localStorage.getItem('reflib_ml_view_state'),
  }))()`);
  assert.equal(st.q, "");
  assert.equal(st.sort, "date_desc");
  assert.equal(st.kindOn, false);
  assert.equal(st.chipQ, "");
  assert.equal(st.resetHidden, true);
  assert.equal(st.saved, null);
});

await check("Media Library with remember_state=false does not keep filters on reopen", async () => {
  await post("/test/reset");
  await post("/test/remember", { remember: false });
  await mlBoot(true);
  await ev(`(() => {
    const q = document.querySelector('.reflib-ib-q');
    q.value = 'vid_';
    q.dispatchEvent(new Event('input', { bubbles: true }));
    return true;
  })()`);
  await sleep(250);
  await mlBoot(false);
  await sleep(250);
  assert.equal(await ev(`document.querySelector('.reflib-ib-q').value`), "");
});

console.log("Galería");
await check("keeps route, search, kinds, sort, extraTags, chipQ, and scroll on reopen from #/", async () => {
  await post("/test/reset");
  await galBoot("#/", true);
  assert.ok(await waitFor(`document.querySelectorAll('figure.tile').length > 10`, 8000));

  // Switch to a collection route, filter by kind + sort + search + tag chip + chipQ + scroll
  await ev(`(() => { location.hash = '#/coleccion/col0'; return true; })()`);
  assert.ok(await waitFor(`location.hash === '#/coleccion/col0' && document.querySelectorAll('figure.tile').length > 5`, 8000));
  await sleep(250);
  await ev(`(() => {
    const sel = document.querySelector('.tools select');
    sel.value = 'name_asc';
    sel.dispatchEvent(new Event('change', { bubbles: true }));
    const kb = [...document.querySelectorAll('.tools button')].find((b) => /Imágenes|Fotos|Images/i.test(b.textContent || ""));
    if (kb) kb.click();
    const s = document.querySelector('input#q');
    const setter = Object.getOwnPropertyDescriptor(HTMLInputElement.prototype, 'value').set;
    setter.call(s, 'img_');
    s.dispatchEvent(new Event('input', { bubbles: true }));
    return true;
  })()`);
  await sleep(250);
  await ev(`(() => {
    const cq = document.querySelector('.chiprow .chipq');
    if (cq) {
      const setter = Object.getOwnPropertyDescriptor(HTMLInputElement.prototype, 'value').set;
      setter.call(cq, 'Persona');
      cq.dispatchEvent(new Event('input', { bubbles: true }));
    }
    const ch = document.querySelector('.chiprow .chipbox .chip');
    if (ch) ch.click();
    return true;
  })()`);
  await sleep(300);
  assert.ok(await waitFor(`!!document.querySelector('button.resetbtn')`, 6000), "resetbtn visible in Galería");
  await ev(`window.scrollTo(0, 260), true`);
  await sleep(350);
  await shot("gal-filtered-before-close");

  // Reopen Galería at bare /reflib/gallery/ (simulating closing tab and clicking Galería again)
  await galBoot("", false);
  assert.ok(await waitFor(`location.hash === '#/coleccion/col0' && document.querySelectorAll('figure.tile').length > 0`, 10000), "route restored");
  await sleep(400);

  const g = await ev(`(() => ({
    hash: location.hash,
    sort: document.querySelector('.tools select')?.value || 'date_desc',
    search: document.querySelector('input#q')?.value,
    chipQ: document.querySelector('.chiprow .chipq')?.value || "",
    activeTags: document.querySelectorAll('.chiprow .chip.on').length,
    resetBtn: !!document.querySelector('button.resetbtn'),
    scrollY: Math.round(window.scrollY),
  }))()`);
  assert.equal(g.hash, "#/coleccion/col0");
  assert.equal(g.sort, "name_asc");
  assert.equal(g.search, "img_");
  assert.equal(g.chipQ, "Persona");
  assert.ok(g.activeTags >= 1, "active extraTag restored");
  assert.equal(g.resetBtn, true);
  assert.ok(g.scrollY >= 150, "scrollY restored: " + g.scrollY);
  const gContrast = await ev(`(() => {
    const rgb = (cs) => { const m = String(cs).match(/rgba?\\((\\d+),\\s*(\\d+),\\s*(\\d+)(?:,\\s*([0-9.]+))?\\)/); return m ? {r:+m[1],g:+m[2],b:+m[3],a:m[4]===undefined?1:+m[4]} : null; };
    const lum = ({r,g,b}) => { const f=(v)=>{v/=255;return v<=0.04045?v/12.92:Math.pow((v+0.055)/1.055,2.4);}; return 0.2126*f(r)+0.7152*f(g)+0.0722*f(b); };
    const ratio = (fg,bg) => { if(!fg||!bg) return 0; const hi=Math.max(lum(fg),lum(bg)), lo=Math.min(lum(fg),lum(bg)); return (hi+0.05)/(lo+0.05); };
    const solidBg = (el) => { for (let n=el;n;n=n.parentElement) { const bg=rgb(getComputedStyle(n).backgroundColor); if(bg&&bg.a>0) return bg; } return rgb(getComputedStyle(document.body).backgroundColor); };
    const el=document.querySelector('button.resetbtn'); if(!el) return {missing:true, contrast:0};
    const fg=rgb(getComputedStyle(el).color), bg=solidBg(el);
    return {missing:false, contrast:Math.round(ratio(fg,bg)*100)/100, color:getComputedStyle(el).color};
  })()`);
  assert.ok(!gContrast.missing, "Galería resetbtn missing");
  assert.ok(gContrast.contrast >= 4.5, "Galería resetbtn contrast " + gContrast.contrast + " < 4.5 (" + gContrast.color + ")");
  await shot("gal-restored-after-reopen");
});

await check("Galería prunes stale deleted collection route cleanly", async () => {
  await post("/test/drop_meta", { col: "col0" });
  await galBoot("", false);
  assert.ok(await waitFor(`location.hash === '#/' || location.hash === ''`, 8000), "pruned stale collection route back to #/, got " + await ev(`location.hash`));
});

await check("Galería Reset filters button clears filters and returns to #/", async () => {
  await ev(`(() => { location.hash = '#/favoritas'; return true; })()`);
  assert.ok(await waitFor(`!!document.querySelector('button.resetbtn')`, 6000));
  await ev(`document.querySelector('button.resetbtn').click(), true`);
  assert.ok(await waitFor(`location.hash === '#/'`, 6000));
  await sleep(250);
  const g = await ev(`(() => ({
    hash: location.hash,
    search: document.querySelector('input#q')?.value,
    sort: document.querySelector('.tools select')?.value || 'date_desc',
    resetBtn: !!document.querySelector('button.resetbtn'),
    saved: localStorage.getItem('reflib_gal_view_state'),
  }))()`);
  assert.ok(g.hash === "#/" || g.hash === "");
  assert.equal(g.search, "");
  assert.equal(g.sort, "date_desc");
  assert.equal(g.resetBtn, false);
  assert.equal(g.saved, null);
});

await check("Galería with remember_state=false does not restore route or filters", async () => {
  await post("/test/reset");
  await post("/test/remember", { remember: false });
  await galBoot("#/", true);
  await ev(`(() => { location.hash = '#/favoritas'; return true; })()`);
  assert.ok(await waitFor(`location.hash === '#/favoritas'`, 6000));
  await sleep(250);
  await galBoot("", false);
  await sleep(300);
  assert.ok(["#/", ""].includes(await ev(`location.hash`)));
});

const ex = c.logs.filter((l) => l.startsWith("EXC "));
if (ex.length) { console.log("EXCEPTIONS:", ex.slice(0, 5)); fails.push("page-exceptions"); }
console.log(fails.length ? `test_browser_keepstate: ${fails.length} FAILED` : "test_browser_keepstate: all OK");
done(fails.length ? 1 : 0);
