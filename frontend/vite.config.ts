import { defineConfig } from "vite";
import react from "@vitejs/plugin-react";
import cesium from "vite-plugin-cesium";

// vite-plugin-cesium handles:
//   - Copying CesiumJS static Workers, Assets, ThirdParty to dist/
//   - Setting CESIUM_BASE_URL define so Cesium can resolve its own Workers at runtime
//   - Excluding cesium from Vite's dep optimisation (prevents Worker inlining crash)
export default defineConfig({
  plugins: [react(), cesium()],
  resolve: {
    alias: { "@": new URL("./src", import.meta.url).pathname },
  },
  build: {
    chunkSizeWarningLimit: 20000,
    rollupOptions: {
      output: {
        // Vite 6+ requires manualChunks as a function, not an object
        manualChunks: (id) => {
          if (id.includes("node_modules/cesium")) return "cesium-core";
          if (id.includes("node_modules/react-dom") || id.includes("node_modules/react/")) return "react-core";
          if (id.includes("node_modules/zustand")) return "zustand";
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
    CESIUM_BASE_URL: JSON.stringify("/cesium"),
  },
});
