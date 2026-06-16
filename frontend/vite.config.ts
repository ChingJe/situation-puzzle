import { defineConfig } from "vite";
import react from "@vitejs/plugin-react";

export default defineConfig({
  plugins: [react()],
  esbuild: {
    target: "esnext"
  },
  build: {
    target: "esnext"
  },
  optimizeDeps: {
    esbuildOptions: {
      target: "esnext"
    }
  },
  server: {
    port: 5173,
    proxy: {
      "/api": "http://localhost:8000"
    }
  }
});
