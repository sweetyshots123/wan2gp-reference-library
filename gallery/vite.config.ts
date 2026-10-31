import { defineConfig } from "vite";
import react from "@vitejs/plugin-react";

// WanGP corre en 7860 (PC). Cambia con: WANGP=http://127.0.0.1:7882 npm run dev
const target = process.env.WANGP || "http://127.0.0.1:7860";

export default defineConfig({
  base: "/reflib/gallery/",
  plugins: [react()],
  server: {
    port: 5174,
    strictPort: true,
    proxy: { "/reflib/api": target, "/reflib/upload": target, "/gradio_api": target },
  },
  build: { outDir: "dist", emptyOutDir: true },
});
