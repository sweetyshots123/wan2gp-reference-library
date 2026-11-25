// node tests/test_browser_ml_search.mjs — 1.12.18: Media Library search-as-you-type inside WanGP (from the 1.12.17 retest,
// _retest/ml/ml_search.mjs). Real reference_library.js in headless Chrome; the WanGP Gradio bridge is simulated (hidden
// textboxes + buttons that round-trip through the mock, one request at a time like Gradio). Server cost model from the
// retest's timings: query 50 ms, at_facets 18, at_suggest 60, thumbs 25, and a catalog rebuild (REB ms) after an
// action that drops the catalog (INVAL=1 models the server before 1.12.18, where at_suggest / col_peek did).
// Checks: read-only actions go straight to /reflib/api (thumbs no longer queue behind query / facets / suggest on the
// one Gradio channel); without /reflib/api it falls back to the bridge; older keystrokes' queued requests are dropped.
// MEASURE=1: print timings only (used with another tree for before/after). Synthetic only.
import assert from "node:assert/strict";
import fs from "node:fs"; import os from "node:os"; import path from "node:path"; import { spawn, spawnSync } from "node:child_process";
import { fileURLToPath } from "node:url";
const root = path.join(path.dirname(fileURLToPath(import.meta.url)), "..");
const has = (cmd) => spawnSync("sh", ["-c", "command -v " + cmd]).status === 0;
if (!has("google-chrome") || !has("ffmpeg")) { console.log("test_browser_ml_search: SKIP"); process.exit(0); }
const MEASURE = !!process.env.MEASURE, INVAL = process.env.INVAL === "1", REB = +(process.env.REB || 5000);
const sleep = (ms) => new Promise((r) => setTimeout(r, ms));
const tmp = fs.mkdtempSync(path.join(os.tmpdir(), "rl-mls-")); const MEDIA = path.join(tmp, "media"); fs.mkdirSync(MEDIA);
spawnSync("ffmpeg", ["-v", "error", "-f", "lavfi", "-i", "testsrc=duration=2:size=160x90:rate=10", "-c:v", "libvpx", "-b:v", "100k", path.join(MEDIA, "clip.webm")]);
spawnSync("ffmpeg", ["-v", "error", "-f", "lavfi", "-i", "color=c=red:s=64x64", "-frames:v", "1", path.join(MEDIA, "img.png")]);
const VERSION = JSON.parse(fs.readFileSync(path.join(root, "plugin_info.json"), "utf8")).version;
const { freePort } = await import(path.join(root, "tests/browser/ports.mjs"));
const PORT = await freePort(); let CDP = await freePort(); while (CDP === PORT) CDP = await freePort();
const BASE = `http://127.0.0.1:${PORT}`;
const srv = spawn(process.execPath, [path.join(root, "tests/browser/server.mjs")], { env: { ...process.env, DIST: path.join(root, "gallery/dist"), PLUGIN: root, VERSION, PORT: String(PORT), MEDIA, QDELAY: "0", N_ITEMS: "2000" }, stdio: ["ignore", "pipe", "inherit"] });
process.on("exit", () => { try { srv.kill(); } catch {} });   // 1.12.18: never leave the mock running (it holds the runner's stderr)
await new Promise((r) => srv.stdout.once("data", r));
process.env.CHROME_PROFILE = path.join(tmp, "chrome");
const { launch } = await import(path.join(root, "tests/browser/cdp.mjs"));
const c = await launch(CDP);
const done = (code) => { try { c.close(); } catch {} srv.kill(); try { fs.rmSync(tmp, { recursive: true, force: true }); } catch {} process.exit(code); };
const fails = [];
async function check(name, fn) { try { await fn(); console.log("  ok  " + name); } catch (e) { fails.push(name); console.log("  FAIL " + name + ": " + (e && e.message)); } }

// api: "ok" = /reflib/api reachable from the page, "down" = only the bridge works (404 for direct calls)
const inject = (api, qcost) => `(() => {
  try { localStorage.clear(); } catch {}
  const INVAL = ${INVAL}, REB = ${REB}, API = ${JSON.stringify(api)};
  const COST = { query: ${qcost}, at_facets: 18, at_suggest: 60, thumbs: 25, open: 45 }, NEEDCAT = new Set(["query", "at_facets", "at_suggest", "open", "range", "index_of"]);
  let dirty = false, rebuilding = null; window.__rlog = []; window.__bridgeN = {}; const T0 = performance.now(); window.__T = () => performance.now() - T0;
  const of = window.fetch.bind(window);
  window.fetch = async (u, o) => {
    if (!String(u).includes("/reflib/api")) return of(u, o);
    const viaBridge = !!(o && o.headers && o.headers["X-Bridge"]);
    if (!viaBridge && API === "down" && window.__booted) return new Response("no", { status: 404 });
    if (!viaBridge && API === "flaky" && window.__booted && !window.__flaked && JSON.parse(o.body).action === "thumbs") { window.__flaked = true; throw new TypeError("Failed to fetch"); }
    const b = JSON.parse(o.body); const s = performance.now() - T0;
    if (NEEDCAT.has(b.action) && dirty) { if (!rebuilding) rebuilding = new Promise((r) => setTimeout(() => { dirty = false; rebuilding = null; r(); }, REB)); await rebuilding; }
    await new Promise((r) => setTimeout(r, COST[b.action] || 5));
    if (INVAL && (b.action === "at_suggest" || b.action === "col_peek")) dirty = true;
    const res = await of(u, o); let j = await res.json();
    const q = b.f && b.f.q;
    if (b.action === "query" && q && j.page) j.page.items = j.page.items.map((it) => Object.assign({}, it, { hash: it.hash + "_" + q }));
    window.__rlog.push([b.action, Math.round(s), Math.round(performance.now() - T0), q || b.text || "", (b.hashes || []).length, viaBridge ? "bridge" : "direct"]);
    return new Response(JSON.stringify(j), { status: 200, headers: { "Content-Type": "application/json" } });
  };
  Object.defineProperty(window, "__REFLIB_STANDALONE__", { configurable: true, get() { return !window.__booted; }, set() {} });
  document.addEventListener("DOMContentLoaded", () => {
    for (const [rq, bn] of [["reflib_ilib_req", "reflib_ilib_btn"], ["reflib_ilib_fast_req", "reflib_ilib_fast_btn"]]) {
      const d = document.createElement("div"); d.id = rq; d.style.display = "none"; d.appendChild(document.createElement("textarea")); document.body.appendChild(d);
      const bt = document.createElement("button"); bt.id = bn; bt.style.display = "none";
      bt.onclick = () => { const body = d.querySelector("textarea").value; const a = JSON.parse(body).action; window.__bridgeN[a] = (window.__bridgeN[a] || 0) + 1;
        setTimeout(() => fetch("/reflib/api", { method: "POST", headers: { "Content-Type": "application/json", "X-Bridge": "1" }, body }).then((r) => r.json()).then((j) => { j.id = JSON.parse(body).id; j.ilib = true; setTimeout(() => window.referenceLibrary.bridgeResponse(JSON.stringify(j)), 15); }), 15); };
      document.body.appendChild(bt);
    }
    setTimeout(() => { window.__booted = true; }, 0);
  });
})();`;
const waitFor = async (expr, ms = 30000) => { const t0 = Date.now(); while (Date.now() - t0 < ms) { try { const v = await c.ev(expr); if (v) return v; } catch {} await sleep(25); } return null; };
async function run(api, { word = "esth", keyMs = 150, qcost = 50 } = {}) {
  const { identifier } = await c.send("Page.addScriptToEvaluateOnNewDocument", { source: inject(api, qcost) }).then((r) => r.result);
  await c.send("Page.navigate", { url: BASE + "/reflib/media-library/" });
  const booted = await waitFor(`document.querySelectorAll('.reflib-ib-card .reflib-ib-thumb img').length >= 20`);
  await sleep(500);
  await c.ev(`document.querySelector('.reflib-ib-q').focus(), true`);
  const tStart = await c.ev(`window.__T()`);
  for (const ch of word) { await c.send("Input.insertText", { text: ch }); await sleep(keyMs); }
  const tLast = await c.ev(`window.__T()`) - keyMs;
  const tGrid = await waitFor(`(() => { const cs = [...document.querySelectorAll('.reflib-ib-card')].filter(e => (e.dataset.hash || '').endsWith('_${word}')); return cs.length >= 1 ? window.__T() : 0; })()`, 60000);
  const tThumbs = await waitFor(`(() => { const cs = [...document.querySelectorAll('.reflib-ib-card')].filter(e => (e.dataset.hash || '').endsWith('_${word}') && e.querySelector('.reflib-ib-thumb img')); return cs.length >= 20 ? window.__T() : 0; })()`, 60000);
  await sleep(300);
  const log = (await c.ev(`window.__rlog`)).filter((x) => x[1] >= tStart - 5);
  const bridgeN = await c.ev(`window.__bridgeN`);
  const superseded = await c.ev(`(() => { const s = window.__reflibSched; if (!s) return null; let n = 0; for (const x of [s.fast, s.main, s.lanes && s.lanes.lane("q"), s.lanes && s.lanes.lane("pv")]) n += (x && x.stats && x.stats.superseded) || 0; return n; })()`);
  await c.send("Page.removeScriptToEvaluateOnNewDocument", { identifier });
  const cnt = {}; for (const x of log) cnt[x[0] + "/" + x[5]] = (cnt[x[0] + "/" + x[5]] || 0) + 1;
  return { superseded, booted: !!booted, grid_ms: tGrid ? Math.round(tGrid - tLast) : null, thumbs20_ms: tThumbs ? Math.round(tThumbs - tLast) : null, requests: cnt, bridgeN,
           staleQueries: log.filter((x) => x[0] === "query" && x[3] && x[3] !== word).length, staleSuggest: log.filter((x) => x[0] === "at_suggest" && x[3] !== word).length, log };
}

console.log("Media Library in WanGP (simulated Gradio bridge)" + (INVAL ? `, server drops the catalog on at_suggest (rebuild ${REB} ms)` : ""));
const R = {};
await check("typing 'esth': results + 20 thumbnails quickly; read-only actions skip the Gradio channel", async () => {
  const r = R.direct = await run("ok");
  console.log("    direct: grid " + r.grid_ms + " ms, 20 thumbs " + r.thumbs20_ms + " ms, " + JSON.stringify(r.requests) + " bridge " + JSON.stringify(r.bridgeN));
  if (MEASURE) return;
  assert.ok(r.booted && r.grid_ms != null && r.grid_ms < 1500, "grid: " + r.grid_ms);
  assert.ok(r.thumbs20_ms != null && r.thumbs20_ms < 2000, "thumbs: " + r.thumbs20_ms);
  for (const a of ["query", "thumbs", "at_suggest", "at_facets"]) assert.ok(!r.bridgeN[a], a + " went through the bridge: " + JSON.stringify(r.bridgeN));
});
await check("one transient network error (keep-alive race) is retried directly, not a switch to the Gradio channel", async () => {
  const r = await run("flaky");
  console.log("    flaky: " + JSON.stringify(r.requests) + " bridge " + JSON.stringify(r.bridgeN));
  if (MEASURE) return;
  assert.ok(r.thumbs20_ms != null, "thumbs");
  for (const a of ["query", "thumbs", "at_suggest", "at_facets"]) assert.ok(!r.bridgeN[a], a + " went through the bridge: " + JSON.stringify(r.bridgeN));
});
await check("/reflib/api not reachable: falls back to the Gradio channel and still works", async () => {
  const r = R.down = await run("down");
  console.log("    bridge only: grid " + r.grid_ms + " ms, 20 thumbs " + r.thumbs20_ms + " ms, bridge " + JSON.stringify(r.bridgeN));
  if (MEASURE) return;
  assert.ok(r.booted && r.grid_ms != null && r.thumbs20_ms != null, JSON.stringify(r));
  assert.ok((r.bridgeN.query || 0) > 0 && (r.bridgeN.thumbs || 0) > 0);
});
await check("slow queries + slow typing: queued requests of earlier keystrokes are dropped", async () => {
  const r = R.slow = await run("ok", { keyMs: 260, qcost: 700 });
  console.log("    slow: grid " + r.grid_ms + " ms, stale queries run " + r.staleQueries + ", stale suggestions run " + r.staleSuggest + ", superseded " + r.superseded + " " + JSON.stringify(r.requests));
  if (MEASURE) return;
  assert.ok(r.superseded >= 1, "queued requests of older keystrokes were cancelled: " + r.superseded);
  assert.ok(r.staleQueries <= 2, "only the ones already running when the next keystroke came: " + r.staleQueries);
  assert.ok(r.grid_ms != null && r.grid_ms < 2500, "grid: " + r.grid_ms);
});
console.log("ML_SEARCH_REPORT " + JSON.stringify(Object.fromEntries(Object.entries(R).map(([k, v]) => [k, { grid_ms: v.grid_ms, thumbs20_ms: v.thumbs20_ms, staleQueries: v.staleQueries, staleSuggest: v.staleSuggest }]))));
if (fails.length) console.log("console:", c.logs.filter((l) => /unreachable|Gradio channel/.test(l)).slice(0, 5));
const ex = c.logs.filter((l) => l.startsWith("EXC ")); if (ex.length) { console.log(ex.slice(0, 5)); fails.push("exceptions"); }
console.log(fails.length ? `test_browser_ml_search: ${fails.length} FAILED` : "test_browser_ml_search: all OK");
done(fails.length ? 1 : 0);
