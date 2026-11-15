// 1.12.17: OS-assigned free ports for the browser tests (random fixed ranges collided when tests run in parallel)
import net from "node:net";
export const freePort = () => new Promise((res, rej) => { const s = net.createServer(); s.unref(); s.on("error", rej);
  s.listen(0, "127.0.0.1", () => { const p = s.address().port; s.close(() => res(p)); }); });
