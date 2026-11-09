import { readFileSync } from "fs";
import vm from "vm";
import assert from "assert";
import { fileURLToPath } from "url";
import { dirname, join } from "path";

const __dirname = dirname(fileURLToPath(import.meta.url));
const src = readFileSync(join(__dirname, "..", "request_priority.js"), "utf8");
const g = {};
vm.runInNewContext(src, g);
const Net = g.ReflibNet;
assert.ok(Net);
assert.strictEqual(Net.channel("thumbs"), "thumb");
assert.strictEqual(Net.channel("preview"), "view");
assert.strictEqual(Net.channel("media_url"), "view");
assert.strictEqual(Net.channel("open"), "view");

const order = [];
const s = Net.createScheduler();
const slow = () => new Promise((r) => setTimeout(() => { order.push("thumb"); r(); }, 30));
const fast = () => { order.push("view"); return Promise.resolve(); };
const starter = s.enqueue(() => new Promise((r) => setTimeout(r, 5)), 0);
const t1 = s.enqueue(slow, 0);
const v1 = s.enqueue(fast, 10);
await Promise.all([starter, t1, v1]);
assert.deepStrictEqual(JSON.parse(JSON.stringify(order)), ["view", "thumb"]);

const gate = Net.createThumbGate();
gate.enterViewer();
assert.ok(gate.blocked);
let released = false;
const waiter = gate.whenFree().then(() => { released = true; });
await new Promise((r) => setTimeout(r, 20));
assert.strictEqual(released, false);
gate.leaveViewer();
await waiter;
assert.ok(released);
console.log("request_priority ok");
