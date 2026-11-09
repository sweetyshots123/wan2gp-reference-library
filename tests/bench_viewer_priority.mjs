import { readFileSync } from "fs";
import vm from "vm";
import { fileURLToPath } from "url";
import { dirname, join } from "path";

const __dirname = dirname(fileURLToPath(import.meta.url));
vm.runInNewContext(readFileSync(join(__dirname, "..", "request_priority.js"), "utf8"), globalThis);
const Net = ReflibNet;

async function run(label, prioritize) {
  const s = Net.createScheduler();
  const gate = Net.createThumbGate();
  const N = 200;
  const start = performance.now();
  const thumbs = [];
  for (let i = 0; i < N; i++) {
    thumbs.push((async () => {
      if (prioritize) await gate.whenFree();
      await s.enqueue(async () => { await new Promise((r) => setTimeout(r, 2)); }, 0);
    })());
  }
  // let thumb flood start parking on the gate / queue
  await new Promise((r) => setTimeout(r, 15));
  if (prioritize) gate.enterViewer();
  const v0 = performance.now();
  await s.enqueue(async () => { await new Promise((r) => setTimeout(r, 2)); }, prioritize ? 10 : 0);
  const viewMs = performance.now() - v0;
  if (prioritize) gate.leaveViewer();
  await Promise.all(thumbs);
  return { label, viewMs, totalMs: performance.now() - start };
}

const before = await run("before (FIFO)", false);
const after = await run("after (prio+gate)", true);
console.log(JSON.stringify({ before, after }, null, 2));
if (!(after.viewMs < before.viewMs / 2 || after.viewMs < 80)) {
  console.error("viewer latency did not improve enough", before, after);
  process.exit(1);
}
console.log("bench_viewer_priority ok");
