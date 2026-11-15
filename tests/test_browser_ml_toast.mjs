// node tests/test_browser_ml_toast.mjs — 1.12.18 retest: inside WanGP, direct /reflib/api replies must go through
// handleToast (errors, messages, change events). Before the fix, viaFetch(true) skipped it, so a failed "Browse…"
// in the add-folder picker stayed silent. Real reference_library.js in headless Chrome; Gradio bridge simulated.
// Synthetic only. Peer repro: _retest/ml/err_toast.mjs.
import assert from "node:assert/strict";
import fs from "node:fs"; import os from "node:os"; import path from "node:path"; import { spawn, spawnSync } from "node:child_process";
import { fileURLToPath } from "node:url";
const root = path.join(path.dirname(fileURLToPath(import.meta.url)), "..");
const has = (cmd) => spawnSync("sh", ["-c", "command -v " + cmd]).status === 0;
if (!has("google-chrome") || !has("ffmpeg")) { console.log("test_browser_ml_toast: SKIP"); process.exit(0); }
const sleep = (ms) => new Promise((r) => setTimeout(r, ms));
const tmp = fs.mkdtempSync(path.join(os.tmpdir(), "rl-mlt-")); const MEDIA = path.join(tmp, "media"); fs.mkdirSync(MEDIA);
spawnSync("ffmpeg", ["-v", "error", "-f", "lavfi", "-i", "testsrc=duration=2:size=160x90:rate=10", "-c:v", "libvpx", "-b:v", "100k", path.join(MEDIA, "clip.webm")]);
spawnSync("ffmpeg", ["-v", "error", "-f", "lavfi", "-i", "color=c=red:s=64x64", "-frames:v", "1", path.join(MEDIA, "img.png")]);
const VERSION = JSON.parse(fs.readFileSync(path.join(root, "plugin_info.json"), "utf8")).version;
const { freePort } = await import(path.join(root, "tests/browser/ports.mjs"));
const PORT = await freePort(); let CDP = await freePort(); while (CDP === PORT) CDP = await freePort();
const BASE = `http://127.0.0.1:${PORT}`;
const srv = spawn(process.execPath, [path.join(root, "tests/browser/server.mjs")], { env: { ...process.env, DIST: path.join(root, "gallery/dist"), PLUGIN: root, VERSION, PORT: String(PORT), MEDIA, QDELAY: "0", N_ITEMS: "40" }, stdio: ["ignore", "pipe", "inherit"] });
process.on("exit", () => { try { srv.kill(); } catch {} });
await new Promise((r) => srv.stdout.once("data", r));
process.env.CHROME_PROFILE = path.join(tmp, "chrome");
const { launch } = await import(path.join(root, "tests/browser/cdp.mjs"));
const c = await launch(CDP);
const done = (code) => { try { c.close(); } catch {} srv.kill(); try { fs.rmSync(tmp, { recursive: true, force: true }); } catch {} process.exit(code); };
const fails = [];
async function check(name, fn) { try { await fn(); console.log("  ok  " + name); } catch (e) { fails.push(name); console.log("  FAIL " + name + ": " + (e && e.message)); } }
const inject = (api) => `(() => {
  const API = ${JSON.stringify(api)};
  const of = window.fetch.bind(window);
  window.__bridgeN = {};
  window.fetch = async (u, o) => {
    if (!String(u).includes("/reflib/api")) return of(u, o);
    const viaBridge = !!(o && o.headers && o.headers["X-Bridge"]);
    if (!viaBridge && API === "down" && window.__booted) return new Response("no", { status: 404 });
    const b = JSON.parse(o.body);
    const res = await of(u, o); let j = await res.json();
    if (b.action === "browse") j = { ok: false, error: "ERR_SYNTH_BROWSE" };
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
const waitFor = async (expr, ms = 15000) => { const t0 = Date.now(); while (Date.now() - t0 < ms) { try { const v = await c.ev(expr); if (v) return v; } catch {} await sleep(50); } return null; };
const toastExpr = `[...document.querySelectorAll('.reflib-toast')].filter(t => t.textContent.includes('ERR_SYNTH_BROWSE')).length`;
async function browseError(api) {
  const { identifier } = await c.send("Page.addScriptToEvaluateOnNewDocument", { source: inject(api) }).then((r) => r.result);
  await c.send("Page.navigate", { url: BASE + "/reflib/media-library/" });
  assert.ok(await waitFor(`document.querySelectorAll('.reflib-ib-card').length > 5`), "library did not load");
  await waitFor(`!!document.querySelector('.reflib-ib-addfolder')`);
  await c.ev(`document.querySelector('.reflib-ib-addfolder').click(), true`);
  assert.ok(await waitFor(`!!document.querySelector('[data-act="fbrowse"]')`), "Browse… button missing");
  await c.ev(`document.querySelector('[data-act="fbrowse"]').click(), true`);
  const n = await waitFor(`${toastExpr} > 0`, 4000);
  const count = (await c.ev(toastExpr)) || 0;
  const direct = await c.ev(`window.__reflibDirect`);
  const bridgeN = await c.ev(`window.__bridgeN`);
  await c.send("Page.removeScriptToEvaluateOnNewDocument", { identifier });
  return { n: !!n, count, direct, bridgeN };
}
await check("embedded ML, direct /reflib/api: a browse error shows one toast (not silent, not doubled)", async () => {
  const r = await browseError("ok");
  console.log("    direct: " + JSON.stringify(r));
  assert.equal(r.direct, true, "expected the direct /reflib/api path: " + JSON.stringify(r));
  assert.ok(!r.bridgeN.browse, "browse went through the Gradio channel: " + JSON.stringify(r.bridgeN));
  assert.equal(r.count, 1, "toast count: " + r.count);
});
await check("embedded ML, /reflib/api down: the Gradio fallback still shows the toast", async () => {
  const r = await browseError("down");
  console.log("    fallback: " + JSON.stringify(r));
  assert.ok((r.bridgeN.browse || 0) > 0, "browse did not use the bridge: " + JSON.stringify(r.bridgeN));
  assert.equal(r.count, 1, "toast count: " + r.count);
});
const ex = c.logs.filter((l) => l.startsWith("EXC ")); if (ex.length) { console.log(ex.slice(0, 5)); fails.push("exceptions"); }
console.log(fails.length ? `test_browser_ml_toast: ${fails.length} FAILED` : "test_browser_ml_toast: all OK");
done(fails.length ? 1 : 0);
