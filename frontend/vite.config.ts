import { defineConfig } from "vite";
import react from "@vitejs/plugin-react";
import cesium from "vite-plugin-cesium";
import path from "path";

// vite-plugin-cesium handles:
//   - Copying CesiumJS static Workers, Assets, ThirdParty to dist/
//   - Setting CESIUM_BASE_URL define so Cesium can resolve its own Workers at runtime
//   - Excluding cesium from Vite's dep optimisation (prevents Worker inlining crash)
export default defineConfig({
  plugins: [react(), cesium()],
  resolve: {
    alias: { "@": path.resolve(__dirname, "./src") },
  },
  build: {
    chunkSizeWarningLimit: 20000,
    rollupOptions: {
      output: {
        manualChunks: {
          "cesium-core": ["cesium"],
          "react-core": ["react", "react-dom"],
          "zustand": ["zustand"],
        },
      },
    },
    assetsInlineLimit: 0,
  },
  server: {
    proxy: {
      "/api": {
        target: "http://localhost:8080",
        changeOrigin: true,
      },
    },
  },
  define: {
    // Cesium uses these global checks internally
    CESIUM_BASE_URL: JSON.stringify("/cesium"),
  },
});
