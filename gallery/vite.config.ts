import { defineConfig } from "vite";
import react from "@vitejs/plugin-react";
import { readFileSync } from "node:fs";

// 1.12.13: the build knows its plugin version; an open tab compares it with the server's (query → r.v) and offers a reload
const PLUGIN_VERSION = JSON.parse(readFileSync(new URL("../plugin_info.json", import.meta.url), "utf8")).version;

// WanGP corre en 7860 (PC). Cambia con: WANGP=http://127.0.0.1:7882 npm run dev
const target = process.env.WANGP || "http://127.0.0.1:7860";

export default defineConfig({
  base: "/reflib/gallery/",
  plugins: [react()],
  define: { __REFLIB_BUILD__: JSON.stringify(PLUGIN_VERSION) },
  server: {
    port: 5174,
    strictPort: true,
    proxy: { "/reflib/api": target, "/reflib/upload": target, "/gradio_api": target },
  },
  build: { outDir: "dist", emptyOutDir: true },
});
